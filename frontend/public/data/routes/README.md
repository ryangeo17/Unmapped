# Example routes

Two trips, three modes each, solved by `scripts/route_examples.py` against the
graph built from `Pathways.geojson`. Regenerate with:

    python3 scripts/route_examples.py

| | Walking | Partially accessible | Fully accessible |
|---|---|---|---|
| **Malone → Clark** | 1.9 min, 149 m, **1 stair segment (3 risers)** | 2.3 min, 181 m, step-free | 2.3 min, 181 m, step-free |
| **Malone → San Martin Garage** | 10.4 min, 816 m, **4 stair segments (48 risers)** | 10.5 min, 825 m, step-free | 11.0 min, 870 m, step-free, 71% fully compliant |

Malone → Clark is the clean demo: the walking route saves 32 m by taking three
steps, and the step-free route is the same trip 0.4 min longer. Malone → San
Martin Garage is the one that shows the modes really diverging — 48 risers
avoided for 9 m, and another 45 m buys a route that is 71% fully compliant
instead of 59%.

## Cost model

Each mode is a hard filter plus a weight on `walktime`:

| Mode | Blocked | Weight |
|---|---|---|
| `walking` | nothing | 1.0 |
| `partial` | stairs (`pathway_type=2`), `NonCompliant` | 1.5 on `PartiallyCompliant` |
| `accessible` | stairs, `NonCompliant` | 8.0 on `PartiallyCompliant` |

**Fully compliant cannot be a hard filter.** Keeping only `FullyCompliant`
segments splits the network into 165 components, the largest holding 276 of
1746 nodes, so most building pairs have no route at all. The official grading
leaves too many connector segments partially compliant. Penalising keeps the
graph whole and still prefers good surface — that is why `accessible` takes
the longer 870 m line.

## Caveats

- **Undirected.** `travel_direction` is filled on 16% of segments, so one-way
  restrictions are not modelled.
- **No slope.** There is no elevation in this data, so the skateboard/bike
  mode in `design.md` still needs USGS.
- **Endpoints snap to the graph.** Malone and Clark resolve to named
  entryways; San Martin Garage has none, so it uses the building centroid and
  the route ends inside the garage footprint.
- **Nodes snap at 5 decimals (~0.9 m).** Tighter leaves more of the network
  disconnected; 17% of endpoints are dangling even so.
- Stairs the routing network does not model are a real risk here — 39% of the
  basemap's stair polygons sit more than 10 m from any stair segment, so a
  step-free route can still meet steps. See `../surfaces/README.md`.
