from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


ROOT = Path(__file__).resolve().parents[2]
VERIFIED_PATH_ID = "e-robot-verified"
DATA_DIR = ROOT / "data"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads"))


def _normalise_database_url(url: str) -> str:
    """Accept whichever spelling the host hands out.

    Neon, Vercel and Heroku all print postgres:// URLs. SQLAlchemy 2 only
    recognises postgresql://, and the driver pinned for deployment is psycopg 3,
    which is selected by the +psycopg suffix rather than by being installed.
    Normalising here means DATABASE_URL can be pasted from any dashboard
    unedited, which is the form people actually copy.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalise_database_url(
    os.getenv("DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parents[1] / 'unmapped.db'}")
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Landmark(Base):
    __tablename__ = "landmarks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="building")
    accessible: Mapped[bool] = mapped_column(Boolean, default=True)
    # A second name the place is commonly searched by: "MSEL", or the wording
    # an earlier seed used ("MSE Library" for Milton S. Eisenhower Library).
    alias: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)


class LandmarkDoor(Base):
    """Where you can actually arrive at a place.

    A building has several doors and which one is nearest decides the route,
    so this replaces the old one-landmark-one-node link. San Martin Garage is
    the case that forces it: the survey records no entrance for it at all, only
    a lift, and aiming at the building centre instead walks you 169 m further
    round the block.
    """
    __tablename__ = "landmark_doors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    landmark_id: Mapped[str] = mapped_column(ForeignKey("landmarks.id"), index=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    kind: Mapped[str] = mapped_column(String(20), default="entrance")
    step_free: Mapped[bool] = mapped_column(Boolean, default=False)
    # Distance from the door to the pavement node it snaps to. Seven
    # off-campus buildings are 165-338 m out; the route ends where the mapped
    # network does, and says so.
    snap_m: Mapped[float] = mapped_column(Float, default=0.0)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    from_node: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    to_node: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    distance_m: Mapped[float] = mapped_column(Float)
    # Null means nobody has measured it. Not "fine" — a default of 0 slope and
    # 1.0 safety would make every unsurveyed segment look ideal, which is
    # exactly the person this app exists for being misled. edge_cost() skips
    # the term and compute_route() discloses the distance involved.
    surface: Mapped[str | None] = mapped_column(String(30), nullable=True)
    roughness: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety: Mapped[float | None] = mapped_column(Float, nullable=True)
    lit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stairs: Mapped[bool] = mapped_column(Boolean, default=False)
    curb: Mapped[bool] = mapped_column(Boolean, default=False)
    # From JHU's own accessibility survey: FullyCompliant, PartiallyCompliant
    # or NonCompliant ("may have travel hazards"). The real substitute for the
    # slope reading this data does not carry.
    grade: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    riser_count: Mapped[int] = mapped_column(Integer, default=0)
    # paved / stairs / ramp / indoor / shortcut. Shortcuts are lawn desire
    # paths inferred from geometry, so they are opt-in and walking-only.
    kind: Mapped[str] = mapped_column(String(20), default="paved", index=True)
    # Which lawn a shortcut crosses, or which project closed the segment, so
    # the route can name it.
    space: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Searchable campus places an admin-drawn robot path connects.
    from_place: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_place: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The segment's own name where the survey has one — "Gilman Hall Tunnel",
    # "Crosswalk", "Breezeway". Directions read from this, not from node ids.
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Drawn polylines from admin/community traces. Routing still uses the
    # snapped endpoints; this is what the map actually draws.
    geometry: Mapped[str] = mapped_column(Text, default="[]")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.55)
    construction: Mapped[bool] = mapped_column(Boolean, default=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    bidirectional: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(30), default="seed")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    submission_id: Mapped[int | None] = mapped_column(ForeignKey("submissions.id"), nullable=True)


class Hazard(Base):
    __tablename__ = "hazards"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[int] = mapped_column(Integer, default=1)
    edge_id: Mapped[str | None] = mapped_column(ForeignKey("graph_edges.id"), nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    kind: Mapped[str] = mapped_column(String(40), default="other")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    # always | day | night — night-only lighting cautions stay off in daylight.
    active_when: Mapped[str] = mapped_column(String(20), default="always")
    robot_note: Mapped[str] = mapped_column(Text, default="")


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="")
    geometry: Mapped[str] = mapped_column(Text, default="[]")
    from_node: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"))
    to_node: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"))
    distance_m: Mapped[float] = mapped_column(Float)
    surface: Mapped[str] = mapped_column(String(30), default="paved")
    roughness: Mapped[float] = mapped_column(Float, default=0)
    slope: Mapped[float] = mapped_column(Float, default=0)
    stairs: Mapped[bool] = mapped_column(Boolean, default=False)
    curb: Mapped[bool] = mapped_column(Boolean, default=False)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    jobs: Mapped[list["RobotJob"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class RobotJob(Base):
    __tablename__ = "robot_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    submission: Mapped[Submission] = relationship(back_populates="jobs")


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # A serverless instance is frozen between requests, so a pooled connection is
    # a connection held open against a database that caps them — and one the
    # provider may have dropped while the instance slept. NullPool opens a
    # connection per checkout and closes it after, which is what a hosted
    # pooler expects to see.
    engine = create_engine(DATABASE_URL, poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


def _load_json(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


def _columns(model) -> set[str]:
    return {column.key for column in model.__table__.columns}


def _rows(model, items):
    """Keep only keys the table actually has.

    The seed files carry a little provenance the database does not model — a
    shortcut edge records which lawn it crosses — and splatting an unknown key
    into the ORM constructor is a TypeError at startup.
    """
    allowed = _columns(model)
    return [model(**{k: v for k, v in item.items() if k in allowed}) for item in items]


def seed_database(db: Session) -> None:
    """Idempotently import the editable checked-in Homewood graph."""
    graph = None
    if not db.scalar(select(GraphNode.id).limit(1)):
        graph = _load_json("homewood_graph.json")
        db.add_all(_rows(GraphNode, graph["nodes"]))
        db.commit()
    if not db.scalar(select(GraphEdge.id).where(GraphEdge.source == "seed").limit(1)):
        graph = graph or _load_json("homewood_graph.json")
        edges = _rows(GraphEdge, graph["edges"])
        for edge in edges:
            edge.source = "seed"
            edge.published = True
        db.add_all(edges)
        db.commit()
    if not db.scalar(select(Landmark.id).limit(1)):
        db.add_all(_rows(Landmark, _load_json("homewood_landmarks.json")))
        db.commit()
    if not db.scalar(select(LandmarkDoor.id).limit(1)):
        db.add_all(_rows(LandmarkDoor, _load_json("homewood_doors.json")))
        db.commit()
    if not db.scalar(select(Hazard.id).limit(1)):
        db.add_all(_rows(Hazard, _load_json("homewood_hazards.json")))
    db.commit()


def ensure_schema() -> None:
    """SQLite create_all does not add new columns to existing tables."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    extras = {
        "graph_edges": [
            ("geometry", "TEXT DEFAULT '[]'"),
            ("from_place", "VARCHAR(64)"),
            ("to_place", "VARCHAR(64)"),
            ("grade", "VARCHAR(30)"),
            ("riser_count", "INTEGER DEFAULT 0"),
            ("kind", "VARCHAR(20) DEFAULT 'paved'"),
            ("space", "VARCHAR(80)"),
            ("name", "VARCHAR(120)"),
        ],
        "hazards": [
            ("active_when", "VARCHAR(20) DEFAULT 'always'"),
            ("robot_note", "TEXT DEFAULT ''"),
        ],
    }
    with engine.begin() as connection:
        for table, columns in extras.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}
            if not existing:
                continue
            for name, ddl in columns:
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def initialize_database() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    ensure_schema()
    with SessionLocal() as db:
        try:
            seed_database(db)
        except IntegrityError:
            # Against a shared database two cold starts can look at the same
            # empty tables at the same moment and both decide to fill them. The
            # loser collides on rows the winner already wrote, which is the
            # desired end state reached by the other route.
            db.rollback()


def new_tracking_code() -> str:
    return f"UM-{secrets.token_hex(4).upper()}"
