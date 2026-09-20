#!/usr/bin/env python3
"""Spatially de-duplicate the teleoperated Go2 image logs.

For every experiment run (one ``<timestamp>/`` directory holding ``dataset.db``,
``color/`` and ``clouds/``) this keeps a subset of the colour frames such that

  * any two kept frames were taken at least ``--min-dist`` metres apart, and
  * every dropped frame is within ``--min-dist`` of some kept frame (no gaps), and
  * whenever several frames compete for the same place -- above all during the
    long stationary stretches -- the one kept is the one recorded with the least
    camera motion, i.e. the sharpest.

The selection is greedy non-maximum suppression over frame positions, visiting
frames in order of increasing motion (``|w| + |v| / --depth-ref``). Processing the
clearest frames first is what makes a stop collapse onto its steadiest frame;
the >= min-dist test against everything already kept is what enforces the spacing.
Ties are broken by frame index, so runs are reproducible.

Clock note: odometry / IMU / point clouds carry the robot's own DDS clock, which
lags the RealSense host clock by ~282 s. The offset is estimated per run (see
``estimate_clock_offset``) and applied before anything is matched in time.

Nothing is deleted unless you ask for it: the default writes CSV manifests only.


Ok cool cool, so I also want to make a notebook that, given a particular image, it uses VLM, and segment anything to exactly target the 

Examples
--------
    python3 filter_frames.py                       # analyse, write manifests
    python3 filter_frames.py --action symlink      # + build filtered/ trees
    python3 filter_frames.py --refine-sharpness    # decode images to pick best
    python3 filter_frames.py --min-dist 2.0 --plot
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass

import numpy as np

# --------------------------------------------------------------------------- #
# clock alignment
# --------------------------------------------------------------------------- #

def _imu(con: sqlite3.Connection, source: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (seconds, |angular rate|) for one IMU source, time-ordered."""
    rows = con.execute(
        "SELECT stamp_ns, wx, wy, wz FROM imu_samples WHERE source=? ORDER BY stamp_ns",
        (source,),
    ).fetchall()
    a = np.asarray(rows, dtype=float)
    if a.size == 0:
        return np.empty(0), np.empty(0)
    return a[:, 0] / 1e9, np.linalg.norm(a[:, 1:4], axis=1)


def estimate_clock_offset(con: sqlite3.Connection, mode: str = "auto") -> tuple[float, str]:
    """Seconds to add to robot-clock stamps to put them on the camera clock.

    The two IMUs (``utlidar`` on the robot clock, ``realsense`` on the host clock)
    observe the same rotations, so the lag between them is the clock offset. A
    first-sample difference gets within ~0.1 s; cross-correlating the angular-rate
    magnitudes refines it. The refinement is rejected if it disagrees with the
    coarse estimate by more than 2 s, which would mean the correlation locked onto
    a spurious peak.
    """
    if mode == "none":
        return 0.0, "disabled"
    try:
        return float(mode), "user"
    except ValueError:
        pass

    lt, lw = _imu(con, "utlidar")
    rt, rw = _imu(con, "realsense")
    if lt.size == 0 or rt.size == 0:
        return 0.0, "no IMU data"
    naive = float(rt[0] - lt[0])
    if mode == "naive":
        return naive, "first-sample"

    dt = 0.01
    t0, t1 = max(lt[0] + naive, rt[0]), min(lt[-1] + naive, rt[-1])
    if t1 - t0 < 30.0:
        return naive, "first-sample (overlap too short to refine)"
    grid = np.arange(t0, t1, dt)
    a = np.interp(grid, lt + naive, lw)
    b = np.interp(grid, rt, rw)
    a -= a.mean()
    b -= b.mean()
    corr = np.correlate(b, a, mode="full")
    lags = np.arange(-len(a) + 1, len(b))
    keep = np.abs(lags) <= int(2.0 / dt)
    residual = float(lags[keep][np.argmax(corr[keep])] * dt)
    return naive + residual, f"IMU cross-correlation (first-sample {naive:.3f} s {residual:+.3f} s)"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

@dataclass
class Frames:
    """Per-colour-frame table, all arrays parallel and time-ordered."""
    index: np.ndarray        # 1-based frame number from the database
    t: np.ndarray            # camera-clock seconds
    path: list[str]          # absolute local path
    pos: np.ndarray          # (N, 3) odometry position, metres
    yaw: np.ndarray          # radians
    speed: np.ndarray        # |linear velocity| m/s, averaged over the window
    omega: np.ndarray        # |angular velocity| rad/s, averaged over the window
    valid: np.ndarray        # bool: pose could be interpolated
    cmd: np.ndarray          # (N, 3) last teleop velocity command, NaN if none


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _window_mean(src_t: np.ndarray, values: np.ndarray, at: np.ndarray, half: float) -> np.ndarray:
    """Mean of ``values`` over [t-half, t+half]; nearest sample if the window is empty."""
    lo = np.searchsorted(src_t, at - half)
    hi = np.searchsorted(src_t, at + half)
    out = np.empty(at.shape, dtype=float)
    for i, (a, b) in enumerate(zip(lo, hi)):
        if b > a:
            out[i] = values[a:b].mean()
        else:
            j = min(max(a, 0), len(values) - 1)
            out[i] = values[j]
    return out


def _yaw_from_quat(qx, qy, qz, qw):
    return np.arctan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy ** 2 + qz ** 2))


def load_frames(con: sqlite3.Connection, run_dir: str, offset: float, args) -> Frames:
    odom = np.asarray(
        con.execute(
            "SELECT stamp_ns, px, py, pz, qx, qy, qz, qw, vx, vy, vz, wx, wy, wz "
            "FROM odom_samples ORDER BY stamp_ns"
        ).fetchall(),
        dtype=float,
    )
    if odom.size == 0:
        raise RuntimeError("odom_samples is empty")
    ot = odom[:, 0] / 1e9 + offset
    opos, oquat = odom[:, 1:4], odom[:, 4:8]
    olin, oang = odom[:, 8:11], odom[:, 11:14]

    rows = con.execute("SELECT stamp_ns, path FROM color_frames ORDER BY stamp_ns").fetchall()
    ct = np.asarray([r[0] for r in rows], dtype=float) / 1e9
    paths = [os.path.join(run_dir, "color", os.path.basename(r[1])) for r in rows]
    index = np.arange(1, len(rows) + 1)

    # position by linear interpolation; orientation from the nearest sample (20 Hz,
    # so slerp would buy nothing). Frames whose nearest odometry sample is further
    # away than --max-pose-gap, or that fall outside odometry coverage, get no pose.
    pos = np.column_stack([np.interp(ct, ot, opos[:, k]) for k in range(3)])
    near = np.clip(np.searchsorted(ot, ct), 0, len(ot) - 1)
    near = np.where(
        (near > 0) & (np.abs(ot[near - 1] - ct) < np.abs(ot[np.minimum(near, len(ot) - 1)] - ct)),
        near - 1,
        near,
    )
    gap = np.abs(ot[near] - ct)
    valid = (gap <= args.max_pose_gap) & (ct >= ot[0]) & (ct <= ot[-1])
    yaw = _yaw_from_quat(*(oquat[near, k] for k in range(4)))

    half = args.vel_window / 2.0
    src = args.score_source
    if src in ("sport", "blend") and not _table_exists(con, "sport_mode_state"):
        src = "odom"
    if src == "sport":
        sms = np.asarray(
            con.execute(
                "SELECT stamp_ns, vx, vy, vz, yaw_speed FROM sport_mode_state ORDER BY stamp_ns"
            ).fetchall(),
            dtype=float,
        )
        st = sms[:, 0] / 1e9 + offset
        speed = _window_mean(st, np.linalg.norm(sms[:, 1:3], axis=1), ct, half)
        omega = _window_mean(st, np.abs(sms[:, 4]), ct, half)
    else:
        speed = _window_mean(ot, np.linalg.norm(olin[:, :2], axis=1), ct, half)
        if src == "camera-imu":
            rt, rw = _imu(con, "realsense")      # co-located with the camera, no offset
            omega = _window_mean(rt, rw, ct, half) if rt.size else _window_mean(
                ot, np.linalg.norm(oang, axis=1), ct, half)
        else:
            omega = _window_mean(ot, np.linalg.norm(oang, axis=1), ct, half)

    cmd = np.full((len(ct), 3), np.nan)
    if _table_exists(con, "sport_requests"):
        reqs = con.execute(
            "SELECT stamp_ns, parameter FROM sport_requests WHERE api_id=1008 ORDER BY stamp_ns"
        ).fetchall()
        if reqs:
            rt = np.asarray([r[0] for r in reqs], dtype=float) / 1e9 + offset
            rv = np.zeros((len(reqs), 3))
            for i, (_, param) in enumerate(reqs):
                try:
                    p = json.loads(param)
                    rv[i] = (p.get("x", 0.0), p.get("y", 0.0), p.get("z", 0.0))
                except (json.JSONDecodeError, TypeError):
                    rv[i] = np.nan
            rv[np.abs(rv) < 1e-30] = 0.0        # denormal floats stand in for exact 0
            j = np.searchsorted(rt, ct, side="right") - 1
            ok = j >= 0
            cmd[ok] = rv[j[ok]]
            # The teleop app only publishes while the stick is deflected, so a command
            # older than --cmd-stale means the operator let go: the robot was told to
            # stop, not to keep the last velocity.
            stale = np.zeros(len(ct), dtype=bool)
            stale[ok] = (ct[ok] - rt[j[ok]]) > args.cmd_stale
            cmd[stale] = 0.0

    return Frames(index, ct, paths, pos, yaw, speed, omega, valid, cmd)


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #

def select(pos: np.ndarray, yaw: np.ndarray, score: np.ndarray, order: np.ndarray,
           min_dist: float, yaw_thresh: float | None) -> tuple[np.ndarray, np.ndarray]:
    """Greedy NMS: keep frames clearest-first, suppressing anything too close.

    ``order`` lists candidate frames best-first. Returns (kept indices into the
    candidate arrays, suppressor index per frame or -1). Two frames conflict when
    they are within ``min_dist`` -- and, if ``yaw_thresh`` is given, also pointing
    within that many radians of each other, so a second pass through the same spot
    facing elsewhere is kept as a genuinely different view.
    """
    from scipy.spatial import cKDTree

    tree = cKDTree(pos)
    neighbours = tree.query_ball_point(pos, r=min_dist)

    suppressor = np.full(len(pos), -1, dtype=np.int64)
    taken = np.zeros(len(pos), dtype=bool)
    kept: list[int] = []
    for i in order:
        if suppressor[i] != -1:
            continue
        kept.append(int(i))
        taken[i] = True
        for j in neighbours[i]:
            if j == i or suppressor[j] != -1 or taken[j]:
                continue
            if yaw_thresh is not None:
                d = abs(np.arctan2(np.sin(yaw[j] - yaw[i]), np.cos(yaw[j] - yaw[i])))
                if d > yaw_thresh:
                    continue
            suppressor[j] = i
    return np.asarray(sorted(kept), dtype=np.int64), suppressor


def _sharpness(path: str) -> float:
    """Variance of the Laplacian on a 1/4-scale grey decode (JPEG draft mode)."""
    from PIL import Image

    with Image.open(path) as im:
        im.draft("L", (320, 180))
        a = np.asarray(im.convert("L"), dtype=float)
    lap = a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4.0 * a[1:-1, 1:-1]
    return float(lap.var())


def refine_with_sharpness(frames: Frames, cand: np.ndarray, kept: np.ndarray,
                          suppressor: np.ndarray, score: np.ndarray, pos: np.ndarray,
                          yaw: np.ndarray, min_dist: float, yaw_thresh: float | None,
                          topk: int) -> np.ndarray:
    """Swap each kept frame for the measured-sharpest of its steadiest neighbours.

    Standing still, the velocity signal is pure noise -- it cannot tell one frame of
    a 40 s stop from another -- so the frame that wins on motion score alone lands
    around the median sharpness of its stop. Measuring instead lifts that to the
    ~95th percentile. Laplacian variance also tracks scene texture, so it is only
    ever compared inside one suppression group, where the view is the same. Only the
    ``topk`` lowest-motion members are decoded; a frame recorded mid-stride is not
    going to win. A swap is taken only if the replacement still clears ``min_dist``
    against every other kept frame, so the spacing guarantee survives refinement.
    """
    groups: dict[int, list[int]] = {int(k): [int(k)] for k in kept}
    for j, s in enumerate(suppressor):
        if s != -1 and s in groups:
            groups[int(s)].append(j)

    current = {int(k): int(k) for k in kept}
    for k in kept:
        k = int(k)
        members = np.asarray(groups[k])
        members = members[np.argsort(score[members], kind="stable")][:topk]
        if len(members) == 1:
            continue
        sharp = np.asarray([_sharpness(frames.path[cand[m]]) for m in members])
        others = np.asarray([v for key, v in current.items() if key != k])
        for m in members[np.argsort(-sharp, kind="stable")]:
            d = np.linalg.norm(pos[others] - pos[m], axis=1)
            clash = d < min_dist
            if yaw_thresh is not None and clash.any():
                dy = np.abs(np.arctan2(np.sin(yaw[others] - yaw[m]),
                                       np.cos(yaw[others] - yaw[m])))
                clash &= dy <= yaw_thresh
            if not clash.any():
                current[k] = int(m)
                break
    return np.asarray(sorted(current.values()), dtype=np.int64)


def match_clouds(con: sqlite3.Connection, offset: float, at: np.ndarray,
                 run_dir: str, max_dt: float) -> list[str]:
    """Nearest-in-time point cloud for each timestamp, '' when none is close enough."""
    rows = con.execute("SELECT stamp_ns, path FROM clouds ORDER BY stamp_ns").fetchall()
    if not rows:
        return [""] * len(at)
    ct = np.asarray([r[0] for r in rows], dtype=float) / 1e9 + offset
    j = np.clip(np.searchsorted(ct, at), 0, len(ct) - 1)
    j = np.where((j > 0) & (np.abs(ct[j - 1] - at) < np.abs(ct[j] - at)), j - 1, j)
    return [
        os.path.join(run_dir, "clouds", os.path.basename(rows[int(k)][1]))
        if abs(ct[int(k)] - t) <= max_dt else ""
        for k, t in zip(j, at)
    ]


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #

MANIFEST_COLS = [
    "run", "frame_index", "kept", "drop_reason", "stamp_ns", "t_rel_s",
    "image", "cloud", "x", "y", "z", "yaw_deg",
    "speed_mps", "omega_radps", "motion_score", "stationary",
    "cmd_vx", "cmd_vy", "cmd_wz", "suppressed_by",
]


def write_manifest(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLS)
        w.writeheader()
        w.writerows(rows)


def materialise(rows: list[dict], out_dir: str, action: str) -> None:
    """Place the kept frames (and their clouds) under ``out_dir`` -- or delete the rest.

    ``out_dir`` is always per-run: frame numbering restarts in every experiment, so
    colour_000001.jpg exists three times over and a shared destination would have the
    runs overwrite each other. A kept-only manifest is written alongside so the folder
    describes itself -- pose, velocities and the original path of every file in it.
    """
    kept = [r for r in rows if r["kept"]]
    if action == "delete":
        for r in rows:
            if r["kept"]:
                continue
            for p in (r["image"],):
                if p and os.path.exists(p):
                    os.remove(p)
        return

    for sub in ("color", "clouds"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    for r in kept:
        for p, sub in ((r["image"], "color"), (r["cloud"], "clouds")):
            if not p:
                continue
            dst = os.path.join(out_dir, sub, os.path.basename(p))
            if os.path.lexists(dst):
                os.remove(dst)
            if action == "symlink":
                os.symlink(os.path.abspath(p), dst)
            elif action == "copy":
                shutil.copy2(p, dst)
            elif action == "move":
                shutil.move(p, dst)
    write_manifest(os.path.join(out_dir, "kept_frames.csv"), kept)


def plot_run(out_png: str, frames: Frames, cand: np.ndarray, kept_global: np.ndarray, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 8))
    ax.plot(frames.pos[cand, 0], frames.pos[cand, 1], "-", color="0.8", lw=1, label="trajectory")
    ax.scatter(frames.pos[cand, 0], frames.pos[cand, 1], s=3, c=frames.speed[cand],
               cmap="viridis", label="all frames")
    ax.scatter(frames.pos[kept_global, 0], frames.pos[kept_global, 1], s=26,
               facecolors="none", edgecolors="crimson", lw=1.1, label="kept")
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def process_run(run_dir: str, args) -> list[dict]:
    name = os.path.basename(run_dir.rstrip("/"))
    db = os.path.join(run_dir, "dataset.db")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        offset, how = estimate_clock_offset(con, args.clock_offset)
        frames = load_frames(con, run_dir, offset, args)

        cand = np.flatnonzero(frames.valid)
        score = frames.omega + frames.speed / args.depth_ref
        dims = 2 if args.dist_mode == "2d" else 3
        pos = frames.pos[cand, :dims]
        order = cand_order = np.argsort(score[cand], kind="stable")
        yaw_thresh = np.deg2rad(args.yaw_thresh) if args.yaw_thresh is not None else None

        kept_local, suppressor = select(pos, frames.yaw[cand], score[cand], order,
                                        args.min_dist, yaw_thresh)
        if args.refine_sharpness:
            kept_local = refine_with_sharpness(frames, cand, kept_local, suppressor,
                                               score[cand], pos, frames.yaw[cand],
                                               args.min_dist, yaw_thresh, args.refine_topk)
        kept_global = cand[kept_local]

        clouds = match_clouds(con, offset, frames.t, run_dir, args.max_cloud_dt)
    finally:
        con.close()

    keep_mask = np.zeros(len(frames.t), dtype=bool)
    keep_mask[kept_global] = True
    sup_global = np.full(len(frames.t), -1, dtype=np.int64)
    sup_global[cand] = np.where(suppressor >= 0, cand[np.maximum(suppressor, 0)], -1)

    still = (frames.speed < args.still_speed) & (frames.omega < args.still_omega)
    t0 = frames.t[0]
    rows = []
    for i in range(len(frames.t)):
        if not frames.valid[i]:
            reason = "no_pose"
        elif keep_mask[i]:
            reason = ""
        else:
            reason = "within_min_dist"
        rows.append({
            "run": name,
            "frame_index": int(frames.index[i]),
            "kept": bool(keep_mask[i]),
            "drop_reason": reason,
            "stamp_ns": int(round(frames.t[i] * 1e9)),
            "t_rel_s": round(float(frames.t[i] - t0), 3),
            "image": frames.path[i],
            "cloud": clouds[i] if keep_mask[i] else "",
            "x": round(float(frames.pos[i, 0]), 4),
            "y": round(float(frames.pos[i, 1]), 4),
            "z": round(float(frames.pos[i, 2]), 4),
            "yaw_deg": round(float(np.rad2deg(frames.yaw[i])), 2),
            "speed_mps": round(float(frames.speed[i]), 4),
            "omega_radps": round(float(frames.omega[i]), 4),
            "motion_score": round(float(score[i]), 5),
            "stationary": bool(still[i]),
            "cmd_vx": "" if np.isnan(frames.cmd[i, 0]) else round(float(frames.cmd[i, 0]), 4),
            "cmd_vy": "" if np.isnan(frames.cmd[i, 1]) else round(float(frames.cmd[i, 1]), 4),
            "cmd_wz": "" if np.isnan(frames.cmd[i, 2]) else round(float(frames.cmd[i, 2]), 4),
            "suppressed_by": ("" if keep_mask[i] or sup_global[i] < 0
                              else int(frames.index[sup_global[i]])),
        })

    # summary
    path_len = float(np.linalg.norm(np.diff(frames.pos[cand, :2], axis=0), axis=1).sum())
    n_kept = int(keep_mask.sum())
    kept_pos = frames.pos[kept_global, :dims]
    if n_kept > 1:
        from scipy.spatial import cKDTree
        d, _ = cKDTree(kept_pos).query(kept_pos, k=2)
        nn = d[:, 1]
        sep = f"min {nn.min():.3f} m, median {np.median(nn):.2f} m"
        if yaw_thresh is not None:
            sep += f" (heading-aware: closer pairs face >{args.yaw_thresh:g} deg apart)"
    else:
        sep = "n/a"
    print(f"[{name}]")
    print(f"  clock offset      {offset:+.3f} s  ({how})")
    print(f"  frames            {len(frames.t)} colour, {len(cand)} with pose"
          f"{'' if len(cand) == len(frames.t) else f', {len(frames.t) - len(cand)} unposed (dropped)'}")
    print(f"  trajectory        {path_len:.1f} m over {frames.t[-1] - frames.t[0]:.0f} s"
          f"  ({(frames.speed[cand] < args.still_speed).mean():.0%} of frames stationary)")
    print(f"  kept              {n_kept}  ({n_kept / max(len(frames.t), 1):.1%} of frames)")
    print(f"  spacing of kept   {sep}")
    rot = sup_global[(sup_global >= 0)]
    src = np.flatnonzero(sup_global >= 0)
    if len(src):
        dyaw = np.abs(np.arctan2(np.sin(frames.yaw[src] - frames.yaw[rot]),
                                 np.cos(frames.yaw[src] - frames.yaw[rot])))
        close = np.linalg.norm(frames.pos[src, :2] - frames.pos[rot, :2], axis=1) < 0.5
        turned = int((close & (dyaw > np.pi / 2)).sum())
        if turned:
            print(f"  turned-in-place   {turned} frames dropped at a spot already kept but "
                  f"facing >90 deg away\n                    (pass --yaw-thresh 60 to keep those "
                  f"as separate views)")
    print(f"  motion of kept    |v| median {np.median(frames.speed[kept_global]):.3f} m/s,"
          f" |w| median {np.median(frames.omega[kept_global]):.3f} rad/s"
          f"   (all frames: {np.median(frames.speed[cand]):.3f} / {np.median(frames.omega[cand]):.3f})")
    missing_cloud = sum(1 for r in rows if r["kept"] and not r["cloud"])
    if missing_cloud:
        print(f"  note              {missing_cloud} kept frames have no cloud within {args.max_cloud_dt}s")

    if args.plot:
        png = os.path.join(run_dir, "filter_preview.png")
        plot_run(png, frames, cand, kept_global,
                 f"{name}: {n_kept} kept of {len(frames.t)} (min-dist {args.min_dist} m)")
        print(f"  preview           {png}")

    out_csv = os.path.join(run_dir, args.manifest_name)
    write_manifest(out_csv, rows)
    print(f"  manifest          {out_csv}")

    if args.action != "none":
        out_dir = (os.path.join(args.out_dir, name) if args.out_dir
                   else os.path.join(run_dir, "filtered"))
        materialise(rows, out_dir, args.action)
        print(f"  {args.action:<17} {'removed ' + str(len(rows) - n_kept) + ' images' if args.action == 'delete' else out_dir}")
    return rows


def find_runs(root: str) -> list[str]:
    return sorted(
        os.path.join(root, d)
        for d in os.listdir(root)
        if os.path.isfile(os.path.join(root, d, "dataset.db"))
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-root", default=os.path.dirname(os.path.abspath(__file__)),
                   help="directory holding the per-run folders (default: this script's dir)")
    p.add_argument("--runs", nargs="*", default=None,
                   help="run directory names to process (default: all)")
    p.add_argument("--min-dist", type=float, default=1.0,
                   help="minimum separation between kept frames, metres (default: 1.0)")
    p.add_argument("--dist-mode", choices=("2d", "3d"), default="2d",
                   help="measure separation in the ground plane or in 3D (default: 2d; "
                        "the body bobs vertically while walking, which 3D would count)")
    p.add_argument("--yaw-thresh", type=float, default=None,
                   help="if set, two frames only conflict when also within this many "
                        "degrees of heading -- keeps re-visits that look elsewhere")
    p.add_argument("--score-source", choices=("odom", "sport", "camera-imu", "blend"),
                   default="odom",
                   help="velocities used to rank clarity: odometry (all runs), "
                        "sportmodestate, or the camera IMU for angular rate (default: odom)")
    p.add_argument("--depth-ref", type=float, default=5.0,
                   help="metres; converts linear speed into an equivalent angular rate "
                        "for the motion score, score = |w| + |v|/depth_ref (default: 5.0)")
    p.add_argument("--vel-window", type=float, default=0.12,
                   help="seconds of velocity averaged around each frame (default: 0.12)")
    p.add_argument("--max-pose-gap", type=float, default=0.5,
                   help="drop frames whose nearest odometry sample is further than this (s)")
    p.add_argument("--cmd-stale", type=float, default=0.5,
                   help="a teleop velocity command older than this is reported as a stop (s)")
    p.add_argument("--max-cloud-dt", type=float, default=0.2,
                   help="largest time difference accepted when pairing a cloud (s)")
    p.add_argument("--still-speed", type=float, default=0.05,
                   help="m/s below which a frame counts as stationary in the report")
    p.add_argument("--still-omega", type=float, default=0.05,
                   help="rad/s below which a frame counts as stationary in the report")
    p.add_argument("--refine-sharpness", action=argparse.BooleanOptionalAction, default=True,
                   help="decode the steadiest candidates of each group and keep the one "
                        "measured sharpest; the velocity signal cannot rank frames within "
                        "a stop, so this is what makes stationary picks clear (default: on, "
                        "costs a few seconds per run)")
    p.add_argument("--refine-topk", type=int, default=40,
                   help="candidates decoded per group when refining (default: 40)")
    p.add_argument("--clock-offset", default="auto",
                   help="'auto' (IMU cross-correlation), 'naive', 'none', or seconds")
    p.add_argument("--action", choices=("none", "symlink", "copy", "move", "delete"),
                   default="none",
                   help="what to do with the results (default: none -- manifest only)")
    p.add_argument("--out-dir", default=None,
                   help="root for symlink/copy/move; each run gets its own <root>/<run>/ "
                        "subfolder (default: <run>/filtered)")
    p.add_argument("--manifest-name", default="filter_manifest.csv")
    p.add_argument("--summary", default=None,
                   help="also write one combined manifest here")
    p.add_argument("--plot", action="store_true",
                   help="write a top-down preview PNG per run")
    p.add_argument("--yes", action="store_true",
                   help="skip the confirmation prompt for --action delete/move")
    args = p.parse_args(argv)

    runs = find_runs(args.data_root)
    if args.runs:
        wanted = set(args.runs)
        runs = [r for r in runs if os.path.basename(r) in wanted]
        missing = wanted - {os.path.basename(r) for r in runs}
        if missing:
            p.error(f"no dataset.db for run(s): {', '.join(sorted(missing))}")
    if not runs:
        p.error(f"no runs with a dataset.db under {args.data_root}")

    if args.action in ("delete", "move") and not args.yes:
        what = "DELETE the dropped images" if args.action == "delete" else "MOVE the kept files"
        print(f"About to {what} in {len(runs)} run(s):")
        for r in runs:
            print(f"  {r}")
        if input("This modifies the original data. Type 'yes' to continue: ").strip() != "yes":
            print("aborted")
            return 1

    all_rows = []
    for run in runs:
        all_rows += process_run(run, args)
        print()

    kept = sum(r["kept"] for r in all_rows)
    print(f"total: kept {kept} of {len(all_rows)} frames "
          f"({kept / max(len(all_rows), 1):.1%}) across {len(runs)} run(s)")
    if args.summary:
        write_manifest(args.summary, all_rows)
        print(f"combined manifest: {args.summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
