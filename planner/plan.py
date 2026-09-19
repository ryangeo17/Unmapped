"""The planner entry point: plan_route().

The result is shaped for two consumers at once — a model that has to explain
the route in words, and a frontend that has to draw it. Geometry always comes
from A*; a model must never invent it.
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


def _graph_for(profile):
    adj = collections.defaultdict(list)
    for e in _load()["edges"]:
        props = e["p"]
        if props.get("shortcut") and not profile["shortcuts"]:
            continue
        if not profiles.allows(profile, props):
            continue
        edge = (e["min"] * profiles.weight(profile, props), e["m"], props, e["min"])
        adj[e["a"]].append((e["b"], edge))
        adj[e["b"]].append((e["a"], edge))
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
        return "stairs"
    if props.get("pathway_type") == 3:
        return "ramp"
    if props.get("location_class") in ("Interior", "Underground"):
        return "indoor"
    return "paved"


def _steps(path, edges):
    """Consecutive edges of the same character, so a model has something to
    narrate and a frontend something to list."""
    out = []
    for i, edge in enumerate(edges):
        props = edge[2]
        kind = _character(props)
        name = props.get("directions_name_text") or props.get("space")
        if out and out[-1]["kind"] == kind and out[-1]["name"] == name:
            step = out[-1]
        else:
            step = {"kind": kind, "name": name, "metres": 0.0, "minutes": 0.0,
                    "risers": 0, "from": list(path[i])}
            out.append(step)
        step["metres"] += edge[1]
        step["minutes"] += edge[3]
        if kind == "stairs" and props.get("riser_count"):
            step["risers"] += props["riser_count"]
        step["to"] = list(path[i + 1])
    for step in out:
        step["metres"] = round(step["metres"], 1)
        step["minutes"] = round(step["minutes"], 2)
    return out


def plan_route(origin, destination, profile="walk_smart"):
    """Plan one route. `origin`/`destination` are free text place names."""
    state = _load()
    pl = state["places"]

    if profile not in profiles.PROFILES:
        return {"status": "error",
                "error": "unknown profile %r; use one of %s"
                         % (profile, sorted(profiles.PROFILES))}
    cfg = profiles.PROFILES[profile]

    a, a_alts = pl.resolve(origin)
    b, b_alts = pl.resolve(destination)
    for name, place, alts in (("origin", a, a_alts), ("destination", b, b_alts)):
        if place:
            continue
        if alts:
            return {"status": "ambiguous", "field": name,
                    "query": origin if name == "origin" else destination,
                    "candidates": alts,
                    "error": "%s matches %d places; ask which one"
                             % (name, len(alts))}
        return {"status": "error", "field": name,
                "error": "could not resolve %s %r" % (name, origin if name == "origin" else destination)}

    step_free = cfg["entrances"] == "step_free"
    from_doors = pl.entrances(a, accessible_only=step_free)
    to_doors = pl.entrances(b, accessible_only=step_free)

    adj = _graph_for(cfg)
    start_at = {_nearest(adj, d["point"]): d for d in from_doors}
    end_at = {_nearest(adj, d["point"]): d for d in to_doors}

    path, edges = _astar(adj, start_at, end_at)
    if not path:
        return {
            "status": "no_route",
            "profile": profile,
            "origin": {"query": origin, "resolved": a["properties"]["name"]},
            "destination": {"query": destination, "resolved": b["properties"]["name"]},
            "error": ("no %s route between these buildings" % cfg["label"].lower()),
        }

    total_m = sum(e[1] for e in edges)
    minutes = sum(e[3] for e in edges)
    risers = sum(e[2].get("riser_count") or 0 for e in edges
                 if e[2].get("pathway_type") == 2)
    stair_edges = sum(1 for e in edges if e[2].get("pathway_type") == 2)
    shortcut_m = sum(e[1] for e in edges if e[2].get("shortcut"))
    spaces = sorted({e[2].get("space") for e in edges if e[2].get("shortcut")})
    compliant_m = sum(e[1] for e in edges
                      if e[2].get("ihcd2021routesurveycode") == "FullyCompliant")

    warnings = []
    if shortcut_m:
        warnings.append(
            "%.0f m of this route crosses open lawn (%s). No surface, kerb or "
            "slope data backs those segments." % (shortcut_m, ", ".join(spaces)))
    if risers:
        warnings.append("%d steps on this route." % risers)
    if step_free:
        warnings.append(
            "Step-free here means no stairs in the routing network. 39% of the "
            "basemap's stair footprints are not modelled as network segments, "
            "so steps are still possible.")

    origin_door = start_at[path[0]]
    dest_door = end_at[path[-1]]
    return {
        "status": "ok",
        "profile": profile,
        "profileLabel": cfg["label"],
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
            "stairSegments": stair_edges,
            "risers": risers,
            "shortcutMetres": round(shortcut_m, 1),
            "shortcutSpaces": spaces,
            "fullyCompliantShare": round(compliant_m / total_m, 3) if total_m else None,
        },
        # Ready to hand straight to a GeoJSON source.
        "geometry": {"type": "LineString", "coordinates": [list(p) for p in path]},
        "steps": _steps(path, edges),
        "warnings": warnings,
    }


def compare(origin, destination, profiles_=None):
    """Same trip under several profiles, for 'how much does step-free cost me'."""
    names = profiles_ or list(profiles.PROFILES)
    return {"origin": origin, "destination": destination,
            "routes": [plan_route(origin, destination, p) for p in names]}
