# Campus route planner

Plans a walking route across the JHU Homewood campus and returns real geometry
plus a plain-language breakdown. Built to be called as a tool by a model, and
to be imported directly by Python.

```python
from planner.plan import plan_route
route = plan_route("Malone Hall", "San Martin Garage", "walk_smart")
```

## What this is for, and what it is not for

**The model never computes the path.** The graph holds 3,635 nodes and 4,903
edges; A* solves it exactly in milliseconds, and a language model asked to do
the same will invent coordinates that do not lie on any pavement. The division
of labour is:

| Model | Planner |
|---|---|
| reads the user's situation | filters and weights the graph |
| picks a `profile` | runs A* |
| resolves "the garage" against the place index | returns geometry, distance, time, steps |
| writes the explanation | returns warnings the explanation must include |

**Do not send the campus data to the model.** Pass `place_index()` — about 120
names — so it can resolve free text. Everything else stays server-side.

## Profiles

| `profile` | Blocks | Prefers | Entrances |
|---|---|---|---|
| `walk` | nothing | — | any door or lift |
| `walk_smart` | nothing | lawn shortcuts when faster | any door or lift |
| `step_free` | stairs, hazard-graded segments | — | step-free doors, lifts |
| `accessible` | stairs, hazard-graded segments | fully compliant surface, 8× | step-free doors, lifts |

Pick `walk_smart` by default for someone on foot. Pick `step_free` or
`accessible` when the user mentions a wheelchair, a mobility limit, a pushchair,
crutches, luggage on wheels, or asks to avoid stairs. `accessible` buys better
surface for extra distance; `step_free` is the faster step-free option.

**`walk_smart` is not wheelchair-safe.** Its shortcut edges cross open grass,
and nothing in the data describes their surface, kerbs or slope. Never offer it
in response to an accessibility need.

## Calling it

```
plan_route(origin: str, destination: str, profile: str = "walk_smart") -> dict
compare(origin: str, destination: str, profiles: list[str] | None) -> dict
places().index() -> list[dict]      # name, kind, use, alias
```

`origin` and `destination` are free text. Resolution is exact name, then alias
(`MSEL` → Milton S. Eisenhower Library), then substring, then all-words-match.

## Results

`status` is one of four values and the caller must branch on it.

**`ok`** — a route was found.

```json
{
  "status": "ok",
  "profile": "walk_smart",
  "profileLabel": "Walking (shortcuts)",
  "origin":      {"query": "Malone Hall", "resolved": "Malone Hall",
                  "arrival": "Malone Hall North", "kind": "entrance",
                  "point": [-76.62087, 39.32644]},
  "destination": {"query": "San Martin Garage", "resolved": "San Martin Garage",
                  "arrival": "San Martin Garage Elevator EL2", "kind": "lift",
                  "point": [-76.62352, 39.33062]},
  "summary": {"minutes": 8.2, "metres": 647.5, "feet": 2124,
              "stairSegments": 0, "risers": 0,
              "shortcutMetres": 0, "shortcutSpaces": [],
              "fullyCompliantShare": 0.585},
  "geometry": {"type": "LineString", "coordinates": [[lng, lat], ...]},
  "steps": [{"kind": "paved", "name": null, "metres": 267.6, "minutes": 3.42,
             "risers": 0, "from": [lng, lat], "to": [lng, lat]}],
  "warnings": []
}
```

`geometry` goes straight into a GeoJSON source — do not reformat or round it.
`steps` are runs of consecutive edges sharing a character: `paved`, `stairs`,
`ramp`, `indoor`, `shortcut`. `name` is the segment's own name where the data
has one, such as `Gilman Hall Tunnel`, or the lawn being crossed.

**`ambiguous`** — the query matched several places. Ask which, do not guess.

```json
{"status": "ambiguous", "field": "destination", "query": "the garage",
 "candidates": ["STSCI Parking Garage", "West Gate Garage",
                "San Martin Garage", "South Garage"]}
```

**`no_route`** — the profile's filters disconnect the two buildings.

**`error`** — the name resolved to nothing, or the profile is unknown.

## Rules for a model using this

1. Call the tool. Never write coordinates yourself, and never edit the ones you
   get back.
2. Report `summary.minutes` and `summary.metres` as returned. Do not re-derive
   them from the geometry.
3. Repeat every string in `warnings` to the user. They cover lawn crossings and
   the limits of "step-free"; dropping them is the main way this tool can
   mislead someone with a mobility need.
4. On `ambiguous`, ask. On `no_route`, say which profile failed and offer the
   next most permissive one.
5. Say which door the route arrives at. "Ends at San Martin Garage Elevator
   EL2" is the useful part for a car park; "arrives at San Martin Garage" is
   not.

## Known limits, worth stating when they matter

- **Undirected.** `travel_direction` is populated on 16% of segments, so one-way
  restrictions are not modelled.
- **No slope.** There is no elevation anywhere in this dataset. A cycling or
  skateboarding profile needs USGS data first.
- **Step-free is a claim about the network, not the ground.** 39% of the
  basemap's stair footprints are more than 10 m from any stair segment in the
  routing network, so a step-free route can still meet steps.
- **Outdoor only, one level.** `Levels`, `Units` and `Transitions` are absent
  from this deployment, so there is no indoor or multi-floor routing.
- **Nodes snap at about 0.9 m,** and 17% of segment endpoints are still
  dangling, so some pavement is unreachable.

## Rebuilding

`planner/graph_cache.json` holds the prebuilt graph, including the 933 lawn
shortcuts that take about 40 seconds to derive. Regenerate after the campus
data changes:

    python3 -m planner.build_cache
