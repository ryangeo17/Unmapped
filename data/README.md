# Demo campus data

Files in this directory are synthetic, deterministic hackathon seed data. They
approximate the Johns Hopkins Homewood campus and are not an accessibility
survey or a guarantee that a path is open or safe.

The backend imports these records idempotently into SQLite. Edit landmarks,
nodes, edges, hazards, and evidence references here rather than duplicating
constants in the frontend. See `docs/SEED_DATA_GUIDE.md` before replacing the
five planned records with real robot observations.
