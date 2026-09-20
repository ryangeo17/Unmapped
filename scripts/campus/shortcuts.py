"""Desire-path edges across open lawns, for the walking mode only.

The official network routes around quads; people cut across them. This adds
straight-line edges between network nodes whose connecting line stays on the
grass, priced at a slower speed so A* only takes one when it genuinely saves
time.

Nothing here is wheelchair-safe: no surface, kerb or slope data backs these
edges. They belong to walking modes only.
"""
import math

from .geometry import dist_to_rings, in_any, in_ring, metres as m, rings  # noqa: F401

# Median speed implied by walktime/length over the 2085 graded segments.
PAVED_SPEED = 1.31          # m/s
GRASS_SPEED = 1.05          # m/s, about 80% of paved

BUFFER_M = 15.0             # how far outside a lawn a node can sit
MIN_LEN_M = 15.0            # shorter than this is not worth a synthetic edge
MAX_LEN_M = 250.0
SAMPLE_M = 2.0              # spacing of the on-grass check
MIN_ON_GRASS = 0.85         # fraction of samples that must be inside the lawn


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
