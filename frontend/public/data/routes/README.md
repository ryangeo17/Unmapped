# Example routes

Two walking trips, solved by the `planner` package.
`scripts/route_examples.py` is a thin wrapper that writes these files; the
planner itself, its contract and its limits live in [`planner/SKILL.md`](../../../../planner/SKILL.md).

    python3 scripts/route_examples.py

**Walking only.** Accessibility routing is a separate feature and produces no
files here.

| | Walking | Walking (shortcuts) |
|---|---|---|
| **Malone → Clark** | 1.9 min, 149 m, 3 steps | **1.8 min, 122 m**, cuts 80 m across Decker Quad |
| **Malone → San Martin Garage** | 8.2 min, 648 m | 8.2 min, 648 m |

Malone → Clark is the one that shows the shortcut earning its place: the paved
line takes three steps and 27 m more than the diagonal across Decker Quad. On
the garage trip the two are identical — the lawns are not on the way — and the
whole saving there comes from finishing at `San Martin Garage Elevator EL2`
rather than at the building centre, which is 169 m further round the block.

## Caveats

- **Undirected.** `travel_direction` is filled on 16% of segments, so one-way
  restrictions are not modelled.
- **No slope.** There is no elevation in this data.
- **Endpoints snap to the graph** at about 0.9 m, and 17% of segment endpoints
  are still dangling, so some pavement is unreachable.
- **Shortcut edges are inferred, not surveyed.** Nothing in this data describes
  the surface of a line drawn across grass.
