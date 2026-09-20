from __future__ import annotations

import heapq
import json
import math
import re
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .core import VERIFIED_PATH_ID, GraphEdge, GraphNode, Hazard, Landmark, LandmarkDoor, hazard_evidence


STOPWORDS = {"the", "and", "for", "building", "hall", "center", "centre", "house"}
GPS_RE = re.compile(
    r"^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)(?:\s*,\s*-?\d+(?:\.\d+)?)?$"
)
HAZARD_SNAP_M = 40.0

SPEED_MPS = {"walking": 1.35, "wheelchair": 1.05, "scooter": 3.8, "bicycle": 4.5}
# Grass is 1.25 for walking because the campus network's own walktime implies
# 1.31 m/s on pavement and turf walks at about 1.05; without it a lawn diagonal
# is priced as though it were a footpath and gets taken when it should not.
SURFACE_PENALTY = {
    "walking": {"paved": 1.0, "brick": 1.08, "grass": 1.25, "gravel": 1.25, "dirt": 1.4},
    "wheelchair": {"paved": 1.0, "brick": 1.3, "grass": 3.0, "gravel": 2.2, "dirt": 3.0},
    "scooter": {"paved": 1.0, "brick": 1.45, "grass": 3.5, "gravel": 2.5, "dirt": 3.5},
    "bicycle": {"paved": 1.0, "brick": 1.2, "grass": 1.8, "gravel": 1.45, "dirt": 1.8},
}


def _closure_around(edges, nodes: set[str]) -> str | None:
    """Name the construction sealing these nodes off.

    Called only once the search has already failed, so the question is not
    whether they are enclosed but what to tell the user. A closure bordering
    the destination is the answer worth giving: it has a name and an end date,
    where "no route available" sounds like a gap in the map.
    """
    closed = [e for e in edges
              if e.closed and (e.from_node in nodes or e.to_node in nodes)]
    if not closed:
        return None
    named = {e.space for e in closed if e.space}
    return sorted(named)[0] if named else "construction"


def _door(door) -> dict | None:
    if door is None or door.kind == "node":
        return None
    return {"label": door.label, "kind": door.kind, "step_free": door.step_free}


def metres(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlng = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def nearest_graph_node(db: Session, lat: float, lng: float) -> tuple[GraphNode, float]:
    """Snap a GPS fix to the pavement network."""
    best: GraphNode | None = None
    best_d = float("inf")
    for node in db.scalars(select(GraphNode)).all():
        dx = (node.longitude - lng) * 111320 * 0.7735
        dy = (node.latitude - lat) * 110540
        distance = math.hypot(dx, dy)
        if distance < best_d:
            best, best_d = node, distance
    if best is None:
        raise HTTPException(404, "The graph has no nodes")
    return best, round(best_d, 1)


def parse_gps(value: str) -> tuple[float, float] | None:
    match = GPS_RE.match(value.strip())
    if not match:
        return None
    first, second = float(match.group(1)), float(match.group(2))
    # The app sends latitude,longitude. GeoJSON and some clients send the reverse.
    if abs(first) > 90 and abs(second) <= 90:
        return second, first
    if abs(first) > 50 and abs(second) < 50:
        return second, first
    return first, second


def hazard_applies(hazard: Hazard, nighttime: bool) -> bool:
    when = (getattr(hazard, "active_when", "always") or "always").lower()
    if when == "night":
        return nighttime
    if when == "day":
        return not nighttime
    return True


def path_length_m(points: list[list[float]]) -> float:
    total = 0.0
    for index in range(1, len(points)):
        total += metres(points[index - 1][0], points[index - 1][1], points[index][0], points[index][1])
    return total


def project_point_to_path(lat: float, lng: float, geometry: list[list[float]]) -> tuple[float, float, float]:
    """Return the closest point on a [lat, lng] polyline and the distance in metres."""
    if len(geometry) < 2:
        raise HTTPException(422, "The verified path has no drawable geometry yet")
    origin = (lat, lng)
    best_lat, best_lng, best_d = geometry[0][0], geometry[0][1], float("inf")
    for index in range(len(geometry) - 1):
        start, end = geometry[index], geometry[index + 1]
        ax = (start[1] - origin[1]) * 111320 * math.cos(math.radians(origin[0]))
        ay = (start[0] - origin[0]) * 111320
        bx = (end[1] - origin[1]) * 111320 * math.cos(math.radians(origin[0]))
        by = (end[0] - origin[0]) * 111320
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        fraction = 0.0 if length == 0 else min(1.0, max(0.0, -(ax * dx + ay * dy) / length))
        px, py = ax + dx * fraction, ay + dy * fraction
        distance = math.hypot(px, py)
        if distance < best_d:
            best_d = distance
            best_lat = start[0] + (end[0] - start[0]) * fraction
            best_lng = start[1] + (end[1] - start[1]) * fraction
    return best_lat, best_lng, best_d


@dataclass
class Arc:
    edge: GraphEdge
    target: str
    reversed: bool


def find_landmark(db: Session, value: str) -> Landmark | None:
    """Exact id, then exact name or alias, then substring, then all-words.

    The loose tiers matter now that there are 116 places rather than 7: people
    type "malone" and "the garage". An ambiguous query is answered with its
    candidates rather than a guess — "the garage" matches four, and silently
    picking one sends someone to the wrong side of campus.
    """
    exact = db.scalar(
        select(Landmark).where(
            or_(Landmark.id == value, Landmark.name.ilike(value), Landmark.alias.ilike(value))
        )
    )
    if exact:
        return exact

    hits = db.scalars(
        select(Landmark).where(
            or_(Landmark.name.ilike(f"%{value}%"), Landmark.alias.ilike(f"%{value}%"))
        )
    ).all()
    if not hits:
        # Drop the words that carry no signal, or "the garage" matches nothing
        # and a real ambiguity is reported as an unknown place.
        words = [w for w in re.split(r"[^A-Za-z0-9]+", value.lower())
                 if len(w) > 2 and w not in STOPWORDS]
        if words:
            clauses = [Landmark.name.ilike(f"%{w}%") for w in words]
            hits = [
                row for row in db.scalars(select(Landmark).where(or_(*clauses))).all()
                if all(w.lower() in row.name.lower() for w in words)
            ]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise HTTPException(
            409,
            {
                "error": f"{value!r} matches {len(hits)} places",
                "candidates": sorted(row.name for row in hits)[:12],
            },
        )
    return None


def resolve_doors(db: Session, value: str, step_free: bool = False) -> list[LandmarkDoor]:
    """Every way into a place, as graph nodes.

    A building has several doors and which one is nearest decides the route, so
    the search starts from all of them at once. San Martin Garage is the case
    that forces it: the survey records no entrance for it, only a lift.
    """
    if db.get(GraphNode, value):
        # A bare node id — a GPS fix that the client already snapped. It is by
        # definition on the network, so there is no shortfall to report.
        return [LandmarkDoor(landmark_id="", node_id=value, label=value, kind="node",
                             step_free=True, snap_m=0.0)]

    gps = parse_gps(value)
    if gps is not None:
        node, snap_m = nearest_graph_node(db, *gps)
        return [LandmarkDoor(
            landmark_id="",
            node_id=node.id,
            label="Current location",
            kind="node",
            step_free=True,
            snap_m=snap_m,
        )]

    landmark = find_landmark(db, value)
    if landmark is None:
        raise HTTPException(404, f"Unknown node or landmark: {value}")

    doors = db.scalars(
        select(LandmarkDoor).where(LandmarkDoor.landmark_id == landmark.id)
    ).all()
    if step_free:
        # A lift is step-free by nature; a door only if the survey says so.
        preferred = [d for d in doors if d.step_free]
        doors = preferred or doors
    if not doors:
        raise HTTPException(422, f"No mapped entrance for {landmark.name}")
    return doors


def landmark_route_node(db: Session, value: str) -> tuple[Landmark, LandmarkDoor]:
    """The door a verified path should attach to for a searchable place."""
    doors = resolve_doors(db, value)
    landmark = find_landmark(db, value)
    if landmark is None:
        raise HTTPException(404, f"Unknown landmark: {value}")
    preferred = next((door for door in doors if door.step_free), doors[0])
    return landmark, preferred


# Blocking every NonCompliant segment leaves only 77% of campus reachable by
# wheelchair, so the official grade is weighted rather than gated. Stairs and
# unlowered curbs stay hard gates: those are physical, not a preference.
GRADE_PENALTY = {
    "wheelchair": {"NonCompliant": 8.0, "PartiallyCompliant": 1.5},
    "scooter": {"NonCompliant": 4.0, "PartiallyCompliant": 1.3},
    "bicycle": {"NonCompliant": 1.5, "PartiallyCompliant": 1.1},
    "walking": {"NonCompliant": 1.0, "PartiallyCompliant": 1.0},
}
# Displayed accessibility rating, from JHU's own pathway survey.
GRADE_ACCESS = {
    "FullyCompliant": 100.0,
    "PartiallyCompliant": 70.0,
    "NonCompliant": 40.0,
}


def edge_cost(edge: GraphEdge, mode: str, nighttime: bool, hazard_severity: int = 0) -> float:
    """Single source of truth for travel-mode and day/night edge weighting.

    Every measured attribute is optional. Null means nobody has surveyed it,
    and an unmeasured term is skipped rather than assumed good — a missing
    slope must not read as flat, and missing lighting must not read as lit.
    """
    if edge.closed or not edge.published:
        return math.inf
    if mode == "wheelchair" and (edge.stairs or edge.curb):
        return math.inf
    if edge.slope is not None and mode == "wheelchair" and abs(edge.slope) > 0.10:
        return math.inf
    if mode in {"scooter", "bicycle"} and edge.stairs:
        return math.inf
    if mode == "scooter" and edge.surface in {"dirt", "gravel"}:
        return math.inf

    cost = edge.distance_m / SPEED_MPS[mode]
    if edge.surface is not None:
        cost *= SURFACE_PENALTY[mode].get(edge.surface, 1.4)
    if edge.roughness is not None:
        cost *= 1 + edge.roughness * (2.5 if mode in {"wheelchair", "scooter"} else 0.8)
    if edge.slope is not None:
        cost *= 1 + max(0.0, edge.slope) * (8 if mode == "wheelchair" else 3)
    if edge.safety is not None:
        cost *= 1 + (1 - edge.safety) * (1.8 if nighttime else 0.8)
    # `is False`, not `not`: unknown lighting must not trigger the unlit penalty.
    if nighttime and edge.lit is False:
        cost *= 1.7
    if edge.grade:
        cost *= GRADE_PENALTY.get(mode, {}).get(edge.grade, 1.0)
    cost *= 1 + hazard_severity * 0.15
    # Verification is a confidence preference, never a safety gate.
    # Admin-drawn robot paths are the one measured walkway, so prefer them
    # when a user asks for the buildings they connect.
    if edge.source == "admin" and edge.verified:
        cost *= 0.82
    elif edge.verified:
        cost *= 0.96
    else:
        cost *= 1 + max(0.0, 0.7 - edge.confidence) * 0.08
    return cost


def _direction(start: GraphNode, end: GraphNode) -> str:
    dy, dx = end.latitude - start.latitude, end.longitude - start.longitude
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


def _cautions(edge: GraphEdge, nighttime: bool) -> list[str]:
    out = []
    if edge.stairs:
        out.append("stairs")
    if edge.curb:
        out.append("unlowered curb")
    if edge.roughness is not None and edge.roughness >= 0.4:
        out.append("rough surface")
    if nighttime and edge.lit is False:
        out.append("unlit at night")
    if edge.grade == "NonCompliant":
        out.append("may have travel hazards")
    if edge.kind == "shortcut":
        out.append("crosses open lawn")
    return out


def _instruction(step: dict) -> str:
    """Name the thing you are walking along, never the node you are walking to.

    Node ids are derived from coordinates now, so the old "toward {node.name}"
    read as "toward n-7662088_3932650".
    """
    heading = _direction(step["_from"], step["_to"])
    name = step["name"]
    kind = step["kind"]
    if kind == "shortcut":
        return f"Cut {heading} across {name}" if name else f"Cut {heading} across the lawn"
    if kind == "stairs":
        risers = step["risers"]
        steps_text = f" ({risers} steps)" if risers else ""
        return f"Take the steps {heading}{steps_text}"
    if kind == "ramp":
        return f"Follow the ramp {heading}"
    if kind == "indoor":
        return f"Go {heading} through {name}" if name else f"Continue {heading} indoors"
    if name:
        # Generic words read better lowercased after "the"; proper names — the
        # San Martin Bridge, the Breezeway — must keep their capitals.
        generic = name in {"Hallway", "Sidewalk", "Crosswalk", "Curb", "Ramp",
                           "Stairs", "Curb Ramp", "Escalator", "Elevator",
                           "Wheelchair Lift", "Temporary Pathway"}
        return f"Head {heading} along the {name.lower() if generic else name}"
    return f"Head {heading}"


def _as_lnglat(point: list[float] | tuple[float, float]) -> list[float]:
    first, second = float(point[0]), float(point[1])
    # Admin/community traces are stored [latitude, longitude]. GeoJSON is the reverse.
    if 38 < first < 41 and -78 < second < -75:
        return [second, first]
    return [first, second]


def _edge_line(edge: GraphEdge, origin: GraphNode, target: GraphNode, is_reversed: bool) -> list[list[float]]:
    raw = json.loads(getattr(edge, "geometry", None) or "[]")
    points = [_as_lnglat(item) for item in raw if isinstance(item, (list, tuple)) and len(item) == 2]
    if len(points) >= 2:
        return list(reversed(points)) if is_reversed else points
    return [[origin.longitude, origin.latitude], [target.longitude, target.latitude]]


def _route_geometry(arcs: list[tuple[str, Arc]], nodes: dict[str, GraphNode], path_nodes: list[str]) -> list[list[float]]:
    if not arcs:
        node = nodes[path_nodes[0]]
        return [[node.longitude, node.latitude]]
    geometry: list[list[float]] = []
    for origin, arc in arcs:
        line = _edge_line(arc.edge, nodes[origin], nodes[arc.target], arc.reversed)
        if not geometry:
            geometry.extend(line)
        elif line:
            geometry.extend(line[1:] if geometry[-1] == line[0] else line)
    return geometry


def _named_landmark(db: Session, value: str) -> Landmark | None:
    if parse_gps(value) or db.get(GraphNode, value):
        return None
    try:
        return find_landmark(db, value)
    except HTTPException as error:
        if error.status_code == 409:
            return None
        raise


def match_verified_path(db: Session, start_value: str, end_value: str) -> tuple[GraphEdge, bool] | None:
    """If the user asked for the robot path's two places, use that path as-is."""
    edge = db.get(GraphEdge, VERIFIED_PATH_ID)
    if not edge or not edge.published or edge.closed:
        return None
    start = _named_landmark(db, start_value)
    end = _named_landmark(db, end_value)
    if not start or not end or start.id == end.id:
        return None
    places = {edge.from_place, edge.to_place} - {None}
    if places and {start.id, end.id} == places:
        return edge, start.id == edge.to_place
    start_nodes = {door.node_id for door in resolve_doors(db, start.name)}
    end_nodes = {door.node_id for door in resolve_doors(db, end.name)}
    if edge.from_node in start_nodes and edge.to_node in end_nodes:
        return edge, False
    if edge.from_node in end_nodes and edge.to_node in start_nodes:
        return edge, True
    return None


def route_from_verified_edge(
    db: Session,
    edge: GraphEdge,
    reversed_path: bool,
    mode: str,
    nighttime: bool,
) -> dict:
    nodes = {node.id: node for node in db.scalars(select(GraphNode)).all()}
    origin = nodes[edge.to_node if reversed_path else edge.from_node]
    target = nodes[edge.from_node if reversed_path else edge.to_node]
    geometry = _edge_line(edge, origin, target, reversed_path)
    hazards = [
        hazard
        for hazard in db.scalars(select(Hazard).where(Hazard.edge_id == edge.id, Hazard.active.is_(True))).all()
    ]
    start_place = db.get(Landmark, edge.from_place) if edge.from_place else None
    end_place = db.get(Landmark, edge.to_place) if edge.to_place else None
    if reversed_path:
        start_place, end_place = end_place, start_place
    heading = _direction(origin, target)
    label = edge.name or "robot-verified path"
    return {
        "start_node": origin.id,
        "end_node": target.id,
        "start_door": {"label": start_place.name if start_place else origin.name, "kind": "entrance", "step_free": True},
        "end_door": {"label": end_place.name if end_place else target.name, "kind": "entrance", "step_free": True},
        "smarter": False,
        "mode": mode,
        "nighttime": nighttime,
        "geometry": geometry,
        "node_ids": [origin.id, target.id],
        "edge_ids": [edge.id],
        "steps": [{
            "index": 1,
            "distance_m": round(edge.distance_m, 1),
            "edge_id": edge.id,
            "surface": edge.surface,
            "kind": edge.kind,
            "name": edge.name,
            "risers": edge.riser_count or 0,
            "cautions": _cautions(edge, nighttime),
            "instruction": f"Follow the robot-verified path {heading} along {label}",
        }],
        "scores": {
            "safety": round((edge.safety or 0.92) * 100, 1),
            "accessibility": 100.0,
            "cost": round(edge.distance_m / SPEED_MPS[mode], 2),
        },
        "verified_stats": {
            "distance_m": round(edge.distance_m, 1),
            "estimated_seconds": round(edge.distance_m / SPEED_MPS[mode]),
            "verified_distance_m": round(edge.distance_m, 1),
            "unverified_distance_m": 0.0,
            "verified_segments": 1,
            "unverified_segments": 0,
            "verified_percent": 100,
            "stairs_count": int(edge.stairs),
            "riser_count": edge.riser_count or 0,
            "rough_surface_m": 0.0,
            "unlit_m": 0.0,
            "shortcut_m": 0.0,
            "shortcut_spaces": [],
            "unknown_attribute_m": 0.0,
            "fully_compliant_percent": 100,
            "max_abs_slope": edge.slope,
        },
        "hazards": [
            {
                "id": hazard.id,
                "title": hazard.title,
                "severity": hazard.severity,
                "kind": hazard.kind,
                "edge_id": hazard.edge_id,
                "description": hazard.description,
                "latitude": hazard.latitude,
                "longitude": hazard.longitude,
                "verified": hazard.verified,
                "verified_at": hazard.verified_at,
                "evidence": hazard_evidence(hazard),
                "active_when": getattr(hazard, "active_when", "always") or "always",
                "robot_note": getattr(hazard, "robot_note", "") or "",
            }
            for hazard in hazards
        ],
        "explanation": [
            "This is the robot-verified walkway between these two places.",
            "It replaces the generated campus route for this start and destination.",
        ],
    }


def compute_route(
    db: Session,
    start_value: str,
    end_value: str,
    mode: str,
    nighttime: bool,
    avoid_edges: set[str],
    smarter: bool = True,
) -> dict:
    matched = match_verified_path(db, start_value, end_value)
    if matched and matched[0].id not in avoid_edges:
        return route_from_verified_edge(db, matched[0], matched[1], mode, nighttime)
    # Lawn shortcuts are inferred from geometry, never surveyed, so they are
    # offered to walking only and only when the switch is on.
    use_shortcuts = smarter and mode == "walking"
    step_free = mode in {"wheelchair", "scooter"}
    start_doors = resolve_doors(db, start_value, step_free)
    end_doors = resolve_doors(db, end_value, step_free)
    start_by_node = {d.node_id: d for d in start_doors}
    end_by_node = {d.node_id: d for d in end_doors}

    nodes = {node.id: node for node in db.scalars(select(GraphNode)).all()}
    edges = db.scalars(select(GraphEdge).where(GraphEdge.published.is_(True))).all()
    hazards = db.scalars(select(Hazard).where(Hazard.active.is_(True))).all()
    hazards_by_edge: dict[str, list[Hazard]] = {}
    for hazard in hazards:
        if hazard.edge_id:
            hazards_by_edge.setdefault(hazard.edge_id, []).append(hazard)

    graph: dict[str, list[Arc]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        if edge.id in avoid_edges:
            continue
        if edge.kind == "shortcut" and not use_shortcuts:
            continue
        graph.setdefault(edge.from_node, []).append(Arc(edge, edge.to_node, False))
        if edge.bidirectional:
            graph.setdefault(edge.to_node, []).append(Arc(edge, edge.from_node, True))

    # Multi-source, multi-target: any door of either place will do, and the
    # search picks whichever pair is actually cheapest.
    distances = {node: 0.0 for node in start_by_node}
    previous: dict[str, tuple[str, Arc]] = {}
    queue: list[tuple[float, str]] = [(0.0, node) for node in start_by_node]
    heapq.heapify(queue)
    end = None
    while queue:
        current_cost, current = heapq.heappop(queue)
        if current in end_by_node:
            end = current
            break
        if current_cost != distances.get(current):
            continue
        for arc in graph.get(current, []):
            severity = max(
                (h.severity for h in hazards_by_edge.get(arc.edge.id, []) if hazard_applies(h, nighttime)),
                default=0,
            )
            cost = edge_cost(arc.edge, mode, nighttime, severity)
            candidate = current_cost + cost
            if candidate < distances.get(arc.target, math.inf):
                distances[arc.target] = candidate
                previous[arc.target] = (current, arc)
                heapq.heappush(queue, (candidate, arc.target))

    if end is None:
        # Distinguish "the network does not go there" from "a closure is in the
        # way", because the second has a name and an end date. Alumni Memorial
        # Residence 1 sits inside the AMR 1 Replacement zone, so being
        # unreachable is the correct answer, not a gap in the data.
        blocking = _closure_around(edges, set(end_by_node) | set(start_by_node))
        if blocking:
            raise HTTPException(
                422,
                f"No {mode} route is available: the {blocking} closure is in the way.",
            )
        raise HTTPException(422, f"No {mode} route is available with the current restrictions")

    arcs: list[tuple[str, Arc]] = []
    cursor = end
    while cursor in previous:
        prior, arc = previous[cursor]
        arcs.append((prior, arc))
        cursor = prior
    arcs.reverse()
    start = cursor

    path_nodes = [start] + [arc.target for _, arc in arcs]
    route_edges = [arc.edge for _, arc in arcs]
    route_hazards = [
        hazard
        for edge in route_edges
        for hazard in hazards_by_edge.get(edge.id, [])
    ]
    distance_m = sum(edge.distance_m for edge in route_edges)
    verified_m = sum(edge.distance_m for edge in route_edges if edge.verified)
    unlit_m = sum(edge.distance_m for edge in route_edges if edge.lit is False)
    rough_m = sum(edge.distance_m for edge in route_edges
                  if edge.roughness is not None and edge.roughness >= 0.4)
    stairs = sum(1 for edge in route_edges if edge.stairs)
    risers = sum(edge.riser_count or 0 for edge in route_edges if edge.stairs)
    shortcut_m = sum(edge.distance_m for edge in route_edges if edge.kind == "shortcut")
    shortcut_spaces = sorted({edge.space for edge in route_edges
                              if edge.kind == "shortcut" and edge.space})
    # Anything with an unmeasured attribute. Reported rather than assumed good.
    unknown_m = sum(
        edge.distance_m for edge in route_edges
        if edge.slope is None or edge.safety is None or edge.surface is None
        or edge.roughness is None or edge.lit is None
    )
    graded = [edge for edge in route_edges if edge.grade]
    compliant_m = sum(e.distance_m for e in graded if e.grade == "FullyCompliant")

    # Only average over edges that carry a reading; a null must not be scored
    # as perfect, and it must not be scored as zero either.
    measured = [edge for edge in route_edges if edge.safety is not None]
    measured_m = sum(edge.distance_m for edge in measured)
    safety_score = (
        round(sum(e.safety * e.distance_m for e in measured) / measured_m * 100, 1)
        if measured_m else None
    )
    if graded:
        graded_m = sum(edge.distance_m for edge in graded)
        weighted = sum(GRADE_ACCESS.get(edge.grade, 55.0) * edge.distance_m for edge in graded) / graded_m
        ungraded_m = max(0.0, distance_m - graded_m)
        accessibility_score = round((weighted * graded_m + 55.0 * ungraded_m) / max(distance_m, 1), 1)
    else:
        accessibility_score = max(0.0, round(100 - stairs * 35 - rough_m / max(distance_m, 1) * 30, 1))

    # One step per edge was fine for a hand-made eight-node graph. Over the
    # real survey a 648 m walk is 77 edges averaging 8 m, which is a list
    # nobody can follow, so consecutive edges of the same character and name
    # collapse into one instruction.
    steps = []
    for origin, arc in arcs:
        edge = arc.edge
        source_node, target_node = nodes[origin], nodes[arc.target]
        character = (edge.kind, edge.name)
        if steps and steps[-1]["_character"] == character:
            step = steps[-1]
        else:
            step = {
                "_character": character,
                "_from": source_node,
                "index": len(steps) + 1,
                "distance_m": 0.0,
                "edge_id": edge.id,
                "surface": edge.surface,
                "kind": edge.kind,
                "name": edge.name,
                "risers": 0,
                "cautions": [],
            }
            steps.append(step)
        step["distance_m"] += edge.distance_m
        step["_to"] = target_node
        if edge.stairs:
            step["risers"] += edge.riser_count or 0
        for caution in _cautions(edge, nighttime):
            if caution not in step["cautions"]:
                step["cautions"].append(caution)

    for step in steps:
        step["instruction"] = _instruction(step)
        step["distance_m"] = round(step["distance_m"], 1)
        del step["_character"], step["_from"], step["_to"]

    start_door, end_door = start_by_node.get(start), end_by_node.get(end)
    explanations = [f"Optimized centralized {mode} costs for {'night' if nighttime else 'day'} travel."]
    if mode == "wheelchair":
        explanations.append("Excluded stairs and unlowered curbs, and heavily penalised "
                            "segments JHU's survey grades as having travel hazards.")
    if shortcut_m:
        explanations.append(
            f"{shortcut_m:.0f} m of this route crosses open lawn "
            f"({', '.join(shortcut_spaces) or 'unnamed'}); those segments are inferred "
            "from the campus basemap, not surveyed."
        )
    for door, where in ((start_door, "start"), (end_door, "destination")):
        if door is not None and door.snap_m > 40:
            explanations.append(
                f"The mapped pavement stops {door.snap_m:.0f} m short of the {where}; "
                "the route ends where the network does."
            )
    if graded:
        explanations.append(
            "Accessibility rating uses JHU's pathway survey "
            f"({round(compliant_m / max(distance_m, 1) * 100)}% fully compliant)."
        )
    if unknown_m:
        explanations.append(
            f"{unknown_m / max(distance_m, 1) * 100:.0f}% of this route has no slope, "
            "surface, roughness, lighting or security reading yet. Those segments are "
            "routed on distance and JHU's accessibility grade alone."
        )
    if avoid_edges:
        explanations.append(f"Avoided {len(avoid_edges)} user-selected edge(s).")
    if any(hazard_applies(hazard, nighttime) for hazard in route_hazards):
        explanations.append("Applied active hazard penalties.")
    if verified_m < distance_m:
        explanations.append("Unverified segments remain usable and are disclosed rather than treated as unsafe.")
    if nighttime:
        explanations.append("Night routing gives substantially more weight to lighting and security coverage.")

    return {
        "start_node": start,
        "end_node": end,
        "start_door": _door(start_door),
        "end_door": _door(end_door),
        "smarter": use_shortcuts,
        "mode": mode,
        "nighttime": nighttime,
        "geometry": _route_geometry(arcs, nodes, path_nodes),
        "node_ids": path_nodes,
        "edge_ids": [edge.id for edge in route_edges],
        "steps": steps,
        "scores": {"safety": safety_score, "accessibility": accessibility_score, "cost": round(distances[end], 2)},
        "verified_stats": {
            "distance_m": round(distance_m, 1),
            "estimated_seconds": round(distance_m / SPEED_MPS[mode]),
            "verified_distance_m": round(verified_m, 1),
            "unverified_distance_m": round(distance_m - verified_m, 1),
            "verified_segments": sum(1 for edge in route_edges if edge.verified),
            "unverified_segments": sum(1 for edge in route_edges if not edge.verified),
            "verified_percent": round(verified_m / distance_m * 100) if distance_m else 100,
            "stairs_count": stairs,
            "riser_count": risers,
            "rough_surface_m": round(rough_m, 1),
            "unlit_m": round(unlit_m, 1),
            "shortcut_m": round(shortcut_m, 1),
            "shortcut_spaces": shortcut_spaces,
            "unknown_attribute_m": round(unknown_m, 1),
            "fully_compliant_percent": (
                round(compliant_m / distance_m * 100) if distance_m else None
            ),
            "max_abs_slope": max(
                (abs(edge.slope) for edge in route_edges if edge.slope is not None),
                default=None,
            ),
        },
        "hazards": [
            {
                "id": hazard.id,
                "title": hazard.title,
                "severity": hazard.severity,
                "kind": hazard.kind,
                "edge_id": hazard.edge_id,
                "description": hazard.description,
                "latitude": hazard.latitude,
                "longitude": hazard.longitude,
                "verified": hazard.verified,
                "verified_at": hazard.verified_at,
                "evidence": hazard_evidence(hazard),
                "active_when": getattr(hazard, "active_when", "always") or "always",
                "robot_note": getattr(hazard, "robot_note", "") or "",
            }
            for hazard in route_hazards
        ],
        "explanation": explanations,
    }
