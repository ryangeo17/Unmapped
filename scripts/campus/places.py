"""Resolving a name to the points you can actually arrive at.

Entryways.facility_id is populated on 4 of 337 rows, so entrances are matched
to buildings by geometry and name. Footprints overlap — San Martin Center sits
on top of San Martin Garage — so a point inside a building is only claimed when
its own name does not belong to a different building.
"""
import re

from .geometry import centroid, dist_to_rings, in_ring, rings

NEAR_M = 12.0
STOPWORDS = {"the", "a", "an", "at", "to", "in", "of",
             "building", "hall", "center", "centre", "house"}
FAR_M = 50.0     # how far a door may sit from the building its name names


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
        self._doors = None
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

    def _tokens(self, text):
        return set(_norm(text).split())

    def _assign(self):
        """Work out once which place each door belongs to.

        Footprints overlap and abut, so a door can sit inside or within reach
        of several buildings. Resolved by a ladder, most decisive first:

        1. the door's name starts with a building's name — definitive
        2. exactly one candidate's polygon actually contains it
        3. the door's name contains a candidate's name as whole words, e.g.
           "ROTC side entrance" against "ROTC Building"
        4. nearest polygon edge

        Outdoor spaces take no doors at all. Arriving at a quad means reaching
        the quad, not the museum door on its edge.
        """
        if self._doors is not None:
            return self._doors

        doors = {f["properties"]["name"]: [] for f in self.facilities}
        candidates = [(f["properties"]["name"], rings(f),
                       self._bounds(f, f["properties"]["name"]))
                      for f in self.facilities]

        seen_points = {name: set() for name in doors}
        sources = [(self.entryways, "entrance", "entrance_name"),
                   (self.elevators, "lift", "description")]
        for features, kind, field in sources:
            for e in features:
                pt = e["geometry"]["coordinates"]
                label = e["properties"].get(field) or kind
                near = []
                for name, rs, (xmin, ymin, xmax, ymax) in candidates:
                    if label.startswith(name):
                        near.append((name, rs, True, 0.0))
                        continue
                    if not (xmin <= pt[0] <= xmax and ymin <= pt[1] <= ymax):
                        continue
                    contains = any(in_ring(pt, r) for r in rs)
                    distance = 0.0 if contains else dist_to_rings(pt, rs)
                    if contains or distance < NEAR_M:
                        near.append((name, rs, contains, distance))
                if not near:
                    continue

                named = [n for n in near if label.startswith(n[0])]
                if named:                                   # 1
                    winner = max(named, key=lambda n: len(n[0]))
                else:
                    inside = [n for n in near if n[2]]
                    pool = inside or near                   # 2
                    if len(pool) > 1:
                        words = self._tokens(label)
                        worded = [n for n in pool
                                  if self._tokens(n[0]) and self._tokens(n[0]) <= words]
                        if worded:                          # 3
                            pool = worded
                    winner = min(pool, key=lambda n: (n[3], len(n[0])))  # 4

                name = winner[0]
                key = (round(pt[0], 7), round(pt[1], 7))
                if key in seen_points[name]:
                    # The source data records two doors at one point — Bates
                    # Tower has DOOR-003660 and DOOR-003670 on the same spot.
                    # For walking they are one door.
                    continue
                seen_points[name].add(key)
                doors[name].append({
                    "point": pt, "label": label, "kind": kind,
                    # A lift is step-free by nature; a door is only step-free
                    # if the survey says so.
                    "stepFree": kind == "lift"
                    or e["properties"].get("accessible_entrance") == "Y",
                })

        # Doors just outside everything, whose name still says where they
        # belong: "Latrobe SW Basement Exit" sits 13.8 m from Latrobe Hall,
        # past the 12 m radius, and does not start with the full building name.
        # Match on the distinctive part of the name — the building word minus
        # Hall, Building, Center and so on.
        for features, kind, field in sources:
            for e in features:
                pt = e["geometry"]["coordinates"]
                key = (round(pt[0], 7), round(pt[1], 7))
                if any(key in pts for pts in seen_points.values()):
                    continue
                words = self._tokens(e["properties"].get(field) or kind)
                best = None
                for name, rs, _ in candidates:
                    distinctive = self._tokens(name) - STOPWORDS
                    if not distinctive or not distinctive <= words:
                        continue
                    distance = dist_to_rings(pt, rs)
                    if distance < FAR_M and (best is None or distance < best[1]):
                        best = (name, distance)
                if best:
                    seen_points[best[0]].add(key)
                    doors[best[0]].append({
                        "point": pt,
                        "label": e["properties"].get(field) or kind,
                        "kind": kind,
                        "stepFree": kind == "lift"
                        or e["properties"].get("accessible_entrance") == "Y",
                    })

        self._doors = doors
        return doors

    def _bounds(self, feature, name):
        if name not in self._bbox:
            pts = [p for r in rings(feature) for p in r]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            pad = NEAR_M / 111320.0 * 1.6      # generous: degrees, near 39N
            self._bbox[name] = (min(xs) - pad, min(ys) - pad,
                                max(xs) + pad, max(ys) + pad)
        return self._bbox[name]

    def entrances(self, feature, lifts=True, step_free=False):
        """Points that count as a way into this place.

        A lift inside a footprint counts: for a garage it is the whole point,
        and aiming at the building centre instead walks you round the block to
        a door you did not need. Only the smarter search is allowed to notice
        one, since no signage points at it.
        """
        name = feature["properties"]["name"]
        found = [d for d in self._assign().get(name, [])
                 if (lifts or d["kind"] != "lift")
                 and (not step_free or d["stepFree"])]
        if not found:
            return [{"point": centroid(feature), "kind": "centre",
                     "label": name + " (building centre)", "stepFree": None}]
        return found
