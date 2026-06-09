# System Architecture

## Container Map

```
┌──────────────────────────────────────────────────────────────┐
│                   HOST OS (Ubuntu 24.04)                      │
│                                                               │
│              Docker Compose (host networking)                  │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐    │
│  │ ros2-    │  │ motor-   │  │ oak-camera               │    │
│  │ daemon   │  │ control  │  │ ┌──────────────────────┐ │    │
│  │          │  │ ┌──────┐ │  │ │ depthai-ros node     │ │    │
│  │ ros2     │  │ │serial│ │  │ │                      │ │    │
│  │ daemon   │  │ │bridge│ │  │ │ /rgb       (sensor)  │ │    │
│  └──────────┘  │ │ .py  │ │  │ │ /depth     (sensor)  │ │    │
│                │ └──┬───┘ │  │ │ /imu       (sensor)  │ │    │
│                │    │     │  │ └──────────────────────┘ │    │
│                │    │USB  │  └──────────────────────────┘    │
│                │    │serial│                                 │
│                │  ┌─▼────┐│  ┌──────────────────────────┐    │
│                │  │Ard-  ││  │ voice-pipeline            │    │
│                │  │uino  ││  │ ┌──────┐ ┌──────┐ ┌────┐ │    │
│                │  │PID   ││  │ │whis- │ │Ollama│ │Piper│ │    │
│                │  │100Hz ││  │ │per   │ │LLM   │ │TTS  │ │    │
│                │  │PWM→  ││  │ │STT   │ │      │ │     │ │    │
│                │  │motor ││  │ └──────┘ └──────┘ └────┘ │    │
│                │  │driver││  └──────────────────────────┘    │
│                │  └──────┘│                                  │
│                └──────────┘  ┌──────────────────────────┐    │
│                              │ web-dashboard             │    │
│                              │ FastAPI :8000             │    │
│                              │ WebSocket + joystick UI   │    │
│                              └──────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## ROS 2 Topic Graph

```
                            ┌──────────────┐
                            │  /cmd_vel    │
                            │  (Twist)     │
                            └──────┬───────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
              ▼                    ▼                     ▼
  ┌────────────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ motor-control      │  │ web-         │  │ voice-pipeline   │
  │ serial_bridge.py   │  │ dashboard    │  │ voice_node.py    │
  │                    │  │ (joystick)   │  │ (LLM intent)     │
  └─────────┬──────────┘  └──────────────┘  └──────────────────┘
            │ serial (USB)
            ▼
  ┌────────────────────┐
  │ ATmega32U4         │
  │ PID control @100Hz │
  └─────────┬──────────┘
            │
            ▼
  ┌────────────────────┐  ┌────────────────────┐
  │ /odom (Odometry)   │  │ /motor_state       │
  │ /tf (odom→base_fp) │  │ (Float64MultiArray) │
  └─────────┬──────────┘  └────────────────────┘
            │
            ▼
  ┌────────────────────┐
  │ oak-camera         │
  │ depthai-ros node   │
  │                    │
  │ /rgb               │
  │ /depth             │
  │ /imu               │
  │ /depth/points      │
  └────────────────────┘
```

## Container Details

| Container | Base Image | Entrypoint | Key Mounts |
|---|---|---|---|
| ros2-daemon | `ros:jazzy-ros-base` + colcon build | `ros2 daemon start` | `ros2_ws/src` (ro) |
| motor-control | Same as above | `serial_bridge.py --port /dev/ttyACM0` | `ros2_ws/src` (ro), `/dev/ttyACM0` |
| oak-camera | `ros:jazzy-ros-base` + depthai-ros | `depthai_examples` launch | `ros2_ws/src` (ro), `/dev/bus/usb`, `/dev/shm` |
| voice-pipeline | `ros:jazzy-ros-base` + audio deps | `voice_pipeline.launch.py` | models, `/dev/snd` |
| web-dashboard | `python:3.12-slim` | `uvicorn dashboard:app` | `docker/web-dashboard` (ro) |

## Networking

All ROS 2 containers use **host networking** (`network_mode: host`). This is required because:

- ROS 2 / DDS discovery uses UDP multicast on the local network
- Serial ports (`/dev/ttyACM0`) are host devices
- USB cameras (`/dev/bus/usb`) need host access
- Audio devices (`/dev/snd`) need host access

The web-dashboard also uses host networking so its WebSocket and HTTP server are directly reachable.

## Data Flow per Subsystem

### Motor Control

```
/cmd_vel ──► serial_bridge.py ──► USB serial ──► ATmega32U4 ──► PWM ──► Motor Driver ──► DC Motors
                                                                    │
                   ◄── encoder counts ◄── hardware interrupts ◄─────┘
                   │
                   └──► serial_bridge.py ──► /odom + /tf
```

### Vision

```
OAK-D-Lite ──► USB 3.0 ──► depthai-ros node ──┬──► /rgb (sensor_msgs/Image)
                                               ├──► /depth (sensor_msgs/Image)
                                               ├──► /depth/points (sensor_msgs/PointCloud2)
                                               └──► /imu (sensor_msgs/Imu)
```

### Voice

```
USB Mic ──► voice_node.py ──HTTP──► whisper.cpp :8080 ──► text
              │                                              │
              │                     ◄─────────────────────────┘
              │                     │
              │              wake word "robot"?
              │                     │ yes
              │                     ▼
              │              HTTP ──► Ollama :11434 ──► response text
              │                     │
              │              HTTP ──► Piper :5000 ──► raw PCM
              │                     │
              │                     ▼
              │              sd.play() → Speaker
              │
              └──► publish /voice_command (String)
```

### Navigation (Nav2)

```
/depth/points ──► local_costmap (obstacle layer)
/odom ──────────► AMCL ──► /map
/map ───────────► global_costmap (static layer)
/cmd_vel ◄────── planner + controller
```

## Startup Order

```
docker compose up
  │
  ├── 1. ros2-daemon      (healthcheck: ros2 daemon status)
  │
  ├── 2. motor-control    (depends_on: ros2-daemon healthy)
  │      └── opens /dev/ttyACM0, starts reader thread
  │
  ├── 3. oak-camera       (depends_on: ros2-daemon healthy)
  │      └── initializes OAK-D pipeline
  │
  ├── 4. voice-pipeline   (depends_on: ros2-daemon healthy)
  │      └── starts whisper-server, ollama serve, piper server
  │
  └── 5. web-dashboard    (independent, no healthcheck dependency)
         └── uvicorn starts, serves HTML/JS on :8000
```
