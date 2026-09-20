#!/usr/bin/env python
"""Score every image in filtered/ for walkway hazards and wheelchair accessibility.

Sends each frame to the Gemini API and writes one CSV row per image: surface type,
usable width, vertical obstacles, vehicles, construction, hazards and a verdict for
pedestrians and for wheelchair users. Pose and the IMU-measured grade from
label_slopes.py are joined in, so each row carries both what the camera saw and where
the robot was when it saw it.

RUN IT WITH THE navigability ENVIRONMENT:

    conda run -n navigability python analyze_accessibility.py
    # or:  conda activate navigability && python analyze_accessibility.py

API KEY -- pick one, the script checks in this order:

  1. Environment variable (best for one-off shells):
         export GEMINI_API_KEY='...'
  2. A key file, which is what --api-key-file defaults to:
         printf '%s' 'YOUR_KEY' > /home/yuanhong/Desktop/unmapped_data/.gemini_key
         chmod 600 /home/yuanhong/Desktop/unmapped_data/.gemini_key
     Keep that file out of git. Get a key at https://aistudio.google.com/apikey

Results are cached per image under filtered/.gemini_cache/, so re-running costs
nothing for frames already done and a stopped run picks up where it left off. Delete
the cache directory, or pass --refresh, to re-analyse.

Examples
--------
    conda run -n navigability python analyze_accessibility.py --list-models
    conda run -n navigability python analyze_accessibility.py --limit 12    # try it
    conda run -n navigability python analyze_accessibility.py               # all frames
    conda run -n navigability python analyze_accessibility.py --model gemini-2.5-pro
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone
from enum import Enum

try:
    from google import genai
    from google.genai import types
    from pydantic import BaseModel, Field, create_model
except ImportError:
    sys.exit(
        "The Gemini SDK is not importable from this interpreter.\n"
        "This script expects the 'navigability' conda environment:\n"
        "    conda run -n navigability python analyze_accessibility.py ...\n"
        "If that environment is missing, recreate it with:\n"
        "    conda create -n navigability python=3.12 -y\n"
        "    conda run -n navigability pip install google-genai pillow numpy"
    )

# --------------------------------------------------------------------------- #
# what we ask the model for
# --------------------------------------------------------------------------- #
# Every field is a closed enum wherever it can be, so the CSV can be grouped and
# counted without string cleaning afterwards. Nothing is Optional: the model must
# pick a value, and each enum carries an explicit "unclear" member so that not
# being able to tell is a real answer rather than a guess or a null.


class Scene(str, Enum):
    sidewalk = "sidewalk"
    shared_path = "shared_path"
    plaza = "plaza"
    crosswalk = "crosswalk"
    roadway = "roadway"
    parking_lot = "parking_lot"
    driveway = "driveway"
    stairs = "stairs"
    ramp = "ramp"
    building_entrance = "building_entrance"
    indoors = "indoors"
    lawn_or_field = "lawn_or_field"
    unpaved_trail = "unpaved_trail"
    construction_zone = "construction_zone"
    other = "other"
    unclear = "unclear"


class Material(str, Enum):
    asphalt = "asphalt"
    concrete = "concrete"
    concrete_pavers = "concrete_pavers"
    brick = "brick"
    cobblestone = "cobblestone"
    gravel = "gravel"
    dirt = "dirt"
    grass = "grass"
    mulch = "mulch"
    sand = "sand"
    tile = "tile"
    wood = "wood"
    metal_grate = "metal_grate"
    rubber = "rubber"
    carpet = "carpet"
    other = "other"
    unclear = "unclear"


class Traversability(str, Enum):
    smooth = "smooth"
    minor_irregularities = "minor_irregularities"
    rough = "rough"
    very_rough = "very_rough"
    impassable_for_wheels = "impassable_for_wheels"
    unclear = "unclear"


class WidthBand(str, Enum):
    over_1p5m = "over_1p5m"
    between_0p9_and_1p5m = "between_0p9_and_1p5m"
    between_0p8_and_0p9m = "between_0p8_and_0p9m"
    under_0p8m = "under_0p8m"
    unclear = "unclear"


class Constriction(str, Enum):
    none = "none"
    pole_or_signpost = "pole_or_signpost"
    bollard = "bollard"
    parked_vehicle = "parked_vehicle"
    parked_bicycle_or_scooter = "parked_bicycle_or_scooter"
    bin_or_furniture = "bin_or_furniture"
    planter_or_vegetation = "planter_or_vegetation"
    construction_barrier = "construction_barrier"
    building_corner = "building_corner"
    doorway = "doorway"
    narrow_by_design = "narrow_by_design"
    parked_people = "people"
    unclear = "unclear"


class ObstacleKind(str, Enum):
    step_single = "step_single"
    stair_flight = "stair_flight"
    curb = "curb"
    curb_ramp = "curb_ramp"
    threshold_or_lip = "threshold_or_lip"
    gap_or_joint = "gap_or_joint"
    tree_root_heave = "tree_root_heave"
    pothole_or_sunken_slab = "pothole_or_sunken_slab"
    drop_off_edge = "drop_off_edge"


class HeightBand(str, Enum):
    under_6mm = "under_6mm"
    between_6_and_13mm = "between_6_and_13mm"
    between_13_and_50mm = "between_13_and_50mm"
    over_50mm = "over_50mm"
    unclear = "unclear"


class VehicleKind(str, Enum):
    parked_car = "parked_car"
    moving_car = "moving_car"
    truck_or_van = "truck_or_van"
    bus = "bus"
    motorcycle = "motorcycle"
    bicycle = "bicycle"
    scooter = "scooter"
    service_cart = "service_cart"
    construction_vehicle = "construction_vehicle"


class VehicleConflict(str, Enum):
    none = "none"
    adjacent_roadway = "adjacent_roadway"
    driveway_crossing = "driveway_crossing"
    crossing_ahead = "crossing_ahead"
    parking_lot_traverse = "parking_lot_traverse"
    vehicle_blocking_path = "vehicle_blocking_path"
    moving_vehicle_near_path = "moving_vehicle_near_path"
    unclear = "unclear"


class ConstructionSign(str, Enum):
    cones_or_delineators = "cones_or_delineators"
    barriers_or_jersey_walls = "barriers_or_jersey_walls"
    temporary_fencing = "temporary_fencing"
    scaffolding = "scaffolding"
    excavation_or_trench = "excavation_or_trench"
    heavy_equipment = "heavy_equipment"
    materials_stockpile = "materials_stockpile"
    warning_signage = "warning_signage"
    caution_tape = "caution_tape"
    temporary_surface = "temporary_surface"


class PathImpact(str, Enum):
    none = "none"
    narrowed = "narrowed"
    detour_marked = "detour_marked"
    blocked = "blocked"
    unclear = "unclear"


class HazardKind(str, Enum):
    standing_water = "standing_water"
    ice_or_snow = "ice_or_snow"
    loose_gravel = "loose_gravel"
    mud_or_soft_ground = "mud_or_soft_ground"
    wet_leaves_or_debris = "wet_leaves_or_debris"
    broken_or_spalled_pavement = "broken_or_spalled_pavement"
    large_crack = "large_crack"
    uneven_slab_joints = "uneven_slab_joints"
    drain_grate = "drain_grate"
    manhole_or_utility_cover = "manhole_or_utility_cover"
    cable_or_hose_across_path = "cable_or_hose_across_path"
    overhanging_branch = "overhanging_branch"
    low_clearance = "low_clearance"
    protruding_object = "protruding_object"
    obstacle_in_path = "obstacle_in_path"
    missing_curb_ramp = "missing_curb_ramp"
    missing_handrail = "missing_handrail"
    no_tactile_warning = "no_tactile_warning"
    blind_corner = "blind_corner"
    crowding = "crowding"
    animal = "animal"
    poor_lighting = "poor_lighting"
    glare_or_visibility = "glare_or_visibility"
    unprotected_drop = "unprotected_drop"
    other = "other"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Verdict(str, Enum):
    passable = "passable"
    passable_with_difficulty = "passable_with_difficulty"
    likely_impassable = "likely_impassable"
    unclear = "unclear"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Surface(BaseModel):
    primary_material: Material
    is_paved: bool
    traversability: Traversability
    other_materials_present: list[Material] = Field(
        description="Other walkable materials visible in or immediately beside the route.")


class ClearWidth(BaseModel):
    band: WidthBand
    meters: float = Field(
        description="Best numeric estimate of usable clear width in metres; -1 if unclear.")
    constricted_by: list[Constriction]


class VerticalObstacle(BaseModel):
    kind: ObstacleKind
    height_band: HeightBand
    blocks_wheels: bool


class Vehicles(BaseModel):
    present: bool
    kinds: list[VehicleKind]
    conflict: VehicleConflict


class Construction(BaseModel):
    present: bool
    indicators: list[ConstructionSign]
    path_impact: PathImpact


class Hazard(BaseModel):
    kind: HazardKind
    severity: Severity
    note: str = Field(description="Under 15 words, describing what is actually visible.")


class Analysis(BaseModel):
    scene: Scene
    surface: Surface
    clear_width: ClearWidth
    vertical_obstacles: list[VerticalObstacle]
    vehicles: Vehicles
    construction: Construction
    hazards: list[Hazard]
    wheelchair_verdict: Verdict
    pedestrian_verdict: Verdict
    primary_barrier: str = Field(
        description="The single biggest problem for a wheelchair user, or empty if none.")
    confidence: Confidence
    summary: str = Field(description="One sentence, under 25 words.")


# A batch item is an Analysis with its position stamped on the front. Built from
# Analysis's own fields rather than restated, so the two can never drift apart, and
# with image_number declared first because a field the model fills early anchors the
# rest of that object to the right image.
FrameAnalysis = create_model(
    "FrameAnalysis",
    image_number=(int, Field(description=(
        "The number printed above this image, 1 for the first image in the batch. "
        "It must match, or the assessment will be attached to the wrong photograph."))),
    **{name: (f.annotation, f) for name, f in Analysis.model_fields.items()},
)


class BatchResult(BaseModel):
    frames: list[FrameAnalysis]


# --------------------------------------------------------------------------- #
# the prompt
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """\
You assess pedestrian and wheelchair accessibility from images taken by a camera \
mounted on a quadruped robot that was teleoperated around a university campus.

THE VIEWPOINT IS UNUSUAL -- read this before judging anything:
- The camera sits about 0.35 m above the ground, roughly at an adult's knee height, \
facing forward and tilted slightly down. It is not a human eye-level photograph.
- Because the view is so low, the ground fills much of the frame and is seen at a \
very shallow angle. Distance compresses sharply with range: a band of surface that \
looks thin near the top of the frame can be many metres long.
- People and vehicles are seen from below and are often cropped at the waist or \
wheels. Parts of the robot itself may intrude at the bottom edge -- never report the \
robot's own body as an obstacle.
- Frames are 1280x720 and some carry motion blur, blown-out sky or deep shadow.

WHAT TO ASSESS:
Judge the route the robot is travelling along: the walkable surface directly ahead, \
out to roughly 5 m. Ignore surfaces plainly separated from that route -- a lawn \
beyond a kerb, a road across a verge -- except where a field explicitly asks about \
them, such as adjacent roadways under vehicle conflict.

HOW TO JUDGE WIDTH:
Report the unobstructed width actually usable by a wheelchair, not the full corridor \
between buildings. Useful anchors visible in these scenes: a concrete sidewalk slab \
is typically 1.2-1.5 m across, a standard doorway is 0.9 m, a parked car is about \
1.8 m wide, a bollard is about 0.2 m across. The thresholds in the bands come from \
accessibility practice: 0.915 m is the minimum continuous clear width, 0.815 m the \
minimum at a short pinch point, and 1.525 m is what lets two wheelchairs pass.

HOW TO JUDGE SEVERITY:
Severity is the effect on a wheelchair user specifically, not on the robot and not \
on an able-bodied walker. low = noticeable but passable. medium = requires care, \
slows them down or forces a detour. high = likely to stop them, tip them or put \
them in the path of traffic.

DO NOT JUDGE GROUND SLOPE OR GRADIENT. The robot measures it with its IMU, far more \
accurately than a photograph allows, and that measurement is joined to your answer \
afterwards. Do report discrete vertical features -- steps, kerbs, lips, gaps, root \
heave -- because those are exactly what the IMU cannot see.

ACCURACY OVER COMPLETENESS:
This builds a dataset that will be trusted downstream, so a confident wrong answer \
is far worse than admitting the image does not show it. When you cannot tell, use \
the "unclear" value. Leave a list empty rather than padding it with things you \
suspect but cannot see. Report only what is visible in this frame; do not infer \
from what a campus usually has. If the frame is indoors, inside a lift, or so \
blocked or blurred that no route is visible, set the scene accordingly and mark \
both verdicts "unclear"."""

BATCH_INSTRUCTION = """\
Assess the walkway in each of the {n} images above.

Treat every image as a separate scene with nothing to do with the others. They were \
taken at different places and times, and what is true of one says nothing about the \
next. Do not let one image's answer shape another's, and do not repeat an answer \
across images merely because they look alike -- two frames of similar-looking \
pavement can still differ in width, surface and hazards, and a dataset full of \
copied rows is worse than no rows at all. Look at each image again on its own \
before you answer for it.

Return exactly {n} objects in the "frames" array, in the same order as the images, \
and set image_number to the number printed above each image: 1 for the first, {n} \
for the last. Every image gets its own object, including any that are unclear."""


# --------------------------------------------------------------------------- #
# CSV shape
# --------------------------------------------------------------------------- #

COLS = [
    "run", "image", "frame_index",
    # joined from the robot's own measurements
    "x", "y", "heading_deg", "grade_deg", "slope_label",
    # what the model saw
    "scene", "surface_material", "is_paved", "traversability", "other_materials",
    "width_band", "width_m", "constricted_by",
    "vertical_obstacles", "worst_obstacle_height", "obstacle_blocks_wheels",
    "vehicles_present", "vehicle_kinds", "vehicle_conflict",
    "construction_present", "construction_signs", "construction_impact",
    "hazard_count", "hazard_kinds", "max_hazard_severity", "hazard_notes",
    "wheelchair_verdict", "pedestrian_verdict", "primary_barrier",
    "confidence", "summary",
    "model", "analyzed_at", "error",
]

SEV_ORDER = {"low": 1, "medium": 2, "high": 3}
HEIGHT_ORDER = {"unclear": 0, "under_6mm": 1, "between_6_and_13mm": 2,
                "between_13_and_50mm": 3, "over_50mm": 4}


def flatten(a: dict) -> dict:
    """Turn one nested analysis into flat CSV cells; lists become ';'-joined."""
    hz = a.get("hazards") or []
    vo = a.get("vertical_obstacles") or []
    sur, cw = a.get("surface") or {}, a.get("clear_width") or {}
    veh, con = a.get("vehicles") or {}, a.get("construction") or {}
    width = cw.get("meters")
    return {
        "scene": a.get("scene", ""),
        "surface_material": sur.get("primary_material", ""),
        "is_paved": sur.get("is_paved", ""),
        "traversability": sur.get("traversability", ""),
        "other_materials": ";".join(sur.get("other_materials_present") or []),
        "width_band": cw.get("band", ""),
        "width_m": "" if width in (None, "") or float(width) < 0 else round(float(width), 2),
        "constricted_by": ";".join(c for c in (cw.get("constricted_by") or []) if c != "none"),
        "vertical_obstacles": ";".join(o.get("kind", "") for o in vo),
        "worst_obstacle_height": max((o.get("height_band", "unclear") for o in vo),
                                     key=lambda h: HEIGHT_ORDER.get(h, 0), default=""),
        "obstacle_blocks_wheels": any(o.get("blocks_wheels") for o in vo) if vo else False,
        "vehicles_present": veh.get("present", ""),
        "vehicle_kinds": ";".join(veh.get("kinds") or []),
        "vehicle_conflict": veh.get("conflict", ""),
        "construction_present": con.get("present", ""),
        "construction_signs": ";".join(con.get("indicators") or []),
        "construction_impact": con.get("path_impact", ""),
        "hazard_count": len(hz),
        "hazard_kinds": ";".join(h.get("kind", "") for h in hz),
        "max_hazard_severity": max((h.get("severity", "low") for h in hz),
                                   key=lambda s: SEV_ORDER.get(s, 0), default=""),
        "hazard_notes": " | ".join(f"{h.get('kind')}: {h.get('note', '')}" for h in hz),
        "wheelchair_verdict": a.get("wheelchair_verdict", ""),
        "pedestrian_verdict": a.get("pedestrian_verdict", ""),
        "primary_barrier": a.get("primary_barrier", ""),
        "confidence": a.get("confidence", ""),
        "summary": a.get("summary", ""),
    }


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

def find_images(filtered_root: str, runs: list[str] | None) -> list[tuple[str, str]]:
    """(run, image path) for every jpg under filtered/<run>/color, on-disk order.

    The directory is the source of truth, not the manifest that built it: frames
    deleted by hand after filtering are meant to stay deleted.
    """
    out = []
    for run in sorted(os.listdir(filtered_root)):
        d = os.path.join(filtered_root, run, "color")
        if not os.path.isdir(d) or (runs and run not in runs):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                out.append((run, os.path.join(d, f)))
    return out


def load_context(data_root: str, runs: set[str]) -> dict[tuple[str, str], dict]:
    """Pose and measured grade per (run, image basename), from label_slopes.py output."""
    ctx: dict[tuple[str, str], dict] = {}
    for run in runs:
        path = os.path.join(data_root, run, "slope_labels.csv")
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            for r in csv.DictReader(fh):
                ctx[(run, os.path.basename(r["image"]))] = {
                    "frame_index": r["frame_index"], "x": r["x"], "y": r["y"],
                    "heading_deg": r["heading_deg"], "grade_deg": r["grade_deg"],
                    "slope_label": r["slope_label"],
                }
    return ctx


def read_image(path: str, max_dim: int) -> tuple[bytes, str]:
    """JPEG bytes for the request, downscaled only if asked."""
    if max_dim <= 0:
        with open(path, "rb") as fh:
            return fh.read(), "image/jpeg"
    from PIL import Image

    with Image.open(path) as im:
        if max(im.size) <= max_dim:
            with open(path, "rb") as fh:
                return fh.read(), "image/jpeg"
        im = im.convert("RGB")
        im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return buf.getvalue(), "image/jpeg"


# --------------------------------------------------------------------------- #
# the API
# --------------------------------------------------------------------------- #

def _find_api_key(args) -> str | None:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(var, "").strip():
            return os.environ[var].strip()
    if args.api_key_file and os.path.exists(args.api_key_file):
        with open(args.api_key_file) as fh:
            key = fh.read().strip()
        if key:
            if os.stat(args.api_key_file).st_mode & 0o077:
                print(f"note: {args.api_key_file} is readable by others; chmod 600 it",
                      file=sys.stderr)
            return key
    return None


def _find_adc():
    """Resolve Application Default Credentials, returning (credentials, project)."""
    try:
        import google.auth

        return google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except Exception:                                    # noqa: BLE001 - absence is the answer
        return None, None


NO_CREDENTIALS = """\
No Gemini credentials found. There are two ways in, and either works for this script.

A) API key -- Google AI Studio. Simplest, but some organisations disable key
   creation, in which case use (B).
       export GEMINI_API_KEY='your-key'
   or put it in the file this script reads automatically:
       printf '%s' 'your-key' > {key_file}
       chmod 600 {key_file}
   Keys: https://aistudio.google.com/apikey

B) Application Default Credentials -- Vertex AI on Google Cloud. This is what
   you are offered when your organisation manages access centrally. It needs the
   gcloud CLI, which is not installed here:
       conda install -n navigability -c conda-forge google-cloud-sdk
   then sign in and point ADC at your project:
       gcloud auth login
       gcloud auth application-default login
       gcloud auth application-default set-quota-project YOUR_PROJECT_ID
   The project needs the Vertex AI API enabled and billing attached:
       gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
   Then run this script with:
       --auth adc --project YOUR_PROJECT_ID
   (or set GOOGLE_CLOUD_PROJECT and the project is picked up on its own)

Everything else about the run is identical either way: same models, same images,
same schema, same CSV."""


def _no_sdk_retry() -> "types.HttpOptions":
    """Stop the SDK retrying behind our back.

    google-genai retries 429 itself, five attempts deep, inside a single
    generate_content() call. Our limiter counts that as one request while the server
    counts up to five, so a rate-limited run silently spends its whole quota on
    retries and then fails whole batches. Pacing has to live in exactly one place,
    and RateLimiter is that place.
    """
    return types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))


def make_client(args) -> tuple["genai.Client", str]:
    """Build a Gemini client from whichever credentials are available.

    Two backends reach the same models. An API key talks to the AI Studio endpoint;
    ADC talks to Vertex AI, which is what organisations hand out when they do not
    allow long-lived keys. Image input, structured output and model ids are the same
    on both, so nothing below this function needs to know which one is in use.
    """
    key = _find_api_key(args) if args.auth in ("auto", "api-key") else None
    if key:
        return genai.Client(api_key=key, http_options=_no_sdk_retry()), "AI Studio (API key)"

    if args.auth in ("auto", "adc"):
        creds, adc_project = _find_adc()
        project = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT") or adc_project
        if creds is not None and project:
            return (genai.Client(vertexai=True, credentials=creds, project=project,
                                 location=args.location, http_options=_no_sdk_retry()),
                    f"Vertex AI via ADC (project {project}, {args.location})")
        if args.auth == "adc":
            if creds is None:
                sys.exit("--auth adc was requested but Application Default Credentials "
                         "are not configured.\n\n" + NO_CREDENTIALS.format(
                             key_file=args.api_key_file))
            sys.exit("ADC works but no project is set. Pass --project YOUR_PROJECT_ID, "
                     "or:\n    gcloud auth application-default set-quota-project YOUR_PROJECT_ID")

    if args.auth == "api-key":
        sys.exit("--auth api-key was requested but no key was found.\n\n"
                 + NO_CREDENTIALS.format(key_file=args.api_key_file))
    sys.exit(NO_CREDENTIALS.format(key_file=args.api_key_file))


class RateLimiter:
    """Paces requests across all worker threads to a requests-per-minute ceiling.

    Quota is counted per project, so every worker has to draw from one budget. Slots
    are handed out evenly rather than in bursts, because a burst of six against a
    five-per-minute limit spends most of its time in backoff. When the API does push
    back it tells us how long to wait, and ``penalize`` moves the whole queue rather
    than the one thread that happened to be rejected.
    """

    def __init__(self, rpm: float, adaptive: bool = True):
        self.base_interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self.interval = self.base_interval
        self.lock = threading.Lock()
        self.next_slot = 0.0
        self.adaptive = adaptive
        self.streak = 0

    def acquire(self) -> None:
        if not self.interval:
            return
        with self.lock:
            slot = max(time.monotonic(), self.next_slot)
            self.next_slot = slot + self.interval
        wait = slot - time.monotonic()
        if wait > 0:
            time.sleep(wait)

    def penalize(self, seconds: float) -> None:
        """Hold every worker back, and if this keeps happening, go slower for good.

        Quotas are not always what they are documented to be, and a project can be
        metered on tokens per minute as well as requests. Rather than trusting the
        configured rate, each rejection widens the gap between requests; a clean run
        narrows it back towards what was asked for.
        """
        with self.lock:
            self.next_slot = max(self.next_slot, time.monotonic() + seconds)
            if self.adaptive and self.base_interval:
                self.interval = min(self.interval * 1.5, 60.0)
                self.streak = 0

    def succeeded(self) -> None:
        if not (self.adaptive and self.base_interval):
            return
        with self.lock:
            self.streak += 1
            if self.streak >= 4 and self.interval > self.base_interval:
                self.interval = max(self.base_interval, self.interval / 1.25)
                self.streak = 0

    @property
    def effective_rpm(self) -> float:
        return 60.0 / self.interval if self.interval else float("inf")


RETRY_AFTER = re.compile(r"(?:retryDelay'?:\s*'?|[Pp]lease retry in\s*)(\d+(?:\.\d+)?)s")
QUOTA_ID = re.compile(r"quotaId['\"]?:\s*['\"]([^'\"]+)")
QUOTA_METRIC = re.compile(r"Quota exceeded for metric:\s*([^,]+),\s*limit:\s*(\d+)")


class Analyzer:
    """One Gemini call per image, with caching, retry and running token totals."""

    def __init__(self, client, args, prompt_fingerprint: str):
        self.client = client
        self.args = args
        self.fingerprint = prompt_fingerprint
        self.limiter = RateLimiter(args.rpm)
        self.lock = threading.Lock()
        self.throttled = 0
        self.tokens_in = self.tokens_out = 0
        self.calls = self.cached = self.failed = self.done = 0
        self.quota_notes: set[str] = set()

    def _note_quota(self, text: str) -> None:
        """Print which quota is actually binding, once per kind.

        The 429 body names the metric and its limit. Surfacing it turns a wall of
        throttling into something actionable -- it says whether to lower --rpm,
        shrink the batch, or simply wait for tomorrow.
        """
        m = QUOTA_METRIC.search(text)
        q = QUOTA_ID.search(text)
        note = (f"{m.group(1).strip()} (limit {m.group(2)})" if m
                else q.group(1) if q else "")
        if not note:
            return
        with self.lock:
            if note not in self.quota_notes:
                self.quota_notes.add(note)
                print(f"  quota in force: {note}", flush=True)

    def cache_path(self, run: str, image: str) -> str:
        stem = os.path.splitext(os.path.basename(image))[0]
        return os.path.join(self.args.cache_dir, run, f"{stem}.json")

    def cached_result(self, run: str, image: str) -> dict | None:
        p = self.cache_path(run, image)
        if self.args.refresh or not os.path.exists(p):
            return None
        try:
            with open(p) as fh:
                rec = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None
        # a changed prompt, schema or model invalidates the answer
        if rec.get("fingerprint") != self.fingerprint:
            return None
        return rec

    def store(self, run: str, image: str, rec: dict) -> None:
        p = self.cache_path(run, image)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(rec, fh)
        os.replace(tmp, p)

    def call(self, images: list[str]) -> tuple[list[dict], dict]:
        parts: list = []
        for i, image in enumerate(images, 1):
            data, mime = read_image(image, self.args.max_dim)
            parts.append(f"Image {i}:")
            parts.append(types.Part.from_bytes(
                data=data, mime_type=mime,
                media_resolution=self.args.media_resolution_enum))
        parts.append(BATCH_INSTRUCTION.format(n=len(images)))
        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=BatchResult,
            temperature=self.args.temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=self.args.thinking_budget),
            # Campus scenes contain people and vehicles; the default filters can refuse
            # an ordinary streetscape, so only clear-cut cases are blocked.
            safety_settings=[
                types.SafetySetting(category=c, threshold="BLOCK_ONLY_HIGH")
                for c in ("HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
                          "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")
            ],
        )
        self.limiter.acquire()
        resp = self.client.models.generate_content(
            model=self.args.model, contents=parts, config=cfg)
        usage = {
            "in": getattr(resp.usage_metadata, "prompt_token_count", 0) or 0,
            "out": (getattr(resp.usage_metadata, "candidates_token_count", 0) or 0)
                   + (getattr(resp.usage_metadata, "thoughts_token_count", 0) or 0),
        }
        if resp.parsed is not None:
            frames = resp.parsed.model_dump(mode="json")["frames"]
        elif resp.text:
            frames = json.loads(resp.text)["frames"]
        else:
            reason = ""
            if resp.candidates:
                reason = str(getattr(resp.candidates[0], "finish_reason", "") or "")
            raise RuntimeError(f"empty response (finish_reason={reason or 'unknown'})")

        # A short or long array means the answers no longer line up with the images,
        # and a silently shifted row is worse than a missing one. Refuse the batch.
        if len(frames) != len(images):
            raise RuntimeError(
                f"model returned {len(frames)} assessments for {len(images)} images; "
                f"re-run with a smaller --batch-size")
        for i, fr in enumerate(frames, 1):
            if fr.get("image_number") != i:
                raise RuntimeError(
                    f"image_number out of order at position {i} "
                    f"(got {fr.get('image_number')}); re-run with a smaller --batch-size")
        return frames, usage

    def analyze_batch(self, run: str, images: list[str]) -> dict[str, dict]:
        """Assess one batch, caching each image separately so partial work survives.

        The cache is per image, not per batch, so changing --batch-size later does not
        throw away what is already done, and a run stopped halfway resumes at the image
        rather than at the batch.
        """
        delay = self.args.retry_base
        waited = 0.0
        attempt = 0
        last = ""
        while True:
            try:
                frames, usage = self.call(images)
                self.limiter.succeeded()
                share = {"in": usage["in"] / len(images), "out": usage["out"] / len(images)}
                out = {}
                for image, analysis in zip(images, frames):
                    analysis.pop("image_number", None)     # batch position, not a property
                    rec = {"fingerprint": self.fingerprint, "model": self.args.model,
                           "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "analysis": analysis, "usage": share, "error": ""}
                    self.store(run, image, rec)
                    out[image] = rec
                with self.lock:
                    self.calls += 1
                    self.done += len(images)
                    self.tokens_in += usage["in"]
                    self.tokens_out += usage["out"]
                return out
            except Exception as exc:                      # noqa: BLE001 - reported, not raised
                text = str(exc)
                last = f"{type(exc).__name__}: {exc}"

                if "429" in text or "RESOURCE_EXHAUSTED" in text:
                    # Being rate limited is not a failure, it is a queue. Waiting must
                    # not spend the retry budget, or a busy minute turns ten perfectly
                    # good images into ten error rows.
                    self._note_quota(text)
                    m = RETRY_AFTER.search(text)
                    pause = float(m.group(1)) + 1.0 if m else max(delay, 5.0)
                    if waited + pause > self.args.max_throttle_wait:
                        last = (f"waited {waited:.0f}s on rate limits and gave up; raise "
                                f"--max-throttle-wait or lower --rpm. Last error: {last}")
                        break
                    with self.lock:
                        self.throttled += 1
                    self.limiter.penalize(pause)
                    waited += pause
                    time.sleep(pause)
                    continue

                attempt += 1
                transient = any(t in text for t in
                                ("500", "502", "503", "504", "UNAVAILABLE",
                                 "DEADLINE", "timeout", "Timeout"))
                if attempt > self.args.retries or not transient:
                    break
                # jittered backoff so parallel workers do not retry in lockstep
                time.sleep(delay * (1.0 + random.random()))
                delay = min(delay * 2, 60.0)
        with self.lock:
            self.failed += len(images)
            self.done += len(images)
        # Nothing is cached on failure, so a plain re-run retries exactly these images.
        return {image: {"fingerprint": self.fingerprint, "model": self.args.model,
                        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "analysis": {}, "usage": {"in": 0, "out": 0}, "error": last}
                for image in images}


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def synthetic_record(image: str) -> dict:
    """A plausible answer used by --dry-run to exercise parsing and CSV writing."""
    return {"fingerprint": "dry-run", "model": "dry-run",
            "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "usage": {"in": 0, "out": 0}, "error": "",
            "analysis": Analysis(
                scene=Scene.sidewalk,
                surface=Surface(primary_material=Material.concrete, is_paved=True,
                                traversability=Traversability.minor_irregularities,
                                other_materials_present=[Material.grass]),
                clear_width=ClearWidth(band=WidthBand.between_0p9_and_1p5m, meters=1.3,
                                       constricted_by=[Constriction.planter_or_vegetation]),
                vertical_obstacles=[VerticalObstacle(kind=ObstacleKind.gap_or_joint,
                                                     height_band=HeightBand.between_6_and_13mm,
                                                     blocks_wheels=False)],
                vehicles=Vehicles(present=True, kinds=[VehicleKind.parked_car],
                                  conflict=VehicleConflict.adjacent_roadway),
                construction=Construction(present=False, indicators=[],
                                          path_impact=PathImpact.none),
                hazards=[Hazard(kind=HazardKind.large_crack, severity=Severity.low,
                                note="hairline crack across slab")],
                wheelchair_verdict=Verdict.passable,
                pedestrian_verdict=Verdict.passable,
                primary_barrier="", confidence=Confidence.medium,
                summary=f"dry-run synthetic row for {os.path.basename(image)}",
            ).model_dump(mode="json")}


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-root", default=here)
    p.add_argument("--filtered-dir", default=None,
                   help="the work dir holding <run>/color (default: <data-root>/filtered)")
    p.add_argument("--runs", nargs="*", default=None)
    p.add_argument("--model", default="gemini-3.6-flash",
                   help="Gemini model id (default: gemini-3.6-flash, the fastest flash model "
                        "that honours --thinking-budget 0; --list-models shows what your key "
                        "can reach, since the catalogue moves and older ids get retired)")
    p.add_argument("--api-key-file", default=os.path.join(here, ".gemini_key"))
    p.add_argument("--auth", choices=("auto", "api-key", "adc"), default="auto",
                   help="credentials to use: an AI Studio API key, Application Default "
                        "Credentials against Vertex AI, or auto (key first, then ADC)")
    p.add_argument("--project", default=None,
                   help="Google Cloud project for --auth adc (default: GOOGLE_CLOUD_PROJECT, "
                        "else the ADC quota project)")
    p.add_argument("--location", default="global",
                   help="Vertex AI location for --auth adc (default: global, which is "
                        "where the newest models land and what Google's own ADC setup "
                        "script targets; a region such as us-central1 also works)")
    p.add_argument("--concurrency", type=int, default=3,
                   help="images in flight at once (default: 3; --rpm is the real throttle)")
    p.add_argument("--batch-size", type=int, default=10,
                   help="images assessed per request (default: 10). Quota is counted in "
                        "requests, so batching is what makes a free-tier key usable; the "
                        "prompt tells the model to judge each image on its own, and a reply "
                        "that does not line up with the images is rejected rather than "
                        "written out misaligned")
    p.add_argument("--rpm", type=float, default=5.0,
                   help="requests per minute ceiling, shared by all workers. The AI Studio "
                        "free tier allows 5/min; on Vertex with billing attached raise it "
                        "hard, e.g. --rpm 60 --concurrency 8 (default: 5)")
    p.add_argument("--media-resolution", choices=("low", "medium", "high", "default"),
                   default="medium",
                   help="image detail sent to the model, and the ONLY thing that changes "
                        "image token cost: low is a quarter of high, medium about half "
                        "(default: medium)")
    p.add_argument("--limit", type=int, default=0,
                   help="stop after this many images -- use it to sample before a full run")
    p.add_argument("--max-dim", type=int, default=0,
                   help="downscale the long edge before sending (default: 0, send the "
                        "original). This saves upload bandwidth only -- measured on this "
                        "data, 1280x720 and 256x144 cost identical tokens, so use "
                        "--media-resolution to cut cost")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--thinking-budget", type=int, default=0,
                   help="model thinking tokens; 0 is cheapest, -1 lets the model decide")
    p.add_argument("--retries", type=int, default=4,
                   help="retries for genuine errors; rate limits are waited out "
                        "separately and do not spend this budget")
    p.add_argument("--max-throttle-wait", type=float, default=600.0,
                   help="seconds a single batch may spend waiting on rate limits before "
                        "it is given up on (default: 600)")
    p.add_argument("--retry-base", type=float, default=2.0)
    p.add_argument("--cache-dir", default=None,
                   help="default: <filtered-dir>/.gemini_cache")
    p.add_argument("--refresh", action="store_true", help="ignore cached answers and re-ask")
    p.add_argument("--out-name", default="accessibility.csv")
    p.add_argument("--summary", default=None, help="also write one combined CSV here")
    p.add_argument("--list-models", action="store_true",
                   help="print the models this key can use, then exit")
    p.add_argument("--dry-run", action="store_true",
                   help="do everything except call the API, using a synthetic answer; "
                        "needs no key and costs nothing")
    args = p.parse_args(argv)

    # The 2.5 Pro models cannot run with thinking switched off, so a budget of 0 --
    # which is the right default for Flash -- would be rejected outright.
    if "pro" in args.model and args.thinking_budget == 0:
        args.thinking_budget = -1
        print(f"note: {args.model} cannot disable thinking; using a dynamic budget",
              file=sys.stderr)

    args.media_resolution_enum = None if args.media_resolution == "default" else \
        f"MEDIA_RESOLUTION_{args.media_resolution.upper()}"

    args.filtered_dir = args.filtered_dir or os.path.join(args.data_root, "filtered")
    args.cache_dir = args.cache_dir or os.path.join(args.filtered_dir, ".gemini_cache")

    if args.list_models:
        client, how = make_client(args)
        print(f"via {how}\n")
        listed = 0
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if not actions or "generateContent" in actions:
                print(f"{m.name}\n    {(m.display_name or '').strip()}")
                listed += 1
        if not listed:
            # Vertex lists only the models deployed in the project, not the
            # publisher catalogue, so an empty list here is normal, not an error.
            print("no models listed -- on Vertex this endpoint returns only your own "
                  "deployed models.\nThe publisher models are still callable by id, "
                  "e.g. gemini-2.5-flash or gemini-2.5-pro.")
        return 0

    if not os.path.isdir(args.filtered_dir):
        p.error(f"no filtered work dir at {args.filtered_dir}; run filter_frames.py "
                f"--action copy --out-dir filtered first")
    images = find_images(args.filtered_dir, args.runs)
    if not images:
        p.error(f"no images under {args.filtered_dir}/*/color")
    if args.limit:
        images = images[:args.limit]

    ctx = load_context(args.data_root, {r for r, _ in images})
    fingerprint = hashlib.sha256(
        (SYSTEM_PROMPT + BATCH_INSTRUCTION + args.model
         + json.dumps(BatchResult.model_json_schema(), sort_keys=True)).encode()
    ).hexdigest()[:16]

    if args.dry_run:
        client, an = None, None
        print("dry run: no API calls, synthetic answers")
    else:
        client, how = make_client(args)
        an = Analyzer(client, args, fingerprint)
        print(f"auth: {how}")
        pending = sum(1 for run, img in images if an.cached_result(run, img) is None)
        eta = (pending / args.batch_size) / args.rpm if args.rpm > 0 else 0
        print(f"{len(images)} images in {args.filtered_dir} "
              f"({len(images) - pending} cached, {pending} to analyse)")
        print(f"model {args.model}, media resolution {args.media_resolution}, "
              f"{args.batch_size} images per request, "
              f"{args.concurrency} workers capped at {args.rpm:g} req/min"
              + (f"  ->  about {eta:.0f} min ({eta / 60:.1f} h)" if eta >= 1 else ""))

    t0 = time.time()
    results: dict[str, dict] = {}
    if args.dry_run:
        for _, img in images:
            results[img] = synthetic_record(img)
        print(f"{len(images)} images, would be {-(-len(images) // args.batch_size)} requests "
              f"at --batch-size {args.batch_size}")
    else:
        pending_by_run: dict[str, list[str]] = {}
        for run, img in images:
            hit = an.cached_result(run, img)
            if hit is not None:
                results[img] = hit
                an.cached += 1
            else:
                pending_by_run.setdefault(run, []).append(img)

        # Batches never span runs: it keeps each run's CSV self-contained and stops a
        # single bad batch from smearing failures across two runs.
        batches = [(run, imgs[i:i + args.batch_size])
                   for run, imgs in pending_by_run.items()
                   for i in range(0, len(imgs), args.batch_size)]

        total = sum(len(b) for _, b in batches)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for (brun, bimgs), out in zip(batches,
                                          pool.map(lambda b: an.analyze_batch(*b), batches)):
                results.update(out)
                bad = sum(1 for r in out.values() if r["error"])
                rate = an.done / max(time.time() - t0, 1e-9) * 60
                print(f"  {an.done}/{total}  {brun} "
                      f"{'+' + str(len(bimgs) - bad) if bad < len(bimgs) else ''}"
                      f"{f' [{bad} FAILED]' if bad else ''}  "
                      f"{rate:.0f} img/min at {an.limiter.effective_rpm:.1f} req/min  "
                      f"{an.calls} ok, {an.failed} failed, {an.throttled} waits",
                      flush=True)

    # ---- write ----
    by_run: dict[str, list[dict]] = {}
    for run, img in images:
        rec = results[img]
        meta = ctx.get((run, os.path.basename(img)), {})
        row = {c: "" for c in COLS}
        row.update({"run": run, "image": img,
                    "frame_index": meta.get("frame_index", ""),
                    "x": meta.get("x", ""), "y": meta.get("y", ""),
                    "heading_deg": meta.get("heading_deg", ""),
                    "grade_deg": meta.get("grade_deg", ""),
                    "slope_label": meta.get("slope_label", ""),
                    "model": rec.get("model", ""), "analyzed_at": rec.get("analyzed_at", ""),
                    "error": rec.get("error", "")})
        if rec.get("analysis"):
            row.update(flatten(rec["analysis"]))
        by_run.setdefault(run, []).append(row)

    all_rows = []
    for run, rows in by_run.items():
        out = os.path.join(args.filtered_dir, run, args.out_name)
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
        print(f"[{run}] {len(rows)} rows -> {out}")
        all_rows += rows

    combined = args.summary or os.path.join(args.filtered_dir, args.out_name)
    with open(combined, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(all_rows)

    ok = [r for r in all_rows if not r["error"]]
    print(f"\n{len(ok)}/{len(all_rows)} analysed -> {combined}")
    if an is not None:
        print(f"tokens: {an.tokens_in} in, {an.tokens_out} out over {an.calls} calls "
              f"({an.cached} served from cache, {an.failed} failed, "
              f"{an.throttled} rate-limit retries)")
        if an.done:
            print(f"per image: {an.tokens_in / an.done:.0f} in, {an.tokens_out / an.done:.0f} out "
                  f"({an.done / an.calls:.1f} images per request)"
                  f"  -- multiply by your model's current rate for cost")
    if any(r["error"] for r in all_rows):
        print("failed images keep an 'error' cell and are not cached; re-run to retry them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
