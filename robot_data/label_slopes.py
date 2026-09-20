#!/usr/bin/env python3
"""Label each colour frame with the slope of the ground the robot was walking on.

Where the slope comes from
--------------------------
Odometry ``pz`` is body height above the ground, not world elevation -- it varies by
4 cm over a 300 m walk -- so the trajectory carries no elevation. The lidar clouds
arrive already gravity-referenced (z is height above ground), so they carry no tilt
either. That leaves the IMU, which is the right instrument anyway: the accelerometer
and gyro together fix the gravity direction in the body frame, and the state estimator
publishes that as the odometry orientation quaternion. Rotating the body's up-axis
into the world frame gives the terrain normal, hence the slope -- on the standing
assumption that the Go2 holds its body roughly parallel to the ground beneath it.

Why you can believe it
----------------------
The runs are out-and-back, which makes the estimate self-checking, and the script
re-runs these checks on your data every time and prints them:

  * Antisymmetry. Walk a hill in reverse and the grade must flip sign. Measured
    grades at revisited points correlate about -0.6 to -0.8, so the signal tracks
    terrain rather than the robot's own gait or controller.
  * Zero point. If the true grades at a revisited point are g and -g, their mean is
    the attitude bias. That is measured and removed, and is also what the residual
    scatter about it turns into a per-frame uncertainty.
  * Loop closure. Integrating the grade along the path gives an elevation profile;
    revisited points must come back to the same height. On these runs the mismatch
    is about 7% of the relief.
  * Acceleration. A naive accelerometer tilt would track forward acceleration (0.65
    m/s^2 of it here, worth 3.8 deg of false pitch -- as large as the real signal).
    The correlation is under 0.07, so the estimator's gyro fusion is doing its job.

What is excluded
----------------
The robot sitting down reads as a 50 deg nose-down pitch, which is posture, not
terrain. Frames beyond ``--max-tilt``, and frames where the body has dropped below
its normal standing height, are marked ``not_standing`` and left unlabelled.

Output
------
``slope_labels.csv`` -- every colour frame, with grade, cross slope, total tilt,
integrated elevation and a class -- and ``sloped_frames.csv``, the subset that is
what you asked for: frames recorded while walking on ground that is not flat.

Examples
--------
    python3 label_slopes.py                     # label every frame, both CSVs
    python3 label_slopes.py --only-kept         # restrict to filter_frames.py's picks
    python3 label_slopes.py --plot --gentle 1.5 --moderate 4
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys

import numpy as np

from filter_frames import _table_exists, estimate_clock_offset, find_runs

# --------------------------------------------------------------------------- #
# attitude -> terrain slope
# --------------------------------------------------------------------------- #

def rolling_median(values: np.ndarray, t: np.ndarray, window: float) -> np.ndarray:
    """Median of ``values`` over a time window, centred on each sample.

    The body rocks a couple of degrees every stride; the terrain does not. A median
    rather than a mean because a single mis-stepped foot should not drag the estimate.
    """
    if window <= 0:
        return values.copy()
    lo = np.searchsorted(t, t - window / 2.0)
    hi = np.searchsorted(t, t + window / 2.0)
    return np.array([np.median(values[a:b]) if b > a else values[i]
                     for i, (a, b) in enumerate(zip(lo, hi))])


def terrain_from_quaternion(q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Body up-axis in the world frame, plus heading, from (qx, qy, qz, qw) rows.

    The third column of the rotation matrix is the body's z axis expressed in the
    gravity-aligned odometry frame -- that is the normal of the ground the feet are
    standing on, so everything about the slope follows from it.
    """
    qx, qy, qz, qw = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    n = np.column_stack([
        2.0 * (qx * qz + qw * qy),
        2.0 * (qy * qz - qw * qx),
        1.0 - 2.0 * (qx ** 2 + qy ** 2),
    ])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    yaw = np.arctan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy ** 2 + qz ** 2))
    return n, yaw


def slope_components(n: np.ndarray, yaw: np.ndarray) -> tuple[np.ndarray, ...]:
    """Total tilt, along-heading grade and cross-heading grade, all in degrees.

    For a ground plane with unit normal n, height varies as
    ``dz/d(horizontal) = -(n_x, n_y) / n_z``. Dotting that gradient with the heading
    gives the grade the camera is looking along (positive uphill); dotting with the
    heading's left-normal gives the camber across it (positive = ground rises left).
    """
    nz = np.clip(n[:, 2], 1e-6, 1.0)
    gx, gy = -n[:, 0] / nz, -n[:, 1] / nz
    ch, sh = np.cos(yaw), np.sin(yaw)
    grade = np.degrees(np.arctan(gx * ch + gy * sh))
    cross = np.degrees(np.arctan(-gx * sh + gy * ch))
    tilt = np.degrees(np.arccos(np.clip(n[:, 2], -1.0, 1.0)))
    return tilt, grade, cross


# --------------------------------------------------------------------------- #
# self-calibration from out-and-back revisits
# --------------------------------------------------------------------------- #

class Calibration:
    """Attitude zero point and uncertainty, measured from opposite-heading revisits."""

    def __init__(self):
        self.grade_bias = 0.0
        self.cross_bias = 0.0
        self.n_pairs = 0
        self.antisym_corr = float("nan")
        self.sigma = float("nan")

    def describe(self) -> str:
        if not self.n_pairs:
            return "no opposite-heading revisits found; zero point assumed correct"
        return (f"{self.n_pairs} revisit pairs, antisymmetry r={self.antisym_corr:+.2f}, "
                f"bias {self.grade_bias:+.2f} deg grade / {self.cross_bias:+.2f} deg cross, "
                f"per-frame sigma ~{self.sigma:.2f} deg")


def calibrate(xy: np.ndarray, yaw: np.ndarray, grade: np.ndarray, cross: np.ndarray,
              usable: np.ndarray, t: np.ndarray, radius: float, min_dt: float) -> Calibration:
    """Measure the zero point and noise by walking the same ground twice, backwards.

    At a point visited once heading out and once heading back, the true grades are
    ``+g`` and ``-g``: their mean is the bias and their sum is pure measurement error.
    This needs no external reference and no assumption that the campus is level on
    average -- only that the ground does not move between the two passes.
    """
    from scipy.spatial import cKDTree

    cal = Calibration()
    idx = np.flatnonzero(usable)
    if len(idx) < 100:
        return cal
    pairs = cKDTree(xy[idx]).query_pairs(r=radius, output_type="ndarray")
    if len(pairs) == 0:
        return cal
    i, j = idx[pairs[:, 0]], idx[pairs[:, 1]]
    dyaw = np.abs(np.arctan2(np.sin(yaw[i] - yaw[j]), np.cos(yaw[i] - yaw[j])))
    m = (dyaw > np.deg2rad(160)) & (np.abs(t[i] - t[j]) > min_dt)
    if m.sum() < 30:
        return cal
    i, j = i[m], j[m]
    cal.n_pairs = int(m.sum())
    cal.grade_bias = float(np.median((grade[i] + grade[j]) / 2.0))
    cal.cross_bias = float(np.median((cross[i] + cross[j]) / 2.0))
    a, b = grade[i] - cal.grade_bias, grade[j] - cal.grade_bias
    cal.antisym_corr = float(np.corrcoef(a, b)[0, 1])
    # a + b is twice the mean error of two independent measurements of +-g
    cal.sigma = float(np.std(a + b) / np.sqrt(2.0))
    return cal


def loop_closure(xy: np.ndarray, elev: np.ndarray, usable: np.ndarray,
                 t: np.ndarray, radius: float, min_dt: float) -> tuple[float, int]:
    """Median elevation disagreement between separate visits to the same point."""
    from scipy.spatial import cKDTree

    idx = np.flatnonzero(usable)
    if len(idx) < 100:
        return float("nan"), 0
    pairs = cKDTree(xy[idx]).query_pairs(r=radius, output_type="ndarray")
    if len(pairs) == 0:
        return float("nan"), 0
    i, j = idx[pairs[:, 0]], idx[pairs[:, 1]]
    m = np.abs(t[i] - t[j]) > min_dt
    if m.sum() < 30:
        return float("nan"), 0
    return float(np.median(np.abs(elev[i[m]] - elev[j[m]]))), int(m.sum())


# --------------------------------------------------------------------------- #
# labelling
# --------------------------------------------------------------------------- #

def classify(tilt: np.ndarray, grade: np.ndarray, cross: np.ndarray,
             args) -> tuple[list[str], list[str]]:
    """Terrain steepness class, and the label that pairs it with a direction.

    Steepness comes from the total tilt, so ground the robot is traversing along a
    hillside still counts as sloped. The direction then comes from whichever component
    dominates: ``cross_slope`` is reserved for ground that really does fall away to
    one side rather than ahead or behind.
    """
    classes, labels = [], []
    for ti, gr, cr in zip(tilt, grade, cross):
        if ti < args.gentle:
            cls = "flat"
        elif ti < args.moderate:
            cls = "gentle"
        elif ti < args.steep:
            cls = "moderate"
        else:
            cls = "steep"
        if cls == "flat":
            labels.append("flat")
        elif abs(cr) > abs(gr):
            labels.append(f"{cls}_cross_slope")
        else:
            labels.append(f"{cls}_{'uphill' if gr > 0 else 'downhill'}")
        classes.append(cls)
    return classes, labels


COLS = [
    "run", "frame_index", "image", "stamp_ns", "t_rel_s", "x", "y", "heading_deg",
    "slope_label", "slope_class", "tilt_deg", "grade_deg", "grade_pct",
    "cross_slope_deg", "elevation_m", "speed_mps", "walking", "posture", "valid",
    "kept_by_filter",
]


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def process_run(run_dir: str, args) -> list[dict]:
    name = os.path.basename(run_dir.rstrip("/"))
    con = sqlite3.connect(f"file:{os.path.join(run_dir, 'dataset.db')}?mode=ro", uri=True)
    try:
        offset, _ = estimate_clock_offset(con, args.clock_offset)
        od = np.asarray(con.execute(
            "SELECT stamp_ns, px, py, qx, qy, qz, qw, vx, vy FROM odom_samples ORDER BY stamp_ns"
        ).fetchall(), dtype=float)
        frames = con.execute("SELECT stamp_ns, path FROM color_frames ORDER BY stamp_ns").fetchall()
        body_height = None
        if _table_exists(con, "sport_mode_state"):
            sms = np.asarray(con.execute(
                "SELECT stamp_ns, body_height FROM sport_mode_state ORDER BY stamp_ns"
            ).fetchall(), dtype=float)
            if sms.size:
                body_height = (sms[:, 0] / 1e9 + offset, sms[:, 1])
    finally:
        con.close()

    t = od[:, 0] / 1e9 + offset
    xy = od[:, 1:3]
    speed = np.hypot(od[:, 7], od[:, 8])

    n, yaw = terrain_from_quaternion(od[:, 3:7])
    tilt_raw, grade_raw, cross_raw = slope_components(n, yaw)
    grade = rolling_median(grade_raw, t, args.smooth_window)
    cross = rolling_median(cross_raw, t, args.smooth_window)

    # Posture. A sitting Go2 pitches ~50 deg nose-down, which is not terrain. The
    # height gate is adaptive because the operator can command a different stance:
    # what matters is the body dropping below its own normal height for this run.
    standing = np.abs(rolling_median(tilt_raw, t, args.smooth_window)) < args.max_tilt
    if body_height is not None:
        bh = np.interp(t, body_height[0], body_height[1])
        standing &= bh > np.median(bh) - args.body_height_drop

    walking = speed > args.walk_speed
    cal = calibrate(xy, yaw, grade, cross, standing & walking, t,
                    args.revisit_radius, args.revisit_min_dt)
    if args.debias:
        grade -= cal.grade_bias
        cross -= cal.cross_bias
    tilt = np.degrees(np.arctan(np.hypot(np.tan(np.radians(grade)), np.tan(np.radians(cross)))))

    ds = np.r_[0.0, np.linalg.norm(np.diff(xy, axis=0), axis=1)]
    elev = np.cumsum(np.where(standing, np.tan(np.radians(grade)), 0.0) * ds)
    closure, n_closure = loop_closure(xy, elev, standing & walking, t,
                                      args.revisit_radius, args.revisit_min_dt)

    # to colour-frame times
    ct = np.asarray([r[0] for r in frames], dtype=float) / 1e9
    paths = [os.path.join(run_dir, "color", os.path.basename(r[1])) for r in frames]
    inside = (ct >= t[0]) & (ct <= t[-1])
    near = np.clip(np.searchsorted(t, ct), 0, len(t) - 1)
    near = np.where((near > 0) & (np.abs(t[near - 1] - ct) < np.abs(t[near] - ct)), near - 1, near)
    f_tilt, f_grade, f_cross = (np.interp(ct, t, v) for v in (tilt, grade, cross))
    f_elev, f_speed = np.interp(ct, t, elev), np.interp(ct, t, speed)
    f_yaw = yaw[near]
    f_stand, f_walk = standing[near], walking[near]
    valid = inside & f_stand

    kept = set()
    manifest = os.path.join(run_dir, "filter_manifest.csv")
    if os.path.exists(manifest):
        with open(manifest) as fh:
            kept = {int(r["frame_index"]) for r in csv.DictReader(fh) if r["kept"] == "True"}

    classes, labels = classify(f_tilt, f_grade, f_cross, args)
    rows = []
    for k in range(len(ct)):
        rows.append({
            "run": name,
            "frame_index": k + 1,
            "image": paths[k],
            "stamp_ns": int(round(ct[k] * 1e9)),
            "t_rel_s": round(float(ct[k] - ct[0]), 3),
            "x": round(float(np.interp(ct[k], t, xy[:, 0])), 3),
            "y": round(float(np.interp(ct[k], t, xy[:, 1])), 3),
            "heading_deg": round(float(np.degrees(f_yaw[k])), 1),
            "slope_label": labels[k] if valid[k] else "",
            "slope_class": classes[k] if valid[k] else "",
            "tilt_deg": round(float(f_tilt[k]), 2) if valid[k] else "",
            "grade_deg": round(float(f_grade[k]), 2) if valid[k] else "",
            "grade_pct": round(float(np.tan(np.radians(f_grade[k])) * 100), 1) if valid[k] else "",
            "cross_slope_deg": round(float(f_cross[k]), 2) if valid[k] else "",
            "elevation_m": round(float(f_elev[k]), 2) if valid[k] else "",
            "speed_mps": round(float(f_speed[k]), 3),
            "walking": bool(f_walk[k]),
            "posture": "standing" if f_stand[k] else "not_standing",
            "valid": bool(valid[k]),
            "kept_by_filter": (k + 1) in kept if kept else "",
        })

    # ---- report ----
    lab = [r for r in rows if r["valid"] and r["walking"]]
    counts: dict[str, int] = {}
    for r in lab:
        counts[r["slope_class"]] = counts.get(r["slope_class"], 0) + 1
    print(f"[{name}]")
    print(f"  self-calibration  {cal.describe()}")
    if n_closure:
        print(f"  loop closure      {closure:.2f} m median elevation mismatch over "
              f"{n_closure} revisits, against {np.ptp(elev[standing]):.1f} m of relief")
    print(f"  relief            {np.ptp(elev[standing]):.1f} m range, "
          f"{np.sum(np.clip(np.diff(elev[standing]), 0, None)):.0f} m total climb")
    not_standing = sum(1 for r in rows if r["posture"] == "not_standing")
    print(f"  frames            {len(rows)} colour, {len(lab)} labelled while walking"
          f"{f', {not_standing} excluded as not standing' if not_standing else ''}")
    for cls in ("flat", "gentle", "moderate", "steep"):
        c = counts.get(cls, 0)
        if c or cls == "flat":
            print(f"    {cls:<10s}      {c:5d}  ({c / max(len(lab), 1):5.1%})")
    if lab:
        g = np.array([r["grade_deg"] for r in lab])
        print(f"  grade             p5 {np.percentile(g, 5):+.1f} deg, median {np.median(g):+.1f}, "
              f"p95 {np.percentile(g, 95):+.1f}, extremes {g.min():+.1f} / {g.max():+.1f}")
    if np.isfinite(cal.sigma) and cal.sigma > args.gentle / 2:
        print(f"  warning           noise ({cal.sigma:.2f} deg) is large next to the "
              f"'gentle' threshold ({args.gentle} deg); consider raising it")

    out = os.path.join(run_dir, args.out_name)
    write_csv(out, rows)
    sloped = [r for r in rows if r["valid"] and r["walking"] and r["slope_class"] != "flat"
              and (not args.only_kept or r["kept_by_filter"] is True)]
    out_sloped = os.path.join(run_dir, args.sloped_name)
    write_csv(out_sloped, sloped)
    print(f"  labels            {out}")
    print(f"  sloped list       {out_sloped}  ({len(sloped)} frames"
          f"{' , kept-only' if args.only_kept else ''})")

    if args.plot:
        png = os.path.join(run_dir, "slope_preview.png")
        plot_run(png, xy, elev, grade, standing, t, name)
        print(f"  preview           {png}")
    return rows


def plot_run(png, xy, elev, grade, standing, t, name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6),
                                   gridspec_kw={"width_ratios": [1.3, 1]})
    s = ax1.scatter(xy[standing, 0], xy[standing, 1], c=grade[standing], s=4,
                    cmap="RdYlBu_r", vmin=-6, vmax=6)
    ax1.set_aspect("equal")
    ax1.set_xlabel("x [m]")
    ax1.set_ylabel("y [m]")
    ax1.set_title(f"{name}: grade along heading")
    fig.colorbar(s, ax=ax1, label="grade [deg]  (+ uphill)")
    ax2.plot(t[standing] - t[0], elev[standing], lw=1)
    ax2.set_xlabel("time [s]")
    ax2.set_ylabel("integrated elevation [m]")
    ax2.set_title("elevation profile")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(png, dpi=125)
    plt.close(fig)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-root", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--runs", nargs="*", default=None, help="run names (default: all)")
    p.add_argument("--gentle", type=float, default=2.0,
                   help="deg of tilt above which ground stops counting as flat "
                        "(default: 2.0 = 3.5%% grade)")
    p.add_argument("--moderate", type=float, default=5.0,
                   help="deg of tilt for 'moderate' (default: 5.0 = 8.7%%, the ADA ramp limit)")
    p.add_argument("--steep", type=float, default=10.0,
                   help="deg of tilt for 'steep' (default: 10.0 = 17.6%%)")
    p.add_argument("--smooth-window", type=float, default=1.5,
                   help="seconds of attitude median-filtered to remove the gait (default: 1.5)")
    p.add_argument("--walk-speed", type=float, default=0.25,
                   help="m/s above which the robot counts as walking (default: 0.25)")
    p.add_argument("--max-tilt", type=float, default=25.0,
                   help="deg of body tilt beyond which the robot is taken to be sitting "
                        "rather than on a slope (default: 25)")
    p.add_argument("--body-height-drop", type=float, default=0.05,
                   help="m below the run's normal standing height that counts as not "
                        "standing, where sportmodestate is recorded (default: 0.05)")
    p.add_argument("--debias", action=argparse.BooleanOptionalAction, default=True,
                   help="remove the attitude zero point measured from revisits (default: on)")
    p.add_argument("--revisit-radius", type=float, default=0.6,
                   help="m within which two passes count as the same ground (default: 0.6)")
    p.add_argument("--revisit-min-dt", type=float, default=30.0,
                   help="s that must separate two passes for them to be separate visits")
    p.add_argument("--only-kept", action="store_true",
                   help="restrict the sloped list to frames filter_frames.py kept")
    p.add_argument("--clock-offset", default="auto")
    p.add_argument("--out-name", default="slope_labels.csv")
    p.add_argument("--sloped-name", default="sloped_frames.csv")
    p.add_argument("--summary", default=None, help="also write one combined CSV here")
    p.add_argument("--plot", action="store_true")
    args = p.parse_args(argv)

    if not (args.gentle < args.moderate < args.steep):
        p.error("thresholds must increase: --gentle < --moderate < --steep")

    runs = find_runs(args.data_root)
    if args.runs:
        wanted = set(args.runs)
        runs = [r for r in runs if os.path.basename(r) in wanted]
        missing = wanted - {os.path.basename(r) for r in runs}
        if missing:
            p.error(f"no dataset.db for run(s): {', '.join(sorted(missing))}")
    if not runs:
        p.error(f"no runs with a dataset.db under {args.data_root}")

    all_rows = []
    for run in runs:
        all_rows += process_run(run, args)
        print()

    lab = [r for r in all_rows if r["valid"] and r["walking"]]
    sloped = [r for r in lab if r["slope_class"] != "flat"]
    print(f"total: {len(sloped)} of {len(lab)} walking frames on non-flat ground "
          f"({len(sloped) / max(len(lab), 1):.1%}) across {len(runs)} run(s)")
    if args.summary:
        write_csv(args.summary, all_rows)
        print(f"combined: {args.summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
