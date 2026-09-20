"""Planar helpers. Campus is small enough that a local flat-earth projection is
exact to well under a metre, so there is no need for a real projection here."""
import math

LAT0 = 39.329
MX = 111320 * math.cos(math.radians(LAT0))
MY = 110540

# Endpoints closer than this are the same node. Tighter leaves more of the
# network disconnected; 17% of endpoints are dangling even at this tolerance.
SNAP = 5


def metres(a, b):
    return math.hypot((a[0] - b[0]) * MX, (a[1] - b[1]) * MY)


def key(pt):
    return (round(pt[0], SNAP), round(pt[1], SNAP))


def lines(feature):
    geom = feature["geometry"]
    coords = geom["coordinates"]
    return coords if geom["type"] == "MultiLineString" else [coords]


def rings(feature):
    geom = feature["geometry"]
    coords = geom["coordinates"]
    polys = coords if geom["type"] == "MultiPolygon" else [coords]
    return [poly[0] for poly in polys]


def centroid(feature):
    pts = [p for ring in rings(feature) for p in ring]
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def in_ring(pt, ring):
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def in_any(pt, ring_sets):
    return any(in_ring(pt, r) for rs in ring_sets for r in rs)


def dist_to_rings(pt, rs):
    best = float("inf")
    for ring in rs:
        for a, b in zip(ring, ring[1:]):
            ax, ay = (a[0] - pt[0]) * MX, (a[1] - pt[1]) * MY
            bx, by = (b[0] - pt[0]) * MX, (b[1] - pt[1]) * MY
            dx, dy = bx - ax, by - ay
            length = dx * dx + dy * dy
            t = 0.0 if length == 0 else max(0, min(1, (-ax * dx - ay * dy) / length))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best
