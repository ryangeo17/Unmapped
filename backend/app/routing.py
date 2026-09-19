from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .core import GraphEdge, GraphNode, Hazard, Landmark


SPEED_MPS = {"walking": 1.35, "wheelchair": 1.05, "scooter": 3.8, "bicycle": 4.5}
SURFACE_PENALTY = {
    "walking": {"paved": 1.0, "brick": 1.08, "gravel": 1.25, "dirt": 1.4},
    "wheelchair": {"paved": 1.0, "brick": 1.3, "gravel": 2.2, "dirt": 3.0},
    "scooter": {"paved": 1.0, "brick": 1.45, "gravel": 2.5, "dirt": 3.5},
    "bicycle": {"paved": 1.0, "brick": 1.2, "gravel": 1.45, "dirt": 1.8},
}


@dataclass
class Arc:
    edge: GraphEdge
    target: str
    reversed: bool


def resolve_location(db: Session, value: str) -> str:
    if db.get(GraphNode, value):
        return value
    landmark = db.scalar(select(Landmark).where(or_(Landmark.id == value, Landmark.name.ilike(value))))
    if landmark:
        return landmark.node_id
    raise HTTPException(404, f"Unknown node or landmark: {value}")


def edge_cost(edge: GraphEdge, mode: str, nighttime: bool, hazard_severity: int = 0) -> float:
    """Single source of truth for travel-mode and day/night edge weighting."""
    if edge.closed or not edge.published:
        return math.inf
    if mode == "wheelchair" and (edge.stairs or edge.curb or abs(edge.slope) > 0.10):
        return math.inf
    if mode in {"scooter", "bicycle"} and edge.stairs:
        return math.inf
    if mode == "scooter" and edge.surface in {"dirt", "gravel"}:
        return math.inf

    cost = edge.distance_m / SPEED_MPS[mode]
    cost *= SURFACE_PENALTY[mode].get(edge.surface, 1.4)
    cost *= 1 + edge.roughness * (2.5 if mode in {"wheelchair", "scooter"} else 0.8)
    uphill = max(0.0, edge.slope)
    cost *= 1 + uphill * (8 if mode == "wheelchair" else 3)
    cost *= 1 + (1 - edge.safety) * (1.8 if nighttime else 0.8)
    if nighttime and not edge.lit:
        cost *= 1.7
    cost *= 1 + hazard_severity * 0.15
    # Verification is a confidence preference, never a safety gate.
    cost *= 0.96 if edge.verified else 1 + max(0.0, 0.7 - edge.confidence) * 0.08
    return cost


def _direction(start: GraphNode, end: GraphNode) -> str:
    dy, dx = end.latitude - start.latitude, end.longitude - start.longitude
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


def compute_route(
    db: Session,
    start_value: str,
    end_value: str,
    mode: str,
    nighttime: bool,
    avoid_edges: set[str],
) -> dict:
    start, end = resolve_location(db, start_value), resolve_location(db, end_value)
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
        graph.setdefault(edge.from_node, []).append(Arc(edge, edge.to_node, False))
        if edge.bidirectional:
            graph.setdefault(edge.to_node, []).append(Arc(edge, edge.from_node, True))

    distances = {start: 0.0}
    previous: dict[str, tuple[str, Arc]] = {}
    queue: list[tuple[float, str]] = [(0.0, start)]
    while queue:
        current_cost, current = heapq.heappop(queue)
        if current == end:
            break
        if current_cost != distances.get(current):
            continue
        for arc in graph.get(current, []):
            severity = max((h.severity for h in hazards_by_edge.get(arc.edge.id, [])), default=0)
            cost = edge_cost(arc.edge, mode, nighttime, severity)
            candidate = current_cost + cost
            if candidate < distances.get(arc.target, math.inf):
                distances[arc.target] = candidate
                previous[arc.target] = (current, arc)
                heapq.heappush(queue, (candidate, arc.target))

    if end not in distances:
        raise HTTPException(422, f"No {mode} route is available with the current restrictions")

    arcs: list[tuple[str, Arc]] = []
    cursor = end
    while cursor != start:
        prior, arc = previous[cursor]
        arcs.append((prior, arc))
        cursor = prior
    arcs.reverse()

    path_nodes = [start] + [arc.target for _, arc in arcs]
    route_edges = [arc.edge for _, arc in arcs]
    route_hazards = [
        hazard
        for edge in route_edges
        for hazard in hazards_by_edge.get(edge.id, [])
    ]
    distance_m = sum(edge.distance_m for edge in route_edges)
    verified_m = sum(edge.distance_m for edge in route_edges if edge.verified)
    unlit_m = sum(edge.distance_m for edge in route_edges if not edge.lit)
    rough_m = sum(edge.distance_m for edge in route_edges if edge.roughness >= 0.4)
    stairs = sum(1 for edge in route_edges if edge.stairs)
    safety_score = (
        round(sum(edge.safety * edge.distance_m for edge in route_edges) / distance_m * 100, 1)
        if distance_m else 100.0
    )
    accessibility_score = max(0.0, round(100 - stairs * 35 - rough_m / max(distance_m, 1) * 30, 1))

    steps = []
    for index, (origin, arc) in enumerate(arcs, 1):
        source_node, target_node = nodes[origin], nodes[arc.target]
        cautions = []
        if arc.edge.stairs:
            cautions.append("stairs")
        if arc.edge.curb:
            cautions.append("unlowered curb")
        if arc.edge.roughness >= 0.4:
            cautions.append("rough surface")
        if nighttime and not arc.edge.lit:
            cautions.append("unlit at night")
        steps.append(
            {
                "index": index,
                "instruction": f"Head {_direction(source_node, target_node)} toward {target_node.name}",
                "distance_m": arc.edge.distance_m,
                "edge_id": arc.edge.id,
                "surface": arc.edge.surface,
                "cautions": cautions,
            }
        )

    explanations = [f"Optimized centralized {mode} costs for {'night' if nighttime else 'day'} travel."]
    if mode == "wheelchair":
        explanations.append("Excluded stairs, unlowered curbs, and steep slopes.")
    if avoid_edges:
        explanations.append(f"Avoided {len(avoid_edges)} user-selected edge(s).")
    if route_hazards:
        explanations.append("Applied active hazard penalties.")
    if verified_m < distance_m:
        explanations.append("Unverified segments remain usable and are disclosed rather than treated as unsafe.")
    if nighttime:
        explanations.append("Night routing gives substantially more weight to lighting and security coverage.")

    return {
        "start_node": start,
        "end_node": end,
        "mode": mode,
        "nighttime": nighttime,
        "geometry": [[nodes[node].longitude, nodes[node].latitude] for node in path_nodes],
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
            "rough_surface_m": round(rough_m, 1),
            "unlit_m": round(unlit_m, 1),
            "max_abs_slope": max((abs(edge.slope) for edge in route_edges), default=0),
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
                "evidence": json.loads(hazard.evidence or "[]"),
            }
            for hazard in route_hazards
        ],
        "explanation": explanations,
    }
