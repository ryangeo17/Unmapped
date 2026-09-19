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

    def entrances(self, feature, accessible_only=False):
        """Points that count as a way into this place.

        A lift inside the footprint counts: for a garage it is the whole point,
        and aiming at the building centre instead walks you round the block to
        a door you did not need.
        """
        name = feature["properties"]["name"]
        rs = rings(feature)
        others = [n for n in self._names if n != name]

        def claimed_elsewhere(label):
            return any(label.startswith(o) for o in others)

        def inside(pt):
            return (any(in_ring(pt, r) for r in rs)
                    or dist_to_rings(pt, rs) < NEAR_M)

        found = []
        for e in self.entryways:
            props = e["properties"]
            label = props.get("entrance_name") or "entrance"
            pt = e["geometry"]["coordinates"]
            if accessible_only and props.get("accessible_entrance") != "Y":
                continue
            if label.startswith(name) or (inside(pt) and not claimed_elsewhere(label)):
                found.append({"point": pt, "label": label, "kind": "entrance",
                              "stepFree": props.get("accessible_entrance") == "Y"})
        # A lift is step-free by nature, so it qualifies under either filter.
        for e in self.elevators:
            label = e["properties"].get("description") or "lift"
            pt = e["geometry"]["coordinates"]
            if label.startswith(name) or (inside(pt) and not claimed_elsewhere(label)):
                found.append({"point": pt, "label": label, "kind": "lift",
                              "stepFree": True})

        if not found:
            return [{"point": centroid(feature), "kind": "centre",
                     "label": name + " (building centre)", "stepFree": None}]
        return found
