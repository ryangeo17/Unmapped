# Example routes

Two walking trips, one route each, solved by the `planner` package.
`scripts/route_examples.py` is a thin wrapper that writes these files; the
planner itself, its contract and its limits live in [`planner/SKILL.md`](../../../../planner/SKILL.md).

    python3 scripts/route_examples.py

**Walking only.** Accessibility routing is a separate feature and produces no
files here.

| | Route | Why it is shorter than the paved line |
|---|---|---|
| **Malone → Clark** | 1.8 min, 122 m | 80 m diagonal across Decker Quad, against 149 m and three steps on pavement |
| **Malone → San Martin Garage** | 8.2 min, 648 m | finishes at `San Martin Garage Elevator EL2`; the building centre is 169 m further round the block |

Lawn shortcuts and entrance choice are priced into the search, not offered as
options, so there is one route per trip rather than a set of variants.

## Caveats

- **Undirected.** `travel_direction` is filled on 16% of segments, so one-way
  restrictions are not modelled.
- **No slope.** There is no elevation in this data.
- **Endpoints snap to the graph** at about 0.9 m, and 17% of segment endpoints
  are still dangling, so some pavement is unreachable.
- **Shortcut edges are inferred, not surveyed.** Nothing in this data describes
  the surface of a line drawn across grass.
