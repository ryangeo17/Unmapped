import os
from glob import glob

from setuptools import setup

package_name = 'unmapped_recorder'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='yzeng52',
    maintainer_email='yzeng52@cs.jhu.edu',
    description=(
        'Records synchronized IMU, front-camera RGB frames, and lidar point clouds from the '
        'Go2 into a file + SQLite dataset for offline navigation-landscape analysis.'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'recorder_node = unmapped_recorder.recorder_node:main',
        ],
    },
)
