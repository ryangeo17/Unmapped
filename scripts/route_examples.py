#!/usr/bin/env python3
"""Build a routable graph from Pathways.geojson and solve two example routes.

Three modes, matching the accessibility grading the official data already
carries on every segment:

    walking     every segment, cost = walktime
    partial     no stairs; FullyCompliant and PartiallyCompliant segments
    accessible  no stairs; FullyCompliant segments only

Writes one GeoJSON per route/mode plus a summary. Standard library only.

    python3 scripts/route_examples.py
"""
import collections
import heapq
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shortcuts

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "frontend", "public", "data")
OUT = os.path.join(DATA, "routes")

# Snapping tolerance for treating two segment endpoints as the same node.
# 5 decimals is about 0.9m; tighter leaves more of the network disconnected.
SNAP = 5
WALK_FPS = 4.6  # feet per second, used only for the A* heuristic


def load(name):
    with open(os.path.join(DATA, name)) as fh:
        return json.load(fh)["features"]


def lines(feature):
    geom = feature["geometry"]
    coords = geom["coordinates"]
    return coords if geom["type"] == "MultiLineString" else [coords]


def key(pt):
    return (round(pt[0], SNAP), round(pt[1], SNAP))


# Local flat-earth metres; campus is small enough that this is exact enough.
LAT0 = 39.329
MX = 111320 * math.cos(math.radians(LAT0))
MY = 110540


def metres(a, b):
    return math.hypot((a[0] - b[0]) * MX, (a[1] - b[1]) * MY)


# Each mode is a hard filter plus a cost multiplier, per design.md: stairs are
# impassable for a wheelchair, everything else is a preference.
#
# Grading FullyCompliant-only as a hard filter does not work. That subgraph
# breaks into 165 components, the largest holding 276 of 1746 nodes, so most
# pairs of buildings have no route at all. The official grading leaves too many
# connector segments Partially compliant for a strict filter to stay connected.
# Penalising instead keeps the network whole and still prefers good surface.
NO_STAIRS = lambda p: p.get("pathway_type") != 2
GRADE = lambda p: p.get("ihcd2021routesurveycode")

MODES = {
    "walking": {
        "label": "Walking",
        "allow": lambda p: True,
        "weight": lambda p: 1.0,
    },
    # Walking, but allowed to cut across lawns and to finish at any entrance
    # including a garage lift. Explicitly not wheelchair-safe: no surface or
    # kerb data backs the shortcut edges.
    "smart": {
        "label": "Walking (shortcuts)",
        "allow": lambda p: True,
        "weight": lambda p: 1.0,
        "shortcuts": True,
        "anyEntrance": True,
    },
    "partial": {
        "label": "Partially accessible",
        "allow": lambda p: NO_STAIRS(p) and GRADE(p) != "NonCompliant",
        "weight": lambda p: 1.0 if GRADE(p) == "FullyCompliant" else 1.5,
    },
    "accessible": {
        "label": "Fully accessible",
        "allow": lambda p: NO_STAIRS(p) and GRADE(p) != "NonCompliant",
        "weight": lambda p: 1.0 if GRADE(p) == "FullyCompliant" else 8.0,
    },
}


def build_graph(pathways, allow, weight, extra=()):
    """Undirected adjacency. travel_direction is filled on 16% of segments, so
    treating the network as undirected is the honest reading of this data."""
    graph = collections.defaultdict(list)
    for feat in pathways:
        props = feat["properties"]
        if not allow(props):
            continue
        for line in lines(feat):
            for a, b in zip(line, line[1:]):
                ka, kb = key(a), key(b)
                if ka == kb:
                    continue
                # Measure between the snapped nodes, since those are the
                # coordinates the emitted route geometry is built from.
                # Measuring the originals leaves the reported length a few
                # metres off what the line actually draws.
                seg = metres(ka, kb)
                total = sum(metres(key(p), key(q))
                            for p, q in zip(line, line[1:])) or seg
                minutes = (props.get("walktime") or 0) * (seg / total)
                # Cost is what A* minimises; minutes is what we report.
                edge = (minutes * weight(props), seg, props, minutes)
                graph[ka].append((kb, edge))
                graph[kb].append((ka, edge))

    for a, b, metres_, minutes_, space in extra:
        if a not in graph or b not in graph:
            continue
        props = {"shortcut": True, "space": space, "pathway_type": 0,
                 "ihcd2021routesurveycode": None}
        edge = (minutes_, metres_, props, minutes_)
        graph[a].append((b, edge))
        graph[b].append((a, edge))
    return graph


def nearest_node(graph, point):
    return min(graph, key=lambda n: metres(n, point))


def astar(graph, starts, goals):
    """Multi-source, multi-target: every entrance of the origin building is a
    valid place to start, every entrance of the destination a valid finish."""
    goals = set(goals)
    open_set = [(0.0, s) for s in starts]
    heapq.heapify(open_set)
    came = {}
    g = {s: 0.0 for s in starts}
    heuristic = lambda n: min(metres(n, t) for t in goals) * 3.28084 / WALK_FPS / 60
    seen = set()
    while open_set:
        _, node = heapq.heappop(open_set)
        if node in goals:
            path = [node]
            edges = []
            while node in came:
                node, edge = came[node]
                path.append(node)
                edges.append(edge)
            return list(reversed(path)), list(reversed(edges))
        if node in seen:
            continue
        seen.add(node)
        for nxt, edge in graph[node]:
            cost = g[node] + edge[0]
            if cost < g.get(nxt, float("inf")):
                g[nxt] = cost
                came[nxt] = (node, edge)
                heapq.heappush(open_set, (cost + heuristic(nxt), nxt))
    return None, None


def describe(edges):
    """Total up what the route actually crosses, from the edges A* chose."""
    total_m = 0.0
    minutes = 0.0
    risers = 0
    compliant_m = 0.0
    shortcut_m = 0.0
    spaces = set()
    grades = collections.Counter()
    types = collections.Counter()
    for edge in edges:
        props = edge[2]
        total_m += edge[1]
        minutes += edge[3]
        grades[props.get("ihcd2021routesurveycode")] += 1
        types[props.get("pathway_type")] += 1
        if props.get("shortcut"):
            shortcut_m += edge[1]
            spaces.add(props.get("space"))
        if props.get("ihcd2021routesurveycode") == "FullyCompliant":
            compliant_m += edge[1]
        if props.get("pathway_type") == 2 and props.get("riser_count"):
            risers += props["riser_count"]
    return total_m, minutes, risers, compliant_m, shortcut_m, spaces, grades, types


def centroid(feature):
    geom = feature["geometry"]
    coords = geom["coordinates"]
    ring = coords[0] if geom["type"] == "Polygon" else coords[0][0]
    return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]


def anchor(facilities, entryways, name, prefer_accessible=None):
    """Prefer a named entryway, fall back to the building centroid."""
    matches = [
        e for e in entryways
        if (e["properties"].get("entrance_name") or "").startswith(name)
    ]
    if prefer_accessible is not None:
        picked = [e for e in matches
                  if e["properties"]["accessible_entrance"] == prefer_accessible]
        matches = picked or matches
    if matches:
        e = matches[0]
        return e["geometry"]["coordinates"], e["properties"]["entrance_name"]
    building = next(f for f in facilities if f["properties"]["name"] == name)
    return centroid(building), name + " (building centre)"


def _ring_list(feature):
    geom = feature["geometry"]
    coords = geom["coordinates"]
    polys = coords if geom["type"] == "MultiPolygon" else [coords]
    return [poly[0] for poly in polys]


def all_entrances(facilities, entryways, elevators, name):
    """Every point that counts as a way into this building.

    entryways.facility_id is populated on 4 of 337 rows, so the link has to be
    made from geometry and names. A lift inside the footprint counts: for a
    garage it is the whole point, and aiming at the building centre instead
    walks you the long way round to a door you did not need.

    Footprints overlap — San Martin Center and San Martin Garage sit on top of
    one another — so a point inside this building is only claimed when its own
    name does not belong to a different one.
    """
    building = next(f for f in facilities if f["properties"]["name"] == name)
    rs = _ring_list(building)
    other_names = [f["properties"]["name"] for f in facilities
                   if f["properties"]["name"] != name]

    def claimed_elsewhere(label):
        return any(label.startswith(o) for o in other_names)

    def inside(pt):
        return (any(shortcuts.in_ring(pt, r) for r in rs)
                or shortcuts.dist_to_rings(pt, rs) < 12.0)

    found = []
    for feature, default in ((entryways, "entrance"), (elevators, "lift")):
        for e in feature:
            pt = e["geometry"]["coordinates"]
            props = e["properties"]
            label = props.get("entrance_name") or props.get("description") or default
            if label.startswith(name):
                found.append((pt, label))
            elif inside(pt) and not claimed_elsewhere(label):
                found.append((pt, label))
    if not found:
        found.append((centroid(building), name + " (building centre)"))
    return found


def main():
    pathways = load("Pathways.geojson")
    facilities = load("Facilities.geojson")
    entryways = load("Entryways-All.geojson")
    elevators = load("Elevators.geojson")
    exterior = load("Exterior_Spaces.geojson")
    barriers = load("Polygon_Barriers.geojson")
    os.makedirs(OUT, exist_ok=True)

    nodes = set()
    for feat in pathways:
        for line in lines(feat):
            nodes.add(key(line[0]))
            nodes.add(key(line[-1]))
    print("building lawn shortcuts over %d network nodes..." % len(nodes))
    extra = shortcuts.build(list(nodes), exterior, facilities, barriers)
    print("  %d shortcut edges" % len(extra))

    trips = [
        ("malone-to-clark", "Malone Hall", "Clark Hall"),
        ("malone-to-san-martin-garage", "Malone Hall", "San Martin Garage"),
    ]

    summary = []
    for slug, from_name, to_name in trips:
        origin, origin_label = anchor(facilities, entryways, from_name, "Y")
        dest, dest_label = anchor(facilities, entryways, to_name, "Y")
        from_doors = all_entrances(facilities, entryways, elevators, from_name)
        to_doors = all_entrances(facilities, entryways, elevators, to_name)
        print("\n=== %s -> %s ===" % (from_name, to_name))
        print("  single anchor : %s -> %s" % (origin_label, dest_label))
        print("  all entrances : %d -> %d  (%s)"
              % (len(from_doors), len(to_doors),
                 ", ".join(l for _, l in to_doors)[:90]))

        for mode, cfg in MODES.items():
            graph = build_graph(pathways, cfg["allow"], cfg["weight"],
                                extra if cfg.get("shortcuts") else ())
            if not graph:
                continue

            if cfg.get("anyEntrance"):
                starts = {nearest_node(graph, p) for p, _ in from_doors}
                goals = {nearest_node(graph, p) for p, _ in to_doors}
                label_for = {nearest_node(graph, p): l for p, l in to_doors}
                start_label = from_name + " (any entrance)"
            else:
                starts = {nearest_node(graph, origin)}
                goals = {nearest_node(graph, dest)}
                label_for = {}
                start_label = origin_label

            path, edges = astar(graph, starts, goals)
            entry = {
                "trip": slug, "mode": mode, "modeLabel": cfg["label"],
                "from": start_label, "to": dest_label,
            }
            if not path:
                entry["status"] = "no route"
                print("  %-22s no route" % cfg["label"])
                summary.append(entry)
                continue

            dist, minutes, risers, compliant_m, shortcut_m, spaces, grades, types = \
                describe(edges)
            if label_for:
                entry["to"] = label_for.get(path[-1], dest_label)
            entry.update({
                "status": "ok",
                "minutes": round(minutes, 2),
                "metres": round(dist, 1),
                "feet": round(dist * 3.28084),
                "stairSegments": types.get(2, 0),
                "risers": risers,
                "fullyCompliantShare": round(compliant_m / dist, 3) if dist else None,
                "shortcutMetres": round(shortcut_m, 1),
                "shortcutSpaces": sorted(x for x in spaces if x),
                "grades": {k: v for k, v in grades.items() if k},
            })
            note = ""
            if shortcut_m:
                note = "  cuts %.0fm across %s" % (shortcut_m, ", ".join(entry["shortcutSpaces"]))
            if label_for:
                note += "  -> %s" % entry["to"]
            print("  %-22s %5.1f min  %5.0f m  stairs %d (%d risers)%s"
                  % (cfg["label"], minutes, dist, types.get(2, 0), risers, note))

            geo = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": entry,
                    "geometry": {"type": "LineString",
                                 "coordinates": [list(p) for p in path]},
                }],
            }
            with open(os.path.join(OUT, "%s.%s.geojson" % (slug, mode)), "w") as fh:
                json.dump(geo, fh, separators=(",", ":"))
            summary.append(entry)

    with open(os.path.join(OUT, "_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print("\nwrote %d files to %s/" % (len(os.listdir(OUT)), OUT))


if __name__ == "__main__":
    main()
