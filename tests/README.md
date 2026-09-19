# Tests

Three layers, because each catches a class the others cannot.

    python3 -m planner.build_cache        # once, ~40s, if graph_cache.json is absent
    python3 -m unittest discover tests    # layers 1 and 2, ~0.2s
    cd frontend && npm run dev            # then, in another shell:
    node tests/smoke_frontend.mjs         # layer 3, ~40s, needs Chrome

Or all of it: `./tests/run.sh`.

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

- every field declared in `routes.ts` is actually exported
- every `route.<field>` the component reads is actually exported
- every exported trip has a GeoJSON, with no orphans
- each GeoJSON's geometry matches its summary row
- every declared tool is dispatchable, and the reverse
- the schema advertises no parameter `plan_route` does not accept
- every field in `summary` appears in `SKILL.md`
- the step caveat is in `tool_schema.json` too, not only in `SKILL.md`, since
  a caller may wire up the declarations without ever reading the skill

To see it work, delete `"stepsBesideShortcut"` from `scripts/route_examples.py`,
re-export, and watch two tests name the field.

## 3. Frontend smoke — `smoke_frontend.mjs`

Drives the real page in headless Chrome over CDP and asserts what a user sees:
both trips listed, the Clark card reporting its lawn crossing and its nearby
steps and never claiming step-free, the garage card arriving at the lift, no
4xx and no console errors.

Headless Chrome needs `--use-angle=swiftshader`, otherwise MapLibre renders
nothing and every map assertion passes against a blank canvas.

## Not covered

- **The Gemini round trip.** `gemini_agent.py` needs an API key and a live
  model, so it is not in the suite. The tool layer beneath it is: layer 2
  checks the declarations against the dispatch table and the signature, which
  is where the mismatches actually happen.
- **Whether a route is a good route.** The tests check it is well-formed,
  connected and consistent with the data. Whether it matches how people really
  walk is what the robot survey is for.
