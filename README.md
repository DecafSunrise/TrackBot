# TrackBot

ROS 2 Jazzy + Docker Compose tracked robot with OAK-D-Lite vision and voice control, running on a LattePanda Sigma (i5-1340P / 32GB).

```bash
make build && make up    # start everything
make flash               # flash Arduino firmware
make test-forward        # drive forward 0.3 m/s for 2s
# → http://localhost:8000  (web dashboard)
```

---

## Data Flow Walkthrough

### Scenario: you push "forward" on the dashboard joystick

**Layer 1 — Dashboard → ROS2**

```
Web browser                    web-dashboard container (Python)
──────────                    ─────────────────────────────────
Joystick event ──POST /cmd_vel──► FastAPI ──► bridge.send_cmd_vel(vx=0.3, wz=0)
{vx:0.3, wz:0}                                          │
                                                         │ publishes
                                                         ▼
                                                  /cmd_vel topic
                                             (geometry_msgs/Twist)
```

**Layer 2 — ROS2 → Arduino**

```
motor-control container (Python)
────────────────────────────────
Subscribes to /cmd_vel

serial_bridge.py:
  vx = 0.3 m/s, wz = 0.0 rad/s

  # Differential drive kinematics:
  v_left  = vx - wz × wheel_base/2    = 0.3 m/s
  v_right = vx + wz × wheel_base/2    = 0.3 m/s

  # Convert to motor PWM domain:
  ω = v / wheel_radius                = 8.57 rad/s ≈ 82 RPM
  pwm = int(RPM / max_RPM × 255)     = 209

  port.write("L 209 R 209\n")
```

**Layer 3 — Arduino PID loop (100 Hz)**

```
ATmega32U4 receives: "L 209 R 209\n"

parseCommand():
  targetSpeedL = 209
  targetSpeedR = 209

controlLoop() @ 100 Hz (every 10 ms):
  1. Read encoder counters (hardware interrupt-driven)
  2. Calculate actual speed: delta_ticks × 2
  3. PID:
       error     = target - actual
       integral += error × 0.1
       output    = Kp×error + Ki×integral + Kd×derivative
  4. Write PWM + direction pins to motor driver

setMotor(209):
  digitalWrite(DIR1, HIGH)   // forward
  digitalWrite(DIR2, LOW)
  analogWrite(PWM, 209)      // ~82% duty cycle
```

**Layer 4 — Motor driver → Physical**

```
DRV8833               DC Gearmotor
───────               ───────────
AIN1 = 209 (PWM) ────► Applied voltage proportional to 209/255
AIN2 = HIGH (forward)
                       Encoder pulses on shaft
                       ──► Pin 2 (INT0) increments counter
```

**Layer 5 — Feedback back up**

```
ATmega32U4 @ 20 Hz:
  Serial.println("48291 47923 207 211 209 209")
                   ─┬──  ─┬──  ─┬─  ─┬─  ─┬─  ─┬─
                  encL  encR spdL spdR tgtL tgtR

serial_bridge.py reading:
  delta_enc_L = 48291 - prev_enc_L
  dist_per_tick = (2π × wheel_radius) / (PPR × gear_ratio)

  d_left  = delta_enc_L × dist_per_tick
  d_right = delta_enc_R × dist_per_tick

  x      += (d_left + d_right)/2 × cos(θ)
  y      += (d_left + d_right)/2 × sin(θ)
  theta  += (d_right - d_left) / wheel_base

  → publishes /odom
  → broadcasts TF: odom → base_footprint
```

---

## The Three Control Loops

```
┌────────────────────────────────────────────────────────────────────┐
│ LOOP 1: NAVIGATION / PATH PLANNING   10 Hz (100 ms)               │
│                                                                    │
│  OAK-D depth → costmap → Nav2 planner → /cmd_vel                  │
│  /odom ───────→ AMCL ──────→ /map                                 │
│                                                                    │
│  LattePanda CPU. Only runs during autonomous navigation.           │
└───────────────────────────┬────────────────────────────────────────┘
                            │ /cmd_vel
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│ LOOP 2: SERIAL BRIDGE + ODOMETRY   50 Hz (20 ms)                  │
│                                                                    │
│  /cmd_vel → Twist → PWM → write serial → Arduino                  │
│  read serial ← encoder data → publish /odom + TF                  │
│                                                                    │
│  LattePanda CPU, Python thread, non-blocking.                      │
└───────────────────────────┬────────────────────────────────────────┘
                            │ "L 209 R 209\n"
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│ LOOP 3: PID VELOCITY CONTROL   100 Hz (10 ms)                     │
│                                                                    │
│  ATmega32U4 firmware (hard real-time):                             │
│  1. Read serial buffer                                             │
│  2. Parse target speeds                                            │
│  3. Read encoder counters (hardware interrupts)                    │
│  4. Compute PID                                                    │
│  5. Write PWM + direction pins                                     │
│  6. Every 5th cycle: send state report back to ROS2                │
│                                                                    │
│  Runs even if ROS node crashes — robot coasts to stop gracefully.  │
└────────────────────────────────────────────────────────────────────┘
```

### Why separate the low-level loop onto the ATmega32U4

| If the LattePanda CPU... | The Arduino... |
|---|---|
| Gets busy with SLAM computation | Keeps running PID at 100 Hz |
| Has kernel scheduling jitter of 1–10 ms | Responds in microseconds (hardware interrupts) |
| Crashes or freezes | Motors coast to stop (no new commands → output = 0) |
| Reboots (updates, crash) | Resets in ~50 ms, motors off, waits for serial |

This is the standard architecture used by ROS robots from TurtleBots to full-size autonomous vehicles: **high-level planning on a general-purpose computer, safety-critical real-time control on a dedicated microcontroller.**

---

## Serial Protocol (ATmega32U4 ↔ ROS2)

```
Arduino ←──────────────── ROS2 (LattePanda via USB serial)
         "L 127 R -200\n"
          └──┬──┘ └──┬──┘
             │       └── right motor: -200 = reverse at 78%
             └── left motor: 127 = forward at 50%

Arduino ────────────────► ROS2
         "48291 47923 207 211 209 209\n"
          ─┬──  ─┬──  ─┬─  ─┬─  ─┬─  ─┬─
           │     │     │    │    │    └── target speed R
           │     │     │    │    └── target speed L
           │     │     │    └── actual speed R
           │     │     └── actual speed L
           │     └── encoder R count
           └── encoder L count

ASCII, newline-terminated. ~40 bytes/frame at 20 Hz = 800 bytes/s.
Barely registers on a 115200 baud link (~11,520 bytes/s capacity).
```

---

## Startup Sequence

```
1. Power on → Sigma boots Ubuntu
2. systemd starts Docker daemon
3. docker compose up launches:
   a. ros2-daemon:     "ros2 daemon start"       waits for healthcheck
   b. motor-control:   serial_bridge.py          opens /dev/ttyACM0 @ 115200
   c. oak-camera:      depthai pipeline           streams /rgb, /depth, /imu
   d. voice-pipeline:  whisper-server :8080      Ollama :11434  Piper :5000
   e. web-dashboard:   uvicorn :8000              serves HTML + WebSocket

4. ATmega32U4 boots its sketch:
   - Sets PWM frequency to 5 kHz (Timer1)
   - Initializes encoder library
   - All outputs = 0, motors stopped
   - Starts PID control loop at 100 Hz

5. serial_bridge.py receives "0 0 0 0 0 0\n" (initial state)
   - Publishes /odom at origin (0, 0, 0)
   - Broadcasts TF: odom → base_footprint
```

---

## Hardware

| Component | Detail |
|---|---|
| SBC | LattePanda Sigma (i5-1340P, 32 GB) |
| Camera | Luxonis OAK-D-Lite (stereo depth + RGB + IMU) |
| Motors | 2× DC gearmotors with encoders |
| Motor driver | DRV8833 or TB6612FNG (PWM+DIR, 2 pins per motor) |
| Microcontroller | Onboard ATmega32U4 (Arduino Leonardo-compatible) |
| Power | 18 V power-tool batteries → Sigma direct + buck to 12 V for motors |
| Microphone | USB microphone |

### Pin Wiring (ATmega32U4 → DRV8833)

```
ATmega32U4          DRV8833
─────────           ───────
Pin 9  (PWM)   ───► AIN1   ─── M1
Pin 8  (DIR1)  ───► AIN2
Pin 7  (DIR2)  ───► BIN1   ─── M2
Pin 6  (PWM)   ───► BIN2

Pin 2  (INT0)  ◄── M1 Encoder A
Pin 3  (INT1)  ◄── M1 Encoder B
Pin 4  (INT2)  ◄── M2 Encoder A
Pin 12 (INT3)  ◄── M2 Encoder B
```

### Power Distribution

```
18 V Battery ──┬──► Sigma DC jack (18 V direct, within 12–20 V spec)
               │
               └──► Buck 18 V→12 V ──► Motor driver ──► Motors
```

---

## Voice Commands

Say **"robot"** then a command (e.g. "robot move forward", "robot stop", "robot turn left"). The wake word gates the ASR → LLM → TTS pipeline.

```
USB mic → whisper.cpp :8080 → Ollama :11434 → Piper :5000 → speaker
         (STT)               (LLM)            (TTS)
```

Typical end-to-end latency: **3–5 seconds** (whisper tiny.en, Phi-3 Mini, Piper).

---

## Tuning

Edit `.env` to adjust PID gains, wheel geometry, and motor parameters:

```ini
PID_KP=1.0
PID_KI=0.1
PID_KD=0.05
WHEEL_BASE=0.15    # meters (axle-to-axle)
WHEEL_RADIUS=0.035 # meters
ENCODER_PPR=48     # pulses per revolution
```

---

## Upgrading to I2C Motor Driver

Swap PWM+DIR for I2C (e.g., RoboClaw, Pololu Motoron) by:

1. Change `arduino/trackbot_motor_control.ino` to use the Wire library
2. Add I2C device passthrough in `docker-compose.yml` (if needed)
3. No change to `serial_bridge.py` — it still speaks the same serial protocol

---

## Architecture

```
Host (Ubuntu 24.04)
└── Docker Compose
    ├── ros2-daemon       — Core ROS 2 discovery
    ├── motor-control     — Serial bridge → ATmega32U4 → motor driver
    ├── oak-camera        — OAK-D-Lite depth / RGB / IMU streams
    ├── voice-pipeline    — whisper.cpp + Ollama + Piper
    └── web-dashboard     — FastAPI + joystick UI on port 8000
```

---

## Documentation

See the [docs/](docs/) folder for in-depth coverage of each subsystem:

- [System Architecture](docs/architecture.md) — component interaction, data flow diagrams
- [Power System](docs/power.md) — battery budget, wiring, runtime tables
- [Hardware Wiring](docs/hardware-wiring.md) — pinouts, motor driver, encoder wiring
- [Serial Protocol](docs/serial-protocol.md) — command format, frame timing, error handling
- [Control Loops](docs/control-loops.md) — PID tuning, differential drive math
- [Voice Pipeline](docs/voice-pipeline.md) — STT, LLM, TTS setup and latency
- [Getting Started](docs/getting-started.md) — first-time setup from blank Ubuntu
- [Nav2 Configuration](docs/navigation.md) — costmap, planner, AMCL parameters
