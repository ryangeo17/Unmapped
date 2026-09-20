# Surface polygons (Decker Quad area)

从 JHU 官方底图的矢量瓦片解出来的**地表面**数据。这是 `Pathways` 线段属性
之外更精确的一层：铺装、楼梯、坡道、植被都是真实多边形，不是线上的标签。

**覆盖范围只有 Decker Quad 一带**（含周边一圈 hall，约 244m 缓冲，144 张瓦片）。
不是全校园——全校园 z6 要 2120 张瓦片，对上游生产服务请求量太大。
需要扩范围用 `scripts/mvt/export_surfaces.py --bbox`。

| 文件 | 要素数 | 分类 (`class` 属性) |
|---|---|---|
| `Sidewalk.geojson` | 689 | `Brick Paver` / `Other`（224 个无 symbol） |
| `Vegetation.geojson` | 515 | `Hedgerows` 339 / `Woodland` 106 / `Landscape Beds` 70 |
| `Stairs.geojson` | 316 | — |
| `Road_Area.geojson` | 287 | — |
| `Trees.geojson` | 126 | 点 |
| `Campus_Area.geojson` | 112 | 校园绿底 |
| `Shrubs.geojson` | 71 | 点 |
| `Athletic_Facilities.geojson` | 61 | — |
| `Sidewalk_Ramp.geojson` | 33 | — |
| `Breezeway_and_Skywalk` / `Bridge` / `River_Stream` | 11 / 5 / 11 | — |

## 坐标与精度

源瓦片是 EPSG:2248（马里兰州平面，英尺），**MapLibre 不支持这个投影**，
所以不能直接加载底图服务。本脚本已把坐标逆投影到 EPSG:4326 经纬度。

NAD83→WGS84 的常数基准差已校正（-0.19m 东 / +0.87m 南），校正量由校园两端
3 个控制点实测，离散度 0.000m。

几何交叉验证：底图的 Stairs 面到 `Pathways` 中独立来源的台阶线段，中位距离
5.4m；Sidewalk_Ramp 对坡道线段中位 4.7m。两者本就是面中心与穿过它的路径线
之差，量级正确。

## 已知限制

- **要素在瓦片边界被切开。** ArcGIS 瓦片按 tile 裁剪，同一条人行道跨瓦片会
  变成多个要素。完全相同的重复已去掉，真正被切开的碎片没有合并。
  做面积统计要注意；纯渲染无影响。
- `Sidewalk` 有 224 个要素没有 `_symbol`，区分不出砖铺还是混凝土。
- z6 是瓦片金字塔的中层，小要素可能已被综合掉。需要更细用 `--zoom 8`
  （同范围约 570 张瓦片）。
- 底图 `Stairs` 面有 39% 距离任何 `Pathways` 台阶段超过 10m ——
  **路网没有建模的楼梯**。对轮椅路线是真实风险点，值得让机器人优先核实。
