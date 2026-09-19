# planner

The campus **walking** route planner, as a package. `SKILL.md` is the contract a
model (or an integrator) reads; this file is how to run it.

Accessibility routing — stair and hazard filters, surface grading, robot
observations — is a separate feature. This module deliberately has none of it.

```
planner/
  SKILL.md            the contract — result shape, rules, limits
  tool_schema.json    function declarations for Gemini / Claude / OpenAI
  plan.py             plan_route() and the A*
  places.py           free text -> building -> the doors you can arrive at
  graph.py            graph assembly and the disk cache
  shortcuts.py        lawn desire-path edges
  geometry.py         planar helpers
  tools.py            name -> function dispatch for a model's tool calls
  server.py           FastAPI front (optional)
  gemini_agent.py     worked example of Gemini calling the tool (optional)
  graph_cache.json    prebuilt graph, regenerate with build_cache
```

## Use it directly

```python
from planner.plan import plan_route
route = plan_route("Malone Hall", "San Martin Garage")
route["geometry"]          # LineString, ready for a GeoJSON source
route["summary"]["minutes"]
route["warnings"]          # must be shown to the user
```

Only the standard library is needed for this. FastAPI is needed for `server.py`
and `google-genai` for `gemini_agent.py`, nothing else.

## Rebuild the graph

Deriving the 933 lawn shortcuts takes about 40 seconds, so it is a build step
and not a per-request cost. Rerun after the campus data changes:

    python3 -m planner.build_cache

## Serve it

    pip install fastapi uvicorn
    uvicorn planner.server:app --reload

    GET  /places      every routable name, ~9 KB
    POST /route       {origin, destination, allow_shortcuts?}

## Give it to a model

    pip install google-genai
    export GEMINI_API_KEY=...
    python3 -m planner.gemini_agent "quickest way from Malone to the garage"

The model gets `tool_schema.json` and `SKILL.md`, and the place index when it
asks. It never receives the graph or the campus GeoJSON: it resolves the place
names and explains the result, while A* produces the geometry. `gemini_agent.ask()`
returns `(answer_text, routes)` so the text goes to the chat pane and the
untouched route objects go to the map.
