#!/usr/bin/env python3
"""Solve the example trips with the planner package and write them out.

    python3 scripts/route_examples.py

Writes one GeoJSON per trip/profile under frontend/public/data/routes, plus a
summary the frontend reads. The planner itself lives in ../planner.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from planner import profiles                      # noqa: E402
from planner.plan import plan_route               # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "frontend", "public", "data", "routes")

# Slugs the frontend already uses, mapped to the planner's profile names.
MODES = {"walking": "walk", "smart": "walk_smart",
         "partial": "step_free", "accessible": "accessible"}

TRIPS = [
    ("malone-to-clark", "Malone Hall", "Clark Hall"),
    ("malone-to-san-martin-garage", "Malone Hall", "San Martin Garage"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for slug, origin, dest in TRIPS:
        print("\n=== %s -> %s ===" % (origin, dest))
        for mode, profile in MODES.items():
            route = plan_route(origin, dest, profile)
            entry = {"trip": slug, "mode": mode,
                     "modeLabel": profiles.PROFILES[profile]["label"],
                     "from": origin, "to": dest, "status": route["status"]}
            if route["status"] != "ok":
                print("  %-22s %s" % (entry["modeLabel"], route["status"]))
                summary.append(entry)
                continue

            s = route["summary"]
            entry.update({
                "from": route["origin"]["arrival"],
                "to": route["destination"]["arrival"],
                "minutes": s["minutes"], "metres": s["metres"], "feet": s["feet"],
                "stairSegments": s["stairSegments"], "risers": s["risers"],
                "shortcutMetres": s["shortcutMetres"],
                "shortcutSpaces": s["shortcutSpaces"],
                "fullyCompliantShare": s["fullyCompliantShare"],
                "warnings": route["warnings"],
            })
            note = ""
            if s["shortcutMetres"]:
                note = "  cuts %.0fm across %s" % (s["shortcutMetres"],
                                                   ", ".join(s["shortcutSpaces"]))
            print("  %-22s %5.1f min  %5.0f m  %d risers -> %s%s"
                  % (entry["modeLabel"], s["minutes"], s["metres"], s["risers"],
                     route["destination"]["arrival"], note))

            with open(os.path.join(OUT, "%s.%s.geojson" % (slug, mode)), "w") as fh:
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
