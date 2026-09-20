"""Vercel serverless entrypoint for the UnMapped API.

Vercel's Python runtime serves whatever ASGI application this module exports as
`app`. Everything here is wiring — the application itself lives in
backend/app/main.py and is the same object uvicorn and Docker run, so there is
no second code path to keep in sync.

Two environment defaults are set before the import, because backend/app/core.py
reads them at module scope:

  DATABASE_URL  Only /tmp is writable on a serverless instance. The database is
                rebuilt from data/ on every cold start, which measures 0.4s, so
                an empty /tmp costs a fraction of a second rather than a failed
                boot. The cost is that writes — submissions, admin closures,
                uploaded photos — live only as long as the instance does. Point
                DATABASE_URL at a hosted database when they need to outlive it.
  UPLOAD_DIR    Same reason: main.py mkdirs this at import time, and anywhere
                outside /tmp is read-only.

setdefault, not assignment: a real environment variable set in the Vercel
dashboard still wins.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/unmapped.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/uploads")

from app.main import app  # noqa: E402  (must follow the environment defaults)

__all__ = ["app"]
