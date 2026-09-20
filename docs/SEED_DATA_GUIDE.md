# Replacing demo survey data

The graph, landmarks and doors are now generated from JHU's published campus
data by `scripts/build_campus_seed.py`. Edit that script, not the JSON it
writes — a hand edit is lost on the next rebuild.

    python3 scripts/build_campus_seed.py     # ~40s, the lawn-shortcut pass

## What is measured and what is not

`distance_m`, `stairs`, `curb`, `closed`, `bidirectional`, `grade`,
`riser_count` and `kind` come from the survey. **`surface`, `roughness`,
`slope`, `safety` and `lit` are null**, because nobody has measured them here.

Null means unknown and the cost function skips the term. Do not "fix" it with
a default: zero slope and 1.0 safety make every unsurveyed segment look ideal,
and `edge_cost` deliberately tests `edge.lit is False` rather than
`not edge.lit` for the same reason. Filling these in is what the robot
surveys are for, and `verified_stats.unknown_attribute_m` is how much of a
route is still waiting.

Every imported edge is `verified: false`. JHU's survey is not this project's
robot, and leaving the pipeline real work to do is the point.

## Replacement checklist

1. Update landmark records in the checked-in landmark seed JSON. Preserve each
   stable `id` if existing saved links should keep working; otherwise update
   graph node references at the same time.
2. Replace graph node coordinates and edge GeoJSON coordinates with surveyed
   WGS84 `[longitude, latitude]` positions.
3. For each surveyed edge, set `verified` only after ingestion has succeeded,
   add the robot run/timestamp, and replace slope, surface, roughness, curb-cut,
   lighting, security, closure, freshness, and confidence measurements.
4. Replace hazard records while retaining a stable edge reference. Keep severity
   normalized to the seed schema and use point coordinates on or near the edge.
5. Put robot photos in the backend's static evidence directory and update only
   the corresponding relative evidence paths. Do not embed photos in seed JSON.
6. Run the seed/import command documented in the root README against a fresh
   database, then run backend routing tests.

## Safety rules

- `verified: false` means the robot has not surveyed that segment.
- Never promote user submissions directly. They must complete admin review,
  robot verification, and publication.
- Keep source payloads immutable when adding a production ingest adapter. Map
  them into the current normalized fields and retain source/run IDs.
- Validate that line endpoints match their graph nodes and that coordinates are
  inside the Homewood campus bounds before importing.

The editable files are `data/homewood_landmarks.json`,
`data/homewood_graph.json`, and `data/homewood_hazards.json`; evidence assets
live in `backend/static/evidence/`. The public graph endpoint is the quickest
way to inspect the normalized result.
