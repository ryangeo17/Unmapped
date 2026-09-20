#!/usr/bin/env python3
"""
Dump the structured contents of an ArcGIS Indoors web map.

Walks the web map's operational layers, pulls every layer definition
(fields, renderer, labeling), and pages the features out to GeoJSON.

Defaults target the JHU Homewood Campus Wayfinding app.

Usage:
    python3 indoors_dump.py                    # definitions + features
    python3 indoors_dump.py --defs-only        # skip feature download
    python3 indoors_dump.py --only Units Levels Facilities
    python3 indoors_dump.py --token <token>    # if some layers need auth

Outputs, under ./indoors_out by default:
    index.json                  one entry per layer, with what was found
    fields.csv                  every field of every layer
    labels.csv                  labeling expressions and scale ranges
    defs/<layer>.json           raw layer definition as returned
    geojson/<layer>.geojson     the features
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PORTAL = "https://map.jhu.edu/portal"
WEBMAP_ID = "ea3919e7b5c242ffa8cafb87399b6901"
HEADERS = {"User-Agent": "indoors-dump/1.0"}
TOKEN = None
PAUSE = 0.2  # be polite to someone else's production service


class ApiError(Exception):
    pass


def get_json(url, params=None, retries=3, timeout=90):
    params = dict(params or {})
    params.setdefault("f", "json")
    if TOKEN:
        params.setdefault("token", TOKEN)
    body = urllib.parse.urlencode(params).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            if isinstance(payload, dict) and "error" in payload:
                err = payload["error"]
                raise ApiError("%s %s" % (err.get("code"), err.get("message")))
            time.sleep(PAUSE)
            return payload
        except ApiError:
            raise
        except urllib.error.HTTPError as exc:
            # 4xx are deterministic, retrying just hammers the service
            if 400 <= exc.code < 500:
                raise ApiError("HTTP %d %s" % (exc.code, exc.reason))
            last = exc
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise ApiError("request failed after %d tries: %s" % (retries, last))


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "layer"


def split_service(url):
    """Return (service_url, sublayer_id or None) for a layer url."""
    url = url.rstrip("/")
    tail = url.rsplit("/", 1)[-1]
    if tail.isdigit():
        return url.rsplit("/", 1)[0], int(tail)
    return url, None


def flatten_layers(nodes, trail=()):
    """Walk operationalLayers, following group layers."""
    out = []
    for node in nodes or []:
        title = node.get("title") or node.get("id") or "untitled"
        path = trail + (title,)
        children = node.get("layers")
        if node.get("layerType") == "GroupLayer" and children:
            out.extend(flatten_layers(children, path))
            continue
        url = node.get("url")
        if not url:
            # feature collections live inline, keep them as-is
            out.append({"title": title, "path": list(path), "url": None,
                        "inline": node.get("featureCollection") is not None,
                        "popupInfo": node.get("popupInfo")})
            continue
        service, sub = split_service(url)
        if sub is None and children:
            for child in children:
                out.append({"title": "%s / %s" % (title, child.get("title") or child.get("id")),
                            "path": list(path + (str(child.get("title") or child.get("id")),)),
                            "url": "%s/%s" % (service, child.get("id")),
                            "popupInfo": child.get("popupInfo")})
        else:
            out.append({"title": title, "path": list(path), "url": url,
                        "popupInfo": node.get("popupInfo"),
                        "definitionExpression": (node.get("layerDefinition") or {}).get(
                            "definitionExpression"),
                        "visibility": node.get("visibility")})
    return out


_def_cache = {}


def service_definitions(service_url):
    """One call gets every sublayer definition of a service."""
    if service_url in _def_cache:
        return _def_cache[service_url]
    try:
        data = get_json(service_url + "/layers")
        table = {}
        for item in (data.get("layers") or []) + (data.get("tables") or []):
            table[item.get("id")] = item
    except ApiError as exc:
        print("    service /layers failed (%s), will fetch individually" % exc)
        table = None
    _def_cache[service_url] = table
    return table


def layer_definition(layer_url):
    service, sub = split_service(layer_url)
    if sub is not None:
        table = service_definitions(service)
        if table and sub in table:
            return table[sub]
    return get_json(layer_url)


def label_rows(name, definition):
    rows = []
    for info in (definition.get("drawingInfo") or {}).get("labelingInfo") or []:
        expr = ""
        if info.get("labelExpressionInfo"):
            expr = info["labelExpressionInfo"].get("expression") or ""
        elif info.get("labelExpression"):
            expr = info["labelExpression"]
        symbol = info.get("symbol") or {}
        font = symbol.get("font") or {}
        rows.append({
            "layer": name,
            "expression": expr.replace("\n", " ").strip(),
            "where": info.get("where") or "",
            "minScale": info.get("minScale") or "",
            "maxScale": info.get("maxScale") or "",
            "placement": info.get("labelPlacement") or "",
            "fontFamily": font.get("family") or "",
            "fontSize": font.get("size") or "",
            "color": ",".join(str(c) for c in (symbol.get("color") or [])),
        })
    return rows


def field_rows(name, definition):
    rows = []
    for field in definition.get("fields") or []:
        domain = field.get("domain") or {}
        coded = ""
        if domain.get("type") == "codedValue":
            coded = "; ".join("%s=%s" % (cv.get("code"), cv.get("name"))
                              for cv in domain.get("codedValues") or [])
        rows.append({
            "layer": name,
            "field": field.get("name"),
            "alias": field.get("alias"),
            "type": (field.get("type") or "").replace("esriFieldType", ""),
            "length": field.get("length") or "",
            "nullable": field.get("nullable"),
            "domain": domain.get("name") or "",
            "codedValues": coded,
        })
    return rows


def oid_field(definition):
    for field in definition.get("fields") or []:
        if field.get("type") == "esriFieldTypeOID":
            return field["name"]
    return definition.get("objectIdField") or "OBJECTID"


def fetch_features(layer_url, definition, out_sr, where="1=1"):
    """Page every feature out, GeoJSON when the service supports it."""
    query = layer_url.rstrip("/") + "/query"
    total = get_json(query, {"where": where, "returnCountOnly": "true"}).get("count", 0)
    if not total:
        return {"type": "FeatureCollection", "features": []}, 0, "geojson"

    formats = (definition.get("supportedQueryFormats") or "").lower()
    fmt = "geojson" if "geojson" in formats else "json"
    advanced = definition.get("advancedQueryCapabilities") or {}
    paged = bool(advanced.get("supportsPagination"))
    page = min(int(definition.get("maxRecordCount") or 1000), 2000)
    oid = oid_field(definition)
    has_geom = bool(definition.get("geometryType"))

    features = []
    if paged:
        offset = 0
        while offset < total:
            batch = get_json(query, {
                "where": where, "outFields": "*", "outSR": out_sr, "f": fmt,
                "returnGeometry": "true" if has_geom else "false",
                "resultOffset": offset,
                "resultRecordCount": page, "orderByFields": oid,
            })
            got = batch.get("features") or []
            features.extend(got)
            print("      %d / %d" % (len(features), total))
            if not got:
                break
            offset += len(got)
    else:
        ids = get_json(query, {"where": where, "returnIdsOnly": "true"}).get("objectIds") or []
        ids.sort()
        for start in range(0, len(ids), page):
            chunk = ids[start:start + page]
            batch = get_json(query, {
                "objectIds": ",".join(str(i) for i in chunk),
                "outFields": "*", "outSR": out_sr, "f": fmt,
                "returnGeometry": "true" if has_geom else "false",
            })
            features.extend(batch.get("features") or [])
            print("      %d / %d" % (len(features), total))

    if fmt == "geojson":
        return {"type": "FeatureCollection", "features": features}, total, "geojson"
    return {"esriFeatures": features, "note": "service does not serve geojson"}, total, "esrijson"


def main():
    global TOKEN

    ap = argparse.ArgumentParser(description="Dump an ArcGIS Indoors web map")
    ap.add_argument("--portal", default=PORTAL)
    ap.add_argument("--webmap", default=WEBMAP_ID)
    ap.add_argument("--out", default="indoors_out")
    ap.add_argument("--token", default=None, help="portal token, if layers need auth")
    ap.add_argument("--out-sr", default="4326", help="output wkid, default lon/lat")
    ap.add_argument("--defs-only", action="store_true", help="skip feature download")
    ap.add_argument("--apply-filters", action="store_true",
                    help="apply the web map's definitionExpression instead of exporting all")
    ap.add_argument("--only", nargs="*", default=None,
                    help="only layers whose title contains one of these")
    args = ap.parse_args()
    TOKEN = args.token

    os.makedirs(os.path.join(args.out, "defs"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "geojson"), exist_ok=True)

    item_data = "%s/sharing/rest/content/items/%s/data" % (
        args.portal.rstrip("/"), args.webmap)
    print("reading web map %s" % args.webmap)
    webmap = get_json(item_data)

    layers = flatten_layers(webmap.get("operationalLayers"))
    basemap = (webmap.get("baseMap") or {}).get("baseMapLayers") or []
    print("found %d operational layers, %d basemap layers" % (len(layers), len(basemap)))

    floor_info = webmap.get("mapFloorInfo")
    if floor_info:
        with open(os.path.join(args.out, "floor_info.json"), "w") as fh:
            json.dump(floor_info, fh, indent=2)
        print("saved mapFloorInfo (levels, facilities, site layers)")

    all_fields, all_labels, index = [], [], []

    for entry in layers:
        title = entry["title"]
        if args.only and not any(k.lower() in title.lower() for k in args.only):
            continue
        print("\n[%s]" % title)

        record = {"title": title, "path": entry["path"], "url": entry.get("url"),
                  "status": "ok", "featureCount": None, "labels": 0, "fields": 0}

        if not entry.get("url"):
            record["status"] = "inline feature collection, no service url"
            print("    " + record["status"])
            index.append(record)
            continue

        try:
            definition = layer_definition(entry["url"])
        except ApiError as exc:
            record["status"] = "definition failed: %s" % exc
            print("    " + record["status"])
            index.append(record)
            continue

        name = safe_name(title)
        record["serviceLayerName"] = definition.get("name")
        record["definitionExpression"] = entry.get("definitionExpression")
        record["visibleByDefault"] = entry.get("visibility")
        record["geometryType"] = definition.get("geometryType")
        record["spatialReference"] = (definition.get("extent") or {}).get("spatialReference")

        with open(os.path.join(args.out, "defs", name + ".json"), "w") as fh:
            json.dump(definition, fh, indent=2)

        fields = field_rows(title, definition)
        labels = label_rows(title, definition)
        all_fields.extend(fields)
        all_labels.extend(labels)
        record["fields"] = len(fields)
        record["labels"] = len(labels)
        print("    %d fields, %d label classes" % (len(fields), len(labels)))
        for row in labels:
            print("      label: %s" % (row["expression"] or "(symbol only)"))

        if entry.get("popupInfo"):
            record["popupTitle"] = entry["popupInfo"].get("title")

        if args.defs_only:
            index.append(record)
            continue

        try:
            data, total, kind = fetch_features(
                entry["url"], definition, args.out_sr,
                where=(entry.get("definitionExpression") or "1=1")
                      if args.apply_filters else "1=1")
            ext = "geojson" if kind == "geojson" else "json"
            path = os.path.join(args.out, "geojson", "%s.%s" % (name, ext))
            with open(path, "w") as fh:
                json.dump(data, fh)
            record["featureCount"] = total
            record["file"] = path
            print("    saved %d features to %s" % (total, path))
        except ApiError as exc:
            record["status"] = "features failed: %s" % exc
            print("    " + record["status"])

        index.append(record)

    if args.only:
        print("\n--only run: leaving fields.csv / labels.csv / index.json untouched")
        return

    with open(os.path.join(args.out, "fields.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "layer", "field", "alias", "type", "length", "nullable", "domain", "codedValues"])
        writer.writeheader()
        writer.writerows(all_fields)

    with open(os.path.join(args.out, "labels.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "layer", "expression", "where", "minScale", "maxScale",
            "placement", "fontFamily", "fontSize", "color"])
        writer.writeheader()
        writer.writerows(all_labels)

    with open(os.path.join(args.out, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)

    ok = sum(1 for r in index if r["status"] == "ok")
    print("\ndone. %d/%d layers ok, output in %s/" % (ok, len(index), args.out))
    for record in index:
        if record["status"] != "ok":
            print("  skipped: %s  (%s)" % (record["title"], record["status"]))


if __name__ == "__main__":
    sys.exit(main())
