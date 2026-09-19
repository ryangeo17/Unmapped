# Tests

Five layers, because each catches a class the others cannot. The first four
cost nothing and need no network.

    python3 -m planner.build_cache        # once, ~40s, if graph_cache.json is absent
    python3 -m unittest discover tests    # layers 1, 2, 4 — ~0.3s, no network
    cd frontend && npm run dev            # then, in another shell:
    node tests/smoke_frontend.mjs         # layer 3, ~40s, needs Chrome

Or everything offline: `./tests/run.sh`. The live Gemini test is separate and
opt-in; see below.

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

## 4. Agent loop, stubbed — `test_agent.py`

No key, no network, no cost. A fake client returns scripted responses, so the
glue between a model and the planner is exercised directly: a function call
reaches the planner and the result comes back, geometry is withheld from the
model while the caller still gets it, warnings and `stepsBesideShortcut` do
reach the model, an ambiguous result arrives as candidates rather than a
route, and a model that only ever calls tools cannot spin forever.

Skipped automatically when `google-genai` is not installed, so the plain
`python3 -m unittest discover tests` still passes on a bare checkout.

## 5. Live Gemini — `live_gemini.py`

The only test that spends money, so it is not in `run.sh`.

    python3 -m venv .venv && .venv/bin/pip install google-genai
    echo 'GEMINI_API_KEY=your-key' >> .env          # .env is gitignored
    .venv/bin/python tests/live_gemini.py

It asserts three things the offline tests cannot: that the model calls the
tool instead of answering from memory and quotes the tool's own numbers, that
an ambiguous name produces a question with the candidates rather than a guess,
and that a wheelchair question is declined rather than answered from a planner
that has no accessibility data.

With no key it prints instructions and exits 2 rather than failing. It also
checks the model id before spending anything: when one is retired it lists the
models the key can reach, rather than throwing a 404 stack. Override with
`GEMINI_MODEL=<id>`.

## Not covered

**Whether a route is a good route.** The tests check it is well-formed,
connected and consistent with the data. Whether it matches how people really
walk is what the robot survey is for.
