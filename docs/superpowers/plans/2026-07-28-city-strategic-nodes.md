# 城池战略节点化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把最终地图的每座现役城池迁为唯一战略节点，并删除旧郡级节点结构。

**Architecture:** `administrative_cities` 保持城池行政事实，`regions` 保持郡级事实；`strategic_nodes` 与现役城池 ID 一一对应。静态城际节点、地图锚点与路线由内容目录加载；启动时以可审计、幂等的方式把旧郡地点引用迁到郡治城。

**Tech Stack:** Python 3、SQLite、FastAPI、TypeScript、React、pytest、Node test runner。

## Global Constraints

- 现役节点 ID 等于 `administrative_cities.id`，格式 `city:<slug>`。
- 不保留旧郡级节点、名称别名、临时地图偏移或同州/邻州任意移动回退。
- 旧档只能重写地点引用，不可改控制权、兵力、人口、库存、回合或随机记录。
- 围城、驻军、战役、补给和外势行动只接受现役城池节点。
- 不新增随机域、不改 AI 权限或月度顺序；同步更新架构基线。

---

## File Structure

- `content/administrative_units.json`：现役城池、地图锚点、旧郡 ID → 郡治城的迁移表。
- `content/routes.json`：仅含 `city:*` 节点的真实城际路线。
- `ming_sim/content.py`：目录加载与集合一致性验证。
- `ming_sim/db/schema.py`：迁移审计表及旧地点引用迁移。
- `ming_sim/db/seed.py`：按城池目录播种、清除旧节点。
- `ming_sim/sanguo_rules.py`：真实城际路线验证。
- `ming_sim/siege.py`、`ming_sim/battle.py`、`ming_sim/power_ai.py`：只接受城池节点。
- `web_app.py`、`web/src/types.ts`、`web/src/mapLogic.ts`、`web/src/components/map.tsx`：地图同源节点合同。
- `tests/test_city_strategic_nodes.py`：目录、迁移、路线和不变量回归。
- `docs/AI活世界与随机性架构基线.md`：城池节点口径。

### Task 1: 建立城池战略目录和路线

**Files:**
- Modify: `content/administrative_units.json`, `content/routes.json`, `ming_sim/content.py`
- Create: `tests/test_city_strategic_nodes.py`

**Interfaces:**
- Produces: `CityStrategicNode(id, city_id, commandery_id, province_id, x, y)`；`CityStrategicCatalog(nodes, edges, legacy_node_redirects)`。

- [ ] **Step 1: 写失败测试**

```python
def test_city_catalog_has_one_node_per_active_city():
    content = load_game_content()
    city_ids = {item["id"] for item in content.administrative_units["cities"]}
    assert set(content.city_strategic_catalog.nodes) == city_ids
    assert all(item.startswith("city:") for item in content.city_strategic_catalog.nodes)
```

- [ ] **Step 2: 运行失败测试**

Run: `python3 -m pytest tests/test_city_strategic_nodes.py -q`

Expected: FAIL，`city_strategic_catalog` 尚不存在。

- [ ] **Step 3: 更新静态目录**

每座现役城补充唯一 `id / city_id / x / y` 战略锚点；写全旧郡 ID 到郡治 `city:*` 的迁移表。把 `routes.json.nodes` 替换为全部现役 `city:*`，并给定每条真实城际边的既有合法路线类型。

- [ ] **Step 4: 实现加载校验**

```python
def load_city_strategic_catalog(directory, routes):
    # 节点集合严格等于现役 city 集合；每条边端点有效；redirect 目标是对应郡治城。
    ...
```

- [ ] **Step 5: 验证并提交**

Run: `python3 -m pytest tests/test_city_strategic_nodes.py -q`

```bash
git add content/administrative_units.json content/routes.json ming_sim/content.py tests/test_city_strategic_nodes.py
git commit -m "feat: define city strategic node catalog"
```

### Task 2: 迁移旧档地点并播种城池节点

**Files:**
- Modify: `ming_sim/db/schema.py`, `ming_sim/db/seed.py`, `ming_sim/db/regions.py`
- Modify: `tests/test_city_strategic_nodes.py`, `tests/test_administrative_model.py`

**Interfaces:**
- Produces: `migrate_legacy_strategic_locations()`；`strategic_location_migrations` 审计表。

- [ ] **Step 1: 写失败测试**

```python
def test_legacy_commandery_locations_move_once_to_capital(board):
    board.conn.execute("UPDATE armies SET station_node='jiangling' WHERE id='liubei_main'")
    board.seed_static_data()
    assert _station(board, 'liubei_main') == 'city:jiangling'
    assert _migration_count(board, 'army', 'liubei_main') == 1
    board.seed_static_data()
    assert _migration_count(board, 'army', 'liubei_main') == 1
```

- [ ] **Step 2: 运行失败测试**

Run: `python3 -m pytest tests/test_city_strategic_nodes.py::test_legacy_commandery_locations_move_once_to_capital -q`

Expected: FAIL，旧郡节点尚未删除。

- [ ] **Step 3: 新增审计表和确定性迁移**

```sql
CREATE TABLE IF NOT EXISTS strategic_location_migrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_kind TEXT NOT NULL, object_id TEXT NOT NULL,
  old_node_id TEXT NOT NULL, new_node_id TEXT NOT NULL, reason TEXT NOT NULL,
  UNIQUE(object_kind, object_id, old_node_id, new_node_id)
);
```

迁移 `armies.station_node`、`sieges.target_node` 和未结算军令 payload 的 `to`/`target`。映射缺失时抛带 ID 的 `ValueError`。

- [ ] **Step 4: 重写播种过程并验证**

`seed_static_data()` 先迁移所有引用，再 upsert 城池节点和路线，最后删除不在目录的旧节点/路线；`seed_administrative_units()` 断言城池和节点集合一致。

Run: `python3 -m pytest tests/test_city_strategic_nodes.py tests/test_administrative_model.py -q`

- [ ] **Step 5: 提交**

```bash
git add ming_sim/db/schema.py ming_sim/db/seed.py ming_sim/db/regions.py tests/test_city_strategic_nodes.py tests/test_administrative_model.py
git commit -m "feat: migrate saves to city strategic nodes"
```

### Task 3: 用真实城际路线替换州块规则

**Files:**
- Modify: `ming_sim/sanguo_rules.py`, `ming_sim/siege.py`, `ming_sim/battle.py`, `ming_sim/power_ai.py`
- Modify: `tests/test_sanguo_strategic_rules.py`, `tests/test_siege.py`, `tests/test_city_strategic_nodes.py`

**Interfaces:**
- Produces: `find_strategic_route(db, source, target) -> StrategicEdge`；所有地点校验拒绝非 `city:*`。

- [ ] **Step 1: 写失败测试**

```python
def test_move_requires_direct_city_route(board):
    _place(board, 'liubei_main', 'city:jiangling')
    assert validate_route_move(board, 'liubei_main', 'city:jiangling', 'city:xiangyang').kind == '普通路'
    with pytest.raises(ArmyOrderError, match='不存在直达城际路线'):
        validate_route_move(board, 'liubei_main', 'city:jiangling', 'city:luoyang')
```

- [ ] **Step 2: 运行失败测试**

Run: `python3 -m pytest tests/test_sanguo_strategic_rules.py tests/test_city_strategic_nodes.py -q`

Expected: FAIL，当前仍允许州块移动。

- [ ] **Step 3: 实现直接路线查询**

```python
def find_strategic_route(db, source, target):
    row = db.conn.execute(
        'SELECT source,target,kind,note FROM strategic_routes WHERE (source=? AND target=?) OR (source=? AND target=?)',
        (source, target, target, source),
    ).fetchone()
    if row is None:
        raise ArmyOrderError(f'{source}—{target} 不存在直达城际路线。')
    return StrategicEdge(source, target, str(row['kind']), str(row['note']))
```

围城、战役与外势候选的地点入口统一调用城池节点校验器。

- [ ] **Step 4: 验证并提交**

Run: `python3 -m pytest tests/test_sanguo_strategic_rules.py tests/test_siege.py tests/test_city_strategic_nodes.py -q`

```bash
git add ming_sim/sanguo_rules.py ming_sim/siege.py ming_sim/battle.py ming_sim/power_ai.py tests/test_sanguo_strategic_rules.py tests/test_siege.py tests/test_city_strategic_nodes.py
git commit -m "feat: enforce city-to-city strategic routes"
```

### Task 4: 统一 API 与地图合同

**Files:**
- Modify: `web_app.py`, `web/src/types.ts`, `web/src/mapLogic.ts`, `web/src/components/map.tsx`
- Modify: `tests/test_sanguo_api.py`, `web/tests/mapLogic.test.ts`

**Interfaces:**
- Produces: `/api/map.nodes[] / cities[] / routes[]` 只含同源 `city:*` 节点与真实锚点。

- [ ] **Step 1: 写失败测试**

```python
def test_map_payload_uses_city_nodes_only(client):
    data = client.get('/api/map').json()
    assert {item['id'] for item in data['nodes']} == {item['id'] for item in data['cities']}
    assert all(item['id'].startswith('city:') for item in data['nodes'])
    assert all(edge['source'].startswith('city:') and edge['target'].startswith('city:') for edge in data['routes'])
```

- [ ] **Step 2: 运行失败测试**

Run: `python3 -m pytest tests/test_sanguo_api.py -q && cd web && node --test tests/mapLogic.test.ts`

Expected: FAIL，当前负载有旧郡节点、空路线与临时偏移。

- [ ] **Step 3: 直接查询城池节点**

`web_app.py` 用 `strategic_nodes JOIN administrative_cities JOIN regions` 返回真实城池坐标、驻军和路线；前端删除名称别名、历史城镇借用节点和以 `commandery_id` 选择城市的回退。

- [ ] **Step 4: 验证并提交**

Run: `python3 -m pytest tests/test_sanguo_api.py tests/test_city_strategic_nodes.py -q && cd web && node --test tests/*.test.ts && npm run build`

```bash
git add web_app.py web/src/types.ts web/src/mapLogic.ts web/src/components/map.tsx tests/test_sanguo_api.py web/tests/mapLogic.test.ts
git commit -m "feat: expose real city nodes on strategic map"
```

### Task 5: 同步基线并做全量对抗性验收

**Files:**
- Modify: `docs/AI活世界与随机性架构基线.md`, `tests/test_city_strategic_nodes.py`

- [ ] **Step 1: 写跨层不变量测试**

```python
def test_city_node_world_invariants(board):
    cities = {row['id'] for row in board.conn.execute('SELECT id FROM administrative_cities')}
    nodes = {row['id'] for row in board.conn.execute('SELECT id FROM strategic_nodes')}
    assert nodes == cities
    assert not board.conn.execute('SELECT 1 FROM armies WHERE station_node NOT IN (SELECT id FROM strategic_nodes)').fetchone()
    assert not board.conn.execute('SELECT 1 FROM sieges WHERE target_node NOT IN (SELECT id FROM strategic_nodes)').fetchone()
```

- [ ] **Step 2: 更新基线**

在 §3.0 明确战略节点是 `administrative_cities.id` 的城池投影、路线是城际硬规则、无旧郡节点或州块任意移动；明确随机域、AI 权限和月度顺序不变。

- [ ] **Step 3: 全量回归和旧逻辑扫描**

Run: `python3 -m pytest tests -q && cd web && node --test tests/*.test.ts && npm run build`

Run: `rg -n 'province_block_between|HISTORICAL_CITY_NODE_ALIASES|临时锚点' ming_sim web/src web_app.py`

Expected: 全部测试通过；旧逻辑不得仍处于运行路径。

- [ ] **Step 4: 提交**

```bash
git add docs/AI活世界与随机性架构基线.md tests/test_city_strategic_nodes.py
git commit -m "docs: record city strategic node baseline"
```

## Plan Self-Review

- 覆盖：目录与路线（Task 1）、确定性迁移（Task 2）、硬规则与外势地点（Task 3）、API/地图合同（Task 4）、基线与全量验收（Task 5）。
- 无占位项；测试命令、关键接口、迁移范围与失败条件均已明确。
- ID 在全计划统一为 `city:*`，郡只保留行政汇总职责。
