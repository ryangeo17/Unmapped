# Example routes

Two trips, three modes each, solved by `scripts/route_examples.py` against the
graph built from `Pathways.geojson`. Regenerate with:

    python3 scripts/route_examples.py

| | Walking | Walking (shortcuts) | Partially accessible | Fully accessible |
|---|---|---|---|---|
| **Malone → Clark** | 1.9 min, 149 m, **3 risers** | **1.8 min, 122 m**, cuts 80 m over Decker Quad | 2.3 min, 181 m | 2.3 min, 181 m |
| **Malone → San Martin Garage** | 10.4 min, 816 m, **48 risers** | **8.2 min, 648 m**, ends at the garage lift | 10.5 min, 825 m | 11.1 min, 870 m, 71% compliant |

Malone → Clark is the clean demo: the walking route saves 32 m by taking three
steps, and the step-free route is the same trip 0.4 min longer. Malone → San
Martin Garage is the one that shows the modes really diverging — 48 risers
avoided for 9 m, and another 45 m buys a route that is 71% fully compliant
instead of 59%.

## Cost model

Each mode is a hard filter plus a weight on `walktime`:

| Mode | Blocked | Weight | Extras |
|---|---|---|---|
| `walking` | nothing | 1.0 | — |
| `smart` | nothing | 1.0 | lawn shortcuts, any entrance |
| `partial` | stairs (`pathway_type=2`), `NonCompliant` | 1.5 on `PartiallyCompliant` | — |
| `accessible` | stairs, `NonCompliant` | 8.0 on `PartiallyCompliant` | — |

## The `smart` walking mode

Two things the official network does not model.

**Lawn shortcuts.** `scripts/shortcuts.py` adds straight edges between network
nodes whose connecting line stays on an `Exterior_Spaces` lawn — 933 of them
across 12 quads, most in Keyser (400) and Wyman (241). A candidate has to run
15–250 m, keep 85% of its sampled length inside the lawn, and cross no building
or barrier. They are priced at 1.05 m/s against the 1.31 m/s the network's own
`walktime` implies, so A* only takes one when it genuinely saves time. Decker
Quad contributes 43, one of which is the 80 m diagonal on the Clark trip.

**Any entrance counts.** `Entryways.facility_id` is filled on 4 of 337 rows, so
entrances are matched to a building by geometry and name instead. Lifts count:
San Martin Garage has no entryway at all, so the other modes aim at the
building centre and walk 169 m further round the block, while `smart` finishes
at `San Martin Garage Elevator EL2`. Footprints overlap — San Martin Center
sits on top of the Garage — so a point inside a building is only claimed when
its own name does not belong to a different one, otherwise the garage inherits
the Center's stair entrance.

**Shortcut edges are not wheelchair-safe.** Nothing in this data describes the
surface, kerb or slope of a line drawn across grass, so they are offered to
walking only.

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
