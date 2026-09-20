#!/usr/bin/env python3
import datetime
import os

import rclpy
from cv_bridge import CvBridge
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image, Imu, PointCloud2
from unitree_api.msg import Request as SportRequest
from unitree_go.msg import SportModeState, WirelessController

from .dataset_store import DatasetStore
from .pointcloud_io import cloud_to_xyz_array


def _stamp_to_ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


class RecorderNode(Node):
    def __init__(self):
        super().__init__('unmapped_recorder')

        self.declare_parameter('imu_topic', '/utlidar/imu')
        self.declare_parameter('cloud_topic', '/utlidar/cloud')
        self.declare_parameter('odom_topic', '/utlidar/robot_odom')
        self.declare_parameter('color_topic', '/camera/color/image_raw')
        self.declare_parameter('depth_topic', '/camera/depth/image_rect_raw')
        self.declare_parameter('color_info_topic', '/camera/color/camera_info')
        self.declare_parameter('depth_info_topic', '/camera/depth/camera_info')
        self.declare_parameter('realsense_imu_topic', '/camera/imu')
        self.declare_parameter('sport_mode_state_topic', '/sportmodestate')
        self.declare_parameter('wireless_controller_topic', '/wirelesscontroller')
        self.declare_parameter('sport_request_topic', '/api/sport/request')
        self.declare_parameter('image_rate_hz', 3.0)
        self.declare_parameter('output_dir', '~/unmapped_data')
        self.declare_parameter('session_name', '')

        imu_topic = self.get_parameter('imu_topic').value
        cloud_topic = self.get_parameter('cloud_topic').value
        odom_topic = self.get_parameter('odom_topic').value
        color_topic = self.get_parameter('color_topic').value
        depth_topic = self.get_parameter('depth_topic').value
        color_info_topic = self.get_parameter('color_info_topic').value
        depth_info_topic = self.get_parameter('depth_info_topic').value
        realsense_imu_topic = self.get_parameter('realsense_imu_topic').value
        sport_mode_state_topic = self.get_parameter('sport_mode_state_topic').value
        wireless_controller_topic = self.get_parameter('wireless_controller_topic').value
        sport_request_topic = self.get_parameter('sport_request_topic').value
        image_rate_hz = self.get_parameter('image_rate_hz').value
        output_dir = os.path.expanduser(self.get_parameter('output_dir').value)
        session_name = self.get_parameter('session_name').value

        if not session_name:
            session_name = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        session_dir = os.path.join(output_dir, session_name)

        self._bridge = CvBridge()
        self._store = DatasetStore(session_dir)
        self._store.set_meta(
            imu_topic=imu_topic,
            cloud_topic=cloud_topic,
            odom_topic=odom_topic,
            color_topic=color_topic,
            depth_topic=depth_topic,
            realsense_imu_topic=realsense_imu_topic,
            sport_mode_state_topic=sport_mode_state_topic,
            wireless_controller_topic=wireless_controller_topic,
            sport_request_topic=sport_request_topic,
            image_rate_hz=image_rate_hz,
            started_at=datetime.datetime.now().isoformat(),
        )
        self._min_image_interval_ns = int(1e9 / image_rate_hz) if image_rate_hz > 0 else 0
        self._last_color_stamp_ns = None
        self._last_depth_stamp_ns = None
        self.get_logger().info(f'Recording session to {session_dir}')

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(Imu, imu_topic, self._on_utlidar_imu, qos)
        self.create_subscription(PointCloud2, cloud_topic, self._on_cloud, qos)
        self.create_subscription(Odometry, odom_topic, self._on_odom, qos)
        self.create_subscription(Image, color_topic, self._on_color, qos)
        self.create_subscription(Image, depth_topic, self._on_depth, qos)
        self.create_subscription(Imu, realsense_imu_topic, self._on_realsense_imu, qos)
        self.create_subscription(SportModeState, sport_mode_state_topic, self._on_sport_mode_state, qos)
        self.create_subscription(WirelessController, wireless_controller_topic, self._on_wireless_controller, qos)
        self.create_subscription(SportRequest, sport_request_topic, self._on_sport_request, qos)

        # Intrinsics are static; grab them once each rather than logging every frame.
        self._color_info_sub = self.create_subscription(
            CameraInfo, color_info_topic, lambda msg: self._on_camera_info('color', msg), qos)
        self._depth_info_sub = self.create_subscription(
            CameraInfo, depth_info_topic, lambda msg: self._on_camera_info('depth', msg), qos)

        self._utlidar_imu_count = 0
        self._realsense_imu_count = 0
        self._odom_count = 0
        self._cloud_count = 0
        self._color_count = 0
        self._depth_count = 0
        self._sport_mode_state_count = 0
        self._wireless_controller_count = 0
        self._sport_request_count = 0
        self.create_timer(5.0, self._log_counts)

    def _log_counts(self):
        self.get_logger().info(
            f'utlidar_imu={self._utlidar_imu_count} realsense_imu={self._realsense_imu_count} '
            f'odom={self._odom_count} clouds={self._cloud_count} '
            f'color={self._color_count} depth={self._depth_count} '
            f'sport_mode_state={self._sport_mode_state_count} '
            f'wireless_controller={self._wireless_controller_count} '
            f'sport_requests={self._sport_request_count}')

    def _on_utlidar_imu(self, msg: Imu):
        stamp_ns = _stamp_to_ns(msg.header.stamp)
        self._store.add_imu('utlidar', stamp_ns, msg.orientation, msg.angular_velocity, msg.linear_acceleration)
        self._utlidar_imu_count += 1

    def _on_realsense_imu(self, msg: Imu):
        stamp_ns = _stamp_to_ns(msg.header.stamp)
        self._store.add_imu('realsense', stamp_ns, msg.orientation, msg.angular_velocity, msg.linear_acceleration)
        self._realsense_imu_count += 1

    def _on_odom(self, msg: Odometry):
        stamp_ns = _stamp_to_ns(msg.header.stamp)
        pose = msg.pose.pose
        twist = msg.twist.twist
        self._store.add_odom(stamp_ns, pose.position, pose.orientation, twist.linear, twist.angular)
        self._odom_count += 1

    def _on_cloud(self, msg: PointCloud2):
        stamp_ns = _stamp_to_ns(msg.header.stamp)
        try:
            xyz, intensity = cloud_to_xyz_array(msg)
        except ValueError as exc:
            self.get_logger().error(str(exc))
            return
        self._store.add_cloud(stamp_ns, xyz, intensity)
        self._cloud_count += 1

    def _on_color(self, msg: Image):
        stamp_ns = _stamp_to_ns(msg.header.stamp)
        # Throttled by message stamp, not wall-clock arrival time, so the kept rate is accurate
        # even if processing briefly lags behind the camera.
        if (self._last_color_stamp_ns is not None
                and stamp_ns - self._last_color_stamp_ns < self._min_image_interval_ns):
            return
        self._last_color_stamp_ns = stamp_ns
        # desired_encoding='bgr8' makes cv_bridge do the rgb8->bgr8 swap cv2.imwrite needs,
        # regardless of which encoding the driver actually sent.
        image_bgr = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        self._store.add_color_frame(stamp_ns, image_bgr)
        self._color_count += 1

    def _on_depth(self, msg: Image):
        stamp_ns = _stamp_to_ns(msg.header.stamp)
        if (self._last_depth_stamp_ns is not None
                and stamp_ns - self._last_depth_stamp_ns < self._min_image_interval_ns):
            return
        self._last_depth_stamp_ns = stamp_ns
        # passthrough: keep the raw 16-bit millimeter values, no conversion.
        depth_u16 = self._bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        self._store.add_depth_frame(stamp_ns, depth_u16)
        self._depth_count += 1

    def _on_camera_info(self, name, msg: CameraInfo):
        self._store.set_meta(**{
            f'{name}_width': msg.width,
            f'{name}_height': msg.height,
            f'{name}_fx': msg.k[0],
            f'{name}_fy': msg.k[4],
            f'{name}_cx': msg.k[2],
            f'{name}_cy': msg.k[5],
            f'{name}_distortion_model': msg.distortion_model,
            f'{name}_D': ','.join(str(v) for v in msg.d),
        })
        sub = self._color_info_sub if name == 'color' else self._depth_info_sub
        self.destroy_subscription(sub)

    def _on_sport_mode_state(self, msg: SportModeState):
        stamp_ns = _stamp_to_ns(msg.stamp)
        self._store.add_sport_mode_state(
            stamp_ns, msg.mode, msg.gait_type, msg.progress, msg.body_height,
            msg.foot_raise_height, msg.position, msg.velocity, msg.yaw_speed, msg.error_code)
        self._sport_mode_state_count += 1

    def _on_wireless_controller(self, msg: WirelessController):
        # No header/timestamp on this message; arrival time is the best available.
        stamp_ns = self.get_clock().now().nanoseconds
        self._store.add_wireless_controller(stamp_ns, msg.lx, msg.ly, msg.rx, msg.ry, msg.keys)
        self._wireless_controller_count += 1

    def _on_sport_request(self, msg: SportRequest):
        # No header/timestamp on this message either; arrival time is the best available.
        stamp_ns = self.get_clock().now().nanoseconds
        self._store.add_sport_request(
            stamp_ns, msg.header.identity.id, msg.header.identity.api_id,
            msg.header.policy.priority, msg.header.policy.noreply,
            msg.parameter, len(msg.binary))
        self._sport_request_count += 1

    def destroy_node(self):
        self._store.close()
        super().destroy_node()


def main():
    rclpy.init()
    node = RecorderNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
