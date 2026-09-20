#!/usr/bin/env python3
"""Assemble the lidar scans into one world-frame map and label the ground plane.

How the map is built
--------------------
The Go2's ``/utlidar/cloud`` does not arrive in the body frame. Each scan is
already **gravity-referenced and heading-stabilised**: z is height above the
ground under the robot, and the x/y axes stay parallel to the odometry frame as
the robot turns. Assembly is therefore a pure translation -- no rotation at all.

That is not an assumption, it is measured. ``--check-frame`` re-runs the test on
your data: take pairs of scans recorded at the same place on opposite headings
(the runs are out-and-back, so there are hundreds), transform both, and score how
well their occupied voxels agree. On this run the no-rotation convention scores
IoU 0.137 against 0.043 for body-yaw rotation -- a factor of three, and the same
ordering for every yaw offset tried.

Height comes from the slope pipeline, not from odometry
-------------------------------------------------------
``odom_samples.pz`` is body height above the ground (it moves 4 cm over a 300 m
walk), so it carries no elevation. ``label_slopes.py`` already solves this: the
attitude quaternion gives the terrain normal, hence the grade, and integrating
the grade along the path gives elevation. This script imports those functions
rather than re-deriving them, so the map and ``slope_labels.csv`` cannot drift
apart. World z of a point is its scan z plus the integrated elevation at that
moment.

Self-returns
------------
62% of all points lie within 0.5 m of the origin at z ~ 0.37 m: the robot seeing
its own body at lidar height. They are dropped (``--self-radius``). Leaving them
in buries the scene under a bright blob at every pose and, because they are
body-fixed, corrupts any frame-convention test done on the raw clouds.

Labelling the ground
--------------------
A single plane is the wrong model -- the point of this dataset is that the campus
is sloped. Instead the map is gridded in x/y and a **local plane is fitted per
cell**: a low percentile of z seeds the ground height, points near that seed feed
a least-squares plane fitted over the cell's 3x3 neighbourhood, and a point is
ground if it sits within ``--ground-tol`` of that surface. Cells whose plane comes
out steeper than ``--max-ground-slope`` are walls or steps, not ground, and are
labelled structure. The fit is done from moment sums under a box filter, so all
~50k cells are solved at once.

Outputs (written into the run directory)
----------------------------------------
``slam_map.npz``      world points, ground mask, per-cell ground height and slope
``slam_map.png``      ground/structure split, ground elevation, structure height, 3D view
``ground_profile.png`` elevation and grade along the trajectory
``slam_map.html``     interactive 3D view -- orbit, and toggle ground against structure

Examples
--------
    python build_slam_map.py                          # the run named below
    python build_slam_map.py --run 20260920_041230
    python build_slam_map.py --check-frame            # re-run the convention test
    python build_slam_map.py --voxel 0.03 --cell 0.3  # finer
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from label_slopes import (calibrate, loop_closure, rolling_median,
                          slope_components, terrain_from_quaternion)

# The reference data-viz palette, dark surface (point clouds read better on dark).
INK        = "#ffffff"
INK_2      = "#c3c2b7"
MUTED      = "#898781"
SURFACE    = "#1a1a19"
PLANE      = "#0d0d0d"
GRID       = "#2c2c2a"
GROUND_C   = "#3987e5"   # categorical slot 1, dark step
STRUCT_C   = "#d95926"   # categorical slot 2, dark step
# sequential blue ramp, 100 -> 700
BLUE_RAMP  = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
              "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
              "#0d366b"]
# second sequential context: the slot-2 hue as its own one-hue ramp
ORANGE_RAMP = ["#fbe3d6", "#f7cdb6", "#f3b695", "#ee9f75", "#ea8855", "#e5713c",
               "#d95926", "#c24d20", "#a8421b", "#8d3716", "#722c12", "#59220e"]


# --------------------------------------------------------------------------- #
# io
# --------------------------------------------------------------------------- #

def read_pcd(path: str) -> np.ndarray:
    """(N, 4) float64 of x, y, z, intensity from a binary PCD.

    The recorder writes one fixed layout -- four float32 fields, DATA binary -- so
    this reads the header only far enough to trust that and to get the count.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    marker = b"DATA binary\n"
    cut = raw.index(marker) + len(marker)
    header = raw[:cut].decode("ascii", "replace")
    if "FIELDS x y z intensity" not in header:
        raise ValueError(f"{path}: unexpected FIELDS, expected 'x y z intensity'")
    n = int(re.search(r"POINTS (\d+)", header).group(1))
    return np.frombuffer(raw[cut:cut + n * 16], dtype=np.float32).reshape(n, 4).astype(np.float64)


def load_run(run_dir: str):
    """Odometry array and the cloud list, both on the raw recorder clock.

    Clouds and odometry share a clock (the colour frames do not, which is why
    ``label_slopes`` needs a clock offset and this does not).
    """
    db = os.path.join(run_dir, "dataset.db")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        od = np.asarray(con.execute(
            "SELECT stamp_ns, px, py, qx, qy, qz, qw, vx, vy FROM odom_samples "
            "ORDER BY stamp_ns").fetchall(), dtype=float)
        clouds = con.execute(
            "SELECT stamp_ns, path FROM clouds ORDER BY stamp_ns").fetchall()
    finally:
        con.close()
    if not len(od) or not clouds:
        raise SystemExit(f"{run_dir}: no odometry or no clouds")
    # the db stores the path as recorded on the robot; resolve it here
    clouds = [(int(s), os.path.join(run_dir, "clouds", os.path.basename(p)))
              for s, p in clouds]
    return od, clouds


# --------------------------------------------------------------------------- #
# trajectory: pose and elevation on the cloud clock
# --------------------------------------------------------------------------- #

def trajectory(od: np.ndarray, args):
    """Per-odometry-sample pose, grade and integrated elevation.

    This is ``label_slopes.process_run`` restricted to what a map needs, and it
    calls the same functions, so the elevation here is the elevation in
    ``slope_labels.csv``.
    """
    t = od[:, 0] / 1e9
    xy = od[:, 1:3]
    speed = np.hypot(od[:, 7], od[:, 8])

    n, yaw = terrain_from_quaternion(od[:, 3:7])
    tilt_raw, grade_raw, cross_raw = slope_components(n, yaw)
    grade = rolling_median(grade_raw, t, args.smooth_window)
    cross = rolling_median(cross_raw, t, args.smooth_window)

    standing = np.abs(rolling_median(tilt_raw, t, args.smooth_window)) < args.max_tilt
    walking = speed > args.walk_speed

    cal = calibrate(xy, yaw, grade, cross, standing & walking, t,
                    args.revisit_radius, args.revisit_min_dt)
    grade = grade - cal.grade_bias
    cross = cross - cal.cross_bias

    ds = np.r_[0.0, np.linalg.norm(np.diff(xy, axis=0), axis=1)]
    elev = np.cumsum(np.where(standing, np.tan(np.radians(grade)), 0.0) * ds)

    # How much to trust the map's z: walk over the same ground twice and the two
    # elevations must agree. Only walking revisits count -- a robot standing still
    # for a minute also looks like a "revisit" and would score a perfect 0.
    closure, n_closure = loop_closure(xy, elev, standing & walking, t,
                                      args.revisit_radius, args.revisit_min_dt)
    relief = float(np.ptp(elev[standing])) if standing.any() else float("nan")
    return dict(t=t, xy=xy, yaw=yaw, grade=grade, cross=cross, elev=elev,
                standing=standing, walking=walking, speed=speed, cal=cal,
                path_s=np.cumsum(ds), closure=closure, n_closure=n_closure,
                relief=relief)


# --------------------------------------------------------------------------- #
# frame convention check
# --------------------------------------------------------------------------- #

def check_frame(clouds, traj, args) -> None:
    """Score both conventions on opposite-heading revisits and print the result.

    Out-and-back walking means the same ground is scanned twice from headings
    180 deg apart. Under the right convention the two scans land on each other;
    under the wrong one the second is spun about the robot. Voxel IoU measures it.
    """
    ct = np.array([s for s, _ in clouds], dtype=float) / 1e9
    t, xy, yaw = traj["t"], traj["xy"], traj["yaw"]
    j = np.clip(np.searchsorted(t, ct), 0, len(t) - 1)
    cx, cy, cyaw = xy[j, 0], xy[j, 1], yaw[j]

    pairs = []
    for a in range(0, len(clouds), 10):
        d = np.hypot(cx - cx[a], cy - cy[a])
        dyaw = np.abs(np.arctan2(np.sin(cyaw - cyaw[a]), np.cos(cyaw - cyaw[a])))
        k = np.flatnonzero((d < args.revisit_radius) & (dyaw > np.deg2rad(150))
                           & (np.abs(ct - ct[a]) > args.revisit_min_dt))
        if len(k):
            pairs.append((a, int(k[len(k) // 2])))
    pairs = pairs[:args.check_pairs]
    if len(pairs) < 10:
        print("frame check: too few opposite-heading revisits to decide")
        return

    cache: dict[int, np.ndarray] = {}

    def scan(k):
        if k not in cache:
            a = read_pcd(clouds[k][1])[:, :3]
            cache[k] = a[np.hypot(a[:, 0], a[:, 1]) > args.self_radius]
        return cache[k]

    def placed(k, ang):
        p = scan(k)
        c, s = np.cos(ang), np.sin(ang)
        return np.column_stack([c * p[:, 0] - s * p[:, 1] + cx[k],
                                s * p[:, 0] + c * p[:, 1] + cy[k], p[:, 2]])

    def iou(A, B, v=0.25):
        ka = {tuple(q) for q in np.floor(A / v).astype(np.int64)}
        kb = {tuple(q) for q in np.floor(B / v).astype(np.int64)}
        return len(ka & kb) / max(len(ka | kb), 1)

    print(f"\nframe convention check -- {len(pairs)} opposite-heading revisit pairs, "
          f"self-returns removed")
    none = np.mean([iou(placed(a, 0.0), placed(b, 0.0)) for a, b in pairs])
    print(f"  no rotation (heading-stabilised cloud) : IoU {none:.4f}")
    best = 0.0
    for off in (0, 90, 180, 270):
        o = np.deg2rad(off)
        v = np.mean([iou(placed(a, cyaw[a] + o), placed(b, cyaw[b] + o)) for a, b in pairs])
        best = max(best, v)
        print(f"  body-yaw rotation {off:+4d} deg            : IoU {v:.4f}")
    verdict = "no rotation" if none > best else "body-yaw rotation"
    print(f"  -> {verdict} wins by {max(none, best) / max(min(none, best), 1e-9):.1f}x\n")


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def assemble(clouds, traj, args):
    """Place every scan in the world frame and voxel-downsample the result.

    Scans are translated only (see the module docstring). Points are dropped if
    they are self-returns, beyond useful range, or recorded while the robot was
    not standing -- a sitting Go2 breaks the "z is height above ground" premise.
    """
    ct = np.array([s for s, _ in clouds], dtype=float) / 1e9
    t = traj["t"]
    inside = (ct >= t[0]) & (ct <= t[-1])
    j = np.clip(np.searchsorted(t, ct), 0, len(t) - 1)
    keep_scan = inside & traj["standing"][j]

    px = np.interp(ct, t, traj["xy"][:, 0])
    py = np.interp(ct, t, traj["xy"][:, 1])
    pe = np.interp(ct, t, traj["elev"])

    xs, ys, zs, iv = [], [], [], []
    n_raw = n_self = 0
    for k, (_, path) in enumerate(clouds):
        if not keep_scan[k]:
            continue
        a = read_pcd(path)
        n_raw += len(a)
        r = np.hypot(a[:, 0], a[:, 1])
        m = (r > args.self_radius) & (r < args.max_range)
        n_self += int((r <= args.self_radius).sum())
        if not m.any():
            continue
        a = a[m]
        xs.append((a[:, 0] + px[k]).astype(np.float32))
        ys.append((a[:, 1] + py[k]).astype(np.float32))
        zs.append((a[:, 2] + pe[k]).astype(np.float32))
        iv.append(a[:, 3].astype(np.float32))
        if args.progress and k % 1000 == 0:
            print(f"  scan {k:5d}/{len(clouds)}", flush=True)

    P = np.column_stack([np.concatenate(xs), np.concatenate(ys),
                         np.concatenate(zs), np.concatenate(iv)])
    stats = dict(scans_total=len(clouds), scans_used=int(keep_scan.sum()),
                 points_raw=n_raw, points_self=n_self, points_kept=len(P))
    return voxelise(P, args.voxel), stats


def voxelise(P: np.ndarray, voxel: float):
    """Mean position and intensity per occupied voxel, plus the hit count.

    Averaging inside the voxel rather than picking a representative keeps the
    surface smooth enough for a plane fit; the count is kept because a voxel hit
    once is much more likely to be noise than one hit fifty times.
    """
    q = np.floor(P[:, :3] / voxel).astype(np.int64)
    q -= q.min(axis=0)
    dims = q.max(axis=0) + 1
    key = (q[:, 0] * dims[1] + q[:, 1]) * dims[2] + q[:, 2]
    _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    out = np.empty((len(cnt), 4), dtype=np.float32)
    for c in range(4):
        out[:, c] = np.bincount(inv, weights=P[:, c]) / cnt
    return dict(xyz=out[:, :3], intensity=out[:, 3], count=cnt.astype(np.int32))


# --------------------------------------------------------------------------- #
# ground plane
# --------------------------------------------------------------------------- #

def label_ground(xyz: np.ndarray, args):
    """Fit a local ground plane per x/y cell and label points that lie on it.

    A single plane is the wrong model for a sloped campus, so the ground is fitted
    piecewise. A low percentile of z in each cell seeds the ground height -- robust
    because a cell holding a bench is still mostly pavement. Points within a loose
    band of that seed then feed a least-squares plane over the cell's 3x3
    neighbourhood, which lets the surface follow a ramp instead of stepping down it.

    The fit is done on **centred moments with a ridge prior**, and that detail is
    what makes it work. Solving the raw normal equations lets a cell holding a
    single near-collinear lidar arc pick any slope it likes through that arc: on
    this run a naive fit put a third of all cells at impossible ground heights,
    some +-9 m, because nothing in the system says a nearly one-dimensional
    neighbourhood cannot determine a plane. Centring removes the conditioning
    problem that comes from 140 m coordinates; the ridge ``lambda = N * (cell/2)^2``
    shrinks the slope toward flat in proportion to how little spatial spread the
    neighbourhood actually has; and a cell is only trusted if the smaller principal
    spread of its points clears ``--min-spread``. Anything that fails falls back to
    a flat plane at the smoothed seed height, which is always defined.

    All ~50k cells are solved at once -- the neighbourhood sums are a box filter
    over per-cell sums, so there is no Python loop over cells.
    """
    from scipy import ndimage

    cell = args.cell
    ij = np.floor(xyz[:, :2] / cell).astype(np.int64)
    ij -= ij.min(axis=0)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    cid = ij[:, 0] * ny + ij[:, 1]
    ncell = nx * ny

    # --- seed: a low percentile of z in each cell ---
    order = np.lexsort((xyz[:, 2], cid))
    cs, zs = cid[order], xyz[order, 2]
    start = np.searchsorted(cs, np.arange(ncell), side="left")
    stop = np.searchsorted(cs, np.arange(ncell), side="right")
    cnt = stop - start
    seed = np.full(ncell, np.nan)
    has = cnt >= args.min_cell_points
    pick = start[has] + np.floor(args.ground_pct / 100.0 * (cnt[has] - 1)).astype(np.int64)
    seed[has] = zs[pick]

    grid = seed.reshape(nx, ny)
    has2d = has.reshape(nx, ny)
    # fill unseeded cells from the nearest seeded one, then median-smooth: a plane
    # fit needs a height for every neighbour it touches, and a single mis-seeded
    # cell should not drag its neighbours.
    if not has2d.all():
        idx = ndimage.distance_transform_edt(~has2d, return_distances=False,
                                             return_indices=True)
        grid = grid[tuple(idx)]
    grid = ndimage.median_filter(grid, size=3, mode="nearest")

    # --- local plane fit, centred, with a ridge prior on the slope ---
    # Moments are accumulated in coordinates relative to one origin for the whole
    # map, not to each cell's own centre: summing per-cell moments under a box
    # filter is only valid when every term shares an origin. (Centring per cell
    # first collapses the measured spread to a single cell's width no matter how
    # the points really lie, which silently disables the conditioning test.)
    ox, oy = xyz[:, 0].min(), xyz[:, 1].min()
    u, v, z = xyz[:, 0] - ox, xyz[:, 1] - oy, xyz[:, 2]
    near = np.abs(z - grid.ravel()[cid]) < args.seed_band
    w = near.astype(np.float64)

    def acc(a):
        return np.bincount(cid, weights=a * w, minlength=ncell).reshape(nx, ny)

    def box(a):
        return ndimage.uniform_filter(a, size=3, mode="nearest") * 9.0

    S1 = box(acc(np.ones(len(u))))
    Su, Sv, Sz = box(acc(u)), box(acc(v)), box(acc(z))
    Suu, Suv, Svv = box(acc(u * u)), box(acc(u * v)), box(acc(v * v))
    Suz, Svz = box(acc(u * z)), box(acc(v * z))

    n = np.maximum(S1, 1.0)
    mu, mv, mz = Su / n, Sv / n, Sz / n            # neighbourhood centroid
    Cuu, Cuv, Cvv = Suu - Su * mu, Suv - Su * mv, Svv - Sv * mv
    Cuz, Cvz = Suz - Su * mz, Svz - Sv * mz

    # smaller principal spread of the neighbourhood: a collinear arc has ~0 here
    tr, det = Cuu + Cvv, Cuu * Cvv - Cuv ** 2
    disc = np.sqrt(np.maximum(tr ** 2 / 4.0 - det, 0.0))
    spread = np.sqrt(np.maximum(tr / 2.0 - disc, 0.0) / n)

    lam = n * (cell / 2.0) ** 2                    # shrink slope toward flat
    A11, A22, A12 = Cuu + lam, Cvv + lam, Cuv
    det2 = A11 * A22 - A12 ** 2
    det2 = np.where(np.abs(det2) < 1e-12, 1e-12, det2)
    a_x = (A22 * Cuz - A12 * Cvz) / det2
    a_y = (A11 * Cvz - A12 * Cuz) / det2

    # plane height at the cell centre, for the elevation map
    ccu = (np.arange(nx)[:, None] + 0.5) * cell + (np.floor(ox / cell) * cell - ox)
    ccv = (np.arange(ny)[None, :] + 0.5) * cell + (np.floor(oy / cell) * cell - oy)
    c0 = a_x * (ccu - mu) + a_y * (ccv - mv) + mz

    slope = np.degrees(np.arctan(np.hypot(a_x, a_y)))
    usable = ((S1 >= args.min_cell_points) & (spread >= args.min_spread)
              & (slope <= args.max_ground_slope)
              & (np.abs(c0 - grid) <= args.max_seed_offset))
    a_x = np.where(usable, a_x, 0.0)
    a_y = np.where(usable, a_y, 0.0)
    mz_e = np.where(usable, mz, grid)              # fall back to the flat seed
    mu_e = np.where(usable, mu, 0.0)
    mv_e = np.where(usable, mv, 0.0)
    c0 = np.where(usable, c0, grid)
    slope_out = np.where(usable, slope, np.nan)

    gh = (a_x.ravel()[cid] * (u - mu_e.ravel()[cid])
          + a_y.ravel()[cid] * (v - mv_e.ravel()[cid]) + mz_e.ravel()[cid])
    above = z - gh
    is_ground = np.abs(above) <= args.ground_tol
    return dict(is_ground=is_ground, above=above, height=c0, slope=slope_out,
                usable=usable, has=has2d, cid=cid, nx=nx, ny=ny,
                origin=(np.floor(xyz[:, :2].min(axis=0) / cell) * cell))


# --------------------------------------------------------------------------- #
# figures
# --------------------------------------------------------------------------- #

def _style(ax, title, xlabel="x (m)", ylabel="y (m)"):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=INK, fontsize=11, pad=8, loc="left")
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.tick_params(colors=MUTED, labelsize=8)
    for s in ax.spines.values():
        s.set_color(GRID)


def make_figures(run_dir, pts, gnd, traj, stats, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    blue = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)
    orange = LinearSegmentedColormap.from_list("seq_orange", ORANGE_RAMP)
    for cm in (blue, orange):
        cm.set_bad(SURFACE)
    xyz = pts["xyz"]
    g = gnd["is_ground"]
    tx, ty = traj["xy"][:, 0], traj["xy"][:, 1]
    cell = args.cell
    x0, y0 = gnd["origin"]
    extent = [x0, x0 + gnd["nx"] * cell, y0, y0 + gnd["ny"] * cell]
    w, h = extent[1] - extent[0], extent[3] - extent[2]

    # every panel is drawn at true scale, so the figure is sized from the map's
    # own aspect rather than the map being squeezed into a fixed box
    pw = 8.2
    fig, axes = plt.subplots(2, 2, figsize=(2 * pw + 1.4, 2 * (pw * h / w) + 1.5),
                             facecolor=PLANE, layout="constrained")
    axes = axes.ravel()

    def frame(ax, title):
        _style(ax, title)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        ax.set_aspect("equal")

    def bar(ax, im, label):
        cb = fig.colorbar(im, ax=ax, pad=0.01, fraction=0.03, shrink=0.9)
        cb.set_label(label, color=INK_2, fontsize=9)
        cb.ax.tick_params(colors=MUTED, labelsize=8)
        cb.outline.set_edgecolor(GRID)

    # --- 1. the labelled ground plane ---
    ax = axes[0]; frame(ax, "Ground plane vs structure")
    # structure first, ground over it: seen from above, structure would occlude
    # the ground, but this panel exists to show the ground labelling
    ax.scatter(xyz[~g, 0], xyz[~g, 1], s=0.05, c=STRUCT_C, linewidths=0, rasterized=True)
    ax.scatter(xyz[g, 0], xyz[g, 1], s=0.07, c=GROUND_C, linewidths=0, rasterized=True)
    ax.plot(tx, ty, color=INK, lw=1.6, alpha=0.9)
    hs = [plt.Line2D([], [], marker="o", ls="", ms=7, color=GROUND_C, label="ground plane"),
          plt.Line2D([], [], marker="o", ls="", ms=7, color=STRUCT_C, label="structure"),
          plt.Line2D([], [], color=INK, lw=1.6, label="trajectory")]
    ax.legend(handles=hs, loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK_2)

    # --- 2. ground elevation (sequential, one hue) ---
    ax = axes[1]; frame(ax, "Ground elevation (m, integrated terrain grade)")
    hm = np.where(gnd["usable"] | gnd["has"], gnd["height"], np.nan)
    lo, hi = np.nanpercentile(hm, [1, 99])
    im = ax.imshow(hm.T, origin="lower", extent=extent, cmap=blue, vmin=lo, vmax=hi,
                   aspect="equal", interpolation="nearest")
    ax.plot(tx, ty, color=INK, lw=1.0, alpha=0.6)
    bar(ax, im, "elevation (m)")

    # --- 3. structure height above the ground plane (second sequential context) ---
    ax = axes[2]; frame(ax, "Structure height above the ground plane")
    s = ~g & (gnd["above"] > args.ground_tol)
    o = np.argsort(gnd["above"][s])
    sc = ax.scatter(xyz[s, 0][o], xyz[s, 1][o], s=0.12,
                    c=np.clip(gnd["above"][s][o], 0, 2.0), cmap=orange, vmin=0, vmax=2.0,
                    linewidths=0, rasterized=True)
    ax.plot(tx, ty, color=INK, lw=1.0, alpha=0.6)
    bar(ax, sc, "height above ground (m)")

    # --- 4. ground slope (ties the map back to slope_labels.csv) ---
    ax = axes[3]; frame(ax, "Ground plane slope")
    sm = np.where(gnd["usable"], gnd["slope"], np.nan)
    im = ax.imshow(sm.T, origin="lower", extent=extent, cmap=orange, vmin=0,
                   vmax=max(np.nanpercentile(sm, 97), 1.0), aspect="equal",
                   interpolation="nearest")
    ax.plot(tx, ty, color=INK, lw=1.0, alpha=0.6)
    bar(ax, im, "slope (deg)")

    fig.suptitle(f"SLAM map -- {os.path.basename(run_dir.rstrip('/'))}    "
                 f"{stats['scans_used']:,} scans, {len(xyz):,} voxels at "
                 f"{args.voxel*100:.0f} cm, {100*g.mean():.0f}% ground",
                 color=INK, fontsize=13, x=0.012, ha="left")
    out = os.path.join(run_dir, "slam_map.png")
    fig.savefig(out, dpi=args.dpi, facecolor=PLANE)
    plt.close(fig)
    return out


def make_profile(run_dir, traj, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s, elev, grade = traj["path_s"], traj["elev"], traj["grade"]
    ok = traj["standing"]
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), facecolor=PLANE, sharex=True,
                             gridspec_kw=dict(hspace=0.22))
    ax = axes[0]; _style(ax, "Elevation along the walked path", "", "elevation (m)")
    ax.plot(s[ok], elev[ok], color=GROUND_C, lw=2)
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)

    ax = axes[1]; _style(ax, "Terrain grade along the walked path",
                         "distance walked (m)", "grade (deg)")
    ax.axhline(0, color="#383835", lw=1.2)
    ax.plot(s[ok], grade[ok], color=STRUCT_C, lw=1.6)
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    fig.suptitle(f"Ground profile -- {os.path.basename(run_dir.rstrip('/'))}",
                 color=INK, fontsize=13, x=0.06, ha="left")
    out = os.path.join(run_dir, "ground_profile.png")
    fig.savefig(out, dpi=args.dpi, facecolor=PLANE, bbox_inches="tight")
    plt.close(fig)
    return out


# --------------------------------------------------------------------------- #
# interactive 3D view
# --------------------------------------------------------------------------- #

VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { color-scheme: dark; --surface:#1a1a19; --plane:#0d0d0d; --ink:#ffffff;
          --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --ground:#3987e5;
          --struct:#d95926; --border:rgba(255,255,255,0.10); }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--plane); color:var(--ink);
              font-family:system-ui,-apple-system,"Segoe UI",sans-serif; overflow:hidden; }
  #view { position:fixed; inset:0; }
  #panel { position:fixed; top:16px; left:16px; width:280px; max-height:calc(100% - 32px);
           overflow:auto; background:rgba(26,26,25,0.92); border:1px solid var(--border);
           border-radius:10px; padding:14px 16px; backdrop-filter:blur(8px); }
  h1 { font-size:14px; margin:0 0 2px; letter-spacing:-0.01em; }
  .sub { font-size:11px; color:var(--muted); margin:0 0 12px; line-height:1.45; }
  .lbl { font-size:10px; text-transform:uppercase; letter-spacing:0.07em;
         color:var(--muted); margin:14px 0 6px; }
  .row { display:flex; gap:6px; flex-wrap:wrap; }
  button { flex:1 1 auto; background:transparent; color:var(--ink2); font-size:11px;
           font-family:inherit; border:1px solid var(--border); border-radius:6px;
           padding:6px 8px; cursor:pointer; }
  button:hover { background:rgba(255,255,255,0.06); }
  button[aria-pressed="true"] { background:var(--ground); border-color:var(--ground);
           color:#fff; }
  .chk { display:flex; align-items:center; gap:8px; font-size:12px; color:var(--ink2);
         padding:5px 0; cursor:pointer; }
  .sw { width:11px; height:11px; border-radius:3px; flex:none; }
  input[type=range] { width:100%; accent-color:var(--ground); }
  table { width:100%; border-collapse:collapse; font-size:11px; margin-top:4px; }
  td { padding:3px 0; color:var(--ink2); }
  td:last-child { text-align:right; font-variant-numeric:tabular-nums; color:var(--ink); }
  #legend { position:fixed; bottom:16px; left:16px; background:rgba(26,26,25,0.92);
            border:1px solid var(--border); border-radius:10px; padding:10px 14px;
            font-size:11px; color:var(--ink2); }
  #legend .bar { height:8px; border-radius:2px; margin:6px 0 4px; }
  #legend .ends { display:flex; justify-content:space-between;
                  font-variant-numeric:tabular-nums; color:var(--muted); }
  #hint { position:fixed; bottom:16px; right:16px; font-size:11px; color:var(--muted); }
</style></head><body>
<div id="view"></div>
<div id="panel">
  <h1>__TITLE__</h1>
  <p class="sub">__SUB__</p>
  <div class="lbl">Colour by</div>
  <div class="row" id="modes">
    <button data-mode="class" aria-pressed="true">Ground / structure</button>
    <button data-mode="above">Height above ground</button>
    <button data-mode="elev">Elevation</button>
    <button data-mode="intensity">Intensity</button>
  </div>
  <div class="lbl">Show</div>
  <label class="chk"><input type="checkbox" id="cbGround" checked>
    <span class="sw" style="background:var(--ground)"></span>Ground plane</label>
  <label class="chk"><input type="checkbox" id="cbStruct" checked>
    <span class="sw" style="background:var(--struct)"></span>Structure / obstacles</label>
  <label class="chk"><input type="checkbox" id="cbTraj" checked>
    <span class="sw" style="background:#ffffff"></span>Trajectory</label>
  <div class="lbl">Point size</div>
  <input type="range" id="size" min="0.4" max="4" step="0.1" value="1.4">
  <div class="lbl">Vertical exaggeration <span id="exLabel">1.0x</span></div>
  <input type="range" id="exag" min="1" max="8" step="0.5" value="1">
  <div class="lbl">Map</div>
  <table><tbody id="stats"></tbody></table>
</div>
<div id="legend"></div>
<div id="hint">drag to orbit · scroll to zoom · right-drag to pan</div>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
            "three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const D = __DATA__;
const b64 = s => { const r = atob(s), a = new Uint8Array(r.length);
                   for (let i=0;i<r.length;i++) a[i]=r.charCodeAt(i); return a; };
const u16 = s => new Uint16Array(b64(s).buffer);
const f32 = s => new Float32Array(b64(s).buffer);

const q = u16(D.pos), cls = b64(D.cls), above = b64(D.above), inten = b64(D.inten);
const N = cls.length;
const traj = f32(D.traj);

// de-quantise to metres, recentred so the orbit target sits in the middle of the map
const cx = (D.min[0]+D.max[0])/2, cy = (D.min[1]+D.max[1])/2, cz = (D.min[2]+D.max[2])/2;
const sc = [(D.max[0]-D.min[0])/65535, (D.max[1]-D.min[1])/65535, (D.max[2]-D.min[2])/65535];
const base = new Float32Array(N*3);
for (let i=0;i<N;i++){
  base[i*3]   = D.min[0] + q[i*3]  *sc[0] - cx;
  base[i*3+1] = D.min[2] + q[i*3+2]*sc[2] - cz;   // three.js y is up; map z -> y
  base[i*3+2] = -(D.min[1] + q[i*3+1]*sc[1] - cy);
}

const ramp = (stops, t) => {
  t = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(Math.floor(t), stops.length - 2), f = t - i;
  const a = stops[i], b = stops[i+1];
  return [a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f, a[2]+(b[2]-a[2])*f];
};
const hex = h => [parseInt(h.slice(1,3),16)/255, parseInt(h.slice(3,5),16)/255,
                  parseInt(h.slice(5,7),16)/255];
const BLUE = __BLUE__.map(hex), ORANGE = __ORANGE__.map(hex);
const GROUND = hex('#3987e5'), STRUCT = hex('#d95926');

const geo = new THREE.BufferGeometry();
const pos = new Float32Array(N*3), col = new Float32Array(N*3);
geo.setAttribute('position', new THREE.BufferAttribute(pos,3));
geo.setAttribute('color', new THREE.BufferAttribute(col,3));
const mat = new THREE.PointsMaterial({size:1.4, sizeAttenuation:false, vertexColors:true});
const cloud = new THREE.Points(geo, mat);

let mode='class', showG=true, showS=true, exag=1;
const LEG = {
  class: null,
  above: {ramp:ORANGE, lo:'0 m', hi:'2 m', title:'Height above the ground plane'},
  elev:  {ramp:BLUE,  lo:D.elevLo.toFixed(1)+' m', hi:D.elevHi.toFixed(1)+' m',
          title:'Elevation'},
  intensity: {ramp:BLUE, lo:'low', hi:'high', title:'Return intensity'},
};

function rebuild(){
  let n = 0;
  for (let i=0;i<N;i++){
    const g = cls[i]===0;
    if ((g && !showG) || (!g && !showS)) continue;
    pos[n*3]   = base[i*3];
    pos[n*3+1] = base[i*3+1]*exag;
    pos[n*3+2] = base[i*3+2];
    let c;
    if (mode==='class')          c = g ? GROUND : STRUCT;
    else if (mode==='above')     c = ramp(ORANGE, above[i]/200);
    else if (mode==='intensity') c = ramp(BLUE, inten[i]/255);
    else                         c = ramp(BLUE, (D.min[2]+q[i*3+2]*sc[2]-D.elevLo)/
                                                 Math.max(D.elevHi-D.elevLo,1e-6));
    col[n*3]=c[0]; col[n*3+1]=c[1]; col[n*3+2]=c[2];
    n++;
  }
  geo.setDrawRange(0,n);
  geo.attributes.position.needsUpdate = true;
  geo.attributes.color.needsUpdate = true;
  geo.computeBoundingSphere();
  drawLegend();
}

function drawLegend(){
  const el = document.getElementById('legend'), L = LEG[mode];
  if (!L){
    el.innerHTML = '<div style="margin-bottom:6px">Ground plane, fitted per '
      + D.cell + ' m cell</div>'
      + '<div style="display:flex;gap:14px">'
      + '<span><span class="sw" style="display:inline-block;background:var(--ground)">'
      + '</span> ground</span><span><span class="sw" style="display:inline-block;'
      + 'background:var(--struct)"></span> structure</span></div>';
    return;
  }
  const g = L.ramp.map((c,i)=>`rgb(${c.map(v=>Math.round(v*255)).join(',')}) `
            + (100*i/(L.ramp.length-1)).toFixed(0) + '%').join(',');
  el.innerHTML = `<div>${L.title}</div><div class="bar" style="width:190px;`
    + `background:linear-gradient(90deg,${g})"></div>`
    + `<div class="ends"><span>${L.lo}</span><span>${L.hi}</span></div>`;
}

const scene = new THREE.Scene();
scene.background = new THREE.Color('#0d0d0d');
scene.add(cloud);

const tg = new THREE.BufferGeometry();
const tp = new Float32Array(traj.length);
const trajLine = new THREE.Line(tg, new THREE.LineBasicMaterial({color:0xffffff}));
function rebuildTraj(){
  for (let i=0;i<traj.length/3;i++){
    tp[i*3]   = traj[i*3] - cx;
    tp[i*3+1] = (traj[i*3+2] - cz) * exag;
    tp[i*3+2] = -(traj[i*3+1] - cy);
  }
  tg.setAttribute('position', new THREE.BufferAttribute(tp,3));
  tg.attributes.position.needsUpdate = true;
}
rebuildTraj(); scene.add(trajLine);

const span = Math.max(D.max[0]-D.min[0], D.max[1]-D.min[1]);
const cam = new THREE.PerspectiveCamera(50, innerWidth/innerHeight, 0.1, span*12);
cam.position.set(0, span*0.45, span*0.75);
const rend = new THREE.WebGLRenderer({antialias:true});
rend.setPixelRatio(Math.min(devicePixelRatio,2));
rend.setSize(innerWidth, innerHeight);
document.getElementById('view').appendChild(rend.domElement);
const ctl = new OrbitControls(cam, rend.domElement);
ctl.enableDamping = true;
addEventListener('resize', ()=>{ cam.aspect=innerWidth/innerHeight;
  cam.updateProjectionMatrix(); rend.setSize(innerWidth,innerHeight); });

document.querySelectorAll('#modes button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('#modes button').forEach(o=>o.setAttribute('aria-pressed','false'));
  b.setAttribute('aria-pressed','true'); mode=b.dataset.mode; rebuild();
});
document.getElementById('cbGround').onchange = e => { showG=e.target.checked; rebuild(); };
document.getElementById('cbStruct').onchange = e => { showS=e.target.checked; rebuild(); };
document.getElementById('cbTraj').onchange = e => { trajLine.visible=e.target.checked; };
document.getElementById('size').oninput = e => { mat.size = +e.target.value; };
document.getElementById('exag').oninput = e => {
  exag = +e.target.value;
  document.getElementById('exLabel').textContent = exag.toFixed(1)+'x';
  rebuild(); rebuildTraj();
};
document.getElementById('stats').innerHTML = D.stats
  .map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');

rebuild();
rend.render(scene, cam);          // paint once immediately, before the first rAF
(function loop(){ requestAnimationFrame(loop); ctl.update(); rend.render(scene,cam); })();
</script></body></html>
"""


def make_viewer(run_dir, pts, gnd, traj, stats, args):
    """Write a self-contained three.js view of the map.

    Positions are quantised to uint16 per axis, which over a 140 m map is about
    2 mm -- far below the map's own accuracy -- and keeps the file about a third
    the size of raw float32.
    """
    xyz = pts["xyz"]
    keep = np.ones(len(xyz), bool)
    if len(xyz) > args.web_points:   # thin uniformly, preserving the ground/structure mix
        idx = np.random.default_rng(0).choice(len(xyz), args.web_points, replace=False)
        keep = np.zeros(len(xyz), bool)
        keep[idx] = True
    P = xyz[keep]
    g = gnd["is_ground"][keep]
    above = np.clip(gnd["above"][keep], 0, 2.55)
    inten = pts["intensity"][keep]

    lo, hi = P.min(axis=0), P.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    q = np.round((P - lo) / span * 65535).astype(np.uint16)

    tr = traj["standing"]
    T = np.column_stack([traj["xy"][tr, 0], traj["xy"][tr, 1], traj["elev"][tr]]
                        ).astype(np.float32)

    enc = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
    data = dict(
        pos=enc(q), cls=enc(np.where(g, 0, 1).astype(np.uint8)),
        above=enc(np.round(above * 100).astype(np.uint8)),
        inten=enc(np.clip(inten, 0, 255).astype(np.uint8)),
        traj=enc(T), min=lo.tolist(), max=hi.tolist(),
        elevLo=float(lo[2]), elevHi=float(hi[2]), cell=args.cell,
        stats=[["scans used", f"{stats['scans_used']:,}"],
               ["points kept", f"{stats['points_kept']:,}"],
               ["self-returns dropped", f"{stats['points_self']:,}"],
               [f"voxels at {args.voxel*100:.0f} cm", f"{len(xyz):,}"],
               ["shown here", f"{len(P):,}"],
               ["ground", f"{100*gnd['is_ground'].mean():.0f}%"],
               ["relief walked", f"{traj['relief']:.2f} m"],
               ["elevation repeats to", f"{traj['closure']*100:.1f} cm"]])

    name = os.path.basename(run_dir.rstrip("/"))
    html = (VIEWER_HTML
            .replace("__TITLE__", f"SLAM map {name}")
            .replace("__SUB__", "Lidar scans placed by odometry, with the ground plane "
                                "fitted per cell. Height is integrated terrain grade, "
                                "not odometry.")
            .replace("__BLUE__", json.dumps(BLUE_RAMP))
            .replace("__ORANGE__", json.dumps(ORANGE_RAMP))
            .replace("__DATA__", json.dumps(data)))
    out = os.path.join(run_dir, "slam_map.html")
    with open(out, "w") as fh:
        fh.write(html)
    return out


# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-root", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--run", default="20260920_033440")
    p.add_argument("--self-radius", type=float, default=0.8,
                   help="m; returns closer than this are the robot's own body (default: 0.8)")
    p.add_argument("--max-range", type=float, default=8.0,
                   help="m; drop returns beyond this -- past it the beam is grazing\n                        and the returns are unreliable (default: 8)")
    p.add_argument("--voxel", type=float, default=0.05,
                   help="m; downsampling voxel for the map (default: 0.05)")
    p.add_argument("--cell", type=float, default=0.4,
                   help="m; x/y cell the ground plane is fitted in (default: 0.4)")
    p.add_argument("--ground-pct", type=float, default=8.0,
                   help="percentile of z in a cell taken as the ground seed (default: 8)")
    p.add_argument("--seed-band", type=float, default=0.3,
                   help="m around the seed that feeds the plane fit (default: 0.3)")
    p.add_argument("--ground-tol", type=float, default=0.12,
                   help="m from the fitted plane still counted as ground (default: 0.12)")
    p.add_argument("--max-ground-slope", type=float, default=25.0,
                   help="deg above which a fitted plane is a wall, not ground (default: 25)")
    p.add_argument("--min-spread", type=float, default=0.15,
                   help="m; smaller principal spread a cell's points need before its "
                        "plane is trusted -- rejects single collinear arcs (default: 0.15)")
    p.add_argument("--max-seed-offset", type=float, default=0.30,
                   help="m the fitted plane may sit from the seed height before it is "
                        "rejected as a bad fit (default: 0.30)")
    p.add_argument("--min-cell-points", type=int, default=6,
                   help="points a cell needs before it is fitted (default: 6)")
    p.add_argument("--web-points", type=int, default=400000,
                   help="points kept for the interactive view (default: 400000)")
    p.add_argument("--dpi", type=int, default=140)
    p.add_argument("--check-frame", action="store_true",
                   help="re-run the frame-convention test and exit")
    p.add_argument("--check-pairs", type=int, default=80)
    p.add_argument("--no-progress", dest="progress", action="store_false")
    # shared with label_slopes so the elevation here matches slope_labels.csv
    p.add_argument("--smooth-window", type=float, default=1.5)
    p.add_argument("--walk-speed", type=float, default=0.25)
    p.add_argument("--max-tilt", type=float, default=25.0)
    p.add_argument("--revisit-radius", type=float, default=0.6)
    p.add_argument("--revisit-min-dt", type=float, default=30.0)
    args = p.parse_args(argv)

    run_dir = args.run if os.path.isdir(args.run) else os.path.join(args.data_root, args.run)
    if not os.path.isdir(run_dir):
        raise SystemExit(f"no such run directory: {run_dir}")

    od, clouds = load_run(run_dir)
    traj = trajectory(od, args)
    cal = traj["cal"]
    print(f"{os.path.basename(run_dir.rstrip('/'))}: {len(od)} odometry samples, "
          f"{len(clouds)} clouds, {traj['path_s'][-1]:.0f} m walked")
    print(f"  attitude zero point {cal.grade_bias:+.2f} deg from {cal.n_pairs} revisit pairs, "
          f"per-frame sigma {cal.sigma:.2f} deg")
    print(f"  relief {traj['relief']:.2f} m; elevation repeats to {traj['closure']*100:.1f} cm "
          f"at {traj['n_closure']} walking revisits "
          f"({100*traj['closure']/traj['relief']:.1f}% of relief)")

    if args.check_frame:
        check_frame(clouds, traj, args)
        return 0

    print("assembling...")
    pts, stats = assemble(clouds, traj, args)
    print(f"  {stats['points_raw']:,} raw points, {stats['points_self']:,} self-returns "
          f"dropped, {stats['points_kept']:,} kept -> {len(pts['xyz']):,} voxels")

    print("fitting the ground plane...")
    gnd = label_ground(pts["xyz"], args)
    ng = int(gnd["is_ground"].sum())
    print(f"  {ng:,} ground voxels ({100*ng/len(pts['xyz']):.1f}%), "
          f"{int(gnd['usable'].sum()):,} cells fitted, "
          f"median slope {np.nanmedian(gnd['slope']):.1f} deg")

    np.savez_compressed(
        os.path.join(run_dir, "slam_map.npz"),
        xyz=pts["xyz"], intensity=pts["intensity"], count=pts["count"],
        is_ground=gnd["is_ground"], above_ground=gnd["above"].astype(np.float32),
        ground_height=gnd["height"].astype(np.float32),
        ground_slope=gnd["slope"].astype(np.float32),
        ground_usable=gnd["usable"], cell=args.cell, origin=gnd["origin"],
        traj_xy=traj["xy"], traj_elev=traj["elev"], traj_standing=traj["standing"])

    for f in (make_figures(run_dir, pts, gnd, traj, stats, args),
              make_profile(run_dir, traj, args),
              make_viewer(run_dir, pts, gnd, traj, stats, args),
              os.path.join(run_dir, "slam_map.npz")):
        print(f"  wrote {f}  ({os.path.getsize(f)/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
