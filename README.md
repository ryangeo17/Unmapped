# UnMapped

UnMapped is a Homewood-campus route planner that accounts for stairs, ramps,
surface quality, slope, hazards, lighting, security coverage, closures, and
survey confidence. It supports walking, wheelchair, mobility-scooter, and
bicycle routing. Routes are computed by the FastAPI backend over individual
graph edges; they are not hard-coded complete paths.

> **Demo data:** Every checked-in survey measurement, hazard, verification, and
> evidence image is synthetic placeholder data for the hackathon. Unverified
> segments remain routable and are explicitly labeled.

## Architecture

- `frontend/`: React, TypeScript, Vite, Mapbox Standard with 3D buildings,
  browser geolocation, and the deterministic Demo GPS simulator.
- `backend/`: FastAPI, SQLAlchemy/SQLite persistence, graph routing, public
  submissions, admin sessions, and simulated robot-verification jobs.
- `data/`: editable campus landmarks, graph segments, and hazards.
- `docs/SEED_DATA_GUIDE.md`: swapping in the team's five real surveys.
- `docs/DEMO_SCRIPT.md`: deterministic judge walkthrough.

The edge-cost function is centralized in the backend routing module. Travel time
is the base cost; mode constraints and penalties are applied for stairs, curb
cuts, slope, surface, roughness, hazards, context-sensitive safety, closures,
avoids, confidence, and freshness. SQLite stores submissions, sessions, jobs,
admin actions, and published shortcut edges across restarts.

## Quick start with Docker

Prerequisites: Docker Desktop with Compose.

```bash
ADMIN_PASSWORD='choose-a-demo-password' \
VITE_MAPBOX_ACCESS_TOKEN='pk.your-public-token' \
docker compose up --build
```

Open <http://localhost:8080>. API documentation is at
<http://localhost:8000/docs>. Data is retained in the `unmapped-data` volume.

## Local development

Prerequisites: Python 3.11+ and Node.js 20+.

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open <http://localhost:5173>. On first startup the API idempotently loads the
checked-in JHU Indoors fallback graph plus the robot-verified demo overlay.

## Configuration

Backend:

- `ADMIN_PASSWORD` (required outside tests): admin login secret; never put this
  value in frontend code.
- `DATABASE_URL`: defaults to local SQLite; use an absolute mounted path in
  deployment.
- `CORS_ORIGINS`: comma-separated allowed frontend origins.
- `ADMIN_SESSION_HOURS`: optional short-lived admin-session duration.

Frontend:

- `VITE_API_BASE_URL`: FastAPI API root, such as `http://localhost:8000/api`.
- `VITE_MAPBOX_ACCESS_TOKEN`: a public (`pk.*`) token authorized for the
  application origins. Mapbox Standard and its 3D objects require this token.

Copy the provided `.env.example` files. They contain no secrets.

## Tests and quality checks

```bash
cd backend
pytest

cd ../frontend
npm test
npm run build
```

Backend tests cover mode constraints, day/night weighting, closures, explicit
avoids, unverified routing, authentication, lifecycle transitions, and the rule
that unpublished submissions cannot affect routing. Frontend tests cover route
selection success and API-error behavior.

## API overview

- `GET /api/health`, `/api/landmarks`, `/api/map/graph`
- `POST /api/routes/compute`, `/api/routes/recalculate`
- `GET /api/hazards/{id}`
- `POST /api/submissions`
- `GET /api/submissions/{reference_id}/status`
- `POST /api/admin/login`, `/api/admin/logout`
- Protected admin submission and robot-job review/mutation endpoints

FastAPI's complete interactive OpenAPI contract is available at `/docs`.
Uploads are type/size checked. Invalid coordinates, modes, and lifecycle
transitions return structured errors.

## Deployment

### Frontend on Vercel

Import the repository, set the root directory to `frontend`, and set
`VITE_API_BASE_URL` to the deployed API HTTPS URL ending in `/api`. Also set
`VITE_MAPBOX_ACCESS_TOKEN` to a public token restricted to the production and
preview origins. `frontend/vercel.json` contains the SPA rewrite/build settings.

### API on Render or Railway

Deploy `backend/` using its Dockerfile/config. Set a strong `ADMIN_PASSWORD`,
`CORS_ORIGINS` to the final frontend origins, and `DATABASE_URL` to a SQLite
file on a mounted persistent disk.

**SQLite on ephemeral hosting is erased on restart/redeploy.** Mount persistent
storage (for example at `/data`) and use
`sqlite:////data/unmapped.db`. Back up that volume before schema changes.

### GoDaddy domain

After both services are live, add the chosen domain in Vercel and copy Vercel's
current DNS records into GoDaddy DNS. A common setup uses `www` for Vercel and
`api` as a CNAME to the backend host. Add both final HTTPS origins to
`CORS_ORIGINS`, set `VITE_API_BASE_URL=https://api.example.com/api`, redeploy the
frontend, and enable redirects between the apex and `www` as desired. Use the
exact records shown by each host rather than hard-coding provider IPs.

## Operating notes

- Public submissions begin at `pending_admin_review` and never route immediately.
- Only `verification_succeeded` jobs can be published; publication creates the
  eligible graph edge.
- Robot completion is explicitly simulated. No hardware connection is claimed.
- Mapbox Standard needs internet access and a valid public token. Backend routing
  remains independent of the basemap.
- Replace demo locations and measurements by following
  `docs/SEED_DATA_GUIDE.md`.

## Troubleshooting

- **Mapbox token needed:** set `VITE_MAPBOX_ACCESS_TOKEN` and restart/rebuild the
  frontend. Add the exact local/deployed origins to the token's URL restrictions.
- **CORS error:** include the browser's exact scheme/host/port in `CORS_ORIGINS`.
- **Admin login fails:** verify the API process received `ADMIN_PASSWORD`.
- **Empty data after deploy:** confirm `DATABASE_URL` points at the mounted disk,
  not the container's ephemeral filesystem.
- **Reset demo state:** stop services and remove only the local demo database (or
  the Compose volume), then restart to reseed.
