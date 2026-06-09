FROM ros:jazzy-ros-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    ros-jazzy-cv-bridge \
    ros-jazzy-image-transport \
    ros-jazzy-rclcpp \
    ros-jazzy-rclpy \
    ros-jazzy-sensor-msgs \
    ros-jazzy-std-msgs \
    ros-jazzy-geometry-msgs \
    ros-jazzy-nav-msgs \
    ros-jazzy-tf2 \
    ros-jazzy-tf2-ros \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    depthai

WORKDIR /ros2_ws

# Build depthai-ros from source
RUN . /opt/ros/jazzy/setup.sh && \
    mkdir -p /ros2_ws/src && \
    git clone --depth 1 https://github.com/luxonis/depthai-ros.git /ros2_ws/src/depthai-ros && \
    colcon build --symlink-install

COPY docker/ros2-core/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
