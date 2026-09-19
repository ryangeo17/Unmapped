from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parents[1] / 'unmapped.db'}")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Landmark(Base):
    __tablename__ = "landmarks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    node_id: Mapped[str] = mapped_column(ForeignKey("graph_nodes.id"))
    category: Mapped[str] = mapped_column(String(40), default="building")
    accessible: Mapped[bool] = mapped_column(Boolean, default=True)


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
    surface: Mapped[str] = mapped_column(String(30), default="paved")
    roughness: Mapped[float] = mapped_column(Float, default=0)
    slope: Mapped[float] = mapped_column(Float, default=0)
    safety: Mapped[float] = mapped_column(Float, default=1)
    stairs: Mapped[bool] = mapped_column(Boolean, default=False)
    curb: Mapped[bool] = mapped_column(Boolean, default=False)
    lit: Mapped[bool] = mapped_column(Boolean, default=True)
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


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


def _load_json(name: str) -> list[dict]:
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


def seed_database(db: Session) -> None:
    """Idempotently import the editable checked-in Homewood graph."""
    if not db.scalar(select(GraphNode.id).limit(1)):
        db.add_all(GraphNode(**item) for item in _load_json("homewood_graph.json")["nodes"])
        db.commit()
    if not db.scalar(select(GraphEdge.id).where(GraphEdge.source == "seed").limit(1)):
        db.add_all(GraphEdge(**item, source="seed", published=True) for item in _load_json("homewood_graph.json")["edges"])
        db.commit()
    if not db.scalar(select(Landmark.id).limit(1)):
        db.add_all(Landmark(**item) for item in _load_json("homewood_landmarks.json"))
    if not db.scalar(select(Hazard.id).limit(1)):
        db.add_all(Hazard(**item) for item in _load_json("homewood_hazards.json"))
    db.commit()


def initialize_database() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)


def new_tracking_code() -> str:
    return f"UM-{secrets.token_hex(4).upper()}"
