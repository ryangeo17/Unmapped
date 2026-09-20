"""Contract tests across the seams: planner -> exported files -> frontend type,
and planner -> tool schema -> model.

These exist because typecheck and lint cannot see them. A field can be
declared in the TypeScript type, branched on in a component, and never written
by the exporter; everything compiles and the branch is dead. That happened.

    python3 -m unittest discover tests -v
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from planner.geometry import metres          # noqa: E402
from planner import profiles                 # noqa: E402
from planner.plan import plan_all, plan_route  # noqa: E402

ROUTES = os.path.join(ROOT, "tests", "fixtures")
API_TS = os.path.join(ROOT, "frontend", "src", "api", "planner.ts")
RESULT_TSX = os.path.join(ROOT, "frontend", "src", "components", "route",
                          "RouteOptions.tsx")


def summary():
    with open(os.path.join(ROUTES, "_summary.json")) as fh:
        return json.load(fh)


class TestExportedFiles(unittest.TestCase):
    def _path(self, row):
        return os.path.join(ROUTES, "%s.%s.%s.geojson"
                            % (row["trip"], row["profile"], row["mode"]))

    def test_every_trip_has_a_geojson(self):
        for row in summary():
            if row["status"] != "ok":
                continue
            self.assertTrue(os.path.exists(self._path(row)), self._path(row))

    def test_no_orphan_geojson(self):
        want = {"%s.%s.%s.geojson" % (r["trip"], r["profile"], r["mode"])
                for r in summary()}
        for name in os.listdir(ROUTES):
            if name.endswith(".geojson"):
                self.assertIn(name, want,
                              "%s is not in the summary; stale export?" % name)

    def test_geojson_matches_its_summary_row(self):
        for row in summary():
            if row["status"] != "ok":
                continue
            with open(self._path(row)) as fh:
                feature = json.load(fh)["features"][0]
            self.assertEqual(feature["properties"]["metres"], row["metres"])
            coords = feature["geometry"]["coordinates"]
            drawn = sum(metres(a, b) for a, b in zip(coords, coords[1:]))
            self.assertAlmostEqual(drawn, row["metres"], delta=0.2)

class TestFrontendContract(unittest.TestCase):
    """The TypeScript view of a route must match what the planner returns.

    The frontend calls the service now, so the contract is the RouteOk type
    against a live plan_route result rather than a file on disk.
    """

    def _ts_block(self, name):
        with open(API_TS) as fh:
            src = fh.read()
        block = re.search(r"export type %s = \{(.*?)\n\}" % name, src, re.S)
        self.assertIsNotNone(block, "%s not found in planner.ts" % name)
        return block.group(1)

    def test_route_type_fields_are_all_returned(self):
        declared = {m.group(1) for m in
                    re.finditer(r"^  (\w+)\??:", self._ts_block("RouteOk"), re.M)}
        returned = set(plan_route("Malone Hall", "Clark Hall"))
        missing = declared - returned
        self.assertFalse(missing,
                         "RouteOk declares fields plan_route never returns: %s"
                         % sorted(missing))

    def test_summary_type_fields_are_all_returned(self):
        block = re.search(r"summary: \{(.*?)\n  \}",
                          self._ts_block("RouteOk"), re.S).group(1)
        declared = {m.group(1) for m in re.finditer(r"(\w+):", block)}
        returned = set(plan_route("Malone Hall", "Clark Hall")["summary"])
        self.assertFalse(declared - returned, sorted(declared - returned))

    def test_saved_type_fields_are_all_returned(self):
        declared = {m.group(1) for m in
                    re.finditer(r"^  (\w+):", self._ts_block("Saved"), re.M)}
        returned = set(plan_route("Malone Hall", "Clark Hall")["savedBySmarter"])
        self.assertFalse(declared - returned, sorted(declared - returned))

    def test_fields_the_ui_branches_on_are_returned(self):
        """Catches a live branch reading something nothing produces — the bug
        that prompted this whole file."""
        with open(RESULT_TSX) as fh:
            src = fh.read()
        route = plan_route("Malone Hall", "Clark Hall")
        for expr, available in (("summary", route["summary"]),
                                ("saved", route["savedBySmarter"])):
            used = set(re.findall(r"\b%s\.(\w+)" % expr, src))
            missing = used - set(available)
            self.assertFalse(missing,
                             "RouteResult reads %s.%s which is never returned"
                             % (expr, sorted(missing)))


class TestProfiles(unittest.TestCase):
    def test_all_three_solve_both_example_trips(self):
        for a, b in (("Malone Hall", "Clark Hall"),
                     ("Malone Hall", "San Martin Garage")):
            routes = plan_all(a, b)["routes"]
            self.assertEqual(len(routes), 3)
            for route in routes:
                self.assertEqual(route["status"], "ok",
                                 "%s -> %s %s" % (a, b, route.get("profile")))

    def test_accessible_profiles_never_take_a_shortcut(self):
        """Shortcut edges are inferred from geometry, not surveyed, so they
        have no business in an accessibility answer."""
        for profile in ("step_free", "accessible"):
            route = plan_route("Malone Hall", "Clark Hall", profile)
            self.assertEqual(route["summary"]["shortcutMetres"], 0, profile)
            self.assertFalse(route["smarter"], profile)

    def test_accessible_profiles_take_no_steps(self):
        for profile in ("step_free", "accessible"):
            route = plan_route("Malone Hall", "San Martin Garage", profile)
            self.assertEqual(route["summary"]["steps"], 0, profile)

    def test_accessible_profiles_warn_about_unmodelled_steps(self):
        route = plan_route("Malone Hall", "Clark Hall", "step_free")
        self.assertTrue(any("step-free" in w.lower() for w in route["warnings"]),
                        route["warnings"])

    def test_reported_minutes_are_real_not_the_weighted_cost(self):
        """A* minimises a weighted cost; reporting it as duration showed the
        fully accessible route at 24 minutes for a 9 minute walk."""
        for profile in profiles.ORDER:
            route = plan_route("Malone Hall", "San Martin Garage", profile)
            speed = route["summary"]["metres"] / (route["summary"]["minutes"] * 60)
            self.assertTrue(1.0 < speed < 1.45,
                            "%s implies %.2f m/s" % (profile, speed))

    def test_the_switch_only_reaches_walking(self):
        for profile in ("step_free", "accessible"):
            on = plan_route("Malone Hall", "Clark Hall", profile, smarter=True)
            off = plan_route("Malone Hall", "Clark Hall", profile, smarter=False)
            self.assertEqual(on["geometry"], off["geometry"], profile)

    def test_unknown_profile_is_an_error(self):
        self.assertEqual(
            plan_route("Malone Hall", "Clark Hall", "teleport")["status"], "error")


if __name__ == "__main__":
    unittest.main()
