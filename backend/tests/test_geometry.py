"""Invariants that must hold whatever the numbers become.

Ported from the standalone planner, where each of these caught a real bug:
a reported distance that disagreed with the line actually drawn (twice —
once from coordinate snapping, once from picking the wrong parallel edge),
a lawn shortcut cutting through a building, and a weighted search cost being
reported as a duration, which showed a nine-minute walk as twenty-four.
"""
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CAMPUS = ROOT / "frontend" / "public" / "data"

LAT0 = 39.329
MX = 111320 * math.cos(math.radians(LAT0))
MY = 110540

TRIPS = [
    ("Malone Hall", "Clark Hall"),
    ("Malone Hall", "San Martin Garage"),
    ("Gilman Hall", "Brody Learning Commons"),
]
MODES = ["walking", "wheelchair", "scooter", "bicycle"]


def metres(a, b):
    return math.hypot((a[0] - b[0]) * MX, (a[1] - b[1]) * MY)


def plan(client, start, end, **kwargs):
    payload = {"start": start, "end": end, "mode": "walking"}
    payload.update(kwargs)
    response = client.post("/api/routes", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("start,end", TRIPS)
def test_reported_distance_matches_the_line_drawn(client, start, end):
    route = plan(client, start, end)
    drawn = sum(metres(a, b) for a, b in zip(route["geometry"], route["geometry"][1:]))
    assert drawn == pytest.approx(route["verified_stats"]["distance_m"], abs=0.5)


@pytest.mark.parametrize("start,end", TRIPS)
def test_geometry_is_continuous_and_on_campus(client, start, end):
    coords = route = plan(client, start, end)["geometry"]
    assert len(coords) > 1
    for lng, lat in coords:
        assert -77 < lng < -76, lng      # Baltimore, not the Gulf of Guinea
        assert 39 < lat < 40, lat
    gaps = [metres(a, b) for a, b in zip(coords, coords[1:])]
    assert max(gaps) < 300, "a gap that large means the path is broken"
    del route


@pytest.mark.parametrize("mode", MODES)
def test_implied_speed_is_plausible(client, mode):
    """The search minimises a weighted cost; the duration reported must be the
    real one. Reporting the weighted cost showed a 9 minute walk as 24."""
    route = plan(client, "Malone Hall", "San Martin Garage", mode=mode)
    stats = route["verified_stats"]
    speed = stats["distance_m"] / max(stats["estimated_seconds"], 1)
    assert 0.8 < speed < 5.0, f"{mode} implies {speed:.2f} m/s"


def test_no_shortcut_crosses_a_building(client):
    """A lawn desire path that goes through a wall is not a desire path."""
    with (CAMPUS / "Facilities.geojson").open() as fh:
        facilities = json.load(fh)["features"]
    rings = []
    for feature in facilities:
        coords = feature["geometry"]["coordinates"]
        polys = coords if feature["geometry"]["type"] == "MultiPolygon" else [coords]
        rings.extend(poly[0] for poly in polys)

    def in_ring(pt, ring):
        x, y = pt
        inside = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside

    overlay = client.get("/api/graph/overlay").json()
    nodes = {n["id"]: (n["longitude"], n["latitude"]) for n in overlay["nodes"]}
    shortcuts = [e for e in overlay["edges"] if e["kind"] == "shortcut"]
    assert len(shortcuts) == 933

    for edge in shortcuts:
        a, b = nodes[edge["from_node"]], nodes[edge["to_node"]]
        for i in range(21):
            t = i / 20
            pt = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            assert not any(in_ring(pt, ring) for ring in rings), edge["id"]


def test_every_edge_endpoint_is_a_real_node(client):
    overlay = client.get("/api/graph/overlay").json()
    ids = {node["id"] for node in overlay["nodes"]}
    for edge in overlay["edges"]:
        assert edge["from_node"] in ids, edge["id"]
        assert edge["to_node"] in ids, edge["id"]


def test_every_place_is_routable_or_says_why_not(client):
    """116 places. A name in the search box that fails with a shrug is worse
    than one that is not listed; a name that fails with a reason is fine.

    Four places are inside the AMR 1 Replacement construction zone and are
    genuinely unreachable on foot right now. That is the correct answer.
    """
    landmarks = client.get("/api/landmarks").json()
    blocked, broken = [], []
    for item in landmarks:
        response = client.post(
            "/api/routes",
            json={"start": "Malone Hall", "end": item["name"], "mode": "walking"},
        )
        if response.status_code in (200, 409):
            continue
        detail = response.json().get("detail", "")
        if response.status_code == 422 and "closure is in the way" in str(detail):
            blocked.append(item["name"])
        else:
            broken.append((item["name"], response.status_code, detail))
    assert not broken, broken
    assert len(blocked) <= 6, blocked
    assert "Alumni Memorial Residence 1" in blocked
