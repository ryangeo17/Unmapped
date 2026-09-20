# Campus data

JHU Homewood 官方室内/室外地图数据，从 ArcGIS Enterprise 导出。
Vite 会把这个目录按原路径静态服务，前端用 `fetch('/data/Facilities.geojson')` 取。

坐标 WGS84 经纬度 (EPSG:4326)，精度截断到 6 位小数（约 11cm）。

| 文件 | 几何 | 要素数 | 说明 |
|---|---|---|---|
| `Facilities.geojson` | Polygon | 100 | 建筑轮廓，`name` / `primary_use` |
| `Pathways.geojson` | LineString | 2146 | 路网，带官方无障碍评级 `ihcd2021routesurveycode` |
| `Entryways-All.geojson` | Point | 337 | 出入口，`accessible_entrance` = Y/N |
| `Exterior_Spaces.geojson` | Polygon | 16 | 室外命名空间（Quad 等） |
| `Landmarks.geojson` | Point | 22 | 地标 |
| `Elevators.geojson` | Point | 15 | 电梯 |
| `Polygon_Barriers.geojson` | Polygon | 7 | 施工封闭区 |
| `Sites.geojson` | Polygon | 1 | 校区边界 |
| `_index.json` | — | — | 导出元数据（来源 URL、几何类型、要素数） |

**字段含义、编码域、图层间外键关系见 [`docs/CAMPUS_DATA.md`](../../../docs/CAMPUS_DATA.md)。**
先读那份再写代码，有几个外键和文档预期不一致。

数据由 `scripts/indoors_dump.py` 生成，可重跑。上游是别人的生产服务，
不要在开发循环里反复请求。
