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

- every field the `RouteOk`, `Saved` and `summary` TypeScript types declare is
  actually returned by `plan_route`
- every `summary.<field>` and `saved.<field>` `RouteResult.tsx` reads is
  actually returned
- every fixture trip has a GeoJSON, with no orphans
- each GeoJSON's geometry matches its summary row
- every declared tool is dispatchable, and the reverse
- the schema advertises no parameter `plan_route` does not accept
- every field in `summary` appears in `SKILL.md`
- the step caveat is in `tool_schema.json` too, not only in `SKILL.md`, since
  a caller may wire up the declarations without ever reading the skill

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
