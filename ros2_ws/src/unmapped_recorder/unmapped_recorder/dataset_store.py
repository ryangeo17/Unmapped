"""File + SQLite dataset for one recording session.

Every stream is logged independently and joined later by timestamp, rather than paired live
(see README for why). Layout under <output_dir>/<session_name>/:

  dataset.db          SQLite: session_meta, imu_samples, odom_samples, clouds, color_frames,
                      depth_frames, sport_mode_state, wireless_controller, sport_requests
  clouds/*.pcd         one file per Go2 lidar scan
  color/*.jpg          one file per RealSense color frame
  depth/*.png          one file per RealSense depth frame (16-bit, millimeters, lossless)

session_meta also holds the RealSense color/depth camera intrinsics (recorded once), needed to
back-project a depth+color pair into a 3D point cloud for the SLAM reconstruction.
"""
import os
import sqlite3
import threading

import cv2

from .pointcloud_io import write_pcd

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS imu_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    stamp_ns INTEGER NOT NULL,
    qx REAL, qy REAL, qz REAL, qw REAL,
    wx REAL, wy REAL, wz REAL,
    ax REAL, ay REAL, az REAL
);
CREATE INDEX IF NOT EXISTS idx_imu_stamp ON imu_samples(source, stamp_ns);

CREATE TABLE IF NOT EXISTS odom_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    px REAL, py REAL, pz REAL,
    qx REAL, qy REAL, qz REAL, qw REAL,
    vx REAL, vy REAL, vz REAL,
    wx REAL, wy REAL, wz REAL
);
CREATE INDEX IF NOT EXISTS idx_odom_stamp ON odom_samples(stamp_ns);

CREATE TABLE IF NOT EXISTS clouds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    path TEXT NOT NULL,
    num_points INTEGER
);
CREATE INDEX IF NOT EXISTS idx_clouds_stamp ON clouds(stamp_ns);

CREATE TABLE IF NOT EXISTS color_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_color_frames_stamp ON color_frames(stamp_ns);

CREATE TABLE IF NOT EXISTS depth_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_depth_frames_stamp ON depth_frames(stamp_ns);

CREATE TABLE IF NOT EXISTS sport_mode_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    mode INTEGER, gait_type INTEGER, progress REAL,
    body_height REAL, foot_raise_height REAL,
    px REAL, py REAL, pz REAL,
    vx REAL, vy REAL, vz REAL,
    yaw_speed REAL, error_code INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sport_mode_state_stamp ON sport_mode_state(stamp_ns);

CREATE TABLE IF NOT EXISTS wireless_controller (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    lx REAL, ly REAL, rx REAL, ry REAL,
    keys INTEGER
);
CREATE INDEX IF NOT EXISTS idx_wireless_controller_stamp ON wireless_controller(stamp_ns);

CREATE TABLE IF NOT EXISTS sport_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stamp_ns INTEGER NOT NULL,
    request_id INTEGER, api_id INTEGER,
    priority INTEGER, noreply INTEGER,
    parameter TEXT, binary_len INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sport_requests_stamp ON sport_requests(stamp_ns);
"""


class DatasetStore:
    def __init__(self, session_dir):
        self._clouds_dir = os.path.join(session_dir, 'clouds')
        self._color_dir = os.path.join(session_dir, 'color')
        self._depth_dir = os.path.join(session_dir, 'depth')
        os.makedirs(self._clouds_dir, exist_ok=True)
        os.makedirs(self._color_dir, exist_ok=True)
        os.makedirs(self._depth_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._db = sqlite3.connect(os.path.join(session_dir, 'dataset.db'), check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def set_meta(self, **kv):
        with self._lock:
            self._db.executemany(
                'INSERT OR REPLACE INTO session_meta(key, value) VALUES (?, ?)',
                [(k, str(v)) for k, v in kv.items()],
            )
            self._db.commit()

    def add_imu(self, source, stamp_ns, orientation, angular_velocity, linear_acceleration):
        with self._lock:
            self._db.execute(
                'INSERT INTO imu_samples (source, stamp_ns, qx, qy, qz, qw, wx, wy, wz, ax, ay, az) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (source, stamp_ns, orientation.x, orientation.y, orientation.z, orientation.w,
                 angular_velocity.x, angular_velocity.y, angular_velocity.z,
                 linear_acceleration.x, linear_acceleration.y, linear_acceleration.z),
            )
            self._db.commit()

    def add_odom(self, stamp_ns, position, orientation, linear_velocity, angular_velocity):
        with self._lock:
            self._db.execute(
                'INSERT INTO odom_samples (stamp_ns, px, py, pz, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (stamp_ns, position.x, position.y, position.z,
                 orientation.x, orientation.y, orientation.z, orientation.w,
                 linear_velocity.x, linear_velocity.y, linear_velocity.z,
                 angular_velocity.x, angular_velocity.y, angular_velocity.z),
            )
            self._db.commit()

    def add_cloud(self, stamp_ns, xyz, intensity):
        with self._lock:
            index = self._db.execute('SELECT COALESCE(MAX(id), 0) FROM clouds').fetchone()[0] + 1
            path = os.path.join(self._clouds_dir, f'cloud_{index:06d}.pcd')
            write_pcd(path, xyz, intensity)
            self._db.execute(
                'INSERT INTO clouds (stamp_ns, path, num_points) VALUES (?, ?, ?)',
                (stamp_ns, path, int(xyz.shape[0])),
            )
            self._db.commit()

    def add_color_frame(self, stamp_ns, image_bgr, jpg_quality=92):
        with self._lock:
            index = self._db.execute('SELECT COALESCE(MAX(id), 0) FROM color_frames').fetchone()[0] + 1
            path = os.path.join(self._color_dir, f'color_{index:06d}.jpg')
            cv2.imwrite(path, image_bgr, [cv2.IMWRITE_JPEG_QUALITY, jpg_quality])
            self._db.execute(
                'INSERT INTO color_frames (stamp_ns, path) VALUES (?, ?)', (stamp_ns, path))
            self._db.commit()

    def add_depth_frame(self, stamp_ns, depth_u16):
        with self._lock:
            index = self._db.execute('SELECT COALESCE(MAX(id), 0) FROM depth_frames').fetchone()[0] + 1
            path = os.path.join(self._depth_dir, f'depth_{index:06d}.png')
            cv2.imwrite(path, depth_u16)  # 16UC1 -> 16-bit grayscale PNG, lossless
            self._db.execute(
                'INSERT INTO depth_frames (stamp_ns, path) VALUES (?, ?)', (stamp_ns, path))
            self._db.commit()

    def add_sport_mode_state(self, stamp_ns, mode, gait_type, progress, body_height,
                              foot_raise_height, position, velocity, yaw_speed, error_code):
        # position/velocity are numpy.ndarray for this message (fixed-size float32[3] fields
        # are numpy-backed in rclpy); numpy.float32 isn't a Python float, and sqlite3 silently
        # stores it as a raw 4-byte BLOB instead of a REAL if not cast first - not an error,
        # just silently wrong data. Cast explicitly rather than trust the caller to know this.
        with self._lock:
            self._db.execute(
                'INSERT INTO sport_mode_state (stamp_ns, mode, gait_type, progress, body_height, '
                'foot_raise_height, px, py, pz, vx, vy, vz, yaw_speed, error_code) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (stamp_ns, mode, gait_type, float(progress), float(body_height), float(foot_raise_height),
                 float(position[0]), float(position[1]), float(position[2]),
                 float(velocity[0]), float(velocity[1]), float(velocity[2]),
                 float(yaw_speed), error_code),
            )
            self._db.commit()

    def add_wireless_controller(self, stamp_ns, lx, ly, rx, ry, keys):
        with self._lock:
            self._db.execute(
                'INSERT INTO wireless_controller (stamp_ns, lx, ly, rx, ry, keys) VALUES (?, ?, ?, ?, ?, ?)',
                (stamp_ns, lx, ly, rx, ry, keys),
            )
            self._db.commit()

    def add_sport_request(self, stamp_ns, request_id, api_id, priority, noreply, parameter, binary_len):
        with self._lock:
            self._db.execute(
                'INSERT INTO sport_requests (stamp_ns, request_id, api_id, priority, noreply, parameter, binary_len) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (stamp_ns, request_id, api_id, priority, int(noreply), parameter, binary_len),
            )
            self._db.commit()

    def close(self):
        with self._lock:
            self._db.commit()
            self._db.close()
