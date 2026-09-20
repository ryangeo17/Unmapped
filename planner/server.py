#!/usr/bin/env python3
"""HTTP front for the planner.

    pip install fastapi uvicorn
    uvicorn planner.server:app --reload --host 127.0.0.1

Bind explicitly: on macOS "localhost" resolves to ::1 first, and a server
listening only on 127.0.0.1 refuses the browser's connection.

The graph is loaded once at startup, not per request.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import profiles
from .plan import plan_all, plan_route, places

app = FastAPI(title="Campus route planner")

# The frontend is served from another origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RoutesRequest(BaseModel):
    origin: str
    destination: str
    smarter: bool = True
    profile: str | None = None


@app.on_event("startup")
def warm():
    places()            # builds or reads the graph cache once


@app.get("/places")
def get_places():
    return {"places": places().index()}


@app.get("/profiles")
def get_profiles():
    return {"profiles": [
        {"id": p,
         "label": profiles.PROFILES[p]["label"],
         "smartLabel": profiles.PROFILES[p].get("smartLabel"),
         "description": profiles.PROFILES[p]["description"]}
        for p in profiles.ORDER
    ]}


@app.post("/routes")
def post_routes(req: RoutesRequest):
    """All three answers in one call, so switching between them in the UI
    costs nothing."""
    if req.profile:
        return {"routes": [plan_route(req.origin, req.destination,
                                      req.profile, req.smarter)]}
    return plan_all(req.origin, req.destination, req.smarter)
