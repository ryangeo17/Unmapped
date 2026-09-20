"""Resolving a name to the points you can actually arrive at.

Entryways.facility_id is populated on 4 of 337 rows, so entrances are matched
to buildings by geometry and name. Footprints overlap — San Martin Center sits
on top of San Martin Garage — so a point inside a building is only claimed when
its own name does not belong to a different building.
"""
import re

from .geometry import centroid, dist_to_rings, in_ring, rings

NEAR_M = 12.0
STOPWORDS = {"the", "a", "an", "at", "to", "in", "of", "building", "hall"}


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


class Places:
    def __init__(self, facilities, exterior, entryways, elevators):
        self.facilities = facilities
        self.exterior = exterior
        self.entryways = entryways
        self.elevators = elevators
        self._names = [f["properties"]["name"] for f in facilities]
        # Doors never move, so resolve each building once and keep it. Without
        # this, finding them was 25 ms of a 27 ms route — an order of magnitude
        # more than the A* it feeds.
        self._doors = {}
        # Point-in-polygon and distance-to-edge are per-vertex; a bounding box
        # rejects almost every candidate for a fraction of the cost.
        self._bbox = {}

    def index(self):
        """Compact list for a model to resolve free text against. Names only —
        the graph never leaves the server."""
        out = []
        for f in self.facilities:
            p = f["properties"]
            out.append({
                "name": p["name"],
                "kind": "building",
                "use": p.get("primary_use"),
                "alias": p.get("name_alias"),
            })
        for f in self.exterior:
            out.append({"name": f["properties"]["name"], "kind": "outdoor space"})
        return out

    def resolve(self, query):
        """Free text to a place. Returns (feature, candidates).

        An ambiguous query returns (None, candidates) rather than guessing, so
        the caller can ask which one was meant. "the garage" matches four.
        """
        q = _norm(query)
        if not q:
            return None, []
        everything = self.facilities + self.exterior

        for f in everything:
            if _norm(f["properties"]["name"]) == q:
                return f, []
        for f in self.facilities:
            if _norm(f["properties"].get("name_alias")) == q:
                return f, []

        hits = [f for f in everything if q in _norm(f["properties"]["name"])]
        if not hits:
            # every meaningful word of the query appears in the name
            words = [w for w in q.split() if w not in STOPWORDS]
            if words:
                hits = [f for f in everything
                        if all(w in _norm(f["properties"]["name"]) for w in words)]
        if len(hits) == 1:
            return hits[0], []
        if hits:
            return None, [f["properties"]["name"] for f in hits]
        return None, []

    def _bounds(self, feature, name):
        if name not in self._bbox:
            pts = [p for r in rings(feature) for p in r]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            pad = NEAR_M / 111320.0 * 1.6      # generous: degrees, near 39N
            self._bbox[name] = (min(xs) - pad, min(ys) - pad,
                                max(xs) + pad, max(ys) + pad)
        return self._bbox[name]

    def entrances(self, feature, lifts=True):
        """Points that count as a way into this place.

        A lift inside the footprint counts: for a garage it is the whole point,
        and aiming at the building centre instead walks you round the block to
        a door you did not need.
        """
        name = feature["properties"]["name"]
        cached = self._doors.get((name, lifts))
        if cached is not None:
            return cached

        rs = rings(feature)
        others = [n for n in self._names if n != name]
        xmin, ymin, xmax, ymax = self._bounds(feature, name)

        def claimed_elsewhere(label):
            return any(label.startswith(o) for o in others)

        def inside(pt):
            if not (xmin <= pt[0] <= xmax and ymin <= pt[1] <= ymax):
                return False
            return (any(in_ring(pt, r) for r in rs)
                    or dist_to_rings(pt, rs) < NEAR_M)

        found = []
        for e in self.entryways:
            props = e["properties"]
            label = props.get("entrance_name") or "entrance"
            pt = e["geometry"]["coordinates"]
            if label.startswith(name) or (inside(pt) and not claimed_elsewhere(label)):
                found.append({"point": pt, "label": label, "kind": "entrance"})
        # A lift into a car park is a doorway like any other — but only the
        # smarter search is allowed to notice, since no signage points at it.
        for e in self.elevators if lifts else ():
            label = e["properties"].get("description") or "lift"
            pt = e["geometry"]["coordinates"]
            if label.startswith(name) or (inside(pt) and not claimed_elsewhere(label)):
                found.append({"point": pt, "label": label, "kind": "lift"})

        if not found:
            found = [{"point": centroid(feature), "kind": "centre",
                      "label": name + " (building centre)"}]
        self._doors[(name, lifts)] = found
        return found
