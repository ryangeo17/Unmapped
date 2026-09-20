"""Vercel entrypoint for the UnMapped API.

Vercel's FastAPI support is zero-config: it looks for a FastAPI instance named
`app` at a fixed set of filenames, `server.py` at the project root being one of
them, and serves it as one function with request paths untouched. pyproject.toml
names this file explicitly under [tool.vercel] so detection cannot drift.

The earlier attempt put the app behind an api/index.py function with a
`rewrites` rule in vercel.json. That rule replaces the path rather than
preserving it, so FastAPI saw /api/index for every request and answered 404 to
everything, /docs and /openapi.json included.

This file is wiring only. The application is backend/app/main.py — the same
object uvicorn and Docker run, so there is no second code path.

Two environment defaults are set before the import, because backend/app/core.py
reads them at module scope:

  DATABASE_URL  Only /tmp is writable. The database is rebuilt from data/ on
                every cold start, which measures 0.4s, so an empty /tmp costs a
                fraction of a second rather than a failed boot. The cost is that
                writes — submissions, admin closures, uploaded photos — live
                only as long as the instance. Point DATABASE_URL at a hosted
                database when they need to outlive it.
  UPLOAD_DIR    Same reason: main.py mkdirs this at import time, and anywhere
                outside /tmp is read-only.

setdefault, not assignment, so a variable set in the Vercel dashboard wins.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/unmapped.db")
os.environ.setdefault("UPLOAD_DIR", "/tmp/uploads")

from app.main import app  # noqa: E402  (must follow the environment defaults)

__all__ = ["app"]
