# Campus walking route planner

Plans a walking route across the JHU Homewood campus and returns real geometry
plus a plain-language breakdown. Built to be called as a tool by a model, and
to be imported directly by Python.

```python
from planner.plan import plan_route
route = plan_route("Malone Hall", "San Martin Garage")
```

## Scope

**Walking only.** This module knows nothing about wheelchair access, stairs as
obstacles, surface grading or robot observations. That is a separate feature
with its own data and its own rules. Do not answer accessibility questions from
this planner's output — it will happily route someone up a flight of steps.

## What this is for, and what it is not for

**The model never computes the path.** The graph holds 3,635 nodes and 4,903
edges; A* solves it exactly in milliseconds, and a language model asked to do
the same will invent coordinates that do not lie on any pavement.

| Model | Planner |
|---|---|
| reads what the user wants | runs A* over the campus graph |
| resolves "the garage" against the place index | returns geometry, distance, time, legs |
| decides whether shortcuts are wanted | returns warnings the explanation must include |
| writes the explanation | |

**Do not send the campus data to the model.** Pass `places().index()` — 116
names, about 9 KB — so it can resolve free text. The graph stays server-side.

## Two things this planner models that the official network does not

Both are always on. They are priced into the search rather than offered as
options, so A* takes a shortcut or a side door only when it is genuinely
faster. There is nothing to configure and nothing for a model to choose.

**Lawn shortcuts.** People cut across quads; the official network routes around
them. 933 straight edges cross open lawn where the line stays on grass and
crosses no building, priced at 1.05 m/s against the 1.31 m/s the network's own
walktime implies. Malone → Clark comes back 122 m instead of 149 m because of
one 80 m diagonal over Decker Quad.

**Any entrance counts.** Both ends of the trip may use any door, and a lift
inside a building counts as a door. San Martin Garage has no entryway record at
all, so aiming at the building centre would walk you 169 m further round the
block instead of stopping at `San Martin Garage Elevator EL2`.

## Calling it

```
plan_route(origin: str, destination: str) -> dict
places().index() -> list[dict]      # name, kind, use, alias
```

`origin` and `destination` are free text. Resolution is exact name, then alias
(`MSEL` → Milton S. Eisenhower Library), then substring, then all-words-match.

## Results

`status` is one of four values and the caller must branch on it.

**`ok`**

```json
{
  "status": "ok",
  "origin":      {"query": "Malone Hall", "resolved": "Malone Hall",
                  "arrival": "Malone Hall North", "kind": "entrance",
                  "point": [-76.62087, 39.32644]},
  "destination": {"query": "San Martin Garage", "resolved": "San Martin Garage",
                  "arrival": "San Martin Garage Elevator EL2", "kind": "lift",
                  "point": [-76.62352, 39.33062]},
  "summary": {"minutes": 8.2, "metres": 647.5, "feet": 2124, "steps": 0,
              "stepsBesideShortcut": 0,
              "shortcutMetres": 0, "shortcutSpaces": []},
  "geometry": {"type": "LineString", "coordinates": [[lng, lat], ...]},
  "legs": [{"kind": "paved", "name": null, "metres": 267.6, "minutes": 3.42,
            "from": [lng, lat], "to": [lng, lat]}],
  "warnings": []
}
```

`geometry` goes straight into a GeoJSON source — do not reformat or round it.
`legs` are runs of consecutive edges sharing a character: `paved`, `steps`,
`indoor`, `shortcut`. `name` is the segment's own name where the data has one,
such as `Gilman Hall Tunnel`, or the lawn being crossed.

`summary.steps` counts stair risers the route actually traverses, as
information rather than as a filter. `stepsBesideShortcut` is the caveat on
that number: a shortcut can land on the far side of a short step link, so the
route never traverses it and `steps` reads 0 while a flight is still there on
the ground. Malone → Clark does exactly this — it steps around a 1.4 m,
three-riser link at Clark Hall Main. When `stepsBesideShortcut` is non-zero,
say steps are possible; never report the route as step-free.

**`ambiguous`** — the query matched several places. Ask which, do not guess.

```json
{"status": "ambiguous", "field": "destination", "query": "the garage",
 "candidates": ["STSCI Parking Garage", "West Gate Garage",
                "San Martin Garage", "South Garage"]}
```

**`no_route`** — the two places are not connected in the graph.

**`error`** — the name resolved to nothing.

## Rules for a model using this

1. Call the tool. Never write coordinates yourself, and never edit the ones you
   get back.
2. Report `summary.minutes` and `summary.metres` as returned. Do not re-derive
   them from the geometry.
3. Repeat every string in `warnings` to the user.
4. On `ambiguous`, ask. Do not pick one.
5. Say which door the route arrives at. "Ends at San Martin Garage Elevator
   EL2" is the useful part for a car park; "arrives at San Martin Garage" is
   not.
6. If the user raises a mobility need, say this planner does not cover it
   rather than answering from its output.

## Known limits, worth stating when they matter

- **Undirected.** `travel_direction` is populated on 16% of segments, so one-way
  restrictions are not modelled.
- **No slope.** There is no elevation anywhere in this dataset.
- **Outdoor, one level.** `Levels`, `Units` and `Transitions` are absent from
  this deployment, so there is no indoor or multi-floor routing.
- **Nodes snap at about 0.9 m,** and 17% of segment endpoints are still
  dangling, so some pavement is unreachable.
- **Shortcut edges are inferred, not surveyed.** Nothing in the data describes
  the surface of a line drawn across grass.
- **The graph is flat.** `hasZ` is false and there is no elevation anywhere, so
  a shortcut cannot tell which side of a level change it lands on. See
  `stepsBesideShortcut`.

## Rebuilding

`planner/graph_cache.json` holds the prebuilt graph, including the 933 lawn
shortcuts that take about 40 seconds to derive. Regenerate after the campus
data changes:

    python3 -m planner.build_cache
