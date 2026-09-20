# JHU Homewood 室内地图数据结构

导出源：Web map `ea3919e7b5c242ffa8cafb87399b6901`（"Homewood Campus Indoors Viewer"），
Portal `https://map.jhu.edu/portal`。导出日期 2026-09-19，脚本 `indoors_dump.py`，
输出目录 `indoors_out/`，坐标 WGS84 经纬度（wkid 4326）。

---

## 0. 先读这一节：没有房间数据

**这个部署里不存在房间（Units）和楼层（Levels）要素。** 这不是权限问题，也不是脚本问题：

| 验证途径 | 结果 |
|---|---|
| Web map 的 9 个 operational layer | 没有 Units / Levels / Details |
| `/arcgis/rest/services` 全部 7 个目录、19 个服务枚举 | 没有任何 Units / Levels / Details / Transitions / Occupants 服务 |
| `Indoors/Sites/MapServer` 逐 id 探测（0–25） | 只有 id 24 = Sites，其余全部不存在 |
| 官方移动包 `Homewood_Campus_Indoors_Mobile.mmpk`（4.9 MB，public） | 表存在但 **`Units` 0 行、`Levels` 0 行、`Details` 0 行、`Occupants` 0 行** |

移动包里的 runtime geodatabase 建了完整 AIIM 表结构，但室内空间表是空的。JHU 目前只发布到
**建筑轮廓 + 路网 + 出入口** 这一层级，没有发布楼层平面和房间多边形。

因此：**你要的"房间号 / 房间名 / 用途分类"在公开数据里没有对应要素。**
可用的最细粒度是"建筑 + 楼层序号 + 路径段"。第 3 节给出最接近的替代字段。

移动包里另有两张公开服务没有的表，如果后续需要楼层连通性可以从那里取：
`Transitions`（67 行，跨楼层连接）、`Stairs`（270 行）。注意移动包是较旧快照
（Facilities 94 行 vs 线上 100 行），线上服务更新。

---

## 1. 图层清单

全部 9 个图层导出成功，0 失败。

| 图层 | 文件 | 几何 | 要素数 | 用途 |
|---|---|---|---|---|
| Sites | `Sites.geojson` | Polygon | **1** | 校区边界，整个 Homewood 就一个面 |
| Facilities | `Facilities.geojson` | Polygon | **100** | 建筑轮廓。核心图层 |
| Exterior Spaces | `Exterior_Spaces.geojson` | Polygon | **16** | 室外命名空间（Quad、Beach、庭院），当作"伪建筑"建模 |
| Pathways | `Pathways.geojson` | Polyline | **2146** | 路网边。室内外都在这一层 |
| Polygon Barriers | `Polygon_Barriers.geojson` | Polygon | **7** | 施工/临时封闭区，路径规划避让面 |
| Landmarks | `Landmarks.geojson` | Point | **22** | 地标点（电梯、Quad、隧道口） |
| Elevators | `Elevators.geojson` | Point | **15** | 电梯点位，带照片 |
| Entryways-All | `Entryways-All.geojson` | Point | **337** | 全部出入口 |
| Entryways-Accessible | `Entryways-Accessible.geojson` | Point | **337** | 同一个服务图层，**数据完全相同**，Web map 里只是样式和默认可见性不同 |

> `Entryways-All` 和 `Entryways-Accessible` 指向同一个 URL
> (`Hosted/Entryways/FeatureServer/0`) 且都没有 definitionExpression。
> 要筛无障碍出入口，自己按 `accessible_entrance = 'Y'` 过滤（89 个）。

### Web map 层面的过滤器

只有 Pathways 带了 `definitionExpression`：`pathdisplay IS NULL`。
但当前数据里 **`pathdisplay` 2146 行全为 NULL**，所以这个过滤器是空操作，
导出的 2146 条就是应用实际显示的全集。脚本默认导出全集，`--apply-filters` 可按原表达式过滤。

---

## 2. 图层关系图

```
                    Sites  (1)
                      │  NAME = "Homewood Campus"
                      │
                      │  ⚠ 用 NAME 关联，不是 SITE_ID
                      │     Sites.SITE_ID 是空格 " "，无效
                      │
              Facilities.site_id
                      │
                      ▼
            ┌─── Facilities (100) ───┐
            │   PK: facility_id      │      ← 唯一可靠的外键
            │   ("0741" 四位字符串)   │
            └────────────────────────┘
                      ▲
        ┌─────────────┼──────────────┬───────────────┐
        │             │              │               │
   facility_id   facility_id    facility_id      (无键)
   92/2146 ✓      4/337 ⚠        0/15 ✗          按空间/名称
        │             │              │               │
    Pathways      Entryways      Elevators       Landmarks
     (2146)         (337)           (15)            (22)


   Exterior Spaces (16) —— 字段结构与 Facilities 完全相同，
     但 facility_id 自成一套编码（"00X13"、"00X01"），
     与 Facilities.facility_id 零交集。当作独立图层用。

   Polygon Barriers (7) —— 无任何外键，纯空间要素。

   Levels / Units / Details ———— 不存在（见第 0 节）
        ↑
   Pathways.level_id、Landmarks.level_id、Elevators.level_id
   都是指向 Levels 的悬空外键
```

### 外键实测覆盖率

导出后逐条比对的结果，**不要按 AIIM 文档想当然**：

| 关系 | 实际情况 |
|---|---|
| `Facilities.site_id` → `Sites.NAME` | 100/100 命中。**注意是关联 NAME 不是 SITE_ID** |
| `Pathways.facility_id` → `Facilities.facility_id` | 只有 92/2146 非空，非空的全部命中。其余 2054 条是室外路段 |
| `Entryways.facility_id` → `Facilities.facility_id` | 只有 **4/337** 非空。基本没填，要关联建筑得做空间 join |
| `Elevators.facility_id` | **15/15 全为 NULL**。`facility_name` 也全为 NULL。只能靠 `description`（如 "Ames Hall Elevator"）做字符串匹配 |
| `Exterior_Spaces.facility_id` | 16/16 非空但与 Facilities **零交集**，独立编码 |
| `*.level_id` → `Levels` | Levels 不存在。Pathways 里 1521 条是 `"0"`，522 条 NULL，少量是 `"0062-03"`（建筑-楼层）格式 |

**实用建议**：唯一能放心 join 的是 `Facilities.facility_id`。
Entryways 和 Elevators 关联到建筑请用点面相交（point-in-polygon / 最近邻）自己算。

### 楼层怎么表达

没有 Levels 图层，楼层信息散在各表的整数字段里：

- `Pathways.vertical_order` — 实测取值 `-2, -1, 0, 1, 2, 3, 4`（0 占 2071 条）
- `Entryways.geo_level` — 带编码域，见第 5 节
- `Elevators.vertical_order`、`Landmarks.vertical_order`
- `Pathways.level_name_from` / `level_name_to` — 大量是空格 `" "`，不可靠

**做楼层切换用 `vertical_order` / `geo_level` 这个整数，不要用 `level_id`。**

---

## 3. 房间号 / 房间名 / 用途分类

标准 AIIM 里这三项在 `Units` 表（`UNIT_ID` / `NAME` / `USE_TYPE`）。
该表不存在。移动包中它的字段定义如下，可作为将来 JHU 发布数据时的接口预留：

```
Units: UNIT_ID, USE_TYPE, NAME, NAME_LONG, LEVEL_ID, SCHEDULE_EMAIL,
       CAPACITY, AREA_ID, ASSIGNMENT_TYPE, AREA_GROSS, HEIGHT_RELATIVE,
       RESERVATION_METHOD, ORG_AREA_ID, ALLOCATIONS, SHAPE
Levels: LEVEL_ID, NAME, NAME_SHORT, LEVEL_NUMBER, FACILITY_ID,
        AREA_GROSS, HEIGHT_RELATIVE, VERTICAL_ORDER, SHAPE
```

现有数据中最接近的替代：

| 你要的 | 用这个字段 | 图层 | 说明 |
|---|---|---|---|
| 房间号 | — | — | 无。最细是建筑号 `facility_id`（`"0741"`） |
| 建筑编号 | `facility_id` | Facilities | 四位字符串，与 `archibus_id` 取值相同 |
| 建筑名 | `name` | Facilities | 100/100 有值。`name_long` 与 `name` **完全一致**，不用重复取 |
| 建筑简称 | `name_alias` | Facilities | 只有 12 条有值（`MSEL`、`AMR 1`…），搜索时作为补充 |
| **用途分类** | `primary_use` | Facilities | 见第 5 节。92/100 有值 |
| 室外空间名 | `name` | Exterior Spaces | `The Beach`、`Decker Quad` 等 |
| 出入口名 | `entrance_name` | Entryways | 314/337 有值 |
| 电梯名 | `description` | Elevators / Landmarks | 如 `Ames Hall Elevator` |
| 建筑照片 | `image_url` | Facilities | 86/100 有值 |
| 地址 | `address` | Facilities | |
| 校区分组 | `campus` | Facilities | `Homewood` 60 / `Homewood Off` 26 / `Homewood Housing` 13 |

---

## 4. 标注（Labels）

`labels.csv` 里只有两个图层定义了标注，全部是 Arcade 表达式：

| 图层 | 表达式 | minScale | maxScale | 放置方式 | 字体 |
|---|---|---|---|---|---|
| Facilities | `$feature.NAME` | **2000** | 0（无下限） | AlwaysHorizontal | Arial 10 |
| Exterior Spaces | `$feature.NAME` | 无限制 | 0 | AlwaysHorizontal | Arial 8 |

- `minScale: 2000` 指比例尺分母 ≤ 2000（即放大到 1:2000 以内）时才画建筑名。
  Exterior Spaces 的标注任何比例尺都显示。
- 其余 7 个图层没有标注类，要显示名字得自己在前端画。

### 图层自身的可见比例尺

标注之外，图层本身也有比例尺门槛（`minScale` = 比例尺分母大于它就不画）：

| 图层 | minScale | 含义 |
|---|---|---|
| Facilities | 50000 | 1:50000 以内可见，最早出现 |
| Pathways | 1000 | 要放大到 1:1000 才出现 |
| Exterior Spaces | 1000 | 同上 |
| Elevators / Landmarks / Entryways ×2 | 1500 | 1:1500 |
| Sites / Polygon Barriers | 0 | 始终可见 |

前端复刻这套层级显示，照抄这几个数就行。

---

## 5. 编码域（code → name）

完整清单见 `fields.csv` 的 `codedValues` 列。以下是会用到的：

### Facilities.primary_use — 建筑用途（实测分布）

| 代码 | 名称 | 实际条数 |
|---|---|---|
| Research | Research | 22 |
| Residence Hall | Residence Hall | 17 |
| Office | Office | 17 |
| Mixed Use | Mixed Use | 7 |
| Instruction | Instruction | 6 |
| Administration | Administration | 5 |
| Recreation | Recreation | 5 |
| Library | Library | 4 |
| Parking Garage | Parking Garage | 4 |
| Power Plant | Power Plant | 3 |
| Multifamily | Multifamily | 2 |
| *(NULL)* | 未填 | 8 |

域里还定义了 `Dormitory`、`Parking`、`Storage` 等值，但当前数据里没出现。
**这个域的 code 和 name 相同**，直接显示即可，不用查表。

### Pathways.pathway_type — 路径类型（数值码，必须查表）

| 代码 | 名称 | 实际条数 |
|---|---|---|
| 1 | Hallway / Sidewalk | 1900 |
| 2 | Stairs / Curb | 191 |
| 3 | Ramp / Curb Ramp | 55 |
| 4 | Elevator / Wheelchair Lift | 0 |
| 5 | Escalator | 0 |
| 6 | Moving Walkway | 0 |

### Pathways.travel_direction

| 代码 | 名称 |
|---|---|
| 1 | Both Directions Allowed |
| 2 | From-To Allowed |
| 3 | To-From Allowed |

### Pathways.pathway_rank

| 代码 | 名称 |
|---|---|
| 1 | Primary |
| 2 | Secondary |
| 3 | Tertiary |

### Pathways.location_class — 室内外判定（做室内高亮用这个）

| 代码 | 名称 | 实际条数 |
|---|---|---|
| Exterior | Exterior | 1391 |
| Interior | Interior | 85 |
| Semi_Enclosed | Semi-Enclosed | 37 |
| Covered_Exterior | Covered Exterior | 35 |
| Elevated | Elevated | 5 |
| Underground | Underground | 2 |
| *(NULL)* | 未填 | 591 |
| Other | Other | 0 |

### Pathways.ihcd2021routesurveycode — 无障碍评级

| 代码 | 名称 |
|---|---|
| FullyCompliant | Compliant Accessible Route |
| PartiallyCompliant | Partially Compliant |
| NonCompliant | May Have Travel Hazards |
| Other | Other |

对应路径服务的三种 travel mode：`Fully Accesible Pathway`、
`Partially Accessible Pathway`、`Walking`（官方拼写有误，照抄）。

### Pathways.pathdisplay

| 代码 | 名称 |
|---|---|
| Building_Center_Path | Building Center Path |
| Block | Block |
| Hidden | Hidden |

当前 2146 行全为 NULL。

### Pathways.suffix_type

`Hallway` / `Sidewalk` / `Stairs` / `Curb` / `Ramp` / `Curb Ramp` /
`Elevator` / `Wheelchair Lift` / `Escalator` —— code 与 name 相同。

### Entryways.geo_level — 出入口所在楼层

| 代码 | 名称 | 实际条数 |
|---|---|---|
| -2 | Sub-Basement | 2 |
| -1 | Basement | 28 |
| 0 | Ground Floor | 51 |
| 1 | 1st Floor | 202 |
| 2 | 2nd Floor | 46 |
| 3 | 3rd Floor | 7 |
| 4 | 4th Floor | 1 |

### Entryways 的 Y/N 布尔字段

`accessible_entrance`、`automatic_door`、`magnetic_swipe`、`isa_sign`
—— 域都是 `Y=Yes; N=No`。实测 `accessible_entrance`：Y 89 / N 248。

`Entryways.use_type` 332/337 为 NULL，剩 5 条是 `Not on Accessible Route`，基本不可用。

### Landmarks.landmark_type

| 代码 | 名称 | 实际条数 |
|---|---|---|
| Elevator | Elevator | 14 |
| Quad | Quad | 6 |
| Tunnel Entrance | Tunnel Entrance | 2 |
| Art Installation | Art Installation | 0 |
| Other | Other | 0 |

### Facilities / Exterior Spaces `.below_grade`

`Y=Yes; N=No`。

### 所有图层的 `validationstatus`

AIIM 内部的数据校验位（0–7 的位掩码，`0 = 无错误`）。前端忽略即可。

---

## 6. 前端使用提示

- 建筑面 + 建筑名：`Facilities.geojson`，`name` + `primary_use`，1:50000 起显示，1:2000 起标注。
- 搜索建议索引：`Facilities.name` + `name_alias` + `address` + `Exterior_Spaces.name` +
  `Entryways.entrance_name`。
- 楼层切换：用 `vertical_order`（Pathways/Elevators/Landmarks）和 `geo_level`（Entryways）
  这两个整数，取值范围 -2 ~ 4。
- 室内路段高亮：`Pathways.location_class IN ('Interior','Underground')`。
- 施工避让：`Polygon_Barriers.geojson`，`expected_end_date` 是毫秒时间戳，有 3 条为 NULL（长期封闭）。
- Entryways / Elevators 关联建筑必须自己做空间计算，服务里的 `facility_id` 没填。

## 7. 复跑

```bash
python3 indoors_dump.py --defs-only          # 只看结构，不下要素
python3 indoors_dump.py                      # 全量，约 2900 要素，3.3 MB
python3 indoors_dump.py --only Facilities    # 单图层（不覆盖 csv/index）
python3 indoors_dump.py --apply-filters      # 套用 web map 的 definitionExpression
```

导出目录已加入 `.gitignore`。
