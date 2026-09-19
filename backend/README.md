# UnMapped backend

FastAPI service for accessible routing around Johns Hopkins' Homewood campus.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ADMIN_PASSWORD=change-me uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the complete interactive API. The SQLite
schema and checked-in data under `../data/` are seeded idempotently at startup.

## Tests

```bash
cd backend
pytest
```

## Shortcut lifecycle

1. A user sends a multipart request to `POST /api/submissions`.
2. An administrator logs in, then approves or rejects it.
3. Approval creates a queued robot job. Move it through `dispatched` and
   `inspecting`, then send a simulated verification result.
4. A successful job marks the shortcut `verified`.
5. Publishing creates a graph edge; no earlier lifecycle state affects routing.

Admin endpoints accept either the HTTP-only login cookie or the returned token
as `Authorization: Bearer <token>`.
