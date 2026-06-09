# Serial Protocol: ATmega32U4 ↔ ROS2

The motor-control container and Arduino communicate over USB serial (CDC ACM) at 115200 baud.

## Frame Format

### ROS2 → Arduino (commands)

```
L <int16> R <int16>\n
```

| Field | Range | Meaning |
|---|---|---|
| L | -255 .. 255 | Motor 1 (left) target speed. Negative = reverse. |
| R | -255 .. 255 | Motor 2 (right) target speed. Negative = reverse. |

Examples:

```
L 255 R 255\n     # full speed forward
L -200 R 200\n    # pivot left (tank turn)
L 0 R 0\n         # stop
L 127 R -200\n    # mixed: left forward half, right reverse 78%
```

The firmware `parseCommand()` handles both single-command and combined lines:

```
L 127\n           # set left only
R 255\n           # set right only
L 127 R 255\n     # both in one line
```

### Arduino → ROS2 (telemetry)

```
<int64> <int64> <int16> <int16> <int16> <int16>\n
```

| Field | Type | Meaning |
|---|---|---|
| 1 | int64 | Encoder left — absolute position count (monotonic, wraps at 2^31) |
| 2 | int64 | Encoder right — absolute position count |
| 3 | int16 | Measured speed left (-255..255, from delta encoder / 10 ms) |
| 4 | int16 | Measured speed right |
| 5 | int16 | Target speed left (-255..255, most recent command) |
| 6 | int16 | Target speed right |

Example:

```
48291 47923 207 211 209 209\n
```

## Timing

| Direction | Rate | Framing |
|---|---|---|
| ROS2 → Arduino | On `/cmd_vel` receive (~10 Hz typical) | Each msg produces one line |
| Arduino → ROS2 | **20 Hz** (every 5 PID cycles) | Continuous, free-running |

The 20 Hz report rate gives the ROS bridge fresh encoder data every 50 ms. Odometry is computed on each received frame:

```
Arduino @ 20 Hz:
  controlLoop() @ 100 Hz (10 ms)
    if (cycle % 5 == 0):
      Serial.println(state)
```

## Throughput

| Direction | Bytes per frame | Rate | Bandwidth |
|---|---|---|---|
| To Arduino | ~12 bytes (avg) | 10 Hz | 120 B/s |
| From Arduino | ~40 bytes (avg) | 20 Hz | 800 B/s |
| **Total** | | | **920 B/s** |

At 115200 baud (11,520 bytes/s theoretical, ~10,000 usable), this uses under 10% of link capacity.

## Error Handling

### Arduino side

- Serial receive is interrupt-driven (non-blocking)
- Buffer: 32 bytes (plenty for one line)
- Unknown or malformed lines: silently ignored
- No newline within 32 bytes: buffer resets on overflow (partial line discarded)
- No watchdog timeout on serial — if ROS2 stops sending, motors simply hold last commanded speed. (The PID loop keeps running with zero error target.)

### ROS2 side

- Serial read blocks for up to 100 ms (`timeout=0.1`)
- Garbled lines (fewer than 4 fields): `continue`
- `ValueError` on parse: `continue`
- Serial write failure: logged, not fatal
- No response from Arduino for >1 second: odometry uses zero velocity (robot presumed stopped)

## Startup Handshake

On boot, there is **no explicit handshake**. Both sides are designed to tolerate the other being absent:

1. ATmega32U4 boots: starts control loop at 100 Hz, all PWM = 0, begins sending telemetry at 20 Hz.
2. serial_bridge.py connects: reads initial "0 0 0 0 0 0\n" frame, publishes zero odometry.
3. First `/cmd_vel` arrives: serial_bridge writes it, Arduino starts tracking.

If the serial port takes time to appear (`/dev/ttyACM0`), Docker's `restart: unless-stopped` retries the container.
