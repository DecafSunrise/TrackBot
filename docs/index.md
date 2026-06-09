# TrackBot Documentation

A ROS 2 Jazzy + Docker Compose tracked robot with OAK-D-Lite stereo vision and local voice AI, running on a LattePanda Sigma (i5-1340P, 32 GB).

## Quick Links

| Document | What you'll find |
|---|---|
| [Getting Started](getting-started.md) | First-time setup from blank Ubuntu |
| [System Architecture](architecture.md) | Data flow, component interaction, container map |
| [Hardware Wiring](hardware-wiring.md) | Pinouts, motor driver, encoder wiring |
| [Power System](power.md) | Battery budget, distribution, runtime tables |
| [Control Loops](control-loops.md) | PID tuning, differential drive math, loop timing |
| [Serial Protocol](serial-protocol.md) | ATmega32U4 ↔ ROS2 command format |
| [Voice Pipeline](voice-pipeline.md) | STT / LLM / TTS setup and latency |
| [Navigation](navigation.md) | Nav2 costmap, planner, AMCL parameters |

## Quick Start

```bash
make flash          # flash Arduino firmware
make models         # download whisper + piper voice models
make build          # build Docker images
make up             # start all containers
# open http://localhost:8000
make test-forward   # drive forward 0.3 m/s for 2 seconds
```

## Repository Layout

```
trackbot/
├── .env                    # ROS domain, PID gains, wheel geometry
├── docker-compose.yml      # 5 services: daemon, motor, camera, voice, web
├── Makefile                # build, up, logs, flash, test-forward
│
├── arduino/
│   └── trackbot_motor_control.ino   # 100 Hz PID, encoder reading, serial protocol
│
├── ros2_ws/src/
│   ├── trackbot_msgs/      # MotorCommand.msg, MotorState.msg
│   ├── trackbot_control/   # serial_bridge.py (cmd_vel → serial → Arduino)
│   ├── trackbot_vision/    # OAK-D integration scaffold
│   ├── trackbot_voice/     # voice_node.py (whisper → Ollama → Piper)
│   └── trackbot_bringup/   # launch files, nav2 config
│
├── docker/                 # Dockerfiles for each image
├── config/                 # nav2_params.yaml, trackbot.rviz
├── docs/                   # this documentation
└── models/                 # downloaded whisper + piper models
```
