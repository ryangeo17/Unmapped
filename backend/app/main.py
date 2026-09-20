from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core import (
    AdminSession,
    GraphEdge,
    GraphNode,
    Hazard,
    Landmark,
    LandmarkDoor,
    RobotJob,
    Submission,
    UPLOAD_DIR,
    VERIFIED_PATH_ID,
    get_db,
    initialize_database,
    new_tracking_code,
    utcnow,
)
from .routing import (
    HAZARD_SNAP_M,
    compute_route,
    landmark_route_node,
    metres,
    nearest_graph_node,
    path_length_m,
    project_point_to_path,
)


Mode = Literal["walking", "wheelchair", "scooter", "bicycle"]
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
ALLOWED_IMAGES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
SESSION_HOURS = int(os.getenv("ADMIN_SESSION_HOURS", "12"))


class RouteRequest(BaseModel):
    start: str = Field(min_length=1, max_length=200)
    end: str = Field(min_length=1, max_length=200)
    mode: Mode = "walking"
    nighttime: bool = False
    # The smarter planner: lawn shortcuts and any-door arrival. Walking only —
    # a shortcut inferred from geometry has no business in a wheelchair answer.
    smarter: bool = True
    avoid_edges: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("start", "end")
    @classmethod
    def strip_locations(cls, value: str) -> str:
        return value.strip()


class RecalculateRequest(RouteRequest):
    previous_edge_ids: list[str] = Field(default_factory=list, max_length=200)
    avoid_previous_route: bool = False


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class AdminNote(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class JobTransition(BaseModel):
    status: Literal["dispatched", "inspecting"]


class EdgeState(BaseModel):
    closed: bool


class SimulateResult(BaseModel):
    success: bool
    distance_m: float | None = Field(default=None, gt=0, le=5000)
    surface: Literal["paved", "brick", "gravel", "dirt"] | None = None
    roughness: float | None = Field(default=None, ge=0, le=1)
    slope: float | None = Field(default=None, ge=-0.5, le=0.5)
    note: str | None = Field(default=None, max_length=1000)


class VerifiedPathRequest(BaseModel):
    geometry: list[list[float]] = Field(min_length=2)
    from_landmark: str = Field(min_length=1, max_length=120)
    to_landmark: str = Field(min_length=1, max_length=120)
    name: str = Field(default="Robot verified path", max_length=120)
    surface: Literal["paved", "brick", "gravel", "dirt"] = "paved"
    roughness: float = Field(default=0.08, ge=0, le=1)
    slope: float = Field(default=0.01, ge=-0.5, le=0.5)
    safety: float = Field(default=0.92, ge=0, le=1)
    stairs: bool = False
    curb: bool = False
    lit: bool = True
    closed: bool = False
    confidence: float = Field(default=0.98, ge=0, le=1)

    @field_validator("geometry")
    @classmethod
    def valid_geometry(cls, value: list[list[float]]) -> list[list[float]]:
        points = []
        for point in value:
            if len(point) != 2 or not -90 <= float(point[0]) <= 90 or not -180 <= float(point[1]) <= 180:
                raise ValueError("Geometry must be [latitude, longitude] points")
            points.append([float(point[0]), float(point[1])])
        if len(points) < 2:
            raise ValueError("Draw at least two points")
        return points


class HazardUpsert(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=3000)
    severity: int = Field(default=2, ge=1, le=3)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    kind: str = Field(default="other", max_length=40)
    verified: bool = True
    active: bool = True
    active_when: Literal["always", "day", "night"] = "always"
    robot_note: str = Field(default="", max_length=3000)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SubmissionPublic(ORMModel):
    tracking_code: str
    name: str
    status: str
    admin_note: str | None
    created_at: object
    updated_at: object


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def valid_image_signature(content_type: str, content: bytes) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


def require_admin(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    admin_session: Annotated[str | None, Cookie()] = None,
) -> None:
    token = admin_session
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "Admin authentication required")
    session = db.get(AdminSession, hash_token(token))
    now = utcnow()
    if not session:
        raise HTTPException(401, "Invalid admin session")
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        db.delete(session)
        db.commit()
        raise HTTPException(401, "Admin session expired")


def submission_or_404(db: Session, submission_id: int) -> Submission:
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(404, "Submission not found")
    return submission


def job_or_404(db: Session, job_id: int) -> RobotJob:
    job = db.get(RobotJob, job_id)
    if not job:
        raise HTTPException(404, "Robot job not found")
    return job


def serialize_hazard(hazard: Hazard) -> dict:
    return {
        "id": hazard.id,
        "title": hazard.title,
        "description": hazard.description,
        "severity": hazard.severity,
        "kind": hazard.kind,
        "edge_id": hazard.edge_id,
        "latitude": hazard.latitude,
        "longitude": hazard.longitude,
        "active": hazard.active,
        "verified": hazard.verified,
        "verified_at": hazard.verified_at,
        "evidence": json.loads(hazard.evidence or "[]"),
        "active_when": getattr(hazard, "active_when", "always") or "always",
        "robot_note": getattr(hazard, "robot_note", "") or "",
    }


def serialize_verified_path(edge: GraphEdge | None, db: Session) -> dict | None:
    if edge is None:
        return None
    start, end = db.get(GraphNode, edge.from_node), db.get(GraphNode, edge.to_node)
    start_place = db.get(Landmark, edge.from_place) if edge.from_place else None
    end_place = db.get(Landmark, edge.to_place) if edge.to_place else None
    hazards = db.scalars(select(Hazard).where(Hazard.edge_id == edge.id)).all()
    return {
        "id": edge.id,
        "from_node": edge.from_node,
        "to_node": edge.to_node,
        "from_landmark": start_place.id if start_place else edge.from_place,
        "to_landmark": end_place.id if end_place else edge.to_place,
        "from_name": start_place.name if start_place else (start.name if start else edge.from_node),
        "to_name": end_place.name if end_place else (end.name if end else edge.to_node),
        "name": edge.name or "Robot verified path",
        "distance_m": edge.distance_m,
        "surface": edge.surface,
        "roughness": edge.roughness,
        "slope": edge.slope,
        "safety": edge.safety,
        "stairs": edge.stairs,
        "curb": edge.curb,
        "lit": edge.lit,
        "closed": edge.closed,
        "verified": edge.verified,
        "confidence": edge.confidence,
        "geometry": json.loads(edge.geometry or "[]"),
        "hazards": [serialize_hazard(hazard) for hazard in hazards],
    }


def verified_path_or_none(db: Session) -> GraphEdge | None:
    return db.get(GraphEdge, VERIFIED_PATH_ID)


def serialize_submission(item: Submission) -> dict:
    return {
        "id": item.id,
        "tracking_code": item.tracking_code,
        "name": item.name,
        "description": item.description,
        "reason": item.reason,
        "geometry": json.loads(item.geometry or "[]"),
        "from_node": item.from_node,
        "to_node": item.to_node,
        "distance_m": item.distance_m,
        "surface": item.surface,
        "roughness": item.roughness,
        "slope": item.slope,
        "stairs": item.stairs,
        "curb": item.curb,
        "image_url": f"/uploads/{Path(item.image_path).name}" if item.image_path else None,
        "status": item.status,
        "admin_note": item.admin_note,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="UnMapped API",
    description="Accessible Homewood campus routing and shortcut verification API.",
    version="1.0.0",
    lifespan=lifespan,
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount(
    "/evidence",
    StaticFiles(directory=Path(__file__).resolve().parents[1] / "static" / "evidence"),
    name="evidence",
)
origins = [
    item.strip()
    for item in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR, check_dir=False), name="uploads")


@app.get("/health")
@app.get("/api/health")
def health(db: Annotated[Session, Depends(get_db)]) -> dict:
    return {
        "status": "ok",
        "service": "unmapped-api",
        "nodes": len(db.scalars(select(GraphNode)).all()),
        "published_edges": len(db.scalars(select(GraphEdge).where(GraphEdge.published.is_(True))).all()),
    }


@app.get("/api/landmarks")
def list_landmarks(db: Annotated[Session, Depends(get_db)]) -> list[dict]:
    """Every searchable place.

    A place now has several doors rather than one node, so the coordinate
    reported here is its step-free door where there is one and its first door
    otherwise — enough to drop a pin and to centre the map. Routing resolves
    the doors again itself and picks whichever is actually nearest.
    """
    nodes = {node.id: node for node in db.scalars(select(GraphNode)).all()}
    doors: dict[str, list[LandmarkDoor]] = {}
    for door in db.scalars(select(LandmarkDoor)).all():
        doors.setdefault(door.landmark_id, []).append(door)

    out = []
    for item in db.scalars(select(Landmark).order_by(Landmark.name)).all():
        mine = doors.get(item.id) or []
        pick = next((d for d in mine if d.step_free), mine[0] if mine else None)
        node = nodes.get(pick.node_id) if pick else None
        if node is None:
            continue
        out.append({
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "accessible": item.accessible,
            "alias": item.alias,
            "node_id": pick.node_id,
            "doors": len(mine),
            # How far the mapped pavement stops short of this place.
            "snap_m": round(pick.snap_m, 1),
            "latitude": node.latitude,
            "longitude": node.longitude,
        })
    return out


@app.get("/api/nodes/nearest")
def nearest_node(
    lat: float, lng: float, db: Annotated[Session, Depends(get_db)]
) -> dict:
    """Snap a map click to the pavement network.

    The frontend used to do this by downloading the whole graph and scanning
    it client-side, which was 2.2 MB per lookup once the graph became real.
    """
    best, distance_m = nearest_graph_node(db, lat, lng)
    return {
        "id": best.id,
        "latitude": best.latitude,
        "longitude": best.longitude,
        "distance_m": distance_m,
    }


@app.get("/api/graph")
@app.get("/api/graph/overlay")
@app.get("/api/map/graph")
def graph_overlay(db: Annotated[Session, Depends(get_db)]) -> dict:
    nodes = db.scalars(select(GraphNode)).all()
    edges = db.scalars(select(GraphEdge).where(GraphEdge.published.is_(True))).all()
    hazards = db.scalars(select(Hazard).where(Hazard.active.is_(True))).all()
    return {
        "nodes": [{"id": n.id, "name": n.name, "latitude": n.latitude, "longitude": n.longitude} for n in nodes],
        "edges": [
            {
                "id": e.id, "from_node": e.from_node, "to_node": e.to_node,
                "distance_m": e.distance_m, "surface": e.surface, "roughness": e.roughness,
                "slope": e.slope, "safety": e.safety, "stairs": e.stairs, "curb": e.curb,
                "lit": e.lit, "closed": e.closed, "bidirectional": e.bidirectional, "source": e.source,
                "verified": e.verified, "verified_at": e.verified_at,
                "confidence": e.confidence, "construction": e.construction,
                "grade": e.grade, "riser_count": e.riser_count,
                "kind": e.kind, "space": e.space, "name": e.name,
                "geometry": json.loads(e.geometry or "[]"),
            }
            for e in edges
        ],
        "hazards": [
            {
                "id": h.id, "title": h.title, "severity": h.severity, "kind": h.kind,
                "edge_id": h.edge_id, "latitude": h.latitude, "longitude": h.longitude,
                "verified": h.verified, "description": h.description,
                "active_when": getattr(h, "active_when", "always") or "always",
                "robot_note": getattr(h, "robot_note", "") or "",
                "evidence": json.loads(h.evidence or "[]"),
            }
            for h in hazards
        ],
    }


@app.get("/api/hazards/{hazard_id}")
def hazard_detail(hazard_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    hazard = db.get(Hazard, hazard_id)
    if not hazard:
        raise HTTPException(404, "Hazard not found")
    return {
        "id": hazard.id, "title": hazard.title, "description": hazard.description,
        "severity": hazard.severity, "kind": hazard.kind, "edge_id": hazard.edge_id,
        "latitude": hazard.latitude, "longitude": hazard.longitude, "active": hazard.active,
        "verified": hazard.verified, "verified_at": hazard.verified_at,
        "evidence": json.loads(hazard.evidence or "[]"),
        "active_when": getattr(hazard, "active_when", "always") or "always",
        "robot_note": getattr(hazard, "robot_note", "") or "",
    }


@app.post("/api/routes")
@app.post("/api/routes/compute")
def route(request: RouteRequest, db: Annotated[Session, Depends(get_db)]) -> dict:
    return compute_route(db, request.start, request.end, request.mode, request.nighttime,
                         set(request.avoid_edges), request.smarter)


@app.post("/api/routes/recalculate")
def recalculate(request: RecalculateRequest, db: Annotated[Session, Depends(get_db)]) -> dict:
    avoided = set(request.avoid_edges)
    if request.avoid_previous_route:
        avoided.update(request.previous_edge_ids)
    return compute_route(db, request.start, request.end, request.mode, request.nighttime,
                         avoided, request.smarter)


@app.post("/api/submissions", status_code=201)
async def create_submission(
    db: Annotated[Session, Depends(get_db)],
    name: Annotated[str, Form(min_length=2, max_length=120)],
    description: Annotated[str, Form(min_length=5, max_length=3000)],
    from_node: Annotated[str, Form(min_length=1, max_length=64)],
    to_node: Annotated[str, Form(min_length=1, max_length=64)],
    distance_m: Annotated[float, Form(gt=0, le=5000)],
    reason: Annotated[str, Form(max_length=1000)] = "",
    geometry: Annotated[str, Form(max_length=20000)] = "",
    surface: Annotated[Literal["paved", "brick", "gravel", "dirt"], Form()] = "paved",
    roughness: Annotated[float, Form(ge=0, le=1)] = 0,
    slope: Annotated[float, Form(ge=-0.5, le=0.5)] = 0,
    stairs: Annotated[bool, Form()] = False,
    curb: Annotated[bool, Form()] = False,
    image: Annotated[UploadFile | None, File()] = None,
) -> dict:
    if from_node == to_node:
        raise HTTPException(422, "Shortcut endpoints must differ")
    start_node, end_node = db.get(GraphNode, from_node), db.get(GraphNode, to_node)
    if not start_node or not end_node:
        raise HTTPException(422, "Both shortcut endpoints must be valid graph nodes")
    if geometry:
        try:
            points = json.loads(geometry)
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError
            for point in points:
                if (
                    not isinstance(point, list) or len(point) != 2
                    or not -90 <= float(point[0]) <= 90
                    or not -180 <= float(point[1]) <= 180
                ):
                    raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(422, "Geometry must contain at least two valid [latitude, longitude] points")
    else:
        points = [
            [start_node.latitude, start_node.longitude],
            [end_node.latitude, end_node.longitude],
        ]
    tracking_code = new_tracking_code()
    image_path = None
    if image:
        if image.content_type not in ALLOWED_IMAGES:
            raise HTTPException(415, "Image must be JPEG, PNG, or WebP")
        content = await image.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Image exceeds {MAX_UPLOAD_BYTES} bytes")
        if not content:
            raise HTTPException(422, "Uploaded image is empty")
        if not valid_image_signature(image.content_type, content):
            raise HTTPException(422, "Image contents do not match the declared format")
        filename = f"{tracking_code.lower()}-{secrets.token_hex(4)}{ALLOWED_IMAGES[image.content_type]}"
        destination = UPLOAD_DIR / filename
        destination.write_bytes(content)
        image_path = str(destination)
    submission = Submission(
        tracking_code=tracking_code, name=name.strip(), description=description.strip(),
        reason=reason.strip(), geometry=json.dumps(points),
        from_node=from_node, to_node=to_node, distance_m=distance_m, surface=surface,
        roughness=roughness, slope=slope, stairs=stairs, curb=curb, image_path=image_path,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return serialize_submission(submission)


@app.get("/api/submissions/status/{tracking_code}", response_model=SubmissionPublic)
def submission_status(tracking_code: str, db: Annotated[Session, Depends(get_db)]) -> Submission:
    item = db.scalar(select(Submission).where(Submission.tracking_code == tracking_code.upper()))
    if not item:
        raise HTTPException(404, "Submission not found")
    return item


@app.post("/api/admin/login")
def admin_login(request: LoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]) -> dict:
    configured = os.getenv("ADMIN_PASSWORD") or "unmapped-demo"
    if not hmac.compare_digest(request.password, configured):
        raise HTTPException(401, "Invalid credentials")
    token = secrets.token_urlsafe(32)
    expiry = utcnow() + timedelta(hours=SESSION_HOURS)
    db.add(AdminSession(token_hash=hash_token(token), expires_at=expiry))
    db.commit()
    response.set_cookie(
        "admin_session", token, httponly=True, samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=SESSION_HOURS * 3600,
    )
    return {"authenticated": True, "token": token, "expires_at": expiry}


@app.post("/api/admin/logout")
def admin_logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
    authorization: Annotated[str | None, Header()] = None,
    admin_session: Annotated[str | None, Cookie()] = None,
) -> dict:
    token = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else admin_session
    if token:
        record = db.get(AdminSession, hash_token(token))
        if record:
            db.delete(record)
            db.commit()
    response.delete_cookie("admin_session")
    return {"authenticated": False}


@app.get("/api/admin/submissions")
def admin_submissions(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
    status: str | None = None,
) -> list[dict]:
    statement = select(Submission).order_by(Submission.created_at.desc())
    if status:
        statement = statement.where(Submission.status == status)
    return [serialize_submission(item) for item in db.scalars(statement).all()]


@app.post("/api/admin/submissions/{submission_id}/approve")
def approve_submission(
    submission_id: int, request: AdminNote, db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    item = submission_or_404(db, submission_id)
    if item.status != "pending":
        raise HTTPException(409, "Only pending submissions can be approved")
    item.status, item.admin_note = "approved", request.note
    job = RobotJob(submission_id=item.id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"submission": serialize_submission(item), "robot_job_id": job.id, "job_status": job.status}


@app.post("/api/admin/submissions/{submission_id}/reject")
def reject_submission(
    submission_id: int, request: AdminNote, db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    item = submission_or_404(db, submission_id)
    if item.status not in {"pending", "approved"}:
        raise HTTPException(409, "Submission cannot be rejected in its current state")
    item.status, item.admin_note = "rejected", request.note
    db.commit()
    return serialize_submission(item)


@app.get("/api/admin/robot-jobs")
def robot_jobs(
    db: Annotated[Session, Depends(get_db)], _: Annotated[None, Depends(require_admin)]
) -> list[dict]:
    return [
        {"id": j.id, "submission_id": j.submission_id, "status": j.status, "result": json.loads(j.result) if j.result else None}
        for j in db.scalars(select(RobotJob).order_by(RobotJob.id.desc())).all()
    ]


@app.patch("/api/admin/edges/{edge_id}")
def update_edge_state(
    edge_id: str,
    request: EdgeState,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    edge = db.get(GraphEdge, edge_id)
    if not edge:
        raise HTTPException(404, "Graph edge not found")
    edge.closed = request.closed
    db.commit()
    return {"id": edge.id, "closed": edge.closed, "routing_active": not edge.closed}


@app.post("/api/admin/robot-jobs/{job_id}/transition")
def transition_job(
    job_id: int, request: JobTransition, db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    job = job_or_404(db, job_id)
    allowed = {"queued": "dispatched", "dispatched": "inspecting"}
    if allowed.get(job.status) != request.status:
        raise HTTPException(409, f"Cannot transition robot job from {job.status} to {request.status}")
    job.status = request.status
    db.commit()
    return {"id": job.id, "submission_id": job.submission_id, "status": job.status}


@app.post("/api/admin/robot-jobs/{job_id}/simulate-result")
def simulate_job_result(
    job_id: int, request: SimulateResult, db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    job = job_or_404(db, job_id)
    if job.status != "inspecting":
        raise HTTPException(409, "Robot must be inspecting before reporting a result")
    submission = job.submission
    payload = request.model_dump(exclude_none=True)
    job.result = json.dumps(payload)
    if request.success:
        job.status, submission.status = "succeeded", "verified"
        if request.distance_m is not None:
            submission.distance_m = request.distance_m
        if request.surface is not None:
            submission.surface = request.surface
        if request.roughness is not None:
            submission.roughness = request.roughness
        if request.slope is not None:
            submission.slope = request.slope
    else:
        job.status, submission.status = "failed", "rejected"
        submission.admin_note = request.note or "Robot verification failed"
    db.commit()
    return {"id": job.id, "status": job.status, "submission": serialize_submission(submission), "result": payload}


@app.post("/api/admin/submissions/{submission_id}/publish")
def publish_submission(
    submission_id: int, db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    item = submission_or_404(db, submission_id)
    if item.status != "verified":
        raise HTTPException(409, "Only robot-verified submissions can be published")
    edge_id = f"shortcut-{item.id}"
    if db.get(GraphEdge, edge_id):
        raise HTTPException(409, "Shortcut is already published")
    edge = GraphEdge(
        id=edge_id, from_node=item.from_node, to_node=item.to_node, distance_m=item.distance_m,
        surface=item.surface, roughness=item.roughness, slope=item.slope, safety=0.9,
        stairs=item.stairs, curb=item.curb, lit=False, closed=False, bidirectional=True,
        source="submission", published=True, submission_id=item.id,
        verified=True, verified_at=utcnow(), confidence=0.98,
    )
    db.add(edge)
    item.status = "published"
    db.commit()
    return {"submission": serialize_submission(item), "edge_id": edge.id, "routing_active": True}


@app.get("/api/admin/verified-path")
def get_verified_path(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    return {"path": serialize_verified_path(verified_path_or_none(db), db)}


@app.put("/api/admin/verified-path")
def upsert_verified_path(
    request: VerifiedPathRequest,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    start_place, start_door = landmark_route_node(db, request.from_landmark)
    end_place, end_door = landmark_route_node(db, request.to_landmark)
    if start_place.id == end_place.id:
        raise HTTPException(422, "Start and destination must be different campus places.")
    start = db.get(GraphNode, start_door.node_id)
    end = db.get(GraphNode, end_door.node_id)
    if not start or not end:
        raise HTTPException(422, "Those places do not have mapped entrances yet.")
    geometry = list(request.geometry)
    start_point = [start.latitude, start.longitude]
    end_point = [end.latitude, end.longitude]
    if metres(geometry[0][0], geometry[0][1], start_point[0], start_point[1]) > 8:
        geometry = [start_point] + geometry
    if metres(geometry[-1][0], geometry[-1][1], end_point[0], end_point[1]) > 8:
        geometry = geometry + [end_point]
    distance = max(path_length_m(geometry), 1.0)
    edge = verified_path_or_none(db)
    if edge is None:
        edge = GraphEdge(id=VERIFIED_PATH_ID, from_node=start.id, to_node=end.id, distance_m=round(distance, 1))
        db.add(edge)
    edge.from_node = start.id
    edge.to_node = end.id
    edge.from_place = start_place.id
    edge.to_place = end_place.id
    edge.distance_m = round(distance, 1)
    edge.surface = request.surface
    edge.roughness = request.roughness
    edge.slope = request.slope
    edge.safety = request.safety
    edge.stairs = request.stairs
    edge.curb = request.curb
    edge.lit = request.lit
    edge.closed = request.closed
    edge.kind = "paved"
    label = request.name.strip()
    edge.name = label if label and label != "Robot verified path" else f"{start_place.name} → {end_place.name}"
    edge.grade = "FullyCompliant"
    edge.bidirectional = True
    edge.verified = True
    edge.verified_at = utcnow()
    edge.confidence = request.confidence
    edge.construction = False
    edge.source = "admin"
    edge.published = True
    edge.geometry = json.dumps(geometry)
    db.commit()
    db.refresh(edge)
    return serialize_verified_path(edge, db)


@app.delete("/api/admin/verified-path")
def delete_verified_path(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    edge = verified_path_or_none(db)
    if edge is None:
        return {"path": None}
    for hazard in db.scalars(select(Hazard).where(Hazard.edge_id == edge.id)).all():
        db.delete(hazard)
    db.delete(edge)
    db.commit()
    return {"path": None}


@app.post("/api/admin/verified-path/hazards", status_code=201)
def create_verified_hazard(
    request: HazardUpsert,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    edge = verified_path_or_none(db)
    if edge is None:
        raise HTTPException(404, "Publish the robot-verified path before adding a hazard.")
    geometry = json.loads(edge.geometry or "[]")
    latitude, longitude, distance_m = project_point_to_path(request.latitude, request.longitude, geometry)
    if distance_m > HAZARD_SNAP_M:
        raise HTTPException(422, "Click on the verified path to place a hazard.")
    hazard = Hazard(
        id=f"hazard-robot-{secrets.token_hex(3)}",
        title=request.title.strip(),
        description=request.description.strip(),
        severity=request.severity,
        edge_id=edge.id,
        latitude=latitude,
        longitude=longitude,
        active=request.active,
        kind=request.kind,
        verified=request.verified,
        verified_at=utcnow() if request.verified else None,
        evidence="[]",
        active_when=request.active_when,
        robot_note=request.robot_note.strip(),
    )
    db.add(hazard)
    db.commit()
    db.refresh(hazard)
    return serialize_hazard(hazard)


@app.patch("/api/admin/verified-path/hazards/{hazard_id}")
def update_verified_hazard(
    hazard_id: str,
    request: HazardUpsert,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    edge = verified_path_or_none(db)
    hazard = db.get(Hazard, hazard_id)
    if not edge or not hazard or hazard.edge_id != edge.id:
        raise HTTPException(404, "Hazard not found on the verified path")
    geometry = json.loads(edge.geometry or "[]")
    latitude, longitude, distance_m = project_point_to_path(request.latitude, request.longitude, geometry)
    if distance_m > HAZARD_SNAP_M:
        latitude, longitude = request.latitude, request.longitude
    hazard.title = request.title.strip()
    hazard.description = request.description.strip()
    hazard.severity = request.severity
    hazard.latitude = latitude
    hazard.longitude = longitude
    hazard.kind = request.kind
    hazard.verified = request.verified
    hazard.active = request.active
    hazard.active_when = request.active_when
    hazard.robot_note = request.robot_note.strip()
    db.commit()
    return serialize_hazard(hazard)


@app.delete("/api/admin/verified-path/hazards/{hazard_id}")
def delete_verified_hazard(
    hazard_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
) -> dict:
    edge = verified_path_or_none(db)
    hazard = db.get(Hazard, hazard_id)
    if not edge or not hazard or hazard.edge_id != edge.id:
        raise HTTPException(404, "Hazard not found on the verified path")
    db.delete(hazard)
    db.commit()
    return {"deleted": True}


@app.post("/api/admin/verified-path/hazards/{hazard_id}/evidence")
async def upload_verified_hazard_evidence(
    hazard_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_admin)],
    image: Annotated[UploadFile, File()],
) -> dict:
    edge = verified_path_or_none(db)
    hazard = db.get(Hazard, hazard_id)
    if not edge or not hazard or hazard.edge_id != edge.id:
        raise HTTPException(404, "Hazard not found on the verified path")
    if image.content_type not in ALLOWED_IMAGES:
        raise HTTPException(415, "Image must be JPEG, PNG, or WebP")
    content = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image exceeds {MAX_UPLOAD_BYTES} bytes")
    if not content or not valid_image_signature(image.content_type, content):
        raise HTTPException(422, "Image contents do not match the declared format")
    filename = f"{hazard_id}-{secrets.token_hex(4)}{ALLOWED_IMAGES[image.content_type]}"
    destination = UPLOAD_DIR / filename
    destination.write_bytes(content)
    evidence = json.loads(hazard.evidence or "[]")
    evidence.append(f"/uploads/{filename}")
    hazard.evidence = json.dumps(evidence)
    db.commit()
    return serialize_hazard(hazard)

