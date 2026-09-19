#!/usr/bin/env python3
"""Solve the example walking trips and write them out for the frontend.

    python3 scripts/route_examples.py

One route per trip. The planner itself, its contract and its limits live in
../planner/SKILL.md.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from planner.plan import plan_route  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "frontend", "public", "data", "routes")

TRIPS = [
    ("malone-to-clark", "Malone Hall", "Clark Hall"),
    ("malone-to-san-martin-garage", "Malone Hall", "San Martin Garage"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    keep = {"%s.geojson" % slug for slug, _, _ in TRIPS} | {"_summary.json", "README.md"}
    for stale in os.listdir(OUT):
        if stale not in keep:
            os.remove(os.path.join(OUT, stale))
            print("removed stale %s" % stale)

    summary = []
    for slug, origin, dest in TRIPS:
        route = plan_route(origin, dest)
        entry = {"trip": slug, "from": origin, "to": dest,
                 "status": route["status"]}
        if route["status"] != "ok":
            print("%-30s %s" % (slug, route["status"]))
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
            "shortcutSpaces": s["shortcutSpaces"],
            "warnings": route["warnings"],
        })
        note = ""
        if s["shortcutMetres"]:
            note = "  cuts %.0fm across %s" % (s["shortcutMetres"],
                                               ", ".join(s["shortcutSpaces"]))
        print("%-30s %5.1f min  %5.0f m  %d steps -> %s%s"
              % (slug, s["minutes"], s["metres"], s["steps"],
                 route["destination"]["arrival"], note))

        with open(os.path.join(OUT, "%s.geojson" % slug), "w") as fh:
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
