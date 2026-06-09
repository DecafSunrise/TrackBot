FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    portaudio19-dev \
    python3-pyaudio \
    curl \
    alsa-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    pyaudio \
    requests \
    sounddevice \
    numpy

WORKDIR /ros2_ws

COPY docker/ros2-core/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
