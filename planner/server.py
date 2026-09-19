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

from .plan import plan_route, places
from .tools import TOOLS  # noqa: F401  (re-exported for callers that want it)

app = FastAPI(title="Campus route planner")

# The frontend is served from another origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    origin: str
    destination: str
    smarter: bool = True


@app.on_event("startup")
def warm():
    places()            # builds or reads the graph cache once


@app.get("/places")
def get_places():
    return {"places": places().index()}


@app.post("/route")
def post_route(req: RouteRequest):
    return plan_route(req.origin, req.destination, req.smarter)
