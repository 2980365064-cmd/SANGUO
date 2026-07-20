# 三国刘备线完整二开实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 当前用户规则不允许擅自派生子代理，因此默认在主会话内串行执行。

**Goal:** 将现有明末 AI 对话政略游戏完整转换为 208 年赤壁前夕至 223 年白帝托孤的刘备视角三国游戏，并使地图、人物属性、军队、外交、历史改写和终局全部由可测试硬规则承载。

**Architecture:** 保留现有 FastAPI + React/Electron + SQLite + LLM 的“自然语言对话 → 结构化草案 → 硬规则结算 → 月末战报”骨架。三国内容继续以 `content/` 为静态事实源，规则拆为人物、战略地图、战役、外交、国策、事件和结局等独立模块；LLM 只读取结构化盘面、提出受控方案并生成叙事，不直接落高影响状态。

**Tech Stack:** Python 3.11、FastAPI、SQLite、Agno、pytest、React 18、TypeScript、Vite、Electron、Steam。

## 全局事实源与冲突规则

开始任何任务前必须完整阅读以下文件，禁止用对话记忆或明末旧设定补全：

1. `/Users/zhuanzmima0000/Desktop/三国刘备视角_二开设计决策.md`
2. `/Users/zhuanzmima0000/Desktop/刘备视角_赤壁前夕至蜀汉建国_三国演义时间线.md`
3. `/Users/zhuanzmima0000/Desktop/208开局人物能力表_审核版.md`
4. `/Users/zhuanzmima0000/Desktop/208开局人物初始状态注册表_审核版.md`
5. `/Users/zhuanzmima0000/Desktop/人物特性效果对照表_审核版.md`
6. `/Users/zhuanzmima0000/Desktop/人物属性作用矩阵_最终版.md`
7. `/Users/zhuanzmima0000/Desktop/208开局军队编制表_审核版.md`
8. `/Users/zhuanzmima0000/Desktop/36节点路线与关隘表_审核版.md`

冲突优先级按上列序号；但已明确“审核通过”的具体数据表覆盖同类早期概述。地图最终口径已经用户确认修正为 **13 州、35 节点、46 条双向边**；文件名保留“36节点”仅为保持旧链接稳定。

## 全局实施约束

- 玩家始终为刘备；开局 208 年赤壁前夕，1 回合 1 月，最迟 223 年 4 月强制收束。
- 内部玩家势力 id 固定为 `liu_bei`；不再产生新的 `ming` 业务逻辑。
- 旧明末静态内容、业务字段、接口、界面、测试、存档和随机选妃语义全部删除，不保留运行时兼容层；只保留首次启动时识别并删除旧存档的最小一次性逻辑。
- 前端、人物立绘、地图与阶段场景必须使用偏写实的三国国风，以考据服饰武备、写实材质光影、宣纸界画与水墨卷轴为统一视觉语汇。
- 高影响状态必须通过结构化动作和硬规则校验：死亡、领土易主、割地、军队覆灭、政权消亡均不得由 LLM 文本直接写入。
- 人物每项属性必须同时影响规则结算、AI 上下文和审计日志；做不到则删除该字段。
- TDD 顺序不可颠倒：测试失败 → 最小实现 → 定向测试通过 → 全量回归。
- 当前目录不是 Git 仓库，不得擅自 `git init`；所有修改使用 `apply_patch`，每阶段通过测试后在本计划勾选并记录验证结果。
- 每次会话结束前更新 `/Users/zhuanzmima0000/Documents/Obsidian Vault/wiki/DeepSeek-观察/2026-07-16.md`，记录完成阶段、测试证据和下一恢复点。

---

## 当前真实状态（恢复时先读）

- [x] Task 1–22 的代码、静态数据、API、React UI、迁移和发布验证均已执行并记录证据。
- [x] 当前盘面为 208 年 8 月、13 州、35 节点、46 边、9 势力、25 军、140 名历史人物；新档固定写入 `scenario_id=sanguo_liubei_208`。
- [x] 三国月末先执行军令、补给、战役、围城、外交/事件/结局硬规则，再允许 LLM 只润色已裁定事实；LLM 失败自动退回硬规则报告。
- [x] 玩家可见目录的明末关键词扫描为 0 命中；热读档拒绝非三国场景数据库，首次迁移只删除可明确识别的旧明末 SQLite。
- [x] 最终证据：`python3 -m pytest tests -q` → **143 passed**；核心对抗与迁移专项 → **47 passed**；`npm ci && npm run build` 成功；FastAPI 首页和菜单状态均为 HTTP 200。
- [x] 生产依赖 `npm audit --omit=dev` 为 0 漏洞；开发/打包依赖仍有 6 项审计告警，未自动执行可能改变依赖树的 `npm audit fix`。
- [x] 当前目录仍不是 Git 仓库，未创建分支、提交或 worktree。
- [ ] 发布前人工美术验收：五阶段当前复用同一张三国地图并用不同定位表达场景，人物使用 portrait id + 文本回退；独立阶段场景与实际人物立绘仍是素材缺口。

**下一恢复入口：**

```bash
cd /Users/zhuanzmima0000/Desktop/SANGUO
python3 -m pytest tests -q
cd web && npm run build
```

预期：Python `143 passed`，TypeScript/Vite 生产构建成功。之后进入发布候选人工验收或补齐美术素材，不再重做已经审核的数据与规则阶段。

---

## 阶段一：数据库与静态数据骨架

### Task 1：三国数据库 Schema

**Files:**

- Modify: `ming_sim/db/schema.py`
- Create: `ming_sim/db/strategy.py`
- Modify: `ming_sim/db/__init__.py`
- Test: `tests/test_sanguo_schema.py`

**Interfaces:**

- `GameDB.list_strategic_nodes() -> list[dict]`
- `GameDB.list_strategic_routes() -> list[dict]`
- `GameDB.issue_army_order(state, army_id, order_type, payload) -> int`
- `GameDB.list_army_orders(turn: int) -> list[dict]`
- 新表：`strategic_nodes`、`strategic_routes`、`army_orders`、`sieges`、`diplomacy_treaties`、`character_attribute_logs`

- [x] 运行 `python3 -m pytest tests/test_sanguo_schema.py -q`，确认因缺表/缺列失败。
- [x] 在 `characters` 增加 `leadership,intelligence,politics,charisma,ambition,closeness_to_liu_bei,core_tier`。
- [x] 在 `armies` 增加 `fatigue,experience,discipline,hazard_turns,specialties`。
- [x] 在 `game_state` 增加 `stage,collapse_turns,chengdu_crisis_turns`。
- [x] 创建六张三国表；`army_orders` 必须有 `UNIQUE(army_id,turn)`，条约必须保存条款 JSON、起止回合和状态。
- [x] 将战略 DB 方法放入 `_StrategyMixin` 并接入 `GameDB`，避免继续膨胀 `schema.py`。
- [x] 运行定向测试：`python3 -m pytest tests/test_sanguo_schema.py -q` → `5 passed`（扩充了接口与状态往返测试）。
- [x] 运行 `python3 -m pytest tests -q` → `59 passed`。

### Task 2：路线与战略盘面 Seed

**Files:**

- Modify: `ming_sim/db/seed.py`
- Modify: `ming_sim/content.py`
- Modify: `ming_sim/models.py`
- Test: `tests/test_sanguo_schema.py`

**Interfaces:**

- `GameContent.routes: StrategicRouteCatalog`
- `load_strategic_routes()` 仍是 `content/routes.json` 唯一加载入口。

- [x] `StrategicNode/StrategicEdge/StrategicRouteCatalog` 保持在 `sanguo_rules.py`，`GameContent` 与 DB 引用同一类型。
- [x] `GameContent.load()` 加载 routes，并校验节点 id、名称唯一、边端点存在、路线类型闭集。
- [x] `seed_static_data()` 仅在新表为空时写入 35 节点、46 边；已存在盘面不得被启动覆盖。
- [x] 新增断言：重复 id/名称、未知端点、非法路线类型及反向重复边必须让加载失败。
- [x] 定向测试 `13 passed`；全量测试 `62 passed`。

### Task 3：人物 81 人种子数据

**Files:**

- Replace: `content/characters.json`
- Modify: `ming_sim/content.py`
- Modify: `ming_sim/db/seed.py`
- Create: `tests/test_sanguo_characters.py`

**Interfaces:**

- JSON 人物字段：`name,office,office_type,faction,aliases,personal_skills,loyalty,integrity,ambition,courage,closeness_to_liu_bei,martial,leadership,intelligence,politics,diplomacy,charisma,power_id,location,status,debut_year,debut_month,core_tier,style,summary,portrait_id`。

- [x] 写失败测试：恰好 81 个唯一人物；马超只出现一次；能力表与状态表的 81 名完全覆盖；全部数值在 0–100；`core_tier` 只允许 S/1/2/3。
- [x] 用两张审核表逐行转录 81 人，不从旧明末字段推导三国能力；保留 `scripts/import_sanguo_characters.py` 作为可复现导入器。
- [x] `ability/stewardship/intrigue/learning` 仅作为迁移兼容字段；三国六维独立加载并落库。
- [x] 所有 `dead` 人物保留记忆且状态为 `dead`，现有行动查询按 `status='active'` 排除。
- [x] 所有 `offstage` 人物预先映射至有效战略节点，登场不产生悬空所在地。
- [x] 定向测试 `5 passed`（含宗室迁移兼容）；全量测试 `65 passed`。

**Task 4 前置冲突（已解决）：** 用户同意将刘巴提前列为第 81 人，后续计入约 140 人总数；军队审核表保持不变。

### Task 4：九方势力、35 地区与 25 军

**Files:**

- Replace: `content/powers.json`
- Replace: `content/regions.json`
- Replace: `content/armies.json`
- Modify: `ming_sim/models.py`
- Create: `tests/test_sanguo_opening_board.py`

**Interfaces:**

- 势力 id：`cao_cao,sun_quan,liu_bei,liu_qi,liu_zhang,zhang_lu,ma_han,shi_xie,gongsun_kang`。
- 地区 `id` 必须与 `routes.json` 节点完全一致；刘备没有 `controlled_by=liu_bei` 的正式地区，夏口通过驻军权表达。
- 军队 id、兵力、驻地严格使用审核通过军队表。

- [x] 写失败测试：9 势力、35 地区、25 军；刘备三军合计 22,000；所有军队统帅存在且驻地可解析。
- [x] 将旧省级财政字段映射为三国郡级字段，`fiscal` 包含全部 11 项审核字段并暂留旧公式兼容键。
- [x] 为“夏口驻军权”在 `diplomacy_treaties` 新增结构化有效记录，不伪造刘备控制江夏。
- [x] 曹操可调度军队合计 128,000；活动军严格保持25支。
- [x] 定向测试 `4 passed`；迁移旧测试夹具后全量测试 `70 passed`。

**阶段一验收门（已通过）：** 新库可初始化，81 人/9 势力/35 地区/25 军/46 边全部落库；旧明末人物、势力和地区不再进入新局。证据：`python3 -m pytest tests -q` → `70 passed`。

---

## 阶段二：人物属性与 AI 真实作用

### Task 5：统一属性效果引擎

**Files:**

- Create: `ming_sim/character_effects.py`
- Create: `content/character_traits.json`
- Modify: `ming_sim/context.py`
- Create: `tests/test_character_effects.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class AttributeModifier:
    source_character: str
    attribute: str
    context: str
    raw_value: int
    delta: float
    reason: str

def evaluate_character_modifier(character, context: str) -> list[AttributeModifier]: ...
def apply_character_modifiers(base: float, modifiers: list[AttributeModifier]) -> float: ...
```

- [x] 为武力、统率、智略、政治、外交、魅力、忠诚、节义、野心、胆略、亲密度各写至少一个失败测试并实现方向性修正。
- [x] 从审核表转录 20 项特性；同类乘区取最高、跨类可叠加。
- [x] 属性修正可写入 `character_attribute_logs`：人物、属性、场景、原值、修正、原因、回合。
- [x] `character_context_with_db()` 注入属性值、最近变化、刘备关系和可行动范围。
- [x] 糜芳用例证明忠诚下降/野心上升会提高倒戈压力，而非只改变文案。
- [x] 定向测试 `17 passed`；全量测试 `87 passed`。

### Task 6：分级人物情报

**Files:**

- Create: `ming_sim/intelligence.py`
- Modify: `web_app.py`
- Modify: `web/src/types.ts`
- Create: `tests/test_character_intelligence.py`

**Interfaces:**

```python
def visible_character_profile(character, intel_level: int, viewer_power="liu_bei") -> dict: ...
```

- [x] 己方六维公开；人格在低情报时显示倾向/区间，高情报或高亲密度时显示精确值。
- [x] 敌方默认只给身份、所在地和能力评语；侦察/细作/外交提升情报等级。
- [x] 后端响应不得泄漏被隐藏的原始人格数值。
- [x] 添加 API 与序列化测试，确保隐藏在服务端完成；定向 `10 passed`，全量 `97 passed`。

**阶段二验收门：** 已通过。11 项属性均能通过规则测试改变结果、进入 AI 上下文并生成日志；无装饰数值。人物情报由服务端裁剪，低情报响应不含原始人格字段。

---

## 阶段三：路线、补给、围城与战役

### Task 7：单军单令与每边一月移动

**Files:**

- Modify: `ming_sim/sanguo_rules.py`
- Modify: `ming_sim/db/strategy.py`
- Modify: `ming_sim/session.py`
- Create: `tests/test_army_orders.py`

**Interfaces:**

```python
def validate_route_move(db, army_id: str, source: str, target: str) -> StrategicEdge: ...
def resolve_army_order(db, state, order_id: int) -> dict: ...
```

- [x] 军令闭集：移动、驻守、围城、突袭、补给、撤退。
- [x] 同军同回合第二道主军令必须拒绝；不同军可并行。
- [x] 一条边固定消耗一回合，不能按地图直线跨节点。
- [x] 关隘未被攻克时移动拒绝并提供“围城”选项。
- [x] 进入江河/山道扣 20 粮秣；低于 20 拒绝；三回合战力/机动 0.5，重复进入刷新为 3 不叠加。
- [x] 山地特性只把机动减益改为 -35%，不免固定粮耗。
- [x] 定向测试 `13 passed`；全量测试 `104 passed`。

### Task 8：郡仓补给与断粮

**Files:**

- Create: `ming_sim/supply.py`
- Modify: `ming_sim/db/regions.py`
- Modify: `ming_sim/db/armies.py`
- Create: `tests/test_sanguo_supply.py`

**Interfaces:**

```python
def reachable_friendly_granary(db, army_id: str) -> str | None: ...
def settle_army_supply(db, state, army_id: str) -> dict: ...
```

- [x] 驻守或路线可达的友方郡仓优先补给；远征消耗携粮。
- [x] 敌军控制、未攻克关隘或断开的路线阻断补给。
- [x] 断粮依次造成士气、疲劳、逃亡和战力惩罚，全部写日志。
- [x] “补给”军令可从郡仓转入军队，但受仓粮和路线限制。
- [x] 定向测试 `8 passed`；全量测试 `112 passed`。

### Task 9：围城与关隘

**Files:**

- Create: `ming_sim/siege.py`
- Modify: `ming_sim/db/strategy.py`
- Create: `tests/test_siege.py`

**Interfaces:**

```python
def start_siege(db, state, army_id: str, target_node: str) -> int: ...
def advance_siege(db, state, siege_id: int) -> dict: ...
```

- [x] 等势攻守的标准城约 3 回合达到 100 进度。
- [x] 城防、粮仓、守城/攻城特性、救援与断粮可缩短或延长。
- [x] 攻下节点后才更新控制权和关隘通行状态。
- [x] 围城失败、撤退、援军击破须保留可追溯状态与战报。
- [x] 定向阶段三测试 `21 passed`；全量测试 `118 passed`。

### Task 10：战役预览与 60/40 裁决

**Files:**

- Create: `ming_sim/battle.py`
- Modify: `ming_sim/simulation.py`
- Modify: `ming_sim/issues.py`
- Create: `tests/test_battle_resolution.py`

**Interfaces:**

```python
def preview_battle(db, attacker_ids: list[str], defender_ids: list[str], node_id: str) -> dict: ...
def resolve_battle(db, state, battle_input: dict, ai_choice: dict) -> dict: ...
```

- [x] 预览返回胜率区间和主要因素，不返回确定结果。
- [x] 硬规则计算兵力、统率、训练、装备、士气、疲劳、补给、地形和特性。
- [x] AI 40% 只能从已知计策白名单选择；无效援军、复活、跳过补给必须拒绝。
- [x] 战后公开随机值、全部修正和属性来源。
- [x] 一级核心人物遇险优先重伤/被俘/失势/撤退；死亡需要专属事件、处决或严格死亡门槛。
- [x] 定向阶段三测试 `30 passed`；全量测试 `127 passed`。

**阶段三验收门：** 后端规则与会话结算链已通过；可对多军分别下令，完成移动、补给、围城、救援、撤退和可审计战役结算。主地图交互在阶段六接入。

---

## 阶段四：外交、政治、家族与国策

### Task 11：六维外交与规则化盟约

**Files:**

- Create: `ming_sim/diplomacy.py`
- Modify: `ming_sim/db/strategy.py`
- Create: `content/opening_relations.json`
- Create: `tests/test_diplomacy.py`

**Interfaces:**

```python
def propose_treaty(db, proposer: str, target: str, terms: dict) -> dict: ...
def breach_treaty(db, state, treaty_id: int, actor: str, action: dict) -> dict: ...
```

- [x] 公开关系、互信、盟约义务、领土主张、婚姻/人质、军事协作分别存储。
- [x] 玩家与 AI 均可违约，但自动结算互信、名分、士族、婚姻和战争后果。
- [x] 外交能力修正成功率，不能覆盖领土主张与硬性义务。
- [x] 孙刘联盟、荆州归属、孙尚香婚姻必须有独立条款。
- [x] 定向测试 `5 passed`；全量测试 `132 passed`。

### Task 12：五阶段身份与简化官制

**Files:**

- Create: `content/sanguo_offices.json`
- Create: `ming_sim/government.py`
- Modify: `ming_sim/session.py`
- Create: `tests/test_government_stages.py`

**Interfaces:**

```python
def government_stage(year: int, month: int, world_state: dict) -> str: ...
def office_effect(db, office_key: str) -> dict: ...
```

- [x] 阶段：流亡军、荆州立足、益州牧、汉中王、称帝后。
- [x] 职位：首席军师、军政长、政务长、财政长、外交长、情报长、主力统帅、禁卫统帅、郡守、战区都督。
- [x] 职位空缺只降低效率，不封锁行动；任命权始终归玩家。
- [x] 208 年不得使用皇帝/朝会文案，221 称帝后才切换蜀汉宫廷语义。
- [x] 定向测试 `7 passed`；全量测试 `139 passed`。

### Task 13：国策书、地区投资与家族

**Files:**

- Create: `content/national_focuses.json`
- Create: `ming_sim/national_focus.py`
- Create: `content/families.json`
- Create: `tests/test_national_focus.py`

**Interfaces:**

```python
def focus_points(db, state, category: str) -> int: ...
def advance_focus(db, state, focus_id: str) -> dict: ...
```

- [x] 11 条国策按政治/军事/经济三类录入；三类可各并行一项，同类互斥。
- [x] 每类每回合 0–3 点：基础 1，优秀条件 +1，关键人物/特殊国策 +1。
- [x] 每郡同一时间只投资屯田粮仓、城防守备、军备练兵、水军船政、道路粮道、民政市易之一。
- [x] 家族系统只保留历史配偶、子嗣、政治婚姻、联姻盟约和继承风险，不生成随机选妃池。

验收证据：国策修正已接入携粮消耗、水战/骑战及地方投资产出与速度；月末自动推进已接入会话结算。定向测试 `9 passed`，全量测试 `148 passed`。

**阶段四验收门：已通过。** 联盟、婚姻、官职、国策和郡级投资均有结构化状态、规则效果和日志。

---

## 阶段五：历史压力、外部 AI 与结局

### Task 14：15 张历史事件卡与生命周期

**Files:**

- Replace: `content/events.json`
- Replace: `content/seed_events.json`
- Modify: `ming_sim/issues.py`
- Create: `ming_sim/historical_events.py`
- Create: `tests/test_historical_events.py`

**Interfaces:**

```python
def evaluate_historical_event(db, state, event_id: str) -> dict: ...
```

- [x] 录入新野余波、孙刘联盟、赤壁、荆南、孙夫人、入蜀、成都归降、湘水、汉中、汉中王、荆州崩解、曹丕代汉、成都称帝、伐吴/夷陵、白帝托孤。
- [x] 生命周期闭集：scheduled、eligible、adapted、resolved、superseded、expired。
- [x] 每卡含窗口、硬前提、首选/候补、结果变体、世界后果。
- [x] 已死人物不能执行；无合理候补时事件失效并写入史册。
- [x] 未来 12 个月时间线只显示重大事件标题与窗口；不剧透胜负、死生、计策。

验收证据：15 卡及 3 张三国动态情势卡的人物/势力引用对抗校验通过；定向测试 `8 passed`，全量测试 `156 passed`。

### Task 15：外部势力月末 AI

**Files:**

- Create: `ming_sim/power_ai.py`
- Modify: `ming_sim/simulation.py`
- Modify: `content/prompts/season_simulator.md`
- Create: `tests/test_power_ai.py`

**Interfaces:**

```python
def available_power_actions(db, state, power_id: str) -> list[dict]: ...
def validate_power_action(db, state, action: dict) -> dict: ...
```

- [x] AI 根据战略意图、军力、粮秣、外交、地缘和情报行动，不按固定脚本或纯随机。
- [x] 历史锚点之外也可开战、求和、策反、扩张。
- [x] AI 只能从规则层提供的合法行动选择；文本不得直接落领土/死亡事实。

验收证据：月末每外部势力最多一项结构化行动，相邻且未预置外交关系的势力也可依议程开战；直改领土、指定杀人、伪造援军均被拒绝。定向测试 `6 passed`，全量测试 `162 passed`。

### Task 16：四类结局与六维国史评

**Files:**

- Modify: `ming_sim/context.py`
- Modify: `ming_sim/decree.py`
- Replace: `content/prompts/ending_summary.md`
- Create: `tests/test_sanguo_endings.py`

**Interfaces:**

- 结局 id：`liu_bei_dead, yizhou_core_fallen, regime_collapsed, historical_baidi, unified_victory, rewritten_223`。

- [x] 刘备死亡即时结束。
- [x] 214 后成都失守触发三回合危局；收复清零；到期或江州/永安全失则失败。
- [x] 无郡 + 兵力 <3000 连续三回合才政权瓦解。
- [x] 全节点 `liu_bei` 且其他势力无节点、无现役军才一统。
- [x] 223 年 4 月：符合演义病逝走白帝；刘备仍活但未统一走改写收束。
- [x] 所有结局生成全程时间线与统一、名分、民生、将相、外交、军功六项评分和长评。

验收证据：结局只由硬规则判定，战役/围城结算后再次即时核验；文本层仅撰写已定史评。定向测试 `6 passed`，全量测试 `168 passed`。

**阶段五验收门：已通过。** 历史事件可被长期行动改写且不重复；外部势力可自主行动；全部终局由硬规则触发。

---

## 阶段六：API 与前端完整替换

### Task 17：三国 API 合同

**Files:**

- Modify: `web_app.py`
- Modify: `web/src/api.ts`
- Modify: `web/src/types.ts`
- Create: `tests/test_sanguo_api.py`

- [x] API 输出政权阶段、六指标、35 节点/46 边、军队订单、围城、条约、国策、未来事件和分级人物资料。
- [x] 删除 API 响应及后端业务层中的明末专有字段与兼容分支；新 UI 与运行时均不保留明末兼容。
- [x] 所有高影响写接口再次执行服务端校验，不信任前端 payload。

验收证据：三国专用 `state_payload()`、人物情报裁剪、军令与战役服务端复核均已接入；国策与地区投资写接口也重新进入规则层。定向测试 `4 passed`，全量测试 `172 passed`。

### Task 18：主地图军令面板

**Files:**

- Modify: `web/src/components/map.tsx`
- Create: `web/src/components/armyCommandPanel.tsx`
- Modify: `web/src/main.tsx`
- Modify: `web/src/styles.css`

- [x] 地图只允许沿路线边选择目标，关隘和险路有明确图例。
- [x] 选军后显示兵力、粮秣、士气、疲劳、军资缺额和本回合军令状态。
- [x] 战役预览显示胜率区间与主要因素；确认后提交结构化军令。
- [x] 战报面板展示属性、特性、补给、地形和事件修正日志。

验收证据：相邻目标由 46 边计算，关隘/江河/山道图例与风险提示已接入；战前预览、结构化军令、军令状态及最近战役分项审计均在军令面板显示。新增合同测试先 RED 后 GREEN；定向 `1 passed`，全量 `173 passed`，`npm run build` 成功。

### Task 19：HUD、时间线、人物与阶段场景

**Files:**

- Modify: `web/src/components/hud.tsx`
- Create: `web/src/components/historyTimeline.tsx`
- Modify: `web/src/components/drawers.tsx`
- Modify: `web/src/styles.css`

- [x] 顶栏显示政权阶段、年月、军资/粮秣/民望/名分/军心/士族支持。
- [x] 顶部时间线可滑动查看未来 12 个月重大事件；改写后保留并标注改写/失效/变体。
- [x] 人物页公开六维，人格按情报显示倾向/区间/精确值。
- [x] 场景随夏口军营、荆州治所、成都州牧府、汉中王府、蜀汉宫城变化。
- [x] 入口固定为朝议、军令、外交、国策、家族、史册。
- [x] 视觉使用赭石、朱红、金黄、墨黑、米白、宣纸纹理、界画和卷轴；不得保留现代赛博黑卡风。

验收证据：HUD、时间线、人物案卷、阶段场景和六入口均消费 Task 17 三国合同；`npm run build` 完成 TypeScript 与 Vite 生产构建。阶段六全回合实机联调保留至 Task 22 统一执行。

**阶段六验收门：** Electron/Web 共用的新 UI 可完成一个完整月回合，不需访问旧明末页面。

---

## 阶段七：内容补齐、旧内容清除与发布验证

### Task 20：人物补齐到约 140 与小势力厚度

**Files:**

- Modify: `content/characters.json`
- Modify: `content/families.json`
- Modify: `content/character_traits.json`
- Test: `tests/test_sanguo_characters.py`

- [x] 优先补张鲁、公孙康、士燮、刘琦的二线文武，再补蜀汉、曹魏、东吴后期人物。
- [x] 每个具名人物必须有六维、五人格、所在地、状态、官职、核心级、特性和登场窗口。
- [x] 约 40 核心人物使用专属 portrait id，其余使用身份/年龄/势力分级肖像。
- [x] 不允许为了凑数量生成替代演义名将的虚构人物。

验收证据：在首批 81 人之外补入 59 名演义/三国历史人物，总数 140；张鲁、公孙康、士燮、刘琦第二批强制名单 11 人全部覆盖。52 人保留专属 portrait id，其余按势力/身份分级；人物、特性、势力、地点引用闭合。扩展脚本可重复执行；定向测试 `4 passed`，全量测试 `173 passed`。

### Task 21：明末内容与旧存档废弃

**Files:**

- Replace: `content/prompts/*.md`
- Modify: `ming_sim/paths.py`
- Modify: `launcher.py`
- Modify: `web/src/components/gameMenu.tsx`
- Create: `tests/test_legacy_cleanup.py`

- [x] 全局搜索并移除玩家可见的崇祯、大明、后金、皇太极、辽饷、后宫选秀等语义。
- [x] 首次启动三国版只删除可明确识别为旧明末版本的存档，不误删三国新档或其他文件。
- [x] 新存档加入不可混淆的场景版本，如 `scenario_id=sanguo_liubei_208`。
- [x] 保留手动存档与最近三回合自动存档。

验收证据：18 份运行时 prompt、通用静态目录、启动器标题与默认收藏均替换为刘备线；旧人物立绘、旧 HUD/宣传图和旧阶段背景从发布目录移除。迁移器只识别“无场景 id 且含旧势力 id”的 SQLite，且仅运行一次；新库写入 `scenario_id=sanguo_liubei_208`，热读档拒绝其他场景。定向迁移/新局/月末/轮转/结局/热读档测试 `12 passed`；玩家可见目录旧关键词扫描 0 命中；最终全量测试 `143 passed`，`npm run build` 成功。

### Task 22：最终验证与对抗性审查

**Files:**

- Update: `README.md`
- Update: `PROJECT_INIT.md`
- Update: `/Users/zhuanzmima0000/Documents/Obsidian Vault/wiki/DeepSeek-观察/2026-07-16.md`

- [x] 运行 `python3 -m pytest tests -q`，要求 0 failed/0 errors。
- [x] 运行 `npm ci && npm run build`（工作目录 `web/`），要求 TypeScript/Vite 构建成功。
- [x] 启动 FastAPI，验证新局、完整月末结算、存档/读档、结束摘要。
- [x] 对抗性检查：对话声称人物死亡、凭空援军、越过关隘、低粮进险路、同军双令、违约无代价，系统均必须拒绝或规则化结算。
- [x] 搜索玩家可见明末残留并清零；列出仅为迁移兼容而保留的内部字段。
- [x] 更新本计划全部复选框和“当前真实状态”，写明最后测试证据及未完成项。
- [x] 按 Obsidian 协议记录：发现、长期价值、正式归档状态和下一阶段入口。

验收证据：全量 `143 passed`；军令、战役、外交、历史事件、势力 AI 与迁移专项 `47 passed`；前端干净安装与生产构建成功；FastAPI 首页和 `/api/menu/status` 均返回 HTTP 200，首页标题为“汉祚再兴 · 刘备传”。新局、完整月末、手动存读档、三回合自动档轮转、223 结局摘要和异场景热读档拒绝均有集成测试。玩家可见旧题材扫描 0 命中；仅保留 `ming_sim` 包名、`MING_SIM_*` 环境变量前缀和旧 spec 历史参考。未完成项仅为人工美术资产升级：独立五阶段场景和实际人物立绘。

---

## 上下文压缩后的强制恢复协议

新会话或上下文压缩后必须依次执行：

1. 完整读取本计划与八份事实源，不依据摘要直接编码。
2. 找到第一个未勾选任务；查看它前一任务的测试证据。
3. 运行 `python3 -m pytest tests -q` 确认当前基线。
4. 若存在预期 RED 测试，只运行对应测试确认失败原因与计划一致。
5. 继续当前任务，不重新生成已审核数据，不重做已完成阶段。
6. 每完成一个任务，立即勾选本文件并记录实际测试命令和结果。

## 决策升级规则

只有以下情况必须暂停并向用户给出选项：

- 事实源之间出现无法按优先级解决的冲突；
- 需要增删地区、人物、势力、军队、历史事件或结局；
- 需要改变硬数值规则、玩家可见信息、历史剧透程度或 AI 权限；
- 会造成超出已授权旧明末存档范围的数据删除。

以下事项由实现者自行决定，不打断用户：模块拆分、函数命名、索引、SQL 查询、缓存、TypeScript 组件边界、测试夹具与不改变玩法的性能优化。
