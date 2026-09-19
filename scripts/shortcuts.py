"""Desire-path edges across open lawns, for the walking mode only.

The official network routes around quads; people cut across them. This adds
straight-line edges between network nodes whose connecting line stays on the
grass, priced at a slower speed so A* only takes one when it genuinely saves
time.

Nothing here is wheelchair-safe: no surface, kerb or slope data backs these
edges. They belong to walking modes only.
"""
import math

MX = 111320 * math.cos(math.radians(39.329))
MY = 110540

# Median speed implied by walktime/length over the 2085 graded segments.
PAVED_SPEED = 1.31          # m/s
GRASS_SPEED = 1.05          # m/s, about 80% of paved

BUFFER_M = 15.0             # how far outside a lawn a node can sit
MIN_LEN_M = 15.0            # shorter than this is not worth a synthetic edge
MAX_LEN_M = 250.0
SAMPLE_M = 2.0              # spacing of the on-grass check
MIN_ON_GRASS = 0.85         # fraction of samples that must be inside the lawn


def m(a, b):
    return math.hypot((a[0] - b[0]) * MX, (a[1] - b[1]) * MY)


def rings(feature):
    geom = feature["geometry"]
    coords = geom["coordinates"]
    polys = coords if geom["type"] == "MultiPolygon" else [coords]
    return [poly[0] for poly in polys]


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


def build(nodes, exterior_spaces, facilities, barriers):
    """Return [(node_a, node_b, metres, minutes, space_name)]."""
    blocked = [rings(f) for f in facilities] + [rings(f) for f in barriers]
    out = []
    seen = set()

    for space in exterior_spaces:
        name = space["properties"]["name"]
        rs = rings(space)
        near = [n for n in nodes if dist_to_rings(n, rs) < BUFFER_M or in_any(n, [rs])]
        for i, a in enumerate(near):
            for b in near[i + 1:]:
                pair = (a, b) if a < b else (b, a)
                if pair in seen:
                    continue
                length = m(a, b)
                if not (MIN_LEN_M <= length <= MAX_LEN_M):
                    continue

                steps = max(2, int(length / SAMPLE_M))
                on_grass = 0
                ok = True
                for s in range(steps + 1):
                    t = s / steps
                    pt = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                    if in_any(pt, blocked):        # never cut through a building
                        ok = False
                        break
                    if in_any(pt, [rs]):
                        on_grass += 1
                if not ok or on_grass / (steps + 1) < MIN_ON_GRASS:
                    continue

                seen.add(pair)
                out.append((a, b, length, length / GRASS_SPEED / 60, name))
    return out
