# Control Loops

TrackBot uses three nested control loops running at different rates on different processors.

## Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│ LOOP 1: PATH PLANNING / NAVIGATION   10 Hz (100 ms)                 │
│                                                                      │
│ Input:  /map + /odom + /depth/points                                │
│ Output: /cmd_vel (Twist)                                             │
│ Runs:   LattePanda CPU (Nav2, only during autonomous mode)           │
├──────────────────────────────────────────────────────────────────────┤
│ LOOP 2: SERIAL BRIDGE + ODOMETRY   50 Hz (20 ms)                    │
│                                                                      │
│ Input:  /cmd_vel + encoder counts (serial)                          │
│ Output: motor commands (serial) + /odom (ROS topic) + /tf           │
│ Runs:   LattePanda CPU (Python, always)                              │
├──────────────────────────────────────────────────────────────────────┤
│ LOOP 3: PID VELOCITY CONTROL   100 Hz (10 ms)                       │
│                                                                      │
│ Input:  Serial target speeds + encoder pulses (hardware interrupts) │
│ Output: PWM + direction pins to motor driver                        │
│ Runs:   ATmega32U4 (firmware, always)                                │
└──────────────────────────────────────────────────────────────────────┘
```

## Loop 3: ATmega32U4 PID (100 Hz)

This is the only hard real-time loop. It runs on the dedicated microcontroller, isolated from Linux scheduling jitter and ROS node crashes.

### PID Control Law

```
error = target_speed - measured_speed

integral  += error × dt          (dt = 0.01 s, integral limited to ±200)
derivative = error - last_error

output = Kp × error + Ki × integral + Kd × derivative
```

Values are in the motor PWM domain: -255 to +255.

### PID Gains

Default values in `.env`:

```ini
PID_KP = 1.0
PID_KI = 0.1
PID_KD = 0.05
```

### Tuning Procedure

1. Set `KI = 0` and `KD = 0`.
2. Increase `KP` until the motor oscillates (hunts around the setpoint).
3. Set `KP` to half the oscillating value.
4. Increase `KI` until steady-state error is eliminated (motor reaches target speed exactly).
5. Increase `KD` until overshoot is dampened.

### Deadband

```c
#define DEADBAND 15
```

PWM values below 15 are treated as zero. This prevents the motors from humming or creeping when the commanded speed is near zero (common with brushed DC motors due to static friction + PWM nonlinearity at low duty cycles).

### Encoder Velocity Measurement

```
measured_speed = (current_count - previous_count) × 2
```

Multiplied by 2 because the loop runs every 10 ms and we want values normalized to a 20 ms base (matching the -255..255 scale). At full speed this gives:

- Encoder at 48 PPR × gear ratio 30 = 1440 counts per wheel revolution
- 100 RPM = 1.67 rev/s = 2400 counts/s = 24 counts per 10 ms tick
- 24 × 2 = 48 (well within -255..255 range)

### Output to Motor Driver

```c
if speed > DEADBAND:
  DIR1 = HIGH, DIR2 = LOW     // forward
  PWM  = speed
else if speed < -DEADBAND:
  DIR1 = LOW, DIR2 = HIGH     // reverse
  PWM  = -speed
else:
  DIR1 = LOW, DIR2 = LOW      // coast
  PWM  = 0
```

## Loop 2: Serial Bridge + Odometry (50 Hz)

Runs in the `serial_bridge.py` Python thread. It:

1. Receives `/cmd_vel` messages (ROS subscriber, up to 10 Hz)
2. Converts `Twist.linear.x` and `Twist.angular.z` to left/right motor PWM values
3. Writes `L <pwm> R <pwm>\n` to the Arduino serial port
4. Reads encoder telemetry from Arduino (20 Hz, but checked in a tight loop)
5. Computes odometry from encoder deltas
6. Publishes `/odom` + broadcasts `odom → base_footprint` TF

### Differential Drive Kinematics

```
v_left  = vx - wz × wheel_base / 2
v_right = vx + wz × wheel_base / 2

ω_left  = v_left  / wheel_radius
ω_right = v_right / wheel_radius

pwm_left  = ω_left  / max_ω × 255
pwm_right = ω_right / max_ω × 255
```

### Odometry

```
dist_per_tick = 2π × wheel_radius / (encoder_PPR × gear_ratio)

d_left  = delta_enc_left  × dist_per_tick
d_right = delta_enc_right × dist_per_tick

d_center = (d_left + d_right) / 2
d_theta  = (d_right - d_left) / wheel_base

x     += d_center × cos(theta)
y     += d_center × sin(theta)
theta += d_theta
```

### Configuration

Set these in `.env`:

```ini
WHEEL_BASE=0.15     # distance between wheels (meters)
WHEEL_RADIUS=0.035  # wheel radius (meters)
ENCODER_PPR=48      # encoder pulses per revolution
GEAR_RATIO=30       # motor turns per wheel turn
MOTOR_MAX_RPM=100   # used to scale PWM domain
```

## Loop 1: Path Planning (10 Hz)

Only active during autonomous navigation mode. Uses the Nav2 stack:

1. **AMCL** — Localizes the robot on the map using `/odom` + `/depth/points` (or `/scan`)
2. **Global planner** — Computes a path from current pose to goal pose (`Navfn` or `A*`)
3. **Local planner** — Follows the path while avoiding obstacles (`Regulated Pure Pursuit`)
4. **Costmaps** — Inflate obstacles, track unknown space

The Nav2 controller outputs `/cmd_vel` at 10 Hz, which Loop 2 dutifully passes down to the Arduino.

## Why Three Loops?

| If this fails... | Loop 3 (Arduino) still does... | Robot behavior |
|---|---|---|
| Loop 1 (Nav2 crashes) | Last commanded speed indefinitely | Continues on last /cmd_vel path |
| Loop 2 (serial_bridge.py crashes) | Last written speed indefinitely | Continues until human intervention |
| Loop 3 (ATmega32U4 crashes) | Nothing | Motors stop, robot coasts to halt |
| USB serial disconnects | PWM values reset to 0 after PID cycle | Stops immediately |

The layered design ensures that a software crash in the complex ROS 2 / Python / Docker layers never results in a runaway robot.
