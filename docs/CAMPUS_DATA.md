# JHU Homewood campus data

Exported from web map `ea3919e7b5c242ffa8cafb87399b6901` ("Homewood Campus
Indoors Viewer") on portal `https://map.jhu.edu/portal`, 2026-09-19, by
`scripts/indoors_dump.py`. Coordinates are WGS84 lon/lat (wkid 4326).

This is the field reference for everything under `frontend/public/data/`. Read
§2 before writing any join: several foreign keys do not behave the way the
AIIM documentation says they do.

---

## 0. Read this first: there is no room data

**Units and Levels do not exist in this deployment.** Not a permissions
problem, not a bug in the exporter:

| How it was checked | Result |
|---|---|
| The web map's 9 operational layers | No Units / Levels / Details |
| All 7 folders and 19 services under `/arcgis/rest/services` | No Units / Levels / Details / Transitions / Occupants service anywhere |
| `Indoors/Sites/MapServer`, probed id by id (0–25) | Only id 24 = Sites; every other id 404s |
| The official mobile package `Homewood_Campus_Indoors_Mobile.mmpk` (4.9 MB, public) | The tables exist but hold **0 rows** for `Units`, `Levels`, `Details` and `Occupants` |

The runtime geodatabase inside the mobile package has the full AIIM schema, and
the indoor-space tables are empty. JHU publishes down to **building footprints,
the path network and entrances**, and no further.

So: **room numbers, room names and room use classifications are not available.**
The finest granularity is building + floor ordinal + path segment. §3 lists the
closest substitutes.

The mobile package does hold two tables the public services do not, if floor
connectivity is ever needed: `Transitions` (67 rows, cross-floor links) and
`Stairs` (270 rows). Note it is an older snapshot — 94 facilities against 100
live — so the services are fresher.

---

## 1. Layers

All 9 exported successfully.

| Layer | File | Geometry | Features | What it is |
|---|---|---|---|---|
| Sites | `Sites.geojson` | Polygon | **1** | Campus boundary; all of Homewood is one polygon |
| Facilities | `Facilities.geojson` | Polygon | **100** | Building footprints. The core layer |
| Exterior Spaces | `Exterior_Spaces.geojson` | Polygon | **16** | Named outdoor spaces (quads, the Beach, courtyards), modelled as pseudo-buildings |
| Pathways | `Pathways.geojson` | Polyline | **2146** | The path network. Indoor and outdoor are both in here |
| Polygon Barriers | `Polygon_Barriers.geojson` | Polygon | **7** | Construction and temporary closures, as avoidance areas |
| Landmarks | `Landmarks.geojson` | Point | **22** | Landmarks (lifts, quads, tunnel entrances) |
| Elevators | `Elevators.geojson` | Point | **15** | Lifts, with photos |
| Entryways-All | `Entryways-All.geojson` | Point | **337** | Every entrance |
| Entryways-Accessible | *(not exported)* | Point | 337 | The same service layer with **identical data**; only the styling and default visibility differ in the web map |

> Both Entryways entries point at the same URL
> (`Hosted/Entryways/FeatureServer/0`) with no definitionExpression, so only
> one file is kept. Filter `accessible_entrance = 'Y'` yourself for the 89
> step-free ones.

### Filters defined in the web map

Only Pathways carries a `definitionExpression`: `pathdisplay IS NULL`. But
`pathdisplay` is **NULL on all 2146 rows**, so the filter is a no-op and the
exported 2146 are exactly what the app displays. The exporter keeps everything
by default; `--apply-filters` applies the original expression.

---

## 2. How the layers relate

```
                    Sites  (1)
                      │  NAME = "Homewood Campus"
                      │
                      │  ⚠ join on NAME, not SITE_ID.
                      │     Sites.SITE_ID is a single space " ", useless.
                      │
              Facilities.site_id
                      │
                      ▼
            ┌─── Facilities (100) ───┐
            │   PK: facility_id      │   ← the only dependable foreign key
            │   (4-char string, "0741")
            └────────────────────────┘
                      ▲
        ┌─────────────┼──────────────┬───────────────┐
        │             │              │               │
   facility_id   facility_id    facility_id      (no key)
   92/2146 ✓      4/337 ⚠        0/15 ✗        by geometry/name
        │             │              │               │
    Pathways      Entryways      Elevators       Landmarks
     (2146)         (337)           (15)            (22)


   Exterior Spaces (16) — identical field structure to Facilities, but
     facility_id uses its own code space ("00X13", "00X01") with zero
     overlap. Treat it as an independent layer.

   Polygon Barriers (7) — no foreign keys at all, purely spatial.

   Levels / Units / Details ———— do not exist (see §0)
        ↑
   Pathways.level_id, Landmarks.level_id and Elevators.level_id are all
   dangling references to them.
```

### Measured foreign-key coverage

Counted row by row after export. **Do not assume the AIIM documentation:**

| Relationship | Reality |
|---|---|
| `Facilities.site_id` → `Sites.NAME` | 100/100 match. **Joins on NAME, not SITE_ID** |
| `Pathways.facility_id` → `Facilities.facility_id` | Only 92/2146 populated; all of those match. The other 2054 are outdoor segments |
| `Entryways.facility_id` → `Facilities.facility_id` | Only **4/337** populated. Effectively unfilled — use a spatial join |
| `Elevators.facility_id` | **NULL on all 15**, as is `facility_name`. Only `description` ("Ames Hall Elevator") gives a hint |
| `Exterior_Spaces.facility_id` | 16/16 populated but **zero overlap** with Facilities; separate code space |
| `*.level_id` → `Levels` | Levels does not exist. 1521 Pathways rows are `"0"`, 522 NULL, a few `"0062-03"` (building-floor) |

**Practical advice:** `Facilities.facility_id` is the only join you can trust.
Link Entryways and Elevators to buildings with point-in-polygon or nearest-
neighbour yourself. `scripts/campus/places.py` does exactly that.

### How floors are represented

With no Levels layer, floor information is scattered across integer fields:

- `Pathways.vertical_order` — observed values `-2, -1, 0, 1, 2, 3, 4` (2071 rows are 0)
- `Entryways.geo_level` — has a coded domain, see §5
- `Elevators.vertical_order`, `Landmarks.vertical_order`
- `Pathways.level_name_from` / `level_name_to` — mostly a single space `" "`, unusable

**Use the `vertical_order` / `geo_level` integers for floor switching, never
`level_id`.**

---

## 3. Room number, room name, use classification

In standard AIIM these live in `Units` (`UNIT_ID` / `NAME` / `USE_TYPE`). That
table does not exist here. Its schema in the mobile package, as an interface
placeholder for whenever JHU publishes it:

```
Units: UNIT_ID, USE_TYPE, NAME, NAME_LONG, LEVEL_ID, SCHEDULE_EMAIL,
       CAPACITY, AREA_ID, ASSIGNMENT_TYPE, AREA_GROSS, HEIGHT_RELATIVE,
       RESERVATION_METHOD, ORG_AREA_ID, ALLOCATIONS, SHAPE
Levels: LEVEL_ID, NAME, NAME_SHORT, LEVEL_NUMBER, FACILITY_ID,
        AREA_GROSS, HEIGHT_RELATIVE, VERTICAL_ORDER, SHAPE
```

The closest substitutes in what does exist:

| What you want | Field | Layer | Notes |
|---|---|---|---|
| Room number | — | — | Unavailable. The finest is the building's `facility_id` (`"0741"`) |
| Building number | `facility_id` | Facilities | 4-char string, same values as `archibus_id` |
| Building name | `name` | Facilities | 100/100 populated. `name_long` is **identical**; do not read both |
| Short name | `name_alias` | Facilities | Only 12 populated (`MSEL`, `AMR 1`…). Useful as a search alias |
| **Use classification** | `primary_use` | Facilities | See §5. 92/100 populated |
| Outdoor space name | `name` | Exterior Spaces | `The Beach`, `Decker Quad` and so on |
| Entrance name | `entrance_name` | Entryways | 314/337 populated |
| Lift name | `description` | Elevators / Landmarks | e.g. `Ames Hall Elevator` |
| Building photo | `image_url` | Facilities | 86/100 populated |
| Address | `address` | Facilities | |
| Campus grouping | `campus` | Facilities | `Homewood` 60 / `Homewood Off` 26 / `Homewood Housing` 13 |

---

## 4. Labels and scale thresholds

Only two layers define labels, both as Arcade expressions (`docs/labels.csv`):

| Layer | Expression | minScale | maxScale | Placement | Font |
|---|---|---|---|---|---|
| Facilities | `$feature.NAME` | **2000** | 0 (no limit) | AlwaysHorizontal | Arial 10 |
| Exterior Spaces | `$feature.NAME` | none | 0 | AlwaysHorizontal | Arial 8 |

`minScale: 2000` means the building name is drawn only when the scale
denominator is 2000 or less, i.e. zoomed in past 1:2000. Exterior Spaces
labels draw at every scale. The other 7 layers have no label classes; draw
names yourself if you want them.

Layer visibility has its own thresholds (`minScale` = not drawn when the
denominator exceeds it):

| Layer | minScale | Meaning |
|---|---|---|
| Facilities | 50000 | Visible from 1:50000 — appears first |
| Pathways | 1000 | Only from 1:1000 |
| Exterior Spaces | 1000 | Same |
| Elevators / Landmarks / Entryways | 1500 | 1:1500 |
| Sites / Polygon Barriers | 0 | Always visible |

Copy these numbers to reproduce the official map's layering.

---

## 5. Coded domains

The complete list is the `codedValues` column of `docs/fields.csv`. The ones
that matter:

### `Facilities.primary_use` — building use (observed distribution)

| Value | Count |
|---|---|
| Research | 22 |
| Residence Hall | 17 |
| Office | 17 |
| Mixed Use | 7 |
| Instruction | 6 |
| Administration | 5 |
| Recreation | 5 |
| Library | 4 |
| Parking Garage | 4 |
| Power Plant | 3 |
| Multifamily | 2 |
| *(NULL)* | 8 |

The domain also defines `Dormitory`, `Parking` and `Storage`, which do not
occur in the current data. **Code and name are identical in this domain** —
display it directly, no lookup needed.

### `Pathways.pathway_type` — numeric, lookup required

| Code | Name | Count |
|---|---|---|
| 1 | Hallway / Sidewalk | 1900 |
| 2 | Stairs / Curb | 191 |
| 3 | Ramp / Curb Ramp | 55 |
| 4 | Elevator / Wheelchair Lift | 0 |
| 5 | Escalator | 0 |
| 6 | Moving Walkway | 0 |

### `Pathways.travel_direction`

| Code | Name |
|---|---|
| 1 | Both Directions Allowed |
| 2 | From-To Allowed |
| 3 | To-From Allowed |

Populated on 338 of 2146 rows, and only ever `1`, so nothing is actually
one-way today.

### `Pathways.pathway_rank`

| Code | Name |
|---|---|
| 1 | Primary |
| 2 | Secondary |
| 3 | Tertiary |

`1` on 2142 of 2146 rows — effectively a constant. Anything derived from it is
a constant too.

### `Pathways.location_class` — indoor/outdoor

| Value | Count |
|---|---|
| Exterior | 1391 |
| Interior | 85 |
| Semi_Enclosed | 37 |
| Covered_Exterior | 35 |
| Elevated | 5 |
| Underground | 2 |
| *(NULL)* | 591 |
| Other | 0 |

Note the underscores. A filter written as `'Covered Exterior'` matches nothing,
and a `<>` comparison against a NULL-heavy column drops every NULL row.

### `Pathways.ihcd2021routesurveycode` — the accessibility grade

| Code | Name |
|---|---|
| FullyCompliant | Compliant Accessible Route |
| PartiallyCompliant | Partially Compliant |
| NonCompliant | May Have Travel Hazards |
| Other | Other |

Populated on all 2146 rows: 881 / 533 / 732. This is the one real
accessibility signal in the dataset, and it maps to the three travel modes of
JHU's own routing service: `Fully Accesible Pathway`,
`Partially Accessible Pathway`, `Walking` (the misspelling is theirs — copy it
verbatim if you call that service).

### `Pathways.pathdisplay`

| Code | Name |
|---|---|
| Building_Center_Path | Building Center Path |
| Block | Block |
| Hidden | Hidden |

NULL on all 2146 rows.

### `Pathways.suffix_type`

`Hallway` / `Sidewalk` / `Stairs` / `Curb` / `Ramp` / `Curb Ramp` / `Elevator` /
`Wheelchair Lift` / `Escalator` — code and name identical.

### `Entryways.geo_level` — which floor an entrance is on

| Code | Name | Count |
|---|---|---|
| -2 | Sub-Basement | 2 |
| -1 | Basement | 28 |
| 0 | Ground Floor | 51 |
| 1 | 1st Floor | 202 |
| 2 | 2nd Floor | 46 |
| 3 | 3rd Floor | 7 |
| 4 | 4th Floor | 1 |

### Entryways Y/N booleans

`accessible_entrance`, `automatic_door`, `magnetic_swipe`, `isa_sign` — all
`Y=Yes; N=No`. Measured: `accessible_entrance` is Y on 89, N on 248.

`Entryways.use_type` is NULL on 332 of 337; the remaining 5 say
`Not on Accessible Route`. Effectively unusable.

### `Landmarks.landmark_type`

| Value | Count |
|---|---|
| Elevator | 14 |
| Quad | 6 |
| Tunnel Entrance | 2 |
| Art Installation | 0 |
| Other | 0 |

### `Facilities` / `Exterior Spaces` `.below_grade`

`Y=Yes; N=No`.

### `validationstatus`, every layer

An AIIM internal validation bitmask, 0–7, where `0` means no error. Ignore it
in the frontend.

---

## 6. What this data does **not** contain

Worth stating plainly, because it determines what the app can honestly claim.
The Pathways layer has 30 fields, and **none of them is slope, roughness,
surface, lighting or security**. There is no elevation anywhere in the dataset
(`hasZ` is false).

Anything presenting those as measurements is presenting an inference. Where
this app needs them, the columns are null and the route says so.

---

## 7. Notes for the frontend

- Building fills and names: `Facilities.geojson`, `name` + `primary_use`;
  visible from 1:50000, labelled from 1:2000.
- Search index: `Facilities.name` + `name_alias` + `address` +
  `Exterior_Spaces.name` + `Entryways.entrance_name`.
- Floor switching: the `vertical_order` integer (Pathways / Elevators /
  Landmarks) and `geo_level` (Entryways), range -2 to 4.
- Highlighting indoor segments: `location_class IN ('Interior','Underground')`.
- Construction avoidance: `Polygon_Barriers.geojson`. `expected_end_date` is a
  millisecond timestamp, NULL on 3 of the 7 (indefinite closures).
- Linking Entryways or Elevators to buildings needs a spatial computation; the
  service's `facility_id` is not filled in.

## 8. Re-running the export

```bash
python3 scripts/indoors_dump.py --defs-only       # schema only, no features
python3 scripts/indoors_dump.py                   # everything, ~2900 features, 3.3 MB
python3 scripts/indoors_dump.py --only Facilities # one layer (leaves csv/index alone)
python3 scripts/indoors_dump.py --apply-filters   # apply the web map's definitionExpression
```

The output directory is gitignored; the files under `frontend/public/data/`
were copied from it. The upstream is someone else's production service — do not
put this in a development loop.
