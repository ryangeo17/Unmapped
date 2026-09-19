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
from planner.plan import plan_route          # noqa: E402
from planner.tools import TOOLS, declarations  # noqa: E402

ROUTES = os.path.join(ROOT, "tests", "fixtures")
API_TS = os.path.join(ROOT, "frontend", "src", "api", "planner.ts")
RESULT_TSX = os.path.join(ROOT, "frontend", "src", "components", "route",
                          "RouteResult.tsx")


def summary():
    with open(os.path.join(ROUTES, "_summary.json")) as fh:
        return json.load(fh)


class TestExportedFiles(unittest.TestCase):
    def _path(self, row):
        return os.path.join(ROUTES, "%s.%s.geojson" % (row["trip"], row["mode"]))

    def test_every_trip_has_a_geojson(self):
        for row in summary():
            if row["status"] != "ok":
                continue
            self.assertTrue(os.path.exists(self._path(row)), self._path(row))

    def test_no_orphan_geojson(self):
        want = {"%s.%s.geojson" % (r["trip"], r["mode"]) for r in summary()}
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


class TestToolContract(unittest.TestCase):
    def test_every_declared_tool_is_dispatchable(self):
        for decl in declarations():
            self.assertIn(decl["name"], TOOLS)

    def test_no_undeclared_tool(self):
        names = {d["name"] for d in declarations()}
        self.assertEqual(set(TOOLS), names)

    def test_declared_parameters_match_the_signature(self):
        import inspect
        decl = next(d for d in declarations() if d["name"] == "plan_route")
        declared = set(decl["parameters"]["properties"])
        accepted = set(inspect.signature(plan_route).parameters)
        self.assertTrue(
            declared <= accepted,
            "schema advertises parameters plan_route does not take: %s"
            % sorted(declared - accepted))

    def test_required_parameters_are_really_required(self):
        decl = next(d for d in declarations() if d["name"] == "plan_route")
        self.assertEqual(set(decl["parameters"]["required"]),
                         {"origin", "destination"})

    def test_dispatch_returns_a_usable_route(self):
        result = TOOLS["plan_route"]({"origin": "Malone Hall",
                                      "destination": "Clark Hall"})
        self.assertEqual(result["status"], "ok")
        self.assertIn("geometry", result)

    def test_place_index_is_small_enough_to_send_to_a_model(self):
        index = TOOLS["list_places"]({})["places"]
        self.assertGreater(len(index), 50)
        self.assertLess(len(json.dumps(index)), 64_000,
                        "the place index is meant to be cheap to put in a prompt")


class TestSkillDoc(unittest.TestCase):
    """SKILL.md is the contract a model is given, so it must not drift."""

    def _skill(self):
        with open(os.path.join(ROOT, "planner", "SKILL.md")) as fh:
            return fh.read()

    def test_documents_every_status(self):
        skill = self._skill()
        for status in ("ok", "ambiguous", "no_route", "error"):
            self.assertIn("`%s`" % status, skill)

    def test_documents_every_summary_field(self):
        skill = self._skill()
        route = plan_route("Malone Hall", "Clark Hall")
        for field in route["summary"]:
            self.assertIn(field, skill,
                          "%s is returned but not documented in SKILL.md" % field)

    def test_the_step_caveat_is_in_the_schema_too(self):
        """A caller wiring up tool_schema.json without SKILL.md still has to
        learn not to call such a route step-free."""
        with open(os.path.join(ROOT, "planner", "tool_schema.json")) as fh:
            schema = fh.read()
        self.assertIn("stepsBesideShortcut", schema)
        self.assertIn("step-free", schema)


if __name__ == "__main__":
    unittest.main()
