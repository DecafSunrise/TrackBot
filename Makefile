.PHONY: all build up down logs clean models

all: build up

# Build all Docker images
build:
	docker compose build

# Start all services
up:
	docker compose up -d

# Start with logs (foreground)
up-logs:
	docker compose up

# Stop all services
down:
	docker compose down

# View logs
logs:
	docker compose logs -f

# Rebuild a specific service (e.g., `make rebuild motor-control`)
rebuild:
	docker compose build $(SERVICE) && docker compose up -d $(SERVICE)

# Flash Arduino firmware (requires Arduino CLI)
flash:
	arduino-cli compile --fqbn arduino:avr:leonardo arduino/trackbot_motor_control/
	arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:leonardo arduino/trackbot_motor_control/

# Download voice models
models:
	mkdir -p models/whisper models/piper
	# Whisper tiny.en
	wget -q -O models/whisper/ggml-tiny.en.bin \
		https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin
	# Piper voice
	wget -q -O models/piper/en_US-lessac-medium.onnx \
		https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
	wget -q -O models/piper/en_US-lessac-medium.onnx.json \
		https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Open a bash shell in a running container
shell:
	docker compose exec $(SERVICE) bash

# Show robot state topics
topics:
	docker compose exec motor-control ros2 topic list

# Monitor odometry
odom:
	docker compose exec motor-control ros2 topic echo /odom

# Send a test cmd_vel (forward 0.3 m/s for 2 seconds)
test-forward:
	docker compose exec motor-control \
		bash -c 'ros2 topic pub --once /cmd_vel geometry_msgs/Twist "{linear: {x: 0.3}}" & sleep 2 && ros2 topic pub --once /cmd_vel geometry_msgs/Twist "{}"'

clean:
	docker compose down -v
	docker system prune -f

# Serve documentation locally (requires mkdocs)
docs-install:
	pip install mkdocs mkdocs-material

docs-serve:
	mkdocs serve -a 0.0.0.0:8001

docs-build:
	mkdocs build
