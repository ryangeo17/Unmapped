# planner

The campus route planner, as a package: a pure-Python library, plus an HTTP
front the frontend talks to.

```
planner/
  plan.py             plan_route(), plan_all(), the A*
  profiles.py         the three routes offered for a trip
  places.py           free text -> place -> the doors you can arrive at
  graph.py            graph assembly and the disk cache
  shortcuts.py        lawn desire-path edges
  geometry.py         planar helpers
  server.py           FastAPI front
  graph_cache.json    prebuilt graph, regenerate with build_cache
```

## Profiles

| id | label | Blocks | Shortcuts | Doors |
|---|---|---|---|---|
| `walk` | Walking | nothing | yes, when `smarter` | any, plus lifts |
| `step_free` | Partially accessible | steps, hazard-graded segments | never | step-free only, plus lifts |
| `accessible` | Fully accessible | steps, hazard-graded segments | never | step-free only, plus lifts |

`accessible` additionally weights partially-compliant surface at 8x, buying
better surface for extra distance.

**Grading cannot be a hard filter.** Keeping only `FullyCompliant` segments
splits the network into 165 components, the largest holding 276 of 1746 nodes,
so most building pairs come back with no route at all. That is an artifact of
the filter, not a fact about campus, so `accessible` weights instead of blocks.

**`smarter` only reaches walking.** Shortcut edges are inferred from geometry,
not surveyed — nothing in this data describes the surface, kerb or slope of a
line drawn across grass — so they have no place in an accessibility answer.

## What walking models that the official network does not

**Lawn shortcuts.** 933 straight edges cross open lawn where the line stays on
grass and crosses no building, priced at 1.05 m/s against the 1.31 m/s the
network's own walktime implies, so one is taken only when it saves time.
Malone → Clark comes back 122 m instead of 149 m on one 80 m diagonal over
Decker Quad.

**Any entrance counts.** Both ends may use any door, and a lift inside a
building counts as a door. San Martin Garage has no entryway record at all, so
without this the route aims at the building centre and walks 169 m further
round the block instead of stopping at `San Martin Garage Elevator EL2`.

## Use it directly

```python
from planner.plan import plan_route, plan_all
plan_route("Malone Hall", "San Martin Garage")              # walking, smarter
plan_route("Malone Hall", "San Martin Garage", "accessible")
plan_all("Malone Hall", "San Martin Garage")                # all three
```

Standard library only for this. FastAPI is needed for `server.py`, nothing else.

## Results

`status` is one of four values and the caller must branch on it.

**`ok`** carries `geometry` (a LineString, straight into a GeoJSON source),
`summary`, `legs` (runs of consecutive edges sharing a character: `paved`,
`steps`, `indoor`, `shortcut`), `savedBySmarter` (walking only), and
`warnings`, every string of which must be shown to the user.

`summary.steps` counts risers the route traverses.
`summary.stepsBesideShortcut` is the caveat on that number: a shortcut can land
on the far side of a short step link, so the route never traverses it and
`steps` reads 0 while a flight is still there on the ground. Malone → Clark
does exactly this. When it is non-zero, say steps are possible; never report
the route as step-free.

**`ambiguous`** carries `candidates` — ask, do not guess. "the garage" matches
four. **`no_route`** and **`error`** carry `error`.

## Serve it

    pip install fastapi uvicorn
    uvicorn planner.server:app --reload --host 127.0.0.1

Bind explicitly: on macOS `localhost` resolves to `::1` first, and a server
listening only on `127.0.0.1` refuses the browser's connection.

    GET  /places      every routable name, ~9 KB
    GET  /profiles    the three profiles with descriptions
    POST /routes      {origin, destination, smarter, profile?}

## Rebuild the graph

Deriving the 933 lawn shortcuts takes about 40 seconds, so it is a build step
and not a per-request cost. Rerun after the campus data changes:

    python3 -m planner.build_cache

## Known limits

- **Undirected.** `travel_direction` is populated on 16% of segments, so
  one-way restrictions are not modelled.
- **No slope.** There is no elevation anywhere in this dataset.
- **The graph is flat,** so a shortcut cannot tell which side of a level change
  it lands on. See `stepsBesideShortcut`.
- **Step-free is a claim about the network, not the ground.** 39% of the
  basemap's stair footprints are more than 10 m from any stair segment in the
  routing network.
- **Outdoor, one level.** `Levels`, `Units` and `Transitions` are absent from
  this deployment, so there is no indoor or multi-floor routing.
- **Nodes snap at about 0.9 m,** and 17% of segment endpoints are dangling, so
  some pavement is unreachable.
