#!/usr/bin/env python
"""Stamp each filtered frame with a one-word accessibility verdict.

Reads the accessibility.csv written by analyze_accessibility.py and draws a badge in
the top-left corner of every image: a red box naming the single biggest reason the
route is not accessible, or a green "good accessibility" box when nothing is wrong.

RUN IT WITH THE navigability ENVIRONMENT:

    conda run -n navigability python annotate_images.py

Originals are never touched. Annotated copies go to filtered/<run>/annotated/ unless
you pass --in-place, which asks first.

Examples
--------
    conda run -n navigability python annotate_images.py
    conda run -n navigability python annotate_images.py --slope-deg 3   # stricter grade
    conda run -n navigability python annotate_images.py --only-flagged  # red ones only
    conda run -n navigability python annotate_images.py --contact-sheet review.jpg
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is missing. Run this with the navigability environment:\n"
             "    conda run -n navigability python annotate_images.py")

# --------------------------------------------------------------------------- #
# what counts as a barrier, and which word wins when several do
# --------------------------------------------------------------------------- #
# Ordered most-blocking first. A flight of stairs stops a wheelchair outright, so it
# outranks a rough surface that merely slows one down; the badge has room for one
# word, and it should be the word that matters most. Reorder this list to change
# which reason surfaces -- nothing else needs editing.

ACTIVE_VEHICLE = {"vehicle_blocking_path", "moving_vehicle_near_path",
                  "crossing_ahead", "driveway_crossing", "parking_lot_traverse"}
BLOCKING_OBSTACLE = {"stair_flight", "step_single"}
ROUGH = {"rough", "very_rough", "impassable_for_wheels"}
NARROW = {"under_0p8m", "between_0p8_and_0p9m"}
VEHICLE_SCENE = {"roadway", "parking_lot", "driveway"}

# hazard kind -> the word to show, when that hazard is medium or high severity
HAZARD_WORDS = {
    "mud_or_soft_ground": "mud",
    "standing_water": "water",
    "ice_or_snow": "ice",
    "loose_gravel": "gravel",
    "wet_leaves_or_debris": "debris",
    "broken_or_spalled_pavement": "uneven",
    "large_crack": "uneven",
    "uneven_slab_joints": "uneven",
    "pothole_or_sunken_slab": "uneven",
    "tree_root_heave": "roots",
    "drain_grate": "grate",
    "manhole_or_utility_cover": "grate",
    "cable_or_hose_across_path": "cable",
    "overhanging_branch": "branch",
    "low_clearance": "clearance",
    "protruding_object": "obstacle",
    "obstacle_in_path": "obstacle",
    "missing_curb_ramp": "curb",
    "unprotected_drop": "dropoff",
    "blind_corner": "corner",
    "crowding": "crowd",
    "animal": "animal",
    "poor_lighting": "dark",
    "glare_or_visibility": "glare",
}

GOOD_TEXT = "good accessibility"
RED = (200, 30, 30)
GREEN = (22, 150, 70)
GREY = (110, 110, 110)


def cells(row: dict, field: str) -> set[str]:
    return {x for x in (row.get(field) or "").split(";") if x}


def grade_of(row: dict) -> float:
    try:
        return abs(float(row["grade_deg"]))
    except (ValueError, KeyError, TypeError):
        return 0.0


def verdict(row: dict, args) -> tuple[str, str]:
    """Return (colour_key, word) for one analysed frame.

    'grey' means the frame was never successfully analysed, which is deliberately
    distinct from a clean bill of health -- an unlabelled image is not a safe one.
    """
    if row.get("error") or not row.get("scene"):
        return "grey", "no data"

    obstacles = cells(row, "vertical_obstacles")
    hazards = cells(row, "hazard_kinds")
    severity = row.get("max_hazard_severity", "")
    serious = severity in ("medium", "high")

    # Checked in order; the first hit is the word that gets drawn.
    if obstacles & BLOCKING_OBSTACLE or row["scene"] == "stairs":
        return "red", "stairs"
    if row.get("is_paved") == "False":
        return "red", "unpaved"
    if row.get("construction_present") == "True" or \
            row.get("construction_impact") not in ("none", "", "unclear"):
        return "red", "construction"
    if row.get("width_band") in NARROW:
        return "red", "narrow"
    if row.get("vehicle_conflict") in ACTIVE_VEHICLE or row["scene"] in VEHICLE_SCENE:
        return "red", "cars"
    if grade_of(row) >= args.slope_deg:
        return "red", "slope"
    if "curb" in obstacles and row.get("obstacle_blocks_wheels") == "True":
        return "red", "curb"
    if row.get("traversability") in ROUGH:
        return "red", "rough"
    if serious:
        for kind in hazards:                      # first hazard with a word for it
            if kind in HAZARD_WORDS:
                return "red", HAZARD_WORDS[kind]
        return "red", "hazard"
    # The model's own verdict is the backstop: it may have seen something the
    # structured fields above do not capture.
    if row.get("wheelchair_verdict") in ("likely_impassable", "passable_with_difficulty"):
        return "red", "blocked"
    return "green", GOOD_TEXT


# --------------------------------------------------------------------------- #
# drawing
# --------------------------------------------------------------------------- #

def load_font(size: int):
    import matplotlib

    path = os.path.join(os.path.dirname(matplotlib.__file__),
                        "mpl-data", "fonts", "ttf", "DejaVuSans-Bold.ttf")
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        for alt in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
            if os.path.exists(alt):
                return ImageFont.truetype(alt, size)
        return ImageFont.load_default()


def annotate(src: str, dst: str, colour: tuple, word: str, args) -> None:
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        # Sized off image width so the badge stays legible if the frames are ever
        # resized, rather than being pinned to these 1280x720 captures.
        scale = w / 1280.0
        pad = int(14 * scale)
        margin = int(18 * scale)
        font = load_font(max(12, int(args.font_size * scale)))

        d = ImageDraw.Draw(im)
        left, top, right, bottom = d.textbbox((0, 0), word, font=font)
        tw, th = right - left, bottom - top
        box = (margin, margin, margin + tw + 2 * pad, margin + th + 2 * pad)

        d.rectangle(box, fill=colour)
        d.rectangle(box, outline=(255, 255, 255), width=max(1, int(2 * scale)))
        d.text((margin + pad - left, margin + pad - top), word,
               fill=(255, 255, 255), font=font)
        im.save(dst, "JPEG", quality=args.quality)


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--filtered-dir", default=os.path.join(here, "filtered"))
    p.add_argument("--runs", nargs="*", default=None)
    p.add_argument("--csv-name", default="accessibility.csv")
    p.add_argument("--out-name", default="annotated",
                   help="subdirectory under each run for the stamped copies")
    p.add_argument("--in-place", action="store_true",
                   help="overwrite the originals in color/ instead (asks first)")
    p.add_argument("--slope-deg", type=float, default=5.0,
                   help="IMU-measured grade in degrees that counts as a barrier "
                        "(default: 5.0, the 1:12 ramp limit; 3.0 flags far more)")
    p.add_argument("--font-size", type=int, default=44,
                   help="text height in px at 1280 px wide (default: 44)")
    p.add_argument("--quality", type=int, default=92)
    p.add_argument("--only-flagged", action="store_true",
                   help="write only the images that came out red")
    p.add_argument("--contact-sheet", default=None,
                   help="also write a grid of the flagged frames to this path")
    p.add_argument("--yes", action="store_true", help="skip the --in-place prompt")
    args = p.parse_args(argv)

    if not os.path.isdir(args.filtered_dir):
        p.error(f"no filtered dir at {args.filtered_dir}")
    runs = sorted(d for d in os.listdir(args.filtered_dir)
                  if os.path.exists(os.path.join(args.filtered_dir, d, args.csv_name)))
    if args.runs:
        runs = [r for r in runs if r in args.runs]
    if not runs:
        p.error(f"no {args.csv_name} under {args.filtered_dir}/*/ "
                f"-- run analyze_accessibility.py first")

    if args.in_place and not args.yes:
        print(f"This overwrites the original JPEGs in {args.filtered_dir}/*/color/ "
              f"with stamped versions.")
        if input("Type 'yes' to continue: ").strip() != "yes":
            print("aborted")
            return 1

    from collections import Counter
    tally: Counter = Counter()
    words: Counter = Counter()
    flagged: list[tuple[str, str]] = []
    written = missing = 0

    for run in runs:
        run_dir = os.path.join(args.filtered_dir, run)
        out_dir = os.path.join(run_dir, "color") if args.in_place \
            else os.path.join(run_dir, args.out_name)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(run_dir, args.csv_name)) as fh:
            rows = list(csv.DictReader(fh))

        n_run = 0
        for row in rows:
            src = row["image"]
            if not os.path.exists(src):
                missing += 1
                continue
            colour_key, word = verdict(row, args)
            tally[colour_key] += 1
            words[word] += 1
            if colour_key == "red":
                flagged.append((src, word))
            if args.only_flagged and colour_key != "red":
                continue
            colour = {"red": RED, "green": GREEN, "grey": GREY}[colour_key]
            annotate(src, os.path.join(out_dir, os.path.basename(src)), colour, word, args)
            written += 1
            n_run += 1
        print(f"[{run}] {n_run} images -> {out_dir}")

    total = sum(tally.values())
    print(f"\n{written} images written"
          + (f", {missing} listed in the CSV but no longer on disk" if missing else ""))
    print(f"  red   {tally['red']:4d}  ({tally['red'] / max(total, 1):.0%})")
    print(f"  green {tally['green']:4d}  ({tally['green'] / max(total, 1):.0%})")
    if tally["grey"]:
        print(f"  grey  {tally['grey']:4d}  never analysed -- re-run "
              f"analyze_accessibility.py to fill these in")
    print("\nreasons:")
    for word, n in words.most_common():
        if word != GOOD_TEXT:
            print(f"    {word:<16} {n:4d}")

    if args.contact_sheet and flagged:
        sheet(args.contact_sheet, flagged)
        print(f"\ncontact sheet of the {len(flagged)} flagged frames: {args.contact_sheet}")
    return 0


def sheet(path: str, flagged: list[tuple[str, str]], cols: int = 8) -> None:
    """A grid of every flagged frame, for checking the labels in one pass."""
    tw, th = 240, 135
    rows = -(-len(flagged) // cols)
    canvas = Image.new("RGB", (cols * tw, rows * (th + 18)), "white")
    d = ImageDraw.Draw(canvas)
    font = load_font(13)
    for i, (src, word) in enumerate(flagged):
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        with Image.open(src) as im:
            canvas.paste(im.convert("RGB").resize((tw, th)), (x, y + 18))
        d.text((x + 3, y + 2), f"{word}  {os.path.basename(src)[-10:]}",
               fill=(180, 0, 0), font=font)
    canvas.save(path, "JPEG", quality=88)


if __name__ == "__main__":
    sys.exit(main())
