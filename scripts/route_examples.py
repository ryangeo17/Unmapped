#!/usr/bin/env python3
"""Solve the example walking trips and write them out as golden fixtures.

    python3 scripts/route_examples.py

The frontend no longer reads these — it asks the planner service for routes
between whatever the user typed. They stay as a regression baseline, one file
per trip per switch position, so a change in the planner shows up as a diff.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from planner import profiles          # noqa: E402
from planner.plan import plan_route  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "tests", "fixtures")

TRIPS = [
    ("malone-to-clark", "Malone Hall", "Clark Hall"),
    ("malone-to-san-martin-garage", "Malone Hall", "San Martin Garage"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    keep = {"%s.%s.%s.geojson" % (slug, p, sw) for slug, _, _ in TRIPS
            for p in profiles.ORDER for sw in ("smarter", "plain")} \
        | {"_summary.json", "README.md"}
    for stale in os.listdir(OUT):
        if stale not in keep:
            os.remove(os.path.join(OUT, stale))
            print("removed stale %s" % stale)

    summary = []
    for slug, origin, dest in TRIPS:
      for profile in profiles.ORDER:
       for mode, smarter in (("smarter", True), ("plain", False)):
        route = plan_route(origin, dest, profile, smarter)
        entry = {"trip": slug, "profile": profile, "mode": mode,
                 "smarter": smarter, "from": origin, "to": dest,
                 "status": route["status"]}
        if route["status"] != "ok":
            print("%-28s %-11s %-8s %s" % (slug, profile, mode, route["status"]))
            summary.append(entry)
            continue

        s = route["summary"]
        entry.update({
            "label": "%s → %s" % (origin, dest),
            "from": route["origin"]["arrival"],
            "to": route["destination"]["arrival"],
            "toKind": route["destination"]["kind"],
            "minutes": s["minutes"], "metres": s["metres"], "feet": s["feet"],
            "steps": s["steps"],
            "stepsBesideShortcut": s["stepsBesideShortcut"],
            "shortcutMetres": s["shortcutMetres"],
            "profileLabel": route["profileLabel"],
            "shortcutSpaces": s["shortcutSpaces"],
            "savedBySmarter": route["savedBySmarter"],
            "warnings": route["warnings"],
        })
        note = ""
        if s["shortcutMetres"]:
            note = "  cuts %.0fm across %s" % (s["shortcutMetres"],
                                               ", ".join(s["shortcutSpaces"]))
        print("%-28s %-11s %-8s %5.1f min %5.0f m %2d steps -> %s%s"
              % (slug, profile, mode, s["minutes"], s["metres"], s["steps"],
                 route["destination"]["arrival"].strip(), note))

        with open(os.path.join(OUT, "%s.%s.%s.geojson" % (slug, profile, mode)),
                  "w") as fh:
            json.dump({"type": "FeatureCollection",
                       "features": [{"type": "Feature", "properties": entry,
                                     "geometry": route["geometry"]}]},
                      fh, separators=(",", ":"))
        summary.append(entry)

    with open(os.path.join(OUT, "_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print("\nwrote %d files" % len(os.listdir(OUT)))


if __name__ == "__main__":
    main()
