#!/usr/bin/env python3
"""Turn JHU's published campus data into this app's seed files.

    python3 scripts/build_campus_seed.py

Reads the GeoJSON exported from JHU's ArcGIS Enterprise portal (see
scripts/indoors_dump.py for provenance, docs/CAMPUS_DATA.md for field meanings)
and writes data/homewood_{graph,landmarks,doors,hazards}.json, which the
backend seeds into SQLite on first startup.

Standard library only. The lawn-shortcut pass takes about 40 seconds, which is
why this is a build step and not something the backend does at runtime.

**Attributes this data cannot supply are written as null, not as a default.**
Slope, roughness, safety, lighting and surface were never surveyed here. Null
means unknown; writing 0 slope and 1.0 safety would make every segment look
ideal and quietly mislead someone who depends on the answer.
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from campus import shortcuts                                   # noqa: E402
from campus.geometry import in_ring, key, lines, metres, rings  # noqa: E402
from campus.places import Places                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "frontend", "public", "data")
OUT = os.path.join(ROOT, "data")

# Their landmark seed, which we must keep resolving: saved links use these ids,
# and DEMO_SCRIPT.md names them. Two of the seven do not match any real place
# name, so they are carried as aliases.
LEGACY_LANDMARKS = {
    "lm-gilman": "Gilman Hall",
    "lm-mse": "Milton S. Eisenhower Library",      # their name: "MSE Library"
    "lm-brody": "Brody Learning Commons",
    "lm-rec": "Ralph S. O'Connor Recreation Center",
    "lm-levering": "Levering Hall",
    "lm-malone": "Malone Hall",
    "lm-homewood": "Homewood House",               # their name: "Homewood Museum"
}
LEGACY_NAMES = {
    "lm-mse": "MSE Library",
    "lm-rec": "O'Connor Recreation Center",
    "lm-homewood": "Homewood Museum",
}

# primary_use is free text on 92 of 100 buildings; map it onto the category
# vocabulary the frontend already styles.
CATEGORY = {
    "Library": "library",
    "Instruction": "academic",
    "Research": "academic",
    "Administration": "administration",
    "Residence Hall": "residence",
    "Multifamily": "residence",
    "Recreation": "recreation",
    "Mixed Use": "student-life",
    "Parking Garage": "parking",
    "Power Plant": "utility",
}

# The official survey grade is the closest thing this data has to a
# verification confidence. It is not a robot observation, so `verified` stays
# false everywhere; see the module docstring.
CONFIDENCE = {"FullyCompliant": 0.9, "PartiallyCompliant": 0.7, "NonCompliant": 0.5}


def load(name):
    with open(os.path.join(SOURCE, name)) as fh:
        return json.load(fh)["features"]


def node_id(pt):
    """Stable across rebuilds: derived from the snapped coordinate itself."""
    return "n%d_%d" % (round(pt[0] * 1e5), round(pt[1] * 1e5))


def edge_kind(props):
    if props.get("shortcut"):
        return "shortcut"
    if props.get("pathway_type") == 2:
        return "stairs"
    if props.get("pathway_type") == 3:
        return "ramp"
    if props.get("location_class") in ("Interior", "Underground"):
        return "indoor"
    return "paved"


def barrier_test(barriers):
    """Closures come from the construction polygons, the only 'closed' signal
    this data has."""
    zones = [(f["properties"].get("project_name") or "construction", rings(f))
             for f in barriers]

    def inside(pt):
        for name, rs in zones:
            if any(in_ring(pt, r) for r in rs):
                return name
        return None
    return inside


def build_edges(pathways, barriers):
    """One edge per consecutive vertex pair, so the route geometry the backend
    assembles from node coordinates follows the real pavement."""
    blocked = barrier_test(barriers)
    edges = []
    for feature in pathways:
        props = feature["properties"]
        oid = props.get("objectid")
        grade = props.get("ihcd2021routesurveycode")
        stairs = props.get("pathway_type") == 2
        kind = edge_kind(props)
        # directions_name_text is on 91 segments, suffix_type on about 175.
        # Between them most named features — tunnels, crosswalks, breezeways —
        # can be spoken aloud instead of a node id.
        name = props.get("directions_name_text") or props.get("suffix_type")
        for line in lines(feature):
            # walktime is per feature; split it over the feature's own segments
            # by length share, measuring between snapped nodes so the reported
            # distance matches the line that gets drawn.
            total = sum(metres(key(p), key(q)) for p, q in zip(line, line[1:]))
            for i, (a, b) in enumerate(zip(line, line[1:])):
                ka, kb = key(a), key(b)
                if ka == kb:
                    continue
                seg = metres(ka, kb)
                closure = blocked(list(ka)) or blocked(list(kb))
                # A to-from-only segment is the same arc pointing the other way.
                if props.get("travel_direction") == 3:
                    ka, kb = kb, ka
                edges.append({
                    "id": "e-%s-%d" % (oid, i),
                    "from_node": node_id(ka),
                    "to_node": node_id(kb),
                    "distance_m": round(seg, 2),
                    "stairs": stairs,
                    "curb": props.get("suffix_type") == "Curb",
                    "closed": closure is not None,
                    "construction": closure is not None,
                    # The project that closed it, so a blocked route can name
                    # what is in the way rather than shrugging.
                    "space": closure,
                    # 1 = both ways, 2 = from-to only, 3 = to-from only.
                    # Populated on 16% of segments and only ever 1 in this
                    # data, so nothing is actually one-way today; absent means
                    # no recorded restriction, which is two-way.
                    "bidirectional": props.get("travel_direction") not in (2, 3),
                    "grade": grade,
                    "riser_count": props.get("riser_count") or 0,
                    "kind": kind,
                    "name": name,
                    "verified": False,
                    "confidence": CONFIDENCE.get(grade, 0.5),
                    "surface": None,
                    "roughness": None,
                    "slope": None,
                    "safety": None,
                    "lit": None,
                })
    return edges


def build_shortcuts(pathways, exterior, facilities, barriers, known_nodes):
    endpoints = set()
    for feature in pathways:
        for line in lines(feature):
            endpoints.add(key(line[0]))
            endpoints.add(key(line[-1]))
    cuts = shortcuts.build(sorted(endpoints), exterior, facilities, barriers)
    out = []
    for a, b, length, _minutes, space in cuts:
        na, nb = node_id(a), node_id(b)
        if na not in known_nodes or nb not in known_nodes:
            continue
        out.append({
            "id": "sc-%s-%s" % (na, nb),
            "from_node": na, "to_node": nb,
            "distance_m": round(length, 2),
            "stairs": False, "curb": False,
            "closed": False, "construction": False, "bidirectional": True,
            "grade": None, "riser_count": 0, "kind": "shortcut",
            "space": space, "name": space,
            # Not an unmeasured attribute — a desire path over a lawn is grass
            # by construction, and it walks slower than pavement.
            "surface": "grass",
            "verified": False,
            # Inferred from geometry, never surveyed. Lowest confidence in the
            # graph, and the backend keeps them out of accessible modes.
            "confidence": 0.3,
            "roughness": None, "slope": None, "safety": None, "lit": None,
        })
    return out


def build_places(places, nodes_by_key, allowed=None):
    """Landmarks plus the doors you can actually arrive at.

    Their schema is one landmark to one node. A building has several doors, and
    which one is nearest decides the route, so doors go in their own file and
    the backend seeds the graph with all of them.
    """
    by_name = {}
    for slug, real in LEGACY_LANDMARKS.items():
        by_name[real] = slug

    landmarks, doors = [], []
    for feature in places.facilities + places.exterior:
        props = feature["properties"]
        name = props["name"]
        is_building = feature in places.facilities
        slug = by_name.get(name) or "lm-%s" % props["facility_id"].lower()
        landmarks.append({
            "id": slug,
            # Keep their wording where it differs, so the demo script and any
            # saved link keep resolving.
            "name": LEGACY_NAMES.get(slug, name),
            "description": props.get("address") or "",
            "category": (CATEGORY.get(props.get("primary_use"), "building")
                         if is_building else "outdoor"),
            "accessible": any(d["stepFree"] for d in places.entrances(feature)
                              if d["kind"] != "centre"),
            "alias": props.get("name_alias") or (name if slug in LEGACY_NAMES else None),
        })
        for door in places.entrances(feature):
            snapped, snap_m = nearest_key(nodes_by_key, door["point"], allowed)
            if snapped is None:
                continue
            doors.append({
                "landmark_id": slug,
                "node_id": node_id(snapped),
                "label": (door["label"] or "").strip(),
                "kind": door["kind"],
                "step_free": bool(door["stepFree"]),
                # How far the mapped pavement stops short of the door. Seven
                # off-campus buildings sit 165-338 m out because the network
                # does not reach them; that is worth saying, not hiding.
                "snap_m": round(snap_m, 1),
            })
    return landmarks, doors


def backbone(edges):
    """Node keys in the largest connected component.

    ArcGIS carries many short exterior fragments around individual buildings.
    Snapping a door to one of those strands it: the route fails with no reason
    a user can act on. Doors target the backbone instead, which is the idea
    behind largest_pathway_component in the other import.
    """
    adjacency = {}
    for e in edges:
        if e["closed"]:
            continue
        adjacency.setdefault(e["from_node"], set()).add(e["to_node"])
        adjacency.setdefault(e["to_node"], set()).add(e["from_node"])
    seen, best = set(), set()
    for start in adjacency:
        if start in seen:
            continue
        stack, group = [start], set()
        while stack:
            node = stack.pop()
            if node in group:
                continue
            group.add(node)
            stack.extend(adjacency[node] - group)
        seen |= group
        if len(group) > len(best):
            best = group
    return best


def nearest_key(nodes_by_key, point, allowed=None):
    """Snap a door onto the pavement network. Linear, but this runs once."""
    best, best_d = None, float("inf")
    for k in nodes_by_key:
        if allowed is not None and node_id(k) not in allowed:
            continue
        d = metres(k, point)
        if d < best_d:
            best, best_d = k, d
    # Generous, because the network genuinely stops short of the off-campus
    # buildings. The distance is recorded and disclosed rather than used to
    # drop the place from search, which would make it unfindable.
    return (best, best_d) if best_d <= 400 else (None, best_d)


def apply_robot_observations(edges, nodes_by_key):
    """Anchor the hand-authored demo observations onto real segments.

    Returns the hazard records with a real `edge_id`. The measurements are
    stamped onto those segments and marked verified, so they are the only
    place in the graph where slope, surface, roughness and lighting are not
    null — which is exactly the contrast the robot pipeline exists to create.
    """
    path = os.path.join(OUT, "robot_demo_observations.json")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        observations = json.load(fh)["observations"]

    by_id = {e["id"]: e for e in edges}
    midpoints = []
    for e in edges:
        if e["kind"] == "shortcut":
            continue
        a, b = key_of(e["from_node"]), key_of(e["to_node"])
        midpoints.append((e["id"], ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))

    hazards = []
    for obs in observations:
        point = (obs["longitude"], obs["latitude"])
        edge_id, distance = min(
            ((eid, metres(mid, point)) for eid, mid in midpoints),
            key=lambda pair: pair[1],
        )
        edge = by_id[edge_id]
        edge.update(obs["measured"])
        edge["verified"] = True
        edge["confidence"] = 0.96
        hazards.append({
            "id": obs["id"], "title": obs["title"],
            "description": obs["description"], "severity": obs["severity"],
            "kind": obs["kind"], "edge_id": edge_id,
            "latitude": obs["latitude"], "longitude": obs["longitude"],
            "active": True, "verified": True,
            "evidence": json.dumps(obs["evidence"]),
        })
        print("  %-26s -> %s (%.0fm away)" % (obs["id"], edge_id, distance))
    return hazards


def key_of(node):
    """Recover the coordinate a node id was derived from."""
    lng, lat = node[1:].split("_")
    return (int(lng) / 1e5, int(lat) / 1e5)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--skip-shortcuts", action="store_true",
                    help="faster rebuild when only the attribute mapping changed")
    args = ap.parse_args()

    start = time.time()
    pathways = load("Pathways.geojson")
    facilities = load("Facilities.geojson")
    exterior = load("Exterior_Spaces.geojson")
    entryways = load("Entryways-All.geojson")
    elevators = load("Elevators.geojson")
    barriers = load("Polygon_Barriers.geojson")

    print("building network edges...")
    edges = build_edges(pathways, barriers)
    node_keys = {}
    for feature in pathways:
        for line in lines(feature):
            for p in line:
                node_keys[key(p)] = True
    # Only vertices that survived as edge endpoints are real nodes.
    live = {e["from_node"] for e in edges} | {e["to_node"] for e in edges}
    node_keys = {k: True for k in node_keys if node_id(k) in live}
    print("  %d edges over %d nodes" % (len(edges), len(node_keys)))

    if not args.skip_shortcuts:
        print("building lawn shortcuts (~40s)...")
        cuts = build_shortcuts(pathways, exterior, facilities, barriers, live)
        print("  %d shortcut edges" % len(cuts))
        edges.extend(cuts)

    print("applying robot demo observations...")
    hazards = apply_robot_observations(edges, node_keys)

    print("assigning doors...")
    main_component = backbone(edges)
    print("  backbone: %d of %d nodes" % (len(main_component), len(node_keys)))
    places = Places(facilities, exterior, entryways, elevators)
    landmarks, doors = build_places(places, node_keys, main_component)
    print("  %d landmarks, %d doors" % (len(landmarks), len(doors)))

    nodes = [{"id": node_id(k), "name": node_id(k),
              "latitude": round(k[1], 6), "longitude": round(k[0], 6)}
             for k in node_keys]

    os.makedirs(args.out, exist_ok=True)
    write(args.out, "homewood_graph.json", {"nodes": nodes, "edges": edges})
    write(args.out, "homewood_landmarks.json", landmarks)
    write(args.out, "homewood_doors.json", doors)
    write(args.out, "homewood_hazards.json", hazards)

    kinds = {}
    for e in edges:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print("\n%d nodes, %d edges %s" % (len(nodes), len(edges), kinds))
    print("%d landmarks, %d doors, %d hazards" % (len(landmarks), len(doors), len(hazards)))
    print("%.0fs" % (time.time() - start))


def write(out, name, payload):
    path = os.path.join(out, name)
    with open(path, "w") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print("  wrote %s (%.1f MB)" % (name, os.path.getsize(path) / 1048576))


if __name__ == "__main__":
    main()
