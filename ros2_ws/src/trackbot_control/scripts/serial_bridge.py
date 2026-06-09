#!/usr/bin/env python3
"""
Serial bridge: ROS2 (cmd_vel) ⟷ ATmega32U4 (serial)
Translates geometry_msgs/Twist to "L <speed> R <speed>" commands
and parses encoder feedback into odometry.
"""

import argparse
import serial
import struct
import threading
from math import pi

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import Float64MultiArray
import tf2_ros


class SerialBridge(Node):
    WHEEL_BASE = 0.15       # m (adjust to your chassis)
    WHEEL_RADIUS = 0.035    # m (adjust to your wheels)
    ENCODER_PPR = 48
    GEAR_RATIO = 30         # motor:wheel turns (adjust)
    REPORT_HZ = 20

    def __init__(self, port: str, baud: int):
        super().__init__('serial_bridge')

        self.port = serial.Serial(
            port=port, baudrate=baud, timeout=0.1, write_timeout=0.1
        )
        self.lock = threading.Lock()
        self._running = True

        # Subscribers
        self.create_subscription(Twist, '/cmd_vel', self.cmd_vel_cb, 10)

        # Publishers
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.motor_state_pub = self.create_publisher(
            Float64MultiArray, '/motor_state', 10
        )

        # TF
        self.tf_broadcaster = tf2_ros.TransformBroadcaster(self)

        # State
        self.enc_left = 0
        self.enc_right = 0
        self.vel_left = 0.0
        self.vel_right = 0.0
        self.prev_enc_left = 0
        self.prev_enc_right = 0
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.last_odom_time = self.get_clock().now()

        # Start serial reader thread
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

        self.get_logger().info(
            f'Serial bridge started on {port} @ {baud} baud'
        )

    # ── cmd_vel callback ────────────────────────────────────
    def cmd_vel_cb(self, msg: Twist):
        vx = msg.linear.x
        wz = msg.angular.z

        v_left = vx - wz * self.WHEEL_BASE / 2
        v_right = vx + wz * self.WHEEL_BASE / 2

        omega_left = v_left / self.WHEEL_RADIUS
        omega_right = v_right / self.WHEEL_RADIUS

        # Convert to -255..255 (Arduino domain)
        max_omega = 100.0  # adjust to match your motor's max RPM mapped to this scale
        pwm_left = int(max(-255, min(255, omega_left / max_omega * 255)))
        pwm_right = int(max(-255, min(255, omega_right / max_omega * 255)))

        cmd = f'L {pwm_left} R {pwm_right}\n'
        with self.lock:
            try:
                self.port.write(cmd.encode())
            except serial.SerialException as e:
                self.get_logger().error(f'Serial write error: {e}')

    # ── Serial reader thread ────────────────────────────────
    def _read_loop(self):
        while self._running and rclpy.ok():
            try:
                line = self.port.readline().decode().strip()
                if not line:
                    continue
            except serial.SerialException:
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            try:
                self.enc_left = int(parts[0])
                self.enc_right = int(parts[1])
                self.vel_left = float(parts[2])
                self.vel_right = float(parts[3])
            except (ValueError, IndexError):
                continue

            self._publish_odometry()

    # ── Odometry from encoders ──────────────────────────────
    def _publish_odometry(self):
        now = self.get_clock().now()
        dt = (now - self.last_odom_time).nanoseconds / 1e9
        if dt < 1e-6:
            return

        delta_enc_left = self.enc_left - self.prev_enc_left
        delta_enc_right = self.enc_right - self.prev_enc_right
        self.prev_enc_left = self.enc_left
        self.prev_enc_right = self.enc_right

        # Distance traveled per encoder tick
        dist_per_tick = (2 * pi * self.WHEEL_RADIUS) / (self.ENCODER_PPR * self.GEAR_RATIO)

        d_left = delta_enc_left * dist_per_tick
        d_right = delta_enc_right * dist_per_tick

        d_center = (d_left + d_right) / 2
        d_theta = (d_right - d_left) / self.WHEEL_BASE

        self.x += d_center * self.cos_theta
        self.y += d_center * self.sin_theta
        self.theta += d_theta

        vx = d_center / dt if dt > 0 else 0.0
        wz = d_theta / dt if dt > 0 else 0.0

        # Odometry msg
        odom = Odometry()
        odom.header.stamp = now.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_footprint'

        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        q = self._euler_to_quaternion(0, 0, self.theta)
        odom.pose.pose.orientation.x = q[0]
        odom.pose.pose.orientation.y = q[1]
        odom.pose.pose.orientation.z = q[2]
        odom.pose.pose.orientation.w = q[3]

        odom.twist.twist.linear.x = vx
        odom.twist.twist.angular.z = wz

        self.odom_pub.publish(odom)

        # TF
        t = TransformStamped()
        t.header.stamp = now.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_footprint'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation = odom.pose.pose.orientation
        self.tf_broadcaster.sendTransform(t)

        # Motor state
        motor_state = Float64MultiArray()
        motor_state.data = [
            float(self.enc_left), float(self.enc_right),
            self.vel_left, self.vel_right
        ]
        self.motor_state_pub.publish(motor_state)

        self.last_odom_time = now

    # ── Helpers ─────────────────────────────────────────────
    @property
    def cos_theta(self):
        from math import cos
        return cos(self.theta)

    @property
    def sin_theta(self):
        from math import sin
        return sin(self.theta)

    @staticmethod
    def _euler_to_quaternion(roll, pitch, yaw):
        from math import sin, cos
        cy, sy = cos(yaw * 0.5), sin(yaw * 0.5)
        cp, sp = cos(pitch * 0.5), sin(pitch * 0.5)
        cr, sr = cos(roll * 0.5), sin(roll * 0.5)
        return (
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy,
        )

    def cleanup(self):
        self._running = False
        if self.port.is_open:
            self.port.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/ttyACM0')
    parser.add_argument('--baud', type=int, default=115200)
    args = parser.parse_args()

    rclpy.init()
    bridge = SerialBridge(port=args.port, baud=args.baud)
    try:
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.cleanup()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
