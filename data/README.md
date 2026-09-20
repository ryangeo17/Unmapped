# Demo campus data

Files in this directory are synthetic, deterministic hackathon seed data. They
approximate the Johns Hopkins Homewood campus and are not an accessibility
survey or a guarantee that a path is open or safe.

`homewood_graph.json` is generated from the public JHU Indoors Pathways layer
plus a small robot-verified demo overlay. Exterior and covered-exterior
segments keep JHU's fully/partially accessible and travel-hazard codes. Those
segments stay unverified until the team publishes robot surveys.

Regenerate with:

```bash
backend/.venv/bin/python backend/scripts/import_jhu_indoors.py
```

See `docs/SEED_DATA_GUIDE.md` before replacing the five planned records with
real robot observations.
