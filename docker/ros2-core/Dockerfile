FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    python3-rosdep \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    setuptools \
    pyserial \
    transforms3d

RUN rosdep init || true

WORKDIR /ros2_ws

# Copy entire ROS2 workspace source
COPY ros2_ws/src /ros2_ws/src

RUN . /opt/ros/jazzy/setup.sh && \
    rosdep update --rosdistro jazzy && \
    rosdep install -y --from-paths src --ignore-src --rosdistro jazzy || true && \
    colcon build --symlink-install

COPY docker/ros2-core/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
