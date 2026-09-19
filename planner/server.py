#!/usr/bin/env python3
"""HTTP front for the planner.

    pip install fastapi uvicorn
    uvicorn planner.server:app --reload

The graph is loaded once at startup, not per request.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import profiles
from .plan import compare, plan_route, places
from .tools import TOOLS  # noqa: F401  (re-exported for callers that want it)

app = FastAPI(title="Campus route planner")

# The frontend is served from another origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    origin: str
    destination: str
    profile: str = profiles.DEFAULT_PROFILE


class CompareRequest(BaseModel):
    origin: str
    destination: str
    profiles: list[str] | None = None


@app.on_event("startup")
def warm():
    places()            # builds or reads the graph cache once


@app.get("/places")
def get_places():
    return {"places": places().index()}


@app.get("/profiles")
def get_profiles():
    return {"profiles": [
        {"id": k, "label": v["label"], "description": v["description"]}
        for k, v in profiles.PROFILES.items()
    ]}


@app.post("/route")
def post_route(req: RouteRequest):
    return plan_route(req.origin, req.destination, req.profile)


@app.post("/compare")
def post_compare(req: CompareRequest):
    return compare(req.origin, req.destination, req.profiles)
