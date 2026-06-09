# Getting Started

Step-by-step from a blank Ubuntu 24.04 install on the LattePanda Sigma to a driving robot.

## Prerequisites

- LattePanda Sigma with Ubuntu 24.04 installed
- Internet connection (Ethernet or WiFi)
- 18 V power-tool battery + terminal adapter
- Arduino IDE (for initial firmware flash)
- USB keyboard + monitor for setup (or SSH)

---

## Step 1: Install Docker

```bash
# Add Docker's official GPG key and repository
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add your user to docker group so you don't need sudo
sudo usermod -aG docker $USER
newgrp docker
```

## Step 2: Clone the Project

```bash
git clone https://github.com/DecafSunrise/TrackBot.git ~/trackbot
cd ~/trackbot
```

## Step 3: Flash Arduino Firmware

### Option A: Arduino CLI (fastest)

```bash
sudo apt-get install -y arduino-cli
arduino-cli core update-index
arduino-cli core install arduino:avr
make flash
```

### Option B: Arduino IDE

1. Install Arduino IDE from https://www.arduino.cc/en/software
2. Open `arduino/trackbot_motor_control/trackbot_motor_control.ino`
3. Tools → Board → Arduino Leonardo
4. Tools → Port → `/dev/ttyACM0`
5. Upload

## Step 4: Set Up Voice Models

```bash
make models
```

This downloads whisper.cpp tiny.en (~75 MB) and Piper voice (~200 MB) into `models/`.

## Step 5: Build Docker Images

```bash
make build
```

First build takes 10–20 minutes (downloading base images, compiling ROS2 workspace, building depthai-ros, etc.). Subsequent builds are fast due to Docker layer caching.

## Step 6: Configure Environment

Edit `.env` to match your hardware:

```ini
# Change these:
ARDUINO_PORT=/dev/ttyACM0          # verify with `ls /dev/ttyACM*`
MOTOR_MAX_RPM=100                   # your motor's no-load RPM
ENCODER_PPR=48                      # pulses per revolution (check motor datasheet)
WHEEL_BASE=0.15                     # measure axle-to-axle in meters
WHEEL_RADIUS=0.035                  # wheel diameter / 2 in meters
GEAR_RATIO=30                       # motor gearbox ratio
```

## Step 7: Power On

1. Connect 18 V battery to Sigma (barrel jack) — you should see the Sigma power LED
2. The Sigma boots Ubuntu
3. Wait 30–60 seconds for all services to start
4. Check everything is running:

```bash
docker compose ps
```

Expected output:
```
NAME                    IMAGE                          STATUS
trackbot-ros2-daemon    trackbot/ros2-base:latest      Up (healthy)
trackbot-motor-control  trackbot/ros2-base:latest      Up
trackbot-oak-camera     trackbot/ros2-oak:latest       Up
trackbot-voice          trackbot/ros2-voice:latest     Up
trackbot-web            python:3.12-slim               Up
```

## Step 8: Drive

### Web Dashboard

Open **http://localhost:8000** in a browser on the same machine.

- Virtual joystick (click + drag): forward/back, left/right
- Position readout from /odom
- Battery percentage (if /battery topic is published)
- EMERGENCY STOP button

### Command Line

```bash
# Forward 0.3 m/s for 2 seconds
make test-forward

# See what topics are active
make topics

# Watch odometry
make odom

# Send a custom cmd_vel
docker compose exec motor-control \
  ros2 topic pub --once /cmd_vel geometry_msgs/Twist \
    "{linear: {x: 0.2}, angular: {z: 0.5}}"
```

## Step 9: Voice Commands (Optional)

Make sure the microphone is plugged in and recognized:

```bash
arecord -l
```

Speak clearly about 30 cm from the mic:

> **"robot move forward"**
> **"robot stop"**
> **"robot turn left"**
> **"robot go home"**

The wake word "robot" gates the pipeline. The robot will say its response aloud.

## Step 10: Auto-Start on Boot

To have the robot start automatically when powered on:

```bash
sudo cp docker/ros2-core/trackbot.service /etc/systemd/system/
sudo systemctl enable trackbot
sudo systemctl start trackbot
```

Create the systemd service file first:

```bash
cat > /tmp/trackbot.service << 'EOF'
[Unit]
Description=TrackBot ROS2 Stack
Requires=docker.service
After=docker.service

[Service]
WorkingDirectory=/home/<user>/trackbot
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
User=<user>

[Install]
WantedBy=multi-user.target
EOF
sudo mv /tmp/trackbot.service /etc/systemd/system/
# Edit user path above before enabling
```

## Troubleshooting

### "No such file or directory: /dev/ttyACM0"

The Arduino hasn't enumerated. Check:
```bash
ls /dev/tty*     # should list ttyACM0
```
Reseat USB cable. The ATmega32U4 enumerates ~2 seconds after the Sigma boots.

### "Permission denied: /dev/ttyACM0"

```bash
sudo usermod -aG dialout $USER
newgrp dialout
```

### Containers exit immediately

```bash
docker compose logs motor-control
```

Common issues:
- Wrong serial port in `.env`
- Arduino firmware not flashed
- Baud rate mismatch between `.env` and Arduino sketch

### Motors don't move

```bash
# Check the PWM pins are working (LED test)
# Verify motor power is on (buck converter enabled)
# Check motor driver VM voltage with a multimeter
```

### OAK-D not detected

```bash
lsusb | grep Luxonis
# Should show: "Luxonis OAK-D-Lite"
docker compose logs oak-camera
```
