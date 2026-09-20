# Replacing demo survey data

All checked-in locations and measurements are synthetic hackathon demo data.
They are deliberately separated from routing and UI logic so the five real
robot surveys can replace records without code changes.

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

The campus-wide fallback graph comes from JHU's public Indoors Pathways and
Facilities layers. Robot-verified demo edges live in
`data/robot_verified_overlay.json` and are merged into `data/homewood_graph.json`.
Evidence assets live in `backend/static/evidence/`. Refresh the JHU layer with
`backend/scripts/import_jhu_indoors.py`. The public graph endpoint is the
quickest way to inspect the normalized result.
