"""The planner entry point: plan_route().

Walking only. Accessibility routing — stair and hazard filters, surface
grading, robot observations — is a separate feature and deliberately not
modelled here.

The result is shaped for two consumers at once: a model that has to explain the
route in words, and a frontend that has to draw it. Geometry always comes from
A*; a model must never invent it.
"""
import collections
import heapq

from . import graph, profiles
from .geometry import metres
from .places import Places

WALK_FPS = 4.6      # only used to keep the A* heuristic admissible

_state = {}


def _load():
    if not _state:
        _state["edges"] = graph.load_edges()["edges"]
        _state["places"] = Places(
            graph.load("Facilities.geojson"),
            graph.load("Exterior_Spaces.geojson"),
            graph.load("Entryways-All.geojson"),
            graph.load("Elevators.geojson"),
        )
    return _state


def places():
    return _load()["places"]


_graphs = {}


def _graph(profile, shortcuts):
    """Cached per (profile, shortcuts): the filter never changes, and rebuilding
    the adjacency on every request was measurable."""
    cfg = profiles.PROFILES[profile]
    cache_key = (profile, shortcuts)
    if cache_key in _graphs:
        return _graphs[cache_key]
    adj = collections.defaultdict(list)
    for e in _load()["edges"]:
        props = e["p"]
        if props.get("shortcut") and not shortcuts:
            continue
        if not profiles.allows(cfg, props):
            continue
        edge = (e["min"] * profiles.weight(cfg, props), e["m"], props, e["min"])
        adj[e["a"]].append((e["b"], edge))
        adj[e["b"]].append((e["a"], edge))
    _graphs[cache_key] = adj
    return adj


def _nearest(adj, point):
    return min(adj, key=lambda n: metres(n, point))


def _astar(adj, starts, goals):
    """Multi-source, multi-target: any door of either building will do."""
    goals = set(goals)
    heap = [(0.0, s) for s in starts]
    heapq.heapify(heap)
    came, g, seen = {}, {s: 0.0 for s in starts}, set()
    heuristic = lambda n: min(metres(n, t) for t in goals) * 3.28084 / WALK_FPS / 60
    while heap:
        _, node = heapq.heappop(heap)
        if node in goals:
            path, edges = [node], []
            while node in came:
                node, edge = came[node]
                path.append(node)
                edges.append(edge)
            return list(reversed(path)), list(reversed(edges))
        if node in seen:
            continue
        seen.add(node)
        for nxt, edge in adj[node]:
            cost = g[node] + edge[0]
            if cost < g.get(nxt, float("inf")):
                g[nxt] = cost
                came[nxt] = (node, edge)
                heapq.heappush(heap, (cost + heuristic(nxt), nxt))
    return None, None


def _character(props):
    if props.get("shortcut"):
        return "shortcut"
    if props.get("pathway_type") == 2:
        return "steps"
    if props.get("location_class") in ("Interior", "Underground"):
        return "indoor"
    return "paved"


def _steps(path, edges):
    """Runs of consecutive edges sharing a character, so a model has something
    to narrate and a frontend something to list."""
    out = []
    for i, edge in enumerate(edges):
        props = edge[2]
        kind = _character(props)
        name = props.get("directions_name_text") or props.get("space")
        if out and out[-1]["kind"] == kind and out[-1]["name"] == name:
            step = out[-1]
        else:
            step = {"kind": kind, "name": name, "metres": 0.0, "minutes": 0.0,
                    "from": list(path[i])}
            out.append(step)
        step["metres"] += edge[1]
        step["minutes"] += edge[3]
        step["to"] = list(path[i + 1])
    for step in out:
        step["metres"] = round(step["metres"], 1)
        step["minutes"] = round(step["minutes"], 2)
    return out


def plan_route(origin, destination, profile=profiles.DEFAULT, smarter=True):
    """Plan one route between two free-text place names.

    `profile` picks which of the three answers this is. `smarter` is the
    product switch and only reaches walking: on, it may cut across open lawn
    and finish at any door including a car-park lift, and the result carries
    what that saved against the plain paved line. The accessible profiles
    ignore it — a shortcut inferred from geometry has no business in an
    accessibility answer.

    Nothing is forced: shortcuts and side doors are priced, so A* takes one
    only when it is genuinely faster.
    """
    pl = places()
    if profile not in profiles.PROFILES:
        return {"status": "error",
                "error": "unknown profile %r; use one of %s"
                         % (profile, profiles.ORDER)}
    cfg = profiles.PROFILES[profile]
    shortcuts = smarter and profile in profiles.SHORTCUT_PROFILES

    a, a_alts = pl.resolve(origin)
    b, b_alts = pl.resolve(destination)
    for field, place, query, alts in (("origin", a, origin, a_alts),
                                      ("destination", b, destination, b_alts)):
        if place:
            continue
        if alts:
            return {"status": "ambiguous", "field": field, "query": query,
                    "candidates": alts,
                    "error": "%s matches %d places; ask which one"
                             % (field, len(alts))}
        return {"status": "error", "field": field,
                "error": "could not resolve %s %r" % (field, query)}

    adj = _graph(profile, shortcuts)
    # Lifts are a step-free way in, so the accessible profiles always see them;
    # for walking they are part of what the switch buys.
    doors = lambda place: pl.entrances(
        place, lifts=shortcuts or cfg["stepFreeDoors"],
        step_free=cfg["stepFreeDoors"])
    start_at = {_nearest(adj, d["point"]): d for d in doors(a)}
    end_at = {_nearest(adj, d["point"]): d for d in doors(b)}

    path, edges = _astar(adj, start_at, end_at)
    if not path:
        return {"status": "no_route",
                "origin": {"query": origin, "resolved": a["properties"]["name"]},
                "destination": {"query": destination,
                                "resolved": b["properties"]["name"]},
                "error": "no walking route between these buildings"}

    total_m = sum(e[1] for e in edges)
    minutes = sum(e[3] for e in edges)
    shortcut_m = sum(e[1] for e in edges if e[2].get("shortcut"))
    spaces = sorted({e[2].get("space") for e in edges if e[2].get("shortcut")})
    risers = sum(e[2].get("riser_count") or 0 for e in edges
                 if e[2].get("pathway_type") == 2)

    # A shortcut can land on the far side of a step link and make the route
    # look step-free when the ground is not. The graph is flat — hasZ is false
    # and there is no elevation anywhere in this data — so the only honest
    # thing is to say a level change may be there rather than report zero.
    beside = 0
    for i, edge in enumerate(edges):
        if not edge[2].get("shortcut"):
            continue
        for node in (path[i], path[i + 1]):
            for _, other in adj[node]:
                if other[2].get("pathway_type") == 2:
                    beside = max(beside, other[2].get("riser_count") or 0)

    warnings = []
    if shortcut_m:
        warnings.append(
            "%.0f m of this route crosses open lawn (%s)."
            % (shortcut_m, ", ".join(spaces)))
    if beside:
        warnings.append(
            "A shortcut joins the paved network beside a %d-step flight. This "
            "data has no elevation, so whether you meet those steps depends on "
            "the level of the grass." % beside)

    origin_door = start_at[path[0]]
    dest_door = end_at[path[-1]]

    # What the switch bought. Cheap — a second A* over the same cached graph —
    # and it is the only way the toggle means anything to the person using it.
    saved = None
    if shortcuts:
        plain = plan_route(origin, destination, profile, smarter=False)
        if plain["status"] == "ok":
            saved = {
                "plainMetres": plain["summary"]["metres"],
                "plainMinutes": plain["summary"]["minutes"],
                "savedMetres": round(plain["summary"]["metres"] - total_m, 1),
                "savedMinutes": round(plain["summary"]["minutes"] - minutes, 1),
                "plainArrival": plain["destination"]["arrival"],
            }

    if cfg["stepFreeDoors"]:
        warnings.append(
            "Step-free here means no steps in the routing network. 39% of the "
            "basemap's stair footprints are not modelled as network segments, "
            "so steps are still possible.")

    return {
        "status": "ok",
        "profile": profile,
        "profileLabel": (cfg.get("smartLabel") if shortcuts else cfg["label"]),
        "smarter": shortcuts,
        "origin": {
            "query": origin, "resolved": a["properties"]["name"],
            "arrival": origin_door["label"], "kind": origin_door["kind"],
            "point": list(path[0]),
        },
        "destination": {
            "query": destination, "resolved": b["properties"]["name"],
            "arrival": dest_door["label"], "kind": dest_door["kind"],
            "point": list(path[-1]),
        },
        "summary": {
            "minutes": round(minutes, 1),
            "metres": round(total_m, 1),
            "feet": round(total_m * 3.28084),
            "steps": risers,
            "stepsBesideShortcut": beside,
            "shortcutMetres": round(shortcut_m, 1),
            "shortcutSpaces": spaces,
        },
        # Ready to hand straight to a GeoJSON source.
        "geometry": {"type": "LineString", "coordinates": [list(p) for p in path]},
        "legs": _steps(path, edges),
        "savedBySmarter": saved,
        "warnings": warnings,
    }


def plan_all(origin, destination, smarter=True):
    """All three answers for one trip, so the UI can offer them without a
    request per option."""
    return {"routes": [plan_route(origin, destination, p, smarter)
                       for p in profiles.ORDER]}
