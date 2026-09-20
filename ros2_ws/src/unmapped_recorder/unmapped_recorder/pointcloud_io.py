"""PointCloud2 <-> numpy/PCD helpers.

Written by hand instead of depending on sensor_msgs_py.point_cloud2 because that package
isn't installed in this robot's ROS 2 Foxy image.
"""
import numpy as np
from sensor_msgs.msg import PointField

_DATATYPE_TO_DTYPE = {
    PointField.INT8: np.int8,
    PointField.UINT8: np.uint8,
    PointField.INT16: np.int16,
    PointField.UINT16: np.uint16,
    PointField.INT32: np.int32,
    PointField.UINT32: np.uint32,
    PointField.FLOAT32: np.float32,
    PointField.FLOAT64: np.float64,
}


def cloud_to_xyz_array(cloud_msg):
    """Extract an (N,3) float32 xyz array (and optional (N,) intensity) from a PointCloud2,
    reading whatever byte layout the driver declares in `fields` rather than assuming one."""
    endian = '>' if cloud_msg.is_bigendian else '<'
    field_by_name = {f.name: f for f in cloud_msg.fields}
    for required in ('x', 'y', 'z'):
        if required not in field_by_name:
            raise ValueError(
                f"PointCloud2 has no '{required}' field; got {[f.name for f in cloud_msg.fields]}")

    n_points = cloud_msg.width * cloud_msg.height
    raw = np.frombuffer(cloud_msg.data, dtype=np.uint8, count=n_points * cloud_msg.point_step)
    raw = raw.reshape(n_points, cloud_msg.point_step)

    def extract(name):
        field = field_by_name[name]
        dtype = np.dtype(_DATATYPE_TO_DTYPE[field.datatype]).newbyteorder(endian)
        column = raw[:, field.offset:field.offset + dtype.itemsize].copy()
        return column.view(dtype).reshape(n_points).astype(np.float32)

    xyz = np.stack([extract('x'), extract('y'), extract('z')], axis=1)
    intensity = extract('intensity') if 'intensity' in field_by_name else None

    finite = np.isfinite(xyz).all(axis=1)
    xyz = xyz[finite]
    if intensity is not None:
        intensity = intensity[finite]
    return xyz, intensity


def write_pcd(path, xyz, intensity=None):
    """Write a minimal binary PCD v0.7 file, readable by PCL, Open3D, and CloudCompare."""
    n = xyz.shape[0]
    has_intensity = intensity is not None
    fields = 'x y z intensity' if has_intensity else 'x y z'
    sizes = '4 4 4 4' if has_intensity else '4 4 4'
    types = 'F F F F' if has_intensity else 'F F F'
    counts = '1 1 1 1' if has_intensity else '1 1 1'

    header = (
        '# .PCD v0.7 - Point Cloud Data file format\n'
        'VERSION 0.7\n'
        f'FIELDS {fields}\n'
        f'SIZE {sizes}\n'
        f'TYPE {types}\n'
        f'COUNT {counts}\n'
        f'WIDTH {n}\n'
        'HEIGHT 1\n'
        'VIEWPOINT 0 0 0 1 0 0 0\n'
        f'POINTS {n}\n'
        'DATA binary\n'
    )

    if has_intensity:
        payload = np.column_stack([xyz.astype('<f4'), intensity.astype('<f4')])
    else:
        payload = xyz.astype('<f4')

    with open(path, 'wb') as fh:
        fh.write(header.encode('ascii'))
        fh.write(np.ascontiguousarray(payload).tobytes())
