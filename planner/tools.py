"""Dispatch table mapping a model's function calls to the planner.

Kept separate from server.py so the agent glue does not need FastAPI, and so
any transport — HTTP, a queue, a direct import — shares one definition.
"""
import json
import os

from . import profiles
from .plan import compare, plan_route, places

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_schema.json")

TOOLS = {
    "plan_route": lambda a: plan_route(a["origin"], a["destination"],
                                       a.get("profile", profiles.DEFAULT_PROFILE)),
    "compare_routes": lambda a: compare(a["origin"], a["destination"],
                                        a.get("profiles")),
    "list_places": lambda a: {"places": places().index()},
}


def declarations():
    with open(SCHEMA) as fh:
        return json.load(fh)["functionDeclarations"]


def call(name, args):
    if name not in TOOLS:
        return {"status": "error", "error": "unknown tool %r" % name}
    return TOOLS[name](dict(args or {}))
