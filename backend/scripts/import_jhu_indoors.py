#!/usr/bin/env python3
"""Download JHU Indoors pathways/facilities and write checked-in UnMapped seed files.

JHU accessibility codes become the campus-wide unverified fallback graph.
Robot-verified demo edges stay in data/robot_verified_overlay.json.
"""

from __future__ import annotations

import json
import math
import re
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CONTEXT = ssl._create_unverified_context()

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

PATHWAYS_URL = "https://map.jhu.edu/arcgis/rest/services/Hosted/Pathways/FeatureServer/0/query"
FACILITIES_URL = "https://map.jhu.edu/arcgis/rest/services/Hosted/Facilities/FeatureServer/0/query"
ENTRYWAYS_URL = "https://map.jhu.edu/arcgis/rest/services/Hosted/Entryways/FeatureServer/0/query"

KNOWN_LANDMARKS = {
    "Gilman Hall": ("gilman", "academic"),
    "Milton S. Eisenhower Library": ("mse", "library"),
    "Brody Learning Commons": ("brody", "library"),
    "Ralph S. O'Connor Recreation Center": ("rec", "recreation"),
    "Levering Hall": ("levering", "student-life"),
    "Malone Hall": ("malone", "academic"),
    "Homewood House": ("homewood", "museum"),
}

PATH_TYPE = {
    1: "sidewalk",
    2: "stairs",
    3: "ramp",
    4: "elevator",
    5: "escalator",
    6: "moving_walkway",
}


def fetch_all(url: str, where: str, fields: str) -> list[dict]:
    features: list[dict] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {
                "where": where,
                "outFields": fields,
                "outSR": 4326,
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": 1000,
                "f": "json",
            }
        )
        with urllib.request.urlopen(f"{url}?{query}", timeout=60, context=SSL_CONTEXT) as response:
            payload = json.loads(response.read().decode())
        batch = payload.get("features") or []
        features.extend(batch)
        if not batch or not payload.get("exceededTransferLimit"):
            break
        offset += len(batch)
    return features


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def line_length(coords: list[list[float]]) -> float:
    return sum(haversine((coords[i][1], coords[i][0]), (coords[i + 1][1], coords[i + 1][0])) for i in range(len(coords) - 1))


def node_id(lat: float, lon: float) -> str:
    return f"n{round(lat, 5):.5f}_{round(lon, 5):.5f}".replace(".", "p").replace("-", "m")


def slug(name: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return value[:48] or "facility"


def accessibility(code: str | None) -> str:
    value = (code or "").lower().replace(" ", "").replace("_", "")
    if "fully" in value or "compliantaccess" in value:
        return "full"
    if "partial" in value:
        return "partial"
    if "hazard" in value or "noncompliant" in value:
        return "hazard"
    return "unknown"


def largest_pathway_component(nodes: dict[str, dict], edges: list[dict]) -> list[dict]:
    """Return the connected outdoor pathway backbone.

    ArcGIS contains many short, disconnected exterior fragments around individual
    buildings. Snapping a landmark to one of those fragments makes it impossible
    to route to the rest of campus, so access links must target the main network.
    """
    adjacency: dict[str, set[str]] = {ident: set() for ident in nodes}
    for edge in edges:
        if edge["closed"]:
            continue
        adjacency[edge["from_node"]].add(edge["to_node"])
        adjacency[edge["to_node"]].add(edge["from_node"])

    largest: set[str] = set()
    remaining = set(nodes)
    while remaining:
        seed = remaining.pop()
        component = {seed}
        pending = [seed]
        while pending:
            current = pending.pop()
            neighbors = adjacency[current] & remaining
            remaining.difference_update(neighbors)
            component.update(neighbors)
            pending.extend(neighbors)
        if len(component) > len(largest):
            largest = component
    return [nodes[ident] for ident in largest]


def main() -> None:
    pathways = fetch_all(
        PATHWAYS_URL,
        "location_class IN ('Exterior','Covered Exterior') AND pathdisplay <> 'Block'",
        "objectid,ihcd2021routesurveycode,pathway_type,suffix_type,location_class,pathdisplay,riser_count,length_3d,walktime,pathway_rank,travel_direction",
    )
    if not pathways:
        pathways = fetch_all(
            PATHWAYS_URL,
            "location_class IN ('Exterior','Covered Exterior')",
            "objectid,ihcd2021routesurveycode,pathway_type,suffix_type,location_class,pathdisplay,riser_count,length_3d,walktime,pathway_rank,travel_direction",
        )
    facilities = fetch_all(FACILITIES_URL, "1=1", "objectid,name,name_long,address")
    entryways = fetch_all(ENTRYWAYS_URL, "1=1", "objectid,entrance_name,accessible_entrance,facility_id")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def ensure_node(lat: float, lon: float, name: str) -> str:
        ident = node_id(lat, lon)
        nodes.setdefault(ident, {"id": ident, "name": name, "latitude": round(lat, 6), "longitude": round(lon, 6)})
        return ident

    for feature in pathways:
        attrs = feature.get("attributes") or {}
        paths = (feature.get("geometry") or {}).get("paths") or []
        if not paths or len(paths[0]) < 2:
            continue
        coords = [[float(x), float(y)] for x, y in paths[0]]
        start, end = coords[0], coords[-1]
        from_id = ensure_node(start[1], start[0], "JHU pathway")
        to_id = ensure_node(end[1], end[0], "JHU pathway")
        if from_id == to_id:
            continue
        kind = PATH_TYPE.get(attrs.get("pathway_type") or 1, "sidewalk")
        suffix = (attrs.get("suffix_type") or "").lower()
        stairs = kind == "stairs" or suffix == "stairs" or int(attrs.get("riser_count") or 0) > 0
        curb = kind == "stairs" and suffix == "curb" or suffix == "curb"
        access = accessibility(attrs.get("ihcd2021routesurveycode"))
        closed = (attrs.get("pathdisplay") or "").lower() == "block"
        distance = float(attrs.get("length_3d") or 0) * 0.3048
        if distance <= 0:
            distance = line_length(coords)
        roughness = {"full": 0.05, "partial": 0.28, "hazard": 0.55, "unknown": 0.18}[access]
        safety = {"full": 0.92, "partial": 0.8, "hazard": 0.62, "unknown": 0.75}[access]
        edges.append(
            {
                "id": f"jhu-{attrs['objectid']}",
                "from_node": from_id,
                "to_node": to_id,
                "distance_m": round(max(distance, 1.0), 1),
                "surface": "paved" if kind in {"sidewalk", "ramp", "elevator"} else "brick" if stairs else "other",
                "roughness": roughness,
                "slope": 0.08 if kind == "ramp" else 0.04 if stairs else 0.01,
                "safety": safety,
                "stairs": stairs,
                "curb": curb and not kind == "ramp",
                "lit": (attrs.get("pathway_rank") or 3) <= 2,
                "closed": closed,
                "bidirectional": (attrs.get("travel_direction") or 1) == 1,
                "verified": False,
                "confidence": {"full": 0.72, "partial": 0.55, "hazard": 0.38, "unknown": 0.48}[access],
                "construction": False,
                "source": "jhu_indoors",
                "accessibility": access,
                "geometry": coords,
            }
        )

    accessible_facilities = {
        feature["attributes"].get("facility_id")
        for feature in entryways
        if str(feature["attributes"].get("accessible_entrance") or "").lower() in {"yes", "y", "true", "1"}
    }

    landmarks = []
    pathway_nodes = largest_pathway_component(nodes, edges)
    for feature in facilities:
        attrs = feature.get("attributes") or {}
        name = (attrs.get("name") or attrs.get("name_long") or "").strip()
        if not name:
            continue
        rings = ((feature.get("geometry") or {}).get("rings") or [[]])[0]
        if len(rings) < 3:
            continue
        lat = sum(p[1] for p in rings) / len(rings)
        lon = sum(p[0] for p in rings) / len(rings)
        known = KNOWN_LANDMARKS.get(name)
        ident = known[0] if known else slug(name)
        category = known[1] if known else "building"
        nodes[ident] = {"id": ident, "name": name, "latitude": round(lat, 6), "longitude": round(lon, 6)}
        nearest = min(pathway_nodes, key=lambda node: haversine((lat, lon), (node["latitude"], node["longitude"])))
        access_edge = f"access-{ident}"
        if access_edge not in {edge["id"] for edge in edges}:
            edges.append(
                {
                    "id": access_edge,
                    "from_node": ident,
                    "to_node": nearest["id"],
                    "distance_m": round(max(haversine((lat, lon), (nearest["latitude"], nearest["longitude"])), 5), 1),
                    "surface": "paved",
                    "roughness": 0.08,
                    "slope": 0.01,
                    "safety": 0.9,
                    "stairs": False,
                    "curb": False,
                    "lit": True,
                    "closed": False,
                    "bidirectional": True,
                    "verified": False,
                    "confidence": 0.6,
                    "construction": False,
                    "source": "jhu_indoors",
                    "accessibility": "full" if attrs.get("facility_id") in accessible_facilities else "partial",
                    "geometry": [[lon, lat], [nearest["longitude"], nearest["latitude"]]],
                }
            )
        landmarks.append(
            {
                "id": f"lm-{ident}",
                "name": name,
                "description": attrs.get("address") or "JHU Homewood facility from the public Indoors map.",
                "node_id": ident,
                "category": category,
                "accessible": attrs.get("facility_id") in accessible_facilities or ident in {item[0] for item in KNOWN_LANDMARKS.values()},
            }
        )
        if ident == "mse":
            landmarks.append(
                {
                    "id": "lm-mse-short",
                    "name": "MSE Library",
                    "description": "Milton S. Eisenhower Library.",
                    "node_id": "mse",
                    "category": "library",
                    "accessible": True,
                }
            )

    if "quad" not in nodes:
        nodes["quad"] = {"id": "quad", "name": "Keyser Quadrangle", "latitude": 39.32942, "longitude": -76.62086}
        nearest = min(pathway_nodes, key=lambda node: haversine((39.32942, -76.62086), (node["latitude"], node["longitude"])))
        edges.append(
            {
                "id": "access-quad",
                "from_node": "quad",
                "to_node": nearest["id"],
                "distance_m": round(max(haversine((39.32942, -76.62086), (nearest["latitude"], nearest["longitude"])), 5), 1),
                "surface": "paved",
                "roughness": 0.05,
                "slope": 0.01,
                "safety": 0.95,
                "stairs": False,
                "curb": False,
                "lit": True,
                "closed": False,
                "bidirectional": True,
                "verified": False,
                "confidence": 0.6,
                "construction": False,
                "source": "jhu_indoors",
                "accessibility": "full",
                "geometry": [[-76.62086, 39.32942], [nearest["longitude"], nearest["latitude"]]],
            }
        )
        landmarks.append(
            {
                "id": "lm-quad",
                "name": "Keyser Quadrangle",
                "description": "Central Homewood lawn and gathering space.",
                "node_id": "quad",
                "category": "outdoor",
                "accessible": True,
            }
        )

    overlay = json.loads((DATA / "robot_verified_overlay.json").read_text())
    for node in overlay["nodes"]:
        nodes[node["id"]] = node
    edges.extend(overlay["edges"])

    graph = {"nodes": list(nodes.values()), "edges": edges}
    (DATA / "homewood_graph.json").write_text(json.dumps(graph))
    (DATA / "homewood_landmarks.json").write_text(json.dumps(landmarks, indent=2))
    print(f"Wrote {len(graph['nodes'])} nodes, {len(edges)} edges, {len(landmarks)} landmarks")


if __name__ == "__main__":
    main()
