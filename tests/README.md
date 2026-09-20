# Tests

Three layers, because each catches a class the others cannot.

    python3 -m planner.build_cache        # once, ~40s, if graph_cache.json is absent
    python3 -m unittest discover tests    # layers 1 and 2 — ~0.2s, no network
    uvicorn planner.server:app --host 127.0.0.1   # then, in other shells:
    cd frontend && npm run dev
    node tests/smoke_frontend.mjs         # layer 3, ~40s, needs Chrome

Or all of it: `./tests/run.sh`, which starts and stops both servers itself.

## 1. Planner unit — `test_planner.py`

Does A* return a sane route? Name resolution, the four statuses, and the
invariants that must hold whatever the numbers become: the geometry is a
drawable LineString in Baltimore, the reported distance matches the line that
is actually drawn, there are no jumps, the legs sum to the total, endpoints
match the named doors. Plus the two behaviours the planner exists for — the
Decker Quad shortcut and the garage lift — and that no shortcut crosses a
building.

The distance check earns its place: the reported figure disagreed with the
drawn line twice while this was being built, once from snapping and once from
picking the wrong parallel edge.

## 2. Pipeline contract — `test_pipeline.py`

The seams. **This is the layer that catches what typecheck cannot.** A field
can be declared in `RouteSummary`, branched on in `RoutePicker`, and never
written by the exporter: it compiles, it lints, and the branch is dead. That
happened with `stepsBesideShortcut`, so:

- every field the `RouteOk`, `Saved` and `summary` TypeScript types declare is
  actually returned by `plan_route`
- every `summary.<field>` and `saved.<field>` `RouteResult.tsx` reads is
  actually returned
- every fixture trip has a GeoJSON, with no orphans
- each GeoJSON's geometry matches its summary row
- all three profiles solve both example trips
- the accessible profiles never take a shortcut and never take a step
- reported minutes are real minutes, not the weighted cost A* minimises — that
  bug showed a nine-minute walk as twenty-four
- the switch changes nothing for the accessible profiles

To see it work, make `RouteResult.tsx` read `summary.totallyMadeUp` and watch
a test name it.

## 3. Frontend smoke — `smoke_frontend.mjs`

Drives the real page in headless Chrome over CDP, against a running planner
service, and asserts what a user sees: the place list arrives from the API,
the smarter route reaches the garage lift and says what it saved, flipping the
switch produces a different and longer route ending at the building centre, an
ambiguous name offers its candidates instead of being resolved silently, no
4xx and no console errors.

Two `role=switch` elements exist — campus data, and the planner — so every
selector is scoped to the form. An unscoped `querySelector` toggles the wrong
one and the test passes anyway; that happened.

Headless Chrome needs `--use-angle=swiftshader`, otherwise MapLibre renders
nothing and every map assertion passes against a blank canvas.

## Not covered

**Whether a route is a good route.** The tests check it is well-formed,
connected and consistent with the data. Whether it matches how people really
walk is what the robot survey is for.
