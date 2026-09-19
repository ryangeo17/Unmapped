"""Planner unit tests. Standard library only:

    python3 -m unittest discover tests -v

Needs planner/graph_cache.json; build it once with
`python3 -m planner.build_cache` (about 40 seconds).
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from planner.geometry import metres          # noqa: E402
from planner.plan import plan_route, places  # noqa: E402


class TestResolution(unittest.TestCase):
    def test_exact_name(self):
        place, alts = places().resolve("Malone Hall")
        self.assertEqual(place["properties"]["name"], "Malone Hall")
        self.assertEqual(alts, [])

    def test_alias(self):
        place, _ = places().resolve("MSEL")
        self.assertEqual(place["properties"]["name"], "Milton S. Eisenhower Library")

    def test_case_and_partial(self):
        place, _ = places().resolve("malone")
        self.assertEqual(place["properties"]["name"], "Malone Hall")

    def test_outdoor_space(self):
        place, _ = places().resolve("decker quad")
        self.assertEqual(place["properties"]["name"], "Decker Quad")

    def test_ambiguous_returns_candidates_not_a_guess(self):
        place, alts = places().resolve("the garage")
        self.assertIsNone(place)
        self.assertGreater(len(alts), 1)
        self.assertIn("San Martin Garage", alts)

    def test_unknown(self):
        place, alts = places().resolve("xyzzy")
        self.assertIsNone(place)
        self.assertEqual(alts, [])


class TestStatuses(unittest.TestCase):
    def test_ambiguous_destination(self):
        r = plan_route("Malone Hall", "the garage")
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(r["field"], "destination")
        self.assertIn("San Martin Garage", r["candidates"])
        self.assertNotIn("geometry", r)

    def test_unresolvable_origin(self):
        r = plan_route("xyzzy", "Clark Hall")
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["field"], "origin")


class TestRouteShape(unittest.TestCase):
    """Whatever the numbers become, the contract has to hold."""

    @classmethod
    def setUpClass(cls):
        cls.route = plan_route("Malone Hall", "Clark Hall")

    def test_status_ok(self):
        self.assertEqual(self.route["status"], "ok")

    def test_required_keys(self):
        for key in ("origin", "destination", "summary", "geometry", "legs",
                    "warnings"):
            self.assertIn(key, self.route)
        for key in ("minutes", "metres", "feet", "steps", "stepsBesideShortcut",
                    "shortcutMetres", "shortcutSpaces"):
            self.assertIn(key, self.route["summary"], key)

    def test_geometry_is_a_drawable_linestring(self):
        geom = self.route["geometry"]
        self.assertEqual(geom["type"], "LineString")
        self.assertGreater(len(geom["coordinates"]), 1)
        for lng, lat in geom["coordinates"]:
            self.assertTrue(-77 < lng < -76, lng)      # Baltimore, not 0,0
            self.assertTrue(39 < lat < 40, lat)

    def test_reported_length_matches_the_geometry(self):
        """The bug this catches: reporting a distance the drawn line does not
        have, which happened twice while building this."""
        coords = self.route["geometry"]["coordinates"]
        drawn = sum(metres(a, b) for a, b in zip(coords, coords[1:]))
        self.assertAlmostEqual(drawn, self.route["summary"]["metres"], delta=0.2)

    def test_geometry_has_no_jumps(self):
        coords = self.route["geometry"]["coordinates"]
        gaps = [metres(a, b) for a, b in zip(coords, coords[1:])]
        self.assertLess(max(gaps), 300, "a gap that large means a broken path")

    def test_endpoints_match_the_named_doors(self):
        self.assertEqual(self.route["geometry"]["coordinates"][0],
                         self.route["origin"]["point"])
        self.assertEqual(self.route["geometry"]["coordinates"][-1],
                         self.route["destination"]["point"])

    def test_legs_sum_to_the_total(self):
        self.assertAlmostEqual(sum(l["metres"] for l in self.route["legs"]),
                               self.route["summary"]["metres"], delta=0.5)


class TestSmartBehaviour(unittest.TestCase):
    """The two things this planner exists to do."""

    def test_clark_takes_the_lawn_shortcut(self):
        r = plan_route("Malone Hall", "Clark Hall")
        self.assertGreater(r["summary"]["shortcutMetres"], 0)
        self.assertIn("Decker Quad", r["summary"]["shortcutSpaces"])
        self.assertTrue(any("open lawn" in w for w in r["warnings"]))

    def test_garage_finishes_at_the_lift(self):
        """San Martin Garage has no entryway record, so without any-entrance
        arrival this lands on the building centre instead."""
        r = plan_route("Malone Hall", "San Martin Garage")
        self.assertEqual(r["destination"]["kind"], "lift")
        self.assertIn("Elevator", r["destination"]["arrival"])

    def test_a_shortcut_beside_a_flight_is_never_called_step_free(self):
        """Regression: steps read 0 because the shortcut lands on the far side
        of a three-riser link at Clark Hall Main."""
        r = plan_route("Malone Hall", "Clark Hall")
        if r["summary"]["stepsBesideShortcut"]:
            self.assertTrue(any("step" in w.lower() for w in r["warnings"]),
                            "a nearby flight must produce a warning")

    def test_shortcuts_never_cross_a_building(self):
        import json
        from planner import graph
        from planner.geometry import in_ring, rings
        facilities = graph.load("Facilities.geojson")
        blocked = [rings(f) for f in facilities]
        r = plan_route("Malone Hall", "Clark Hall")
        for leg in r["legs"]:
            if leg["kind"] != "shortcut":
                continue
            a, b = leg["from"], leg["to"]
            for i in range(21):
                t = i / 20
                pt = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                for rs in blocked:
                    self.assertFalse(any(in_ring(pt, ring) for ring in rs),
                                     "shortcut passes through a building")
        del json


if __name__ == "__main__":
    unittest.main()
