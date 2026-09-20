#!/usr/bin/env python3
"""Check a deployment before and after it goes up.

    python3 scripts/preflight.py                       # local files only
    python3 scripts/preflight.py --api https://api.example.com \
                                --web https://app.example.com

Without URLs it checks only what is in the repo: that the seed files exist and
agree with each other, that every hazard's evidence image is present, and that
nothing still carries a placeholder. With URLs it also exercises the live pair
the way a browser would, including the CORS preflight that is the usual reason
a freshly deployed site cannot talk to its own API.

Standard library only. Exits non-zero if anything fails.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES = []
WARNINGS = []


def check(name, ok, detail=""):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, ("  — " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


def warn(name, detail=""):
    print("  warn %s%s" % (name, ("  — " + detail) if detail else ""))
    WARNINGS.append(name)


def load(*parts):
    with open(os.path.join(ROOT, *parts)) as fh:
        return json.load(fh)


def check_repo():
    print("\nrepo")
    graph = load("data", "homewood_graph.json")
    landmarks = load("data", "homewood_landmarks.json")
    doors = load("data", "homewood_doors.json")
    hazards = load("data", "homewood_hazards.json")

    check("graph has nodes and edges", bool(graph["nodes"]) and bool(graph["edges"]),
          "%d nodes, %d edges" % (len(graph["nodes"]), len(graph["edges"])))

    node_ids = {n["id"] for n in graph["nodes"]}
    dangling = [e["id"] for e in graph["edges"]
                if e["from_node"] not in node_ids or e["to_node"] not in node_ids]
    check("every edge endpoint is a real node", not dangling, str(dangling[:3]))

    landmark_ids = {item["id"] for item in landmarks}
    orphan_doors = [d for d in doors if d["landmark_id"] not in landmark_ids]
    check("every door belongs to a landmark", not orphan_doors, str(orphan_doors[:2]))

    door_nodes = [d for d in doors if d["node_id"] not in node_ids]
    check("every door snaps to a real node", not door_nodes, str(door_nodes[:2]))

    placeless = landmark_ids - {d["landmark_id"] for d in doors}
    if placeless:
        warn("%d landmarks have no door" % len(placeless), "they will not be routable")

    edge_ids = {e["id"] for e in graph["edges"]}
    bad_hazards = [h["id"] for h in hazards if h.get("edge_id") not in edge_ids]
    check("every hazard sits on a real edge", not bad_hazards, str(bad_hazards))

    missing = []
    for hazard in hazards:
        for path in json.loads(hazard.get("evidence") or "[]"):
            if not os.path.exists(os.path.join(ROOT, "backend", "static", path.lstrip("/"))):
                missing.append(path)
    check("every evidence image exists", not missing, str(missing))

    # A placeholder that reaches production is a site that cannot call its API.
    with open(os.path.join(ROOT, "render.yaml")) as fh:
        render = fh.read()
    check("render.yaml has no placeholder origin", "example.com" not in render)

    served = os.path.join(ROOT, "frontend", "public", "data")
    check("campus GeoJSON is present to serve",
          os.path.isdir(served) and len(os.listdir(served)) > 5)


def get(url, origin=None, timeout=20):
    request = urllib.request.Request(url)
    if origin:
        request.add_header("Origin", origin)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.headers, response.read()


def check_api(api, web, admin_password=None):
    print("\napi  %s" % api)
    base = api.rstrip("/")
    try:
        status, _, body = get(base + "/health")
    except Exception as exc:
        check("reachable", False, str(exc)[:120])
        return
    health = json.loads(body)
    check("healthy", status == 200 and health.get("status") == "ok")
    check("graph is seeded", health.get("nodes", 0) > 1000,
          "%s nodes, %s edges" % (health.get("nodes"), health.get("published_edges")))

    # The CORS preflight is what actually fails first on a fresh deploy.
    if web:
        origin = web.rstrip("/")
        try:
            request = urllib.request.Request(base + "/api/routes/compute", method="OPTIONS")
            request.add_header("Origin", origin)
            request.add_header("Access-Control-Request-Method", "POST")
            request.add_header("Access-Control-Request-Headers", "content-type")
            with urllib.request.urlopen(request, timeout=20) as response:
                allowed = response.headers.get("access-control-allow-origin")
        except urllib.error.HTTPError as exc:
            allowed = exc.headers.get("access-control-allow-origin")
        except Exception as exc:
            allowed = "error: %s" % str(exc)[:60]
        check("CORS allows the frontend origin", allowed == origin,
              "sent Origin %s, got %s — set CORS_ORIGINS on the API" % (origin, allowed))

    try:
        payload = json.dumps({"start": "Malone Hall", "end": "Clark Hall",
                              "mode": "walking", "smarter": True}).encode()
        request = urllib.request.Request(base + "/api/routes/compute", data=payload,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            route = json.loads(response.read())
        check("a route computes", route["verified_stats"]["distance_m"] > 0,
              "%.0f m via %s" % (route["verified_stats"]["distance_m"],
                                 (route.get("end_door") or {}).get("label", "?")))
    except Exception as exc:
        check("a route computes", False, str(exc)[:140])

    try:
        _, _, body = get(base + "/api/landmarks")
        check("places are searchable", len(json.loads(body)) > 50)
    except Exception as exc:
        check("places are searchable", False, str(exc)[:100])

    # The check this file did not have when it was needed. On serverless the
    # database can be per-instance, so a session written while logging in is
    # invisible to whichever instance handles the next request, and the admin
    # console fails with "Invalid session" partway through a workflow. One
    # request cannot see that: the failure only appears once a later call lands
    # somewhere else, so this logs in once and then reuses the token several
    # times, which is what the console itself does.
    if admin_password:
        try:
            payload = json.dumps({"password": admin_password}).encode()
            request = urllib.request.Request(base + "/api/admin/login", data=payload,
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:
                token = json.loads(response.read())["token"]
        except urllib.error.HTTPError as exc:
            check("admin can log in", False,
                  "HTTP %d — is ADMIN_PASSWORD what you passed?" % exc.code)
            token = None
        except Exception as exc:
            check("admin can log in", False, str(exc)[:100])
            token = None
        if token:
            check("admin can log in", True)
            codes = []
            for _ in range(6):
                try:
                    request = urllib.request.Request(base + "/api/admin/submissions")
                    request.add_header("Authorization", "Bearer " + token)
                    with urllib.request.urlopen(request, timeout=20) as response:
                        codes.append(response.status)
                except urllib.error.HTTPError as exc:
                    codes.append(exc.code)
                except Exception:
                    codes.append(0)
            survived = all(code == 200 for code in codes)
            check("the session survives across requests", survived,
                  "%s — a 401 here means the session store is per-instance; "
                  "point DATABASE_URL at a shared database" % codes)


def check_web(web):
    print("\nweb  %s" % web)
    base = web.rstrip("/")
    try:
        status, _, body = get(base + "/")
        html = body.decode("utf-8", "replace")
    except Exception as exc:
        check("reachable", False, str(exc)[:120])
        return
    check("serves the app", status == 200 and "<div id=\"root\">" in html)

    try:
        status, _, _ = get(base + "/admin")
        check("SPA deep links fall back to index.html", status == 200)
    except Exception as exc:
        check("SPA deep links fall back to index.html", False, str(exc)[:100])

    try:
        status, headers, body = get(base + "/data/Facilities.geojson")
        check("campus data is served", status == 200 and len(body) > 100_000,
              "%.0f KB" % (len(body) / 1024))
    except Exception as exc:
        check("campus data is served", False, str(exc)[:100])

    # Whether a Mapbox token was baked in cannot be told from the bundle:
    # mapbox-gl's own code contains the "pk.ey" pattern, so grepping for it
    # says yes either way. A check that cannot fail is worse than none, so
    # this is a reminder rather than an assertion — open the page and look.
    print("  note the Mapbox token is baked in at build time. If the map pane "
          "reads\n       'Mapbox token needed', set VITE_MAPBOX_ACCESS_TOKEN "
          "and rebuild;\n       changing it on the host afterwards has no effect.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", help="deployed API base URL")
    ap.add_argument("--web", help="deployed frontend base URL")
    ap.add_argument("--admin-password", help="enables the admin session check")
    args = ap.parse_args()

    check_repo()
    if args.api:
        check_api(args.api, args.web, args.admin_password)
    if args.web:
        check_web(args.web)

    print()
    if WARNINGS:
        print("%d warning(s): %s" % (len(WARNINGS), ", ".join(WARNINGS)))
    if FAILURES:
        print("%d check(s) failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
