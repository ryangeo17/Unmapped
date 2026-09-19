"""The routable graph, and a disk cache for it.

Building the lawn shortcuts takes about 30 seconds, which is fine as a build
step and not fine per request. build_cache.py writes the result once; the
server loads it at import.
"""
import json
import os

from . import shortcuts
from .geometry import key, lines, metres

DATA = os.environ.get(
    "CAMPUS_DATA",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "frontend", "public", "data"),
)
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_cache.json")


def load(name):
    with open(os.path.join(DATA, name)) as fh:
        return json.load(fh)["features"]


def network_edges(pathways):
    """One entry per graph edge, with the attributes routing cares about."""
    out = []
    for feat in pathways:
        props = feat["properties"]
        keep = {
            "pathway_type": props.get("pathway_type"),
            "ihcd2021routesurveycode": props.get("ihcd2021routesurveycode"),
            "riser_count": props.get("riser_count"),
            "location_class": props.get("location_class"),
            "directions_name_text": props.get("directions_name_text"),
            "facility_name": props.get("facility_name"),
        }
        for line in lines(feat):
            # walktime is per feature, so split it across the feature's own
            # vertices by length. Measure between snapped nodes, since those
            # are the coordinates the emitted geometry is built from.
            total = sum(metres(key(p), key(q)) for p, q in zip(line, line[1:]))
            for a, b in zip(line, line[1:]):
                ka, kb = key(a), key(b)
                if ka == kb:
                    continue
                seg = metres(ka, kb)
                share = (seg / total) if total else 1.0
                out.append({
                    "a": ka, "b": kb, "m": seg,
                    "min": (props.get("walktime") or 0) * share,
                    "p": keep,
                })
    return out


def build():
    pathways = load("Pathways.geojson")
    edges = network_edges(pathways)
    nodes = {e["a"] for e in edges} | {e["b"] for e in edges}

    endpoints = set()
    for feat in pathways:
        for line in lines(feat):
            endpoints.add(key(line[0]))
            endpoints.add(key(line[-1]))

    cuts = shortcuts.build(
        sorted(endpoints),
        load("Exterior_Spaces.geojson"),
        load("Facilities.geojson"),
        load("Polygon_Barriers.geojson"),
    )
    for a, b, length, minutes, space in cuts:
        if a in nodes and b in nodes:
            edges.append({
                "a": a, "b": b, "m": length, "min": minutes,
                "p": {"shortcut": True, "space": space, "pathway_type": 0,
                      "ihcd2021routesurveycode": None},
            })
    return {"edges": edges, "shortcutCount": len(cuts)}


def write_cache():
    data = build()
    with open(CACHE, "w") as fh:
        json.dump({"edges": [[list(e["a"]), list(e["b"]), e["m"], e["min"], e["p"]]
                             for e in data["edges"]],
                   "shortcutCount": data["shortcutCount"]}, fh, separators=(",", ":"))
    return data


def read_cache():
    with open(CACHE) as fh:
        raw = json.load(fh)
    return {
        "edges": [{"a": tuple(a), "b": tuple(b), "m": m_, "min": mn, "p": p}
                  for a, b, m_, mn, p in raw["edges"]],
        "shortcutCount": raw["shortcutCount"],
    }


def load_edges():
    """Cached edges if the cache exists, otherwise build and write one."""
    if os.path.exists(CACHE):
        return read_cache()
    return write_cache()
