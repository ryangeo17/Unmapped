import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    config = os.path.join(get_package_share_directory('unmapped_recorder'), 'config', 'params.yaml')

    realsense = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('realsense2_camera'), 'launch', 'rs_launch.py')),
        launch_arguments={
            'enable_color': 'true',
            'enable_depth': 'true',
            'enable_gyro': 'true',
            'enable_accel': 'true',
            # int, not the method name - this driver version rejects a string here (see README)
            'unite_imu_method': '2',
        }.items(),
    )

    recorder = Node(
        package='unmapped_recorder',
        executable='recorder_node',
        name='unmapped_recorder',
        output='screen',
        parameters=[config],
    )

    return LaunchDescription([realsense, recorder])
