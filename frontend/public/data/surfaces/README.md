# Surface polygons (Decker Quad area)

Ground-surface data decoded from JHU's own basemap vector tiles. It is more
precise than the per-segment attributes on `Pathways`: paving, stairs, ramps
and planting are real polygons here, not labels on a line.

**Coverage is the Decker Quad neighbourhood only** — the surrounding halls,
about a 244 m buffer, 144 tiles. Not the whole campus: that would be 2,120
tiles at zoom 6, too much traffic for someone else's production service.
Widen it with `scripts/mvt/export_surfaces.py --bbox`.

| File | Features | `class` values |
|---|---|---|
| `Sidewalk.geojson` | 689 | `Brick Paver` / `Other` (224 carry no symbol) |
| `Vegetation.geojson` | 515 | Hedgerows 339 / Woodland 106 / Landscape Beds 70 |
| `Stairs.geojson` | 316 | — |
| `Road_Area.geojson` | 287 | — |
| `Trees.geojson` | 126 | points |
| `Campus_Area.geojson` | 112 | the green base |
| `Shrubs.geojson` | 71 | points |
| `Athletic_Facilities.geojson` | 61 | — |
| `Sidewalk_Ramp.geojson` | 33 | — |
| `Breezeway_and_Skywalk` / `Bridge` / `River_Stream` | 11 / 5 / 11 | — |

## Coordinates and accuracy

The source tiles are EPSG:2248 (Maryland State Plane, feet), which **MapLibre
and Mapbox cannot consume**, so the basemap service cannot simply be added as
a style. The exporter inverse-projects to EPSG:4326.

The constant NAD83 to WGS84 offset is already corrected (−0.19 m east,
+0.87 m south), measured at three control points across campus with 0.000 m
spread.

Cross-checked against independent data: the basemap's stair polygons sit a
median 5.4 m from the stair segments in `Pathways`, and ramp polygons 4.7 m
from ramp segments. That is the expected gap between a footprint's centre and
the route line through it.

## Known limits

- **Features are clipped at tile boundaries.** A pavement crossing tiles comes
  back as several features. Exact duplicates are removed; genuine fragments are
  not merged. Fine for rendering, wrong for area statistics.
- 224 `Sidewalk` features carry no `_symbol`, so brick versus concrete is
  unknown for those.
- Zoom 6 is mid-pyramid, so small features may already be generalised away.
  Use `--zoom 8` for finer detail (about 570 tiles over the same area).
- **39% of the basemap's stair polygons are more than 10 m from any stair
  segment in the routing network** — stairs the network does not model. For a
  wheelchair route that is a real risk, and it is why a step-free route is
  described as step-free *in the network*, not on the ground.
