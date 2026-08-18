# SANGUO 三国策略游戏 — ming_sim 核心机制架构

## 一、项目结构总览

```
ming_sim/                       ← 游戏内核包 (26,403 行 Python)
├── __init__.py                 ← 无副作用导入，GameContent.load() 显式触发
├── models.py (13.5K)           ← 数据类：所有实体的 dataclass 定义
├── constants.py (9K)           ← 全局常量、字段白名单、别名映射
├── content.py (55K)            ← 设定加载：content/*.json → GameContent
├── context.py (19K)            ← 结局判定、历史锚点、名称模糊匹配
├── sanguo_rules.py (13K)       ← 州块移动、军令、险路、围城进度公式
│
├── session.py (38K)            ← GameSession 状态机 (CLI/Web 共用入口)
├── decree.py (31K)             ← 诏书生成 + 月末结算 (resolve_directives)
├── simulation.py (33K)         ← LLM 推演 + 打分提取器
├── agents.py (37K)             ← Agno Agent 工厂 + LLM 调用封装
├── llm_config / llm_model      ← LLM 配置与模型创建
│
├── issues.py (104K)            ← Issue 系统：候选事件、立项/推进/结案
├── historical_events.py (24K)  ← 历史事件卡（可改写）
├── random_events.py (12K)      ← 随机事件框架
│
├── battle.py (31K)             ← 战役裁决（60/40 硬规则/AI 战术）
├── siege.py (18K)              ← 多回合围城 + 救援状态机
├── supply.py                   ← 郡仓补给、断粮结算
├── diplomacy.py (21K)          ← 六维外交、盟约、违约
├── national_focus.py (19K)     ← 国策书 + 郡级投资
├── power_ai.py (31K)           ← 外部势力 AI 行动生成
├── identity.py (6K)            ← 称号进位：汉中王→称帝
├── government.py (10K)         ← 五阶段政权 + 十槽官制
│
├── flows.py (37K)              ← 月度财政：税银/军饷/建筑/人口/粮食
├── reactions.py (23K)          ← 人物/诸侯反应层
├── long_term.py (6K)           ← 派系支持度、忠诚调整、口碑
├── phased_execution.py (33K)   ← 五阶段颁令执行器
├── monthly_report.py (29K)     ← 月报生成
│
├── adjudication.py (30K)       ← 统一裁决包协议 (AI 受控裁判)
├── character_effects.py (4K)   ← 人物属性修正器
├── gating.py (11K)             ← 触发条件 DSL 求值器
│
├── world_simulation.py (Facade)← 世界模拟统一入口
├── ws_*.py (12 子模块)         ← 区域/地缘/情报/事件链/内部动态
├── world_random.py (10K)       ← 存档级确定性随机流
│
├── directives.py (8K)          ← 结构化固定指令模板
├── matching.py (4.5K)          ← 地区/军队模糊匹配
├── registry.py (33K)           ← 人物名册管理
├── memories.py (13K)           ← 章节记忆、大臣回顾
├── scenario_tools.py (20K)     ← 剧本编辑工具集
├── tools.py (48K)              ← 给 LLM 的工具集
├── skills.py                   ← 技能系统
│
└── db/                         ← 数据库层 (SQLite)
    ├── schema.py (98K)         ← 全部建表 DDL
    ├── seed.py (28K)           ← 开局数据播种
    ├── regions.py (42K)        ← 地区查询/更新
    ├── armies.py (45K)         ← 军队查询/更新
    ├── characters.py (28K)     ← 人物查询/更新
    ├── turns.py (20K)          ← 回合存储
    ├── fiscal.py (31K)         ← 财政账本
    ├── strategy.py (12K)       ← 战略/战役
    ├── secret_orders.py (28K)  ← 密令
    └── ...
```

## 二、游戏会话 (session.py + decree.py)

### 回合状态机 (TurnPhase)
```python
SUMMONING  → 召见中：对话、大臣拟旨
REVIEWING  → 核定草案：增删改、确认/驳回
AWAITING_DECISION → HITL：simulator 出决策点暂停
ISSUED     → 已颁诏：resolve 完成，待 end_turn
```

### 月度结算流程 (resolve_directives / apply_fixed_period_flows)
1. **诏书推演** — LLM simulator 生成邸报
2. **打分提取** — extractor 从邸报抽结构化增量
3. **财政落账** — 固定收支（compute_budget_lines）
4. **军饷发放** — 按优先级，欠饷累积
5. **建筑产出/维护** — 按 condition 折产
6. **年度粮食结算** — 12月：年产入仓 - 人口口粮
7. **年度人口结算** — 12月：基础增长率 ± 修正
8. **局势推进** — inertia 漂移、结案判定
9. **天下事件** — 历史事件卡生命周期推进
10. **外部势力 AI** — resolve_power_ai_turn
11. **补给结算** — settle_all_army_supply
12. **军令结算** — 移动/驻守/围城/突袭
13. **围城推进** — resolve_siege_turn
14. **战役结算** — resolve_battle_orders_for_turn
15. **国策推进** — advance_all_focuses
16. **地区投资** — advance_all_region_investments
17. **外交漂移** — apply_war_diplomatic_drift

### 关键数值
- TURN_UNIT = "月"
- GameState 初始：year=208, period=8
- metrics 6维：军资60/粮秣60/民望55/名分70/军心65/士族支持40

## 三、人物系统 (models.Character + character_effects.py)

### 属性体系
**三国版六维** (0-100):
- diplomacy (外交), martial (武力), stewardship (管理)
- intrigue (谋略), learning (学识), leadership (统率)
- intelligence (智略), politics (政治), charisma (魅力)
- ambition (野心), closeness_to_liu_bei (对刘备亲密度)

**传统四属性**:
- loyalty (忠诚), ability (能力), integrity (节义), courage (胆略)

**核心等级 core_tier**: S | 1 | 2 | 3

**状态枚举**: active | offstage | dismissed | imprisoned | exiled | retired | dead

### 人物属性修正器 (character_effects.py)
```python
ATTRIBUTE_CONTEXTS = {
    "personal_combat":   {"martial": 0.25},
    "battle_command":    {"leadership": 0.20, "intelligence": 0.05},
    "scheme":            {"intelligence": 0.22, "courage": 0.04},
    "governance":        {"politics": 0.20, "charisma": 0.05},
    "negotiation":       {"diplomacy": 0.20, "charisma": 0.06},
    "pacification":      {"charisma": 0.20, "politics": 0.05},
    "defection_pressure":{"loyalty":-0.20,"integrity":-0.08,"ambition":0.18,"closeness":-0.10},
    "raid":              {"courage": 0.20, "martial": 0.05, "intelligence": 0.04},
    "protect_liu_bei":   {"closeness": 0.20, "loyalty": 0.10, "martial": 0.05},
}
# 公式：delta = (attribute - 50) * weight
```

### 特性系统 (personal_skills)
特性来自 content/character_traits.json，每个特性有 effects 列表:
```json
{"context": "field_battle", "attribute": "leadership", "delta": 10}
```
同一 context+category 取绝对值最大者生效。

## 四、军事系统

### 4.1 军队属性 (models.Army)
- manpower (兵力), maintenance_per_turn (月维护费)
- supply (携粮), supply_turns (可撑月数)
- morale (士气 0-100), training (训练 0-100)
- equipment (装备 0-100), arrears (欠饷 万两)
- mobility (机动 0-100), loyalty (忠诚 0-100)
- fatigue (疲劳 0-100), experience, discipline (50)
- hazard_turns / hazard_combat_multiplier / hazard_mobility_multiplier
- starvation_turns / supply_combat_multiplier

### 4.2 军令系统 (sanguo_rules.py)
```python
PRIMARY_ORDERS = {"移动", "驻守", "围城", "突袭", "补给", "撤退"}
```
每军每回合只能下一道主军令，写入 army_orders 表。

### 4.3 州块移动
- 同州内自由调动
- 跨州须邻接（通过 strategic_routes 检查）
- 移动耗时 = 1 回合

**险路惩罚** (江河/山道):
- 携粮 < 20 → 不可进入
- 进入后: supply - 20, hazard_turns = 3
- combat_multiplier = 0.5, mobility_multiplier = 0.5
- 有"山地"特性 → 山道机动 = 0.65 (而非 0.5)

### 4.4 战役系统 (battle.py)

**军队评分公式**:
```
score = manpower
      * quality_multiplier        # (training+equipment+morale+discipline)/4 → 0.5~1.5
      * command_multiplier         # max(0.5, 1 + attribute_pct/100)
      * fatigue_multiplier         # max(0.4, 1 - fatigue/150)
      * supply_multiplier          # 断粮惩罚
      * hazard_multiplier          # 险路惩罚
      * terrain_multiplier         # 地形修正
      * trait_multiplier           # 人物特性
      * focus_multiplier           # 国策加成
```

**地形修正**:
| 地形 | 攻方 | 守方 |
|------|------|------|
| 关隘 | ×0.75 | ×1.05 |
| 江河 | ×0.85 | ×1.05 |
| 山道 | ×0.85 | ×1.05 |
| 普通路 | ×1.0 | ×1.0 |

**胜率公式**:
```
hard_probability = clamp(50 + 40*(A-D)/(A+D), 10, 90)  # 百分比
```

**战术白名单**:
| 战术 | delta | 需求 |
|------|-------|------|
| 正面交锋 | 0 | 无 |
| 佯攻诱敌 | +7 | 智略≥75 |
| 夜袭 | +7 | 智略≥70, 胆略≥70 |
| 火攻 | +10 | 特性"火攻" |
| 水战突击 | +10 | 特性"水战", 地形江河 |
| 山地伏击 | +10 | 特性"山地", 地形山道 |

**最终概率**:
```
final = hard_probability * 0.6 + tactic_component * 0.4 + environment_delta
tactic_component = clamp(50 + delta*2, 30, 70)
roll = deterministic_random(1, 100)
attacker_won = (roll <= final_probability)
```

**战损**:
- 胜方: manpower -5%~8%, morale +3, fatigue +8
- 败方: manpower -18%~21%, morale -10, fatigue +15

**将领命运** (margin = |roll - final_probability|):
| 核心等级 | margin 阈值 | 结果 |
|----------|-------------|------|
| S/1 | ≥35 | 被俘 (→imprisoned) |
| S/1 | ≥25 | 重伤 |
| S/1 | <25 | 撤退 |
| 2/3 | ≥30 | 失势 |
| 2/3 | <30 | 撤退 |

### 4.5 围城系统 (siege.py)

**围城进度公式** (sanguo_rules.calculate_siege_progress):
```python
monthly = round(34 * attacker_score / defender_score)
monthly = max(10, min(60, monthly))
new_progress = min(100, old + monthly)
```

**攻方评分**:
```
score = (manpower/1000) * quality_factor * leadership_factor * hazard * supply
quality_factor = 0.5 + (morale+training+equipment+discipline)/400
leadership_factor = 0.5 + leadership/100
攻城特性 → ×1.15
```

**守方评分**:
```
score = (manpower/1000) * quality * leadership * fortification * grain
fortification_factor = 0.75 + fortification/100
守城特性 → ×1.15
断粮 → ×0.75
粮足 → ×1.10
每支援军 → +15% (上限+45%)
无守军 → 默认 10000 基础守军
```

**结局**: progress ≥ 100 → 城破，攻方入城，守方溃退

## 五、战略系统

### 5.1 国策 (national_focus.py)
- 三大类: 政治 / 军事 / 经济
- 每类每回合可推进国策点 = 1 + 条件奖励 (最高3点)
- 政治: 士族支持≥65 → +1; 民政主官能力≥85 → +1
- 军事: 总兵力≥40000 → +1; 军事主官能力≥85 → +1
- 经济: 民望≥65 → +1; 财政主官能力≥85 → +1

### 5.2 地区投资 (INVESTMENT_CATEGORIES)
```python
{"屯田粮仓", "城防守备", "军备练兵", "水军船政", "道路粮道", "民政市易"}
```
- 每郡同时只能推一项
- 每月消耗军资 2 点
- 每月进度 +25 (受国策 investment_speed_pct 加成)
- 100进度完成 → 触发效果:
  - 屯田粮仓: grain_output ×1.10, grain_stock +50
  - 城防守备: fortification +10
  - 军备练兵: 本站 training +5
  - 水军船政: shipbuilding +15
  - 道路粮道: transport +10
  - 民政市易: commerce_tax +2, public_support +5

### 5.3 外交系统 (diplomacy.py)

**六维外交关系**:
- public_relation (-100 ~ 100)
- trust (0 ~ 100)
- military_coordination (0 ~ 100)
- obligations (JSON 列表)
- territorial_claims (JSON)
- marriage_hostages (JSON)

**盟约接受率**:
```python
chance = clamp(40 + public_relation*0.20 + trust*0.20 + envoy_modifier, 5, 95)
```

**违约惩罚** (breach_treaty):
- trust -30
- public_relation -15
- military_coordination -25
- 若触发战争 → 刘备方: 名分-10, 士族支持-8
- 被违约方: 名分+2, 士族支持-2
- 婚姻状态 → broken

**战争漂移** (每月):
- public_relation -2 (下限-100)
- trust -1 (下限0)
- military_coordination → 0

### 5.4 政权阶段 (government.py)
```python
STAGES = ("流亡军", "荆州立足", "益州治蜀", "汉中王", "称帝后")
```
由实际控制区域自动推导。

### 5.5 身份进位 (identity.py)
- 汉中王: 需控制成都 + 益州核心 + 名分≥80 + 口碑≥60
- 称帝: 需已为汉中王 + 名分≥85 + 口碑≥70
- 条件不满足 → severity 级天下压力 → 名分/士族支持/军心下降

## 六、经济/补给系统

### 6.1 省级财政 (flows.calc_province_fiscal)
```
田赋 = 官民田万亩 × 田赋亩率(毫/亩/年) / 10000 / 12
辽饷 = 官民田万亩 × 辽饷亩率(毫/亩/年) / 10000 / 12
盐税 = 账面月额
商税 = 账面月额
```

**综合到账率**:
```python
eff = 1.0
  - gentry_resistance/100 * 0.55
  - corruption/100 * 0.45
  - max(0, unrest-20)/100 * 0.30
eff = clamp(eff, 0.05, 1.00)
```
辽饷额外受皇威折扣: `liao_eff = eff * (0.5 + 皇威/200)`

**皇庄 → 内库**: `huang_tian × 皇庄亩率 / 10000 / 12` (不吃 eff 折扣)

### 6.2 军饷发放
- 按 ARMY_SALARY_PRIORITY 顺序
- 当月足额 → 不扣欠饷
- 不足 → 欠饷累积: arrears += shortfall
- 欠饷 → 士气惩罚: `morale -= max(1, round(8 * shortfall / needed))`
- 长期足额且无旧欠 → morale +2

### 6.3 粮食系统
- **月耗**: `ceil(manpower / 1000)` 万石
- **年度结算** (12月): grain_stock += grain_output - population × 人均年耗粮
- **人均年耗粮**: 默认 3 万石/万人 (可配)
- **缺粮** → 人口饥荒惩罚

### 6.4 人口增长 (12月)
```
base_rate = 8‰/年
民心>60 → +4‰
民心<40 → -4‰
动乱>50 → -6‰
缺粮    → -10‰
```

### 6.5 补给系统 (supply.py)
**补给来源优先级**:
1. 可达友方郡仓 → 扣郡仓 grain_stock
2. 消耗携粮 → supply -= 20
3. 断粮 → starvation_turns += 1

**断粮阶梯惩罚**:
| 断粮月数 | 效果 |
|----------|------|
| 1月 | morale -8 |
| 2月 | fatigue +12 |
| 3月+ | 2%兵力逃散, combat_multiplier = 0.65 |

## 七、事件系统

### 7.1 Issue 系统 (issues.py, 2277 行)
- **立项**: seed_events 触发门槛 → trigger_gate DSL → auto_trigger
- **推进**: inertia 每月漂移 bar_value
- **结案**: bar 满 → resolve_condition 满足 → effect_on_resolve
- **失败**: bar 归零 → fail_condition → effect_on_fail
- **结案效果**: metric_delta / economy_moves / region_delta / army_delta 等

### 7.2 历史事件卡 (historical_events.py)

**生命周期**:
```
scheduled → eligible → (adapted) → resolved
           → superseded (硬前提失效)
           → expired (窗口已过)
```

**触发条件**:
- trigger_year / trigger_month: 历史锚定
- trigger_end_year / trigger_end_month: 窗口截止
- hard_conditions: 势力存续等硬前提
- roles: 角色候补 (primary + alternates)
- variants: 可改写结果列表

### 7.3 随机事件 (random_events.py)
- 8 个预定义模板 (蝗灾/风调雨顺/流民/军马交易/盗匪/水患/士族请愿/商队)
- 第二阶段由 world_simulation 生成区域事件接管
- 3 回合未处理 → 自动过期

## 八、结局系统 (context.victory_status)

### 八态结局
| 结局标识 | 触发条件 |
|----------|----------|
| liu_bei_dead | 刘备 status=dead (非史实卒) |
| historical_baidi | 223年4月后 + 刘备史实卒 (白帝/历史卒) |
| yizhou_core_fallen | 214年后丢失成都 + 江州永安不保 / 危机≥3月 |
| regime_collapsed | 无领土 + 兵力<3000 持续3月 |
| unified_victory | 天下郡国尽归刘备 + 无其他势力现役军 |
| three_kingdoms | 223年后: 益州+荆州在握 + ≥2外部强权 + 民望军心≥45 |
| yizhou_guardian | 223年后: 益州在握 + 荆州不在 + 民望军心≥45 |
| rewritten_223 | 223年后: 其他未统一结局 |

**国史评分**:
```
统一 = 领土占比 × 100
名分 = state.metrics["名分"]
民生 = (public_support + 民望) / 2
将相 = 在朝臣平均 (ability+loyalty+integrity+politics+leadership)/5
外交 = 双边关系均值
军功 = 领土×45 + 兵力占比×30 + 胜率×25
```
**评级**: ≥85 兴复之功 / ≥65 建基之业 / ≥45 守成未就 / <45 大业中衰

## 九、AI 系统 (power_ai.py)

### 候选行动生成
```python
MILITARY_TYPES = {"move", "attack", "siege", "fortify", "resupply"}
DIPLOMACY_TYPES = {"declare_war", "seek_peace", "intrigue", "propose_alliance"}
```

**评分公式示例**:
- fortify: `24 + (55-morale)*0.6 + (35-supply)*0.4`
- resupply: `45 + (70-supply)*1.2` (supply<70 时)
- attack: `35 + ratio*12 + (supply-40)*0.15 + (morale-50)*0.15`, 险路 -12
- siege: `42 + manpower/1000 min25 + (supply-50)*0.1`
- seek_peace: `58 + (45-military_strength) + (35-supply)` (军力<45/补给<35/凝聚<40)
- declare_war: `35 + |public_relation|*0.35 + military*0.12` (public≤-40)
- propose_alliance: `25 + public*0.2 + trust*0.2` (public≥45, trust≥40)

### 行动上限
- 每月每势力最多 2 槽 (由 power_budgets 控制)
- 第二槽仅限防御/补给/外交 (不含 attack/siege/declare_war)
- 每月每势力最多 1 次进攻行动 (attack/siege/declare_war)
- 第二槽去重: 不得复用第一槽的 army_id/target_node/target_power

### 裁决包协议 (adjudication.py)
- 统一协议版本 = 1
- AI 只产候选叙事，不能直接改世界
- 所有输出须过 validate_ai_proposal 结构化校验
- COMMON_FORBIDDEN: unlisted_death / spawn_army / territory_change / ignore_supply / revive_character
