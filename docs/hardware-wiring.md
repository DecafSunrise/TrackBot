# Hardware Wiring

## Pin Assignments (ATmega32U4 → DRV8833)

The LattePanda Sigma's onboard ATmega32U4 is Arduino Leonardo-compatible. It provides 20 digital I/O pins (7 with PWM, 4 with hardware interrupt for encoders).

```
┌─────────────────────────────────────────────────────┐
│                  ATmega32U4                          │
│                                                     │
│  Pin 9  (OC1A)  PWM ────────────► AIN1  DRV8833    │
│  Pin 8  (digital) DIR1 ─────────► AIN2  (Motor 1)  │
│  Pin 7  (digital) DIR2 ─────────► BIN1  DRV8833    │
│  Pin 6  (OC1B)  PWM ────────────► BIN2  (Motor 2)  │
│                                                     │
│  Pin 2  (INT0)   ◄── Encoder A (Motor 1)            │
│  Pin 3  (INT1)   ◄── Encoder B (Motor 1)            │
│  Pin 4  (INT2)   ◄── Encoder A (Motor 2)            │
│  Pin 12 (INT3)   ◄── Encoder B (Motor 2)            │
│                                                     │
│  5V ────────► VCC (DRV8833 logic)                   │
│  GND ───────► GND (DRV8833 + encoders)              │
└─────────────────────────────────────────────────────┘
```

## Motor Driver: DRV8833

### Specs

| Parameter | Value |
|---|---|
| Input voltage (motor) | 2.7 – 10.8 V |
| Logic voltage | 2.7 – 5.5 V (use ATmega32U4 5V) |
| Continuous current | 1.2 A per channel |
| Peak current | 3.2 A per channel |
| Interface | 2× PWM + 2× DIR per motor |

### DRV8833 Pin Functions

| DRV8833 Pin | Connection | Purpose |
|---|---|---|
| AIN1 | ATmega Pin 9 (PWM) | Motor 1 speed |
| AIN2 | ATmega Pin 8 (digital) | Motor 1 direction |
| BIN1 | ATmega Pin 7 (digital) | Motor 2 direction |
| BIN2 | ATmega Pin 6 (PWM) | Motor 2 speed |
| AOUT1 | Motor 1 + | Motor output |
| AOUT2 | Motor 1 - | Motor output |
| BOUT1 | Motor 2 + | Motor output |
| BOUT2 | Motor 2 - | Motor output |
| VM | 12 V (from buck converter) | Motor power supply |
| VCC | 5 V (from ATmega32U4) | Logic supply |
| GND | Common ground | Ground |

### Control Modes

| IN1 | IN2 | Function |
|---|---|---|
| PWM | LOW | Forward (speed = PWM duty) |
| LOW | PWM | Reverse (speed = PWM duty) |
| PWM | PWM | Brake (slow decay) |
| HIGH | HIGH | Brake (fast decay) |
| LOW | LOW | Coast (high-Z) |

## Encoder Wiring

Most DC gearmotors with encoders have 6 wires:

| Wire | Color (typical) | Connection |
|---|---|---|
| Motor + | Red | Motor driver AOUT1/BOUT1 |
| Motor - | Black | Motor driver AOUT2/BOUT2 |
| Encoder VCC | Red/White | 5 V |
| Encoder GND | Black/White | GND |
| Encoder A | Yellow/Green | ATmega Pin 2 (M1) or 4 (M2) |
| Encoder B | Blue/White | ATmega Pin 3 (M1) or 12 (M2) |

**Important:** Add **10 kΩ pull-up resistors** from each encoder signal pin to 5 V if your encoders are open-collector (most are). The ATmega32U4 can use internal pull-ups, but external ones are more reliable with long wires.

## DRV8833 vs. TB6612FNG

Since your chassis is small (~10") with cheap plastic tracks and small DC motors, you have two good options at similar cost:

| Driver | Pros | Cons |
|---|---|---|
| **DRV8833** ($10) | 1.2 A cont. / 3.2 A peak, tiny 17×17 mm, built-in current limiting | Runs warm without heatsink |
| **TB6612FNG** ($8) | 3.2 A cont. / 5 A peak, lower Rds(on), slightly more efficient | Slightly larger module |

Either works. The pin mappings in the Arduino sketch assume DRV8833. If using TB6612FNG, the wiring is identical — both use PWM + DIR control.

## Upgrading to I2C Motor Driver (Future)

When you want more capability (4+ motors, current sensing, onboard PID), swap to an I2C driver:

```
Current (PWM+DIR)               Future (I2C)
─────────────────               ────────────
ATmega32U4                      ATmega32U4
  Pin 6 ── PWM ───► DRV8833       SDA ── I2C ──► RoboClaw
  Pin 7 ── DIR ───► DRV8833       SCL ── I2C ──► RoboClaw
  Pin 8 ── DIR ───► DRV8833
  Pin 9 ── PWM ───► DRV8833       4 pins freed up
  Pin 2 ── EncA                    Pin 2 ── EncA (same)
  Pin 3 ── EncB                    Pin 3 ── EncB (same)
  Pin 4 ── EncA                    Pin 4 ── EncA (same)
  Pin 12── EncB                    Pin 12── EncB (same)
```

The Arduino sketch needs the Wire library and I2C register writes. The ROS2 `serial_bridge.py` doesn't change — it still publishes `/cmd_vel` and subscribes to serial replies.
