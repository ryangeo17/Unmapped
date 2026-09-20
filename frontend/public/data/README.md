# Campus data

JHU Homewood's published indoor/outdoor map data, exported from their ArcGIS
Enterprise portal. Vite serves this directory as-is, so the frontend fetches
`/data/Facilities.geojson` and the backend's seed builder reads the same files.

Coordinates are WGS84 (EPSG:4326), truncated to 6 decimals (about 11 cm).

| File | Geometry | Features | What it is |
|---|---|---|---|
| `Facilities.geojson` | Polygon | 100 | Building footprints, with `name` and `primary_use` |
| `Pathways.geojson` | LineString | 2146 | The path network, carrying JHU's own accessibility grade in `ihcd2021routesurveycode` |
| `Entryways-All.geojson` | Point | 337 | Entrances; `accessible_entrance` is Y or N |
| `Exterior_Spaces.geojson` | Polygon | 16 | Named outdoor spaces — the quads |
| `Landmarks.geojson` | Point | 22 | Landmarks |
| `Elevators.geojson` | Point | 15 | Lifts |
| `Polygon_Barriers.geojson` | Polygon | 7 | Construction closures |
| `Sites.geojson` | Polygon | 1 | Campus boundary |
| `_index.json` | — | — | Export metadata: source URLs, geometry types, feature counts |

**Read [`docs/CAMPUS_DATA.md`](../../../docs/CAMPUS_DATA.md) before writing code
against these fields.** Several foreign keys do not behave the way the AIIM
documentation says they do.

Regenerate with `scripts/indoors_dump.py`. That script talks to someone else's
production service, so do not put it in a development loop.
