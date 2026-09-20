# unmapped_recorder

ROS 2 node that records the Go2's own IMU/odometry/lidar point clouds plus an attached Intel
RealSense D435i's RGBD+IMU into a file + SQLite dataset, for offline reconstruction of robot
trajectory + point cloud (a SLAM showcase) and other navigation-landscape analysis.

## What it subscribes to

Go2's own sensors, found by inspecting the live ROS 2 graph on the robot (`ros2 topic list -t`):

| Topic               | Type                        | Notes                                          |
|---------------------|------------------------------|-------------------------------------------------|
| `/utlidar/imu`       | `sensor_msgs/msg/Imu`       | lidar-mounted IMU                                |
| `/utlidar/cloud`     | `sensor_msgs/msg/PointCloud2` | raw L1 lidar scan                              |
| `/utlidar/robot_odom`| `nav_msgs/msg/Odometry`     | onboard lidar-SLAM pose + velocity estimate      |
| `/sportmodestate`    | `unitree_go/msg/SportModeState` | locomotion controller's own state: position, **leg-odometry velocity** (independent of the lidar-SLAM velocity above), yaw speed, gait/mode |
| `/wirelesscontroller` | `unitree_go/msg/WirelessController` | raw joystick: stick axes `lx,ly,rx,ry` + button bitmask `keys` |
| `/api/sport/request` | `unitree_api/msg/Request`   | the actual high-level command sent to the sport controller (e.g. a `Move` call); `parameter` is a raw JSON string, `header.identity.api_id` identifies which call |

`unitree_api` doesn't exist as a ROS2 package anywhere on this robot — only raw IDL text from
the vendor SDK (`unitree_go2_sdk/unitree_dds_idl/api`) — even though `/api/sport/request` is a
live DDS topic (published by a bare, non-ROS2 Unitree binary). `ros2_ws/src/unitree_api/` is a
small message-only package built from that same IDL so `unitree_api/msg/Request` exists as a
buildable ROS2 type here; DDS matches subscribers to publishers by type name, so this only
works because that generated package is named exactly `unitree_api` to match the wire type.

RealSense D435i, via `ros-foxy-realsense2-camera` (see Setup below):

| Topic                       | Type                    | Notes                                  |
|------------------------------|--------------------------|-----------------------------------------|
| `/camera/color/image_raw`    | `sensor_msgs/msg/Image` | 1280x720 RGB8 @ ~30fps                  |
| `/camera/depth/image_rect_raw`| `sensor_msgs/msg/Image`| 848x480 16UC1 (millimeters) @ 30fps     |
| `/camera/imu`                | `sensor_msgs/msg/Imu`   | combined accel+gyro, see note below     |
| `/camera/color/camera_info`, `/camera/depth/camera_info` | `sensor_msgs/msg/CameraInfo` | intrinsics, recorded once each |

An earlier version of this node used the Go2's own front camera (`/frontvideostream`), which
only exposes a raw H.264 stream with no ROS2 image topic and turned out to have a flaky DDS
deserialization issue on this robot's firmware. The RealSense replaces it entirely: standard
`sensor_msgs/Image` for both color and depth, no custom decode needed.

**`/camera/imu` requires `unite_imu_method:=2`** when launching `realsense2_camera` (an int on
this driver version — passing the string `linear_interpolation` is silently rejected with a
type-mismatch warning). Without it, accel and gyro only publish on separate topics
(`/camera/accel/sample` at 100Hz, `/camera/gyro/sample` at 200Hz), each with only one of
`angular_velocity`/`linear_acceleration` populated. `record.launch.py` already passes this.

Also worth knowing: this D435i logs `IMU Calibration is not available, default intrinsic and
extrinsic will be used` at startup (factory IMU-to-camera calibration isn't stored on this
unit, so a generic default offset is used instead — fine for this recorder, but a precision
caveat if you later do tight visual-inertial fusion), and `HID set_power 1 failed for
.../HID-SENSOR-...` for both motion sensors, which looked alarming but is a known-benign
warning on this platform — confirmed via `ros2 topic hz /camera/imu` actually reporting steady
~200Hz.

## Image rate limiting

Color and depth are throttled independently to `image_rate_hz` (default 3.0) — extra frames
between the camera's native rate (~15-30fps observed under load, see caveats) and this target
are dropped in the callback before any file/DB write happens, so they cost nothing. Throttling
is done by comparing each frame's own header timestamp to the last *kept* frame's timestamp
(not wall-clock arrival time), so the achieved rate reflects the source timeline even if
processing briefly lags. Set `image_rate_hz: 0` to disable throttling and keep every frame.

## Why every stream is logged independently, not paired live

Each stream is just logged as fast as it arrives, with its own timestamp; joining happens
afterward by nearest `stamp_ns` (see the reconstruction example below). This survives one
stream being slow, bursty, or briefly missing without silently losing data on the others, and
it's a better fit for analysis anyway — you choose the pairing tolerance per analysis instead
of one being baked into the recorder.

## Dataset layout

```
<output_dir>/<session_name>/
  dataset.db     SQLite: session_meta, imu_samples, odom_samples, clouds, color_frames,
                 depth_frames, sport_mode_state, wireless_controller, sport_requests
  clouds/cloud_000001.pcd ...      Go2 lidar scans
  color/color_000001.jpg ...       RealSense color frames
  depth/depth_000001.png ...       RealSense depth frames (16-bit, millimeters, lossless)
```

`imu_samples` has a `source` column (`'utlidar'` or `'realsense'`) since these are two physically
different sensors with different mounting/frames — don't average them together, query per source.

`sport_mode_state`, `wireless_controller`, and `sport_requests` have no ROS header/timestamp in
their source messages, except `sport_mode_state.stamp` (a custom `TimeSpec`, not `builtin_interfaces/Time`,
but same `sec`/`nanosec` fields so it converts to `stamp_ns` the same way); the other two are
timestamped by ROS arrival time, same "best available" approach used for `Go2FrontVideoData`
in an earlier iteration of this node.

`session_meta` includes the RealSense intrinsics recorded once from `camera_info`:
`color_fx, color_fy, color_cx, color_cy, color_width, color_height, color_distortion_model, color_D`
(and the same with `depth_` prefix) — everything needed to back-project a depth+color pair into
a 3D point cloud.

## Setup

Install the ROS2 RealSense driver (not preinstalled on this robot):

```bash
sudo apt-get install ros-foxy-realsense2-camera
```

If apt 404s on this, it's likely the mirror's pool being incomplete for this package, or the
ROS GPG key having expired (`EXPKEYSIG` in the error) — both hit while setting this up:

```bash
# mirror missing files: point the ROS2 line in your sources file at the official repo instead
sudo sed -i '/ros2\/ubuntu/ s|mirrors.tuna.tsinghua.edu.cn|packages.ros.org|' /etc/apt/sources.list.d/ros-fish.list
# expired signing key: OSRF re-signed the same key with a new expiration
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-key F42ED6FBAB17C654
sudo apt-get update
```

Then build. `sport_mode_state`/`wireless_controller` need the Go2 `unitree_go` message package,
so source that underlay first; `unitree_api` (for `/api/sport/request`) is a small package
included in this workspace (`ros2_ws/src/unitree_api/`, see above) and builds alongside:

```bash
source /opt/ros/foxy/setup.bash
source /unitree/module/graph_pid_ws/install/setup.bash   # provides unitree_go
cd ~/Documents/Unmapped/ros2_ws
colcon build --symlink-install --packages-select unitree_api unmapped_recorder
source install/setup.bash
```

## Run

```bash
ros2 launch unmapped_recorder record.launch.py
```

This brings up the RealSense driver (with `unite_imu_method:=2` and RGBD+IMU enabled) and the
recorder together. To run the recorder against an already-running RealSense driver instead:

```bash
ros2 run unmapped_recorder recorder_node --ros-args --params-file src/unmapped_recorder/config/params.yaml
```

The node logs `utlidar_imu=... realsense_imu=... odom=... clouds=... color=... depth=...
sport_mode_state=... wireless_controller=... sport_requests=...` running counts every 5 seconds
so you can tell at a glance which streams are actually flowing (note `wireless_controller` and
`sport_requests` will only tick up while you're actually moving the joystick / issuing sport
commands — zero counts there while just standing still is expected, not a bug). Ctrl+C stops
it cleanly. Data lands in `~/unmapped_data/<timestamp>/` by default.

## Reconstructing a trajectory + point cloud for a SLAM showcase

```python
import sqlite3, pandas as pd

con = sqlite3.connect('dataset.db')
odom = pd.read_sql('SELECT * FROM odom_samples ORDER BY stamp_ns', con)
clouds = pd.read_sql('SELECT * FROM clouds ORDER BY stamp_ns', con)
color = pd.read_sql('SELECT * FROM color_frames ORDER BY stamp_ns', con)
depth = pd.read_sql('SELECT * FROM depth_frames ORDER BY stamp_ns', con)
meta = dict(con.execute('SELECT key, value FROM session_meta').fetchall())

# nearest-pose-per-cloud (both sides must be sorted by the join key)
cloud_pose = pd.merge_asof(clouds, odom, on='stamp_ns', direction='nearest', suffixes=('_cloud', '_odom'))
# nearest-depth-per-color, e.g. to build a colored point cloud per RGBD pair
rgbd = pd.merge_asof(color, depth, on='stamp_ns', direction='nearest', suffixes=('_color', '_depth'))
```

Each `cloud_pose` row gives a `.pcd` path plus the robot pose (`px,py,pz,qx,qy,qz,qw`) to
transform that Go2 lidar scan into a common world frame with (e.g. via Open3D) and accumulate
into one map. Each `rgbd` row gives a color/depth pair plus `meta['depth_fx']` etc. to
back-project depth pixels into a colored 3D point cloud (`z = depth_mm / 1000`,
`x = (u - cx) * z / fx`, `y = (v - cy) * z / fy`).

## Known caveats

- Color and depth are logged independently (not hardware-synced at record time), same
  philosophy as everything else here — join by nearest `stamp_ns` at whatever tolerance your
  analysis needs.
- RealSense IMU orientation is not a real attitude estimate — the D435i only provides raw
  accel+gyro (no onboard sensor fusion), so `imu_samples.qx/qy/qz/qw` for `source='realsense'`
  rows is a meaningless default, not orientation data. Use `wx/wy/wz` (gyro) and `ax/ay/az`
  (accel) instead, or the Go2's `utlidar` rows for actual orientation.
- There are now two independent robot velocity estimates: `odom_samples.vx/vy/vz` (lidar-SLAM,
  from `/utlidar/robot_odom`) and `sport_mode_state.vx/vy/vz` (leg odometry, from the
  locomotion controller). They can disagree, especially on foot slip — that disagreement can
  itself be informative, don't assume they should match.
- `sport_requests.parameter` is stored as the raw JSON string exactly as sent; what it means
  depends on `api_id`, which this package doesn't maintain a lookup table for. `1008` was seen
  in testing to correspond to a `Move` call with `{"x":...,"y":...,"z":...}`, but treat that as
  a starting point to verify against your own traffic, not a documented mapping.
- A real gotcha hit while building this: fixed-size `float32[N]` array fields in these
  Unitree messages (e.g. `SportModeState.position`/`.velocity`) are `numpy.ndarray`-backed in
  rclpy, and `numpy.float32` isn't a Python `float` — `sqlite3` doesn't raise an error on that
  mismatch, it silently stores the raw 4-byte value as a BLOB instead of a REAL. `dataset_store.py`
  casts explicitly with `float(...)` before every insert for exactly this reason; keep doing so
  if you add more fields from array-typed message fields.
- Measured on real sessions before `image_rate_hz` throttling existed: color/depth were only
  actually landing at ~12-15Hz despite the RealSense running at ~26-30fps, with occasional
  multi-hundred-ms (once 1.5s) stalls. Likely cause: `DatasetStore` commits to SQLite after
  every single insert across all nine streams (two IMUs at 200Hz included), and each commit
  does a disk sync — under load, callbacks queue up behind each other's I/O on the single
  rclpy executor thread. `image_rate_hz` sidesteps this by cutting the write volume rather than
  fixing the underlying per-row commit cost; if you push `image_rate_hz` back up high (or add
  more high-rate streams) and see the achieved rate fall well short of it again, batching
  commits (e.g. every N inserts or every ~0.2s) instead of committing every row is the fix.
