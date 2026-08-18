# AI 活世界与随机性架构基线

> **状态：当前实现基线。**
>
> 任何涉及 AI、随机性、月度世界推演、区域事件、外势行动、人物反应、情报、战役环境或月报的任务，必须先完整阅读本文，再查看对应代码与测试。本文定义系统边界；若实现与本文冲突，先说明冲突并更新方案，不能另起平行机制。

> **同步义务：** 只要任务新增、修改、删除、弃用或修复本文范围内的规则，就必须在同一任务中更新本文。代码、数据库迁移、测试与本文不同步时，该任务不视为完成；若规则未变，也须在交付中明确声明“基线无需更新”。

## 1. 总原则

目标是建立一个**活的、可变化，但不凭空捏造**的三国世界。

- 硬规则决定死亡、领土、兵力、资源、条约、结局等世界事实。
- AI 只能在真实盘面与**数值边界**内判断、提议、叙事。AI 通过只读查询工具获取盘面数据后输出自由提案，由对应的 `_validate_free_xxx()` 校验器做边界裁剪和事实一致性检查（详见 §3.3、§3.6）。白名单快速通道已废弃。
- 所有随机结果必须可按存档与回合复现，并能显示来源和影响。
- 未确认的外部情报不能作为规则事实。
- 玩家只能通过"建议 → 草案 → 校验 → 颁令 → 结算"的行动合同改变世界；聊天、地图、面板均不得绕过该合同。

## 2. 架构分层与唯一入口

| 层 | 唯一/主要模块 | 职责 | 禁止事项 |
| --- | --- | --- | --- |
| 事实底座 | `ming_sim/db/`、规则结算模块 | 地区、军队、人物、资源、条约、历史事实 | AI 或叙事文本直接写世界事实 |
| 随机流 | `ming_sim/world_random.py` | `campaign_seed_v2`、派生种子、落库抽取、候选快照 | 新模块自行 `random.*`、未落库抽取 |
| 世界状态 | `ming_sim/world_simulation.py` | 月度环境、区域状态、事件、奏议、情报 | 直接改死亡、领土、条约、凭空生成军队 |
| 外势行动 | `ming_sim/power_ai.py` | 从合法候选中选择外势行动并走既有结算 | 新建平行 NPC 行动系统 |
| AI 裁决 | `ming_sim/adjudication.py` | 受限 AI 提案、验证、待核议、审计 | 让 AI 返回/执行直接世界写入字段 |
| 展示与审计 | `ming_sim/monthly_report.py`、`web_app.py`、`web/src/` | 情报过滤、月报、局势页、人类可读审计 | 向前端泄露内部风险或未确认情报 |

## 3. 已实现功能

### 3.0 州、郡、城三层行政事实

- `regions` 的 55 条记录定义为**郡级事实**；`content/administrative_units.json` 的 `cities` 是建安十三年城池名册唯一来源，当前经益州首轮、交州七郡及荆州八月断面校勘为 89 城。`administrative_cities` 按 `city_id` 保存城权、城防、仓储、市易、秩序、驻军容量、围城与静态辖区标识；`administrative_provinces` 保存州级转运、征发、治安协同与州域态势。历史校勘中的旧运行 `region id` 可因存档兼容而暂留，但其玩家可见名称、城池归属和郡界必须服从名册；未在当年独立设郡者不得显示为郡界。
- 城权是领土变化的唯一直接写入：围城仅在 `progress>=100` 后写目标 `administrative_cities.id` 的 `controlled_by`；`recompute_administrative_control()` 以辖城多数派生郡权，平手时由 `is_commandery_capital=1` 的郡治城裁定；州权在读取时由辖郡多数派生。AI 不得直接写州权、郡权、城权或辖区。
- 城池辖区是静态地图/交互事实：每个城池辖区必须以所属郡级手绘边界为母范围，按该郡真实城位作确定性无重叠分割，辖区并集恰好覆盖原郡界；它用于控制范围展示、围城目标与驻军归属，不拆分或重复计算郡级人口、田亩、粮产、赋税、国库。旧档新增城只从该郡原有可调余粮中按名册份额确定性划拨，旧治所的既有城权、围城和库存不覆盖，严禁随机补值。
- `settle_administrative_layers()` 是无随机的固定月度阶段：同步城池围城状态、汇总州域民情/军压、推导城→郡→州控制权，并写 `administrative_logs`。郡级生产、人口与区域事件仍由既有 `regions`、`regional_world_states`、`regional_incidents` 唯一结算入口处理。
- 该层不新增随机域；州与城的可见变化全部来自已审计的围城、驻军与郡级事实。补给先按固定顺序消耗辖城库存，再扣郡余粮；两者合计才是可调粮秣，故不重复计入郡税粮或国库汇总。

### 3.1 存档级确定性随机流

- `campaign_seed_v2`：新存档独立种子；旧档通过稳定材料迁移并持久化。
- `world_random_draws`：每次抽取以 `(turn, domain, subject_id, draw_kind)` 唯一落库。
- `draw_int()`：记录范围和结果；同键范围变化必须视为规则不兼容。
- `draw_weighted()`：记录候选快照和最终选择；候选不兼容（键变化、权重变化、快照缺失）返回 None 并写入结构化 audit_warning。
- 新增随机维度必须定义清晰的 `domain`、`subject_id`、`draw_kind`，并保存能解释该抽取的元数据。
- 全局世界上下文（天气、民情）与区域状态、区域事件共用同一 `campaign_seed_v2` 派生流；不同存档产生不同但可重放的全局环境。

### 3.2 区域连续状态与区域事件

- `regional_world_states`：地区每月天气、道路、粮运、收成、疫病、灾害风险、民情变动。
- `regional_incidents`：每月最多两项普通事件；重大事件由一次全局 35% 抽取决定，最多一项。
- 事件即时影响仅限道路、粮运、收成、民心、动乱、军压和有限的补给/灾害战斗修正。
- `effects_applied_at` 保证同一事件同一回合只生效一次；事件重试、读档或重复调用不得重复加减数值。
- 救灾、调兵、惩处、安抚、外交等战略应对必须进入方略/待议事项，不由事件直接完成。

### 3.2.1 外势内部动态

- `power_internal_dynamics`：每月最多三项非刘备势力的内部动态，同势力同月最多一条。
- 动态类型固定为五种：`court_rivalry`（凝聚≤55）、`supply_dispute`（补给≤45）、`command_dispute`（至少一项战争关系且凝聚≤70）、`local_elite_pressure`（控制区平均动乱≥55）、`court_consolidation`（凝聚∈[55,75]且补给≥50）。
- 候选权重由风险/条件强度决定，不使用 LLM。三个槽位分别使用 `domain="power_internal_dynamic"`、`subject_id="global_slot_1/2/3"`、`draw_kind="selection"`。
- 数值效果通过 `draw_int()` 在表列上限内生成，仅写入 `powers.cohesion`、`powers.supply` 与 `power_logs`。
- 不得改人物生死、兵力、军队、领土、条约或结局。
- `effects_applied_at` 幂等规则与 `regional_incidents` 相同。
- 每条动态保存生成前 `cohesion`、`supply`、战争关系、地区动乱等证据快照与随机引用。

### 3.3 战役环境与统一自由路径裁决

- `battle_environment()` 将季节、天气、地形与战场区域状态写入战役审计。
- 环境仅提供有上下限的概率/修正；战役最终事实仍由军令、兵力、补给、地形与战役规则结算。
- **战斗裁决统一走自由路径**（白名单基准路径已废弃）：
  - AI 基于裁决包事实评估玩家战术意图，输出有界修正（`delta` ∈ [-5, +15]）。
  - 不再限制 AI 只能从 `TACTIC_RULES` 的 6 种基准战术中选择；AI 可提出任意战术名称。
- 自由路径校验器 `_validate_free_tactic()` 执行以下检查：
  - `check_forbidden_fields()`：禁止 reinforcements、spawn_army、region_control 等世界修改字段
  - 禁止文本检查：BATTLE_FORBIDDEN_TEXT（援军、阵亡、割让、复活等）
  - delta 边界裁剪：[-5, +15]，无特性匹配时上限 +10，有特性匹配时上限 +15
  - actor 必须是参战攻方统帅
  - feasibility=impossible 退回正面交锋（delta=0）
  - 事实一致性检查（AI 声称的条件如"瘟疫"、"粮草不济"必须在盘面中存在）
- AI 不得指定胜负、伤亡、人物死亡或领土变化。
- 自由路径的裁决包包含 `regional_state`（区域状态数据）和 `defender_supply`（防守方补给数据），用于事实一致性检查。
- 同种子同输入产生相同的掷骰结果（确定性随机）。
- **军府编制与战功（v8）**：`armies.troop_composition` 的唯一规则目录为轻步、重步、弓弩、骑兵、突骑、水军、工兵；旧档四类编制仅作确定性归并，绝不改变兵力、补给或军械。战役硬规则按实际编制计算克制与地形适性，合计修正截断在 ±15%，伤亡以最大余数法按兵种分摊。
- **士气唯一结算器**：`ming_sim.military.morale_delta()` 只读取已结算的补给来源/断粮、欠饷、疲劳、战损率、胜败、军纪和已任命的副将/军司马，单次变化截断为 `[-25,+10]`。断粮保持既有每月 -8；所有影响合并为一条带原因的 `army_logs.morale` 审计记录。AI 仅能读取结果，不能提出或直接写士气事实。
- `character_military_records`、`military_merit_logs` 与 `army_lineage` 是军衔、战功和拆并谱系的审计事实。战功只从已结算战役/围城事实写入，并以来源唯一键防重复；不得由 AI、叙事或情报生成。
- 军府职务固定为主将、副将、军司马，军衔为裨将、校尉、中郎将、杂号将军、重号将军。任命、晋升、改名、调配、拆分、合并必须通过月度“军政”军令结算；AI 仅可读取已确认编制、战功与职务，对既有合法候选给出有界判断，禁止直接授官、改编、增兵或指定战果。

### 3.4 外部势力与人物主动性

- `power_ai.py` 通过 `available_power_actions()` 生成合法候选，`validate_power_action()` 校验，`resolve_power_ai_turn()` 执行。
- `power_ai_actions` 记录外势计划、状态、结果和审计信息；`action_slot` 支持每势力每月最多两槽行动。
- 第一槽允许所有合法候选；第二槽仅限防御/补给/外交类型（`fortify`、`resupply`、`move`、`seek_peace`、`propose_alliance`、`intrigue`），且不得复用第一槽的 `army_id`、`target_node`、`target_power`。
- 每势力每月最多一次进攻类行动（`attack`/`siege`/`declare_war`），跨槽合计。
- `power_budgets` 由 `get_or_create_world_context()` 计算：灭亡/停用 → 0；活跃且凝聚≥75、补给≥70 → 2；其他活跃 → 1。
- `minister_memorials` 基于区域事件、军队补给/疲劳、活跃议题和**确认**情报生成奏议；每月最多三条，同臣同月最多一条。
- 现有事件/章节记忆可以被检索；完整的”承诺/失信—人物长期关系—后续反应”闭环仍是后续工作，不能在新功能里私自另建记忆格式。

#### 3.4.1 奏议与记忆集成

- `build_monthly_memorials()` 的 `_compute_speaker_score()` 接入 `get_relevant_event_memories()` 计算”记忆情绪”维度（-15..15）。
- 奏议 `evidence_json` 中的 `memory_ids` 字段填充相关记忆 ID 列表，可从月报审计层追溯。
- 派系利益维度使用 `political_faction_states.support` 和 `agenda` 真实数据，不再硬编码。
- 新增 3 类奏议候选：
  - `memory_grievance`：近 5 回合负面记忆触发”旧事重提”
  - `loyalty_risk`：近 3 回合 |delta|≥5 的忠诚变动触发”察忠诚”
  - `faction_grievance`：派系支持度<40 时该派系代言人主动上言
- `can_write_memory_from_source()` 守卫：传闻（`verification_status != 'confirmed'`）不得写入记忆。
- 奏议必须有当前事实证据；记忆只影响”谁说、以何种态度说”，不得凭记忆虚构事件。

### 3.5 AI 裁决、情报与月报

- `adjudication.py` 的裁决包含真实事实、可选动作、数值上下限、证据来源与应用合同。
- AI 输出限制为：`choice`、`bounded_modifiers`、`reasoning`、`evidence_refs`、`narrative`。
  - 所有 9 个裁决系统统一走自由路径（白名单快速通道已废弃）。
  - AI 通过 `QueryToolKit` 的 24 个只读查询工具获取盘面真实数据，再输出自由提案。
  - 每个裁决类型有对应的 `_validate_free_xxx()` 校验器，执行边界裁剪 + 禁止字段/文本 + 事实一致性检查。
  - `check_forbidden_fields()` 是共享工具函数，阻止 AI 提案包含 reinforcements、spawn_army、region_control、kill_character 等世界修改字段。
  - 外交裁决统一走自由路径（`_validate_free_diplomacy()`）：
    - AI 基于裁决包事实评估外交意图，输出有界修正（`relation_delta` ∈ [-30, +30]，`trust_delta` ∈ [-20, +20]，`coordination_delta` ∈ [-20, +20]）。
    - 无使臣时 trust_delta 上限收紧为 +10
    - feasibility=impossible 退回标准外交（所有 delta=0）
    - 禁止文本检查（reasoning 和 narrative 都不能写领土割让/条约生效/援军等）
    - 事实一致性检查（AI 声称"共同敌人"必须有盘面战争关系支撑；声称"军力优势"必须 ratio > 1.0）
  - 外交裁决包扩展了 `power_balance`（军力对比）、`strategic_context`（共同敌人、战争态势）、`active_treaties`（活跃条约），为 AI 评估提供充分事实依据。
- 禁止字段包括：人物死亡、结局状态、生成军队、兵力突变、领土控制、条约直接生效、忽略补给、复活人物。
- 越权或无依据提案进入 `pending_adjudications`，不得落账。
- 自由战术的事实一致性检查：AI 在 `reasoning` 中声称的条件（如"瘟疫"、"粮草不济"）必须能在裁决包的 `regional_state` 或 `defender_supply` 中找到依据。
- `external_intelligence_reports` 按 `rumor / assessment / confirmed` 分层，带来源类型、可信度、核验状态和有效期。
- `POST /api/directive-drafts/polish` 仅可将玩家已写入的四类军令正文改写为可编辑的三国语境文书候选稿；它不读写世界状态、不创建草案/批次、不触发执行，也不得增添人物、地点、兵力、资源、条约或战果等事实。最终生效仍必须经过"草案 → 校验 → 批次 → 下达 → 分阶段执行"合同。

#### 3.5.1 情报来源与可信度

| 来源 | 条件 | 初始可见性 | 可信度 |
|---|---|---|---|
| `direct_contact` | 对刘备 attack/siege/declare_war | `confirmed` | 100 |
| `border_observer` | 行动与刘备控制区接壤 | `assessment` | 75 |
| `envoy` | 对该势力有活跃使者 | `assessment` | 85 |
| `merchant_network` | 非战争关系且相邻路线道路 > -20 | `rumor` | 45 |
| `system` | 旧档兼容 | 保留原值 | 50 |

#### 3.5.2 证伪与过期

- `merchant_network` 报告通过 `draw_int(domain="intelligence_report", draw_kind="interpretation")` 决定准确/夸大/误判。
- 误判只允许在同一势力的相邻地区/同类行动间误指，不得制造不存在的势力、军队、人物或领土。
- 后续真实行动与旧报告 `true_subject_ref` 一致 → 标记 `confirmed`。
- 后续真实行动与旧报告势力相同但 action_type 不同 → 标记 `refuted`。
- 超过 `valid_until_turn` 未处理 → 标记 `expired`。
- `usable_as_fact=1` 的唯一条件：`visibility="confirmed"` 且 `verification_status="confirmed"` 且未过期。

#### 3.5.3 玩家可见动态选择

- `select_player_visible_world_dynamics()` 每月常态 3–5 条。
- 排序优先级：直接威胁 > 已确认 > 接壤 > 使者 > 商旅。
- 直接攻击/围城/宣战不受上限影响。
- 普通动态上限：2 confirmed + 2 assessment + 1 rumor。
- 同势力同回合最多显示两条。
- 相同 `true_subject_ref` 只显示最新、可信度最高的一条。
- `true_subject_ref` 不得进入前端 DTO。
- “本月局势”和”每月总计”是统一的人类审计入口，展示结论、证据、环境/随机因素、AI 判断与规则变动，不展示原始 JSON。

#### 3.5.4 区域事件→情报/外交连锁

- `build_incident_intelligence_reports()`：区域事件发生在非刘备控制区时，按来源规则为刘备生成情报。
  - 重大事件（dramatic）：接壤 → `border_observer`（reliability=65）。
  - 普通事件（ordinary）：有活跃使者 → `envoy`（reliability=70）。
  - 重大事件 + 商旅网络条件 → `merchant_network`（reliability=40）。
  - 刘备控制区事件不生成外部情报。
  - 同一 `(incident_id, observing_power)` 最多一条报告（通过 `source_ref` 去重）。
- `generate_incident_diplomatic_reactions()`：区域重大事件触发外势外交反应。
  - 仅重大事件触发，每势力每月最多一条。
  - 灾害类（drought/flood/epidemic）→ `diplomacy_pressure`：`public_relation +3`。
  - 动乱类（bandit_surge/refugee_influx）且处于战争 → `opportunistic_posture`：`cohesion -2`。
  - 反应写入 `diplomacy_logs` / `power_logs` 审计。
- `apply_war_diplomatic_drift()`：战争状态下外交关系每月持续漂移。
  - 每对 `war` 关系：`public_relation -2`（下限 -100）、`trust -1`（下限 0）、`military_coordination` 归零。
  - 每对关系每月只漂移一次（按 `turn + power_a + power_b + reason` 去重）。
- **连锁边界**：
  - 连锁深度 = 1（区域事件 → 情报/反应，不再进一步触发）。
  - 不得改变 `controlled_by`、人物生死、军队存在、条约状态。
  - 所有连锁函数均幂等（读档重放不产生重复记录）。

#### 3.5.5 战果/违约→地缘反应（跨势力态势连锁）

- `collect_significant_battle_outcomes()`：收集本回合可引发外部反应的重大野战。
  - 只读取 `battles.status='resolved'` 且 `turn=current_turn`。
  - 重大判定：纸面劣势方获胜（`final_probability`<40 攻方胜或 >60 守方胜）、总兵力损失≥15%、任一方参战军队≥2。
  - `source_ref` = `battles:<id>`。
- `collect_significant_siege_outcomes()`：收集本回合可引发外部反应的重大围城。
  - 只读取 `sieges.status` 为终态（`conquered`/`failed`/`withdrawn`/`relief_defeat`）且 `last_turn=current_turn`。
  - 普通围城进度变化不触发。
  - `source_ref` = `sieges:<id>`。
- `collect_treaty_breach_outcomes()`：收集本回合可引发外部反应的条约违约。
  - 只读取 `diplomacy_treaties.status='breached'` 且 `end_turn=current_turn`。
  - 不从普通 `diplomacy_logs` 猜测违约。
  - `source_ref` = `treaties:<id>:breach:<turn>`。
- `generate_geopolitical_reactions()`：为重大外部事实生成第三方地缘反应。
  - 候选第三方：活跃势力、非直接双方、有观察路径（接壤/使者/商旅）。
  - 每来源最多两条反应；每势力每月最多一条；全局每月最多四条。
  - 反应类型由规则表确定，LLM 不参与选择：
    - 战果 → `opportunism`（败方关系差）、`balancing`（盟友受挫）、`caution`（双方均紧张）。
    - 违约 → `condemnation`（与违约方高信任）、`reassurance`（与受害方关系好）。
  - 严重度 1-3，由关系状态确定性决定。
  - `geopolitical_reactions` 表记录反应详情，`UNIQUE(turn, source_ref, actor_power_id, target_power_id, reaction_type)` 保证幂等。
- `apply_geopolitical_reaction_effects()`：一次性应用地缘反应的软效果。
  - `soft_effects_json` 仅允许 `public_relation_delta`（`[-4,+4]`）、`trust_delta`（`[-3,+3]`）、`military_coordination_delta`（`[-10,+10]`）。
  - `action_hint_json` 仅允许 `action_score_deltas`：每个候选 `delta` 在 `[-12,+12]`。
  - `effects_applied_at` 幂等守卫。
  - **严禁**写入 `controlled_by`、人物状态、军队数量/存在、条约 `status`、战役 `winner` 或结局字段。
- `_apply_geopolitical_hints()`：在 `available_power_actions()` 末尾叠加反应评分修正。
  - 仅修改既有合法候选的 `score`，不生成新候选类型。
  - 不突破第二槽限制，不绕过每势力每月一次进攻上限。
  - 匹配候选的 `factors.geopolitical_reaction_ids` 记录受影响的反应 ID。
  - 候选因资源/距离/条约校验被拒绝时，保留反应记录但不落地。
- `build_geopolitical_intelligence_reports()`：为地缘反应生成分层情报报告。
  - 复用既有 `record_external_intelligence()` 和来源优先级。
  - `source_ref` = `geopolitical_intel:<reaction_id>:<power_id>` 保证幂等。
  - 可见性规则：与事件势力接壤 → `border_observer`(75)；有使者 → `envoy`(85)；商旅网络 → `merchant_network`(45)；无观察路径 → 不生成。
- **连锁边界**：
  - 连锁深度 = 1（源事实 → 地缘反应/情报/既有候选评分，反应本身不得成为下一轮反应源）。
  - 未确认情报永远不能成为地缘反应的规则证据。
  - 本期不实现自动宣战、自动结盟、自动制裁、自动领土变更或多跳连锁。

### 3.6 统一自由路径校验器架构

所有 9 个裁决系统已统一走自由路径。白名单快速通道（`validate_ai_proposal`、`_validate_ai_choice`、`allowed_change_kinds`、`allowed_outcomes`）已废弃。

#### 校验器通用结构

每个 `_validate_free_xxx(pack, proposal)` 执行以下步骤：
1. **feasibility=impossible** → 返回安全默认值（delta=0 或最小行动）
2. **delta 字段裁剪**到 `FREE_xxx_BOUNDS` 定义的上下限
3. **`check_forbidden_fields()`** → 拒绝包含 `COMMON_FORBIDDEN_FIELDS` 的提案
4. **禁止文本检查** → reasoning 和 narrative 不能包含 `COMMON_FORBIDDEN_TEXT` + 模块特有禁止词
5. **事实一致性检查** → AI 声称的条件必须在裁决包 facts 中有依据
6. **返回校验结果字典**（包含 `outcome` 字段供下游使用）

#### 9 个校验器清单

| 模块 | 校验器 | 文件 | 边界常量 |
|------|--------|------|---------|
| 战斗 | `_validate_free_tactic()` | `battle.py` | delta ∈ [-5, +15] |
| 外交 | `_validate_free_diplomacy()` | `diplomacy.py` | relation ∈ [-30, +30], trust ∈ [-20, +20], coord ∈ [-20, +20] |
| 补给 | `_validate_free_supply()` | `supply.py` | supply_delta ∈ [-30, +30], morale ∈ [-15, +10], fatigue ∈ [-10, +15] |
| 围城 | `_validate_free_siege()` | `siege.py` | progress_delta ∈ [-10, +20], casualty_pct ∈ [0, 30] |
| 区域投资 | `_validate_free_region_investment()` | `national_focus.py` | progress_delta ∈ [-5, +15], cost_modifier ∈ [0.5, 1.5] |
| 密令 | `_validate_free_secret_order()` | `db/secret_orders.py` | progress_delta ∈ [-20, +30] |
| 人事 | `_validate_free_personnel()` | `government.py` | efficiency_delta ∈ [-10, +20] |
| 势力行动 | `_validate_free_power_action()` | `power_ai.py` | priority ∈ {low,normal,high}, risk ∈ {low,medium,high} |
| 世界事件 | `_validate_free_world_event()` | `historical_events.py` | urgency_delta ∈ [-5, +10] |

#### 共享工具

- **`check_forbidden_fields(proposal, *, extra=())`**（`adjudication.py`）：检查提案不含世界修改字段。`COMMON_FORBIDDEN_FIELDS` 包括 spawn_army、region_control、kill_character、reinforcements 等。各模块可通过 `extra` 参数扩展。
- **`COMMON_FORBIDDEN_TEXT`**（`adjudication.py`）：通用禁止文本标记（阵亡、援军、割让等），各模块可叠加模块特有禁止词。
- **`record_pending_adjudication()`**：越界提案记录到 `pending_adjudications` 表供人类审核，不得直接落账。

### 3.7 裁决性能优化

月末批处理 `run_monthly_adjudication_batch()` 已实现四层优化（预期 5-8x 整体加速）：

| 层级 | 机制 | 效果 |
|------|------|------|
| **P0: 并行批处理** | `ThreadPoolExecutor` + 独立 SQLite 连接 | 4-6x 加速 |
| **P1: 批次缓存** | `BatchQueryCache` 线程安全缓存，同批次共享 | 20-40% 查询减少 |
| **P2: N+1 消除** | JOIN 合并：army 4→1, character 2→1, power 2→1, diplomacy 4→3 | 50-75% DB 往返减少 |
| **P3: 上下文复用** | `_build_validation_context()` 结果注入 QueryToolKit 缓存 | 15-25% 冗余查询减少 |

**关键组件：**
- `BatchQueryCache`（`query_tools.py`）：线程安全 dict 缓存，`threading.Lock` 保护
- `preload_context()`（`query_tools.py`）：将校验上下文注入缓存
- `validation_context` 参数（`run_adjudication_with_tools()`）：传递预构建的上下文
- `ADJUDICATION_MAX_WORKERS` 环境变量：控制并行度（默认 4，上限 8）

**计时埋点：** 每个裁决结果附加 `_timing` 字段记录耗时，批处理 summary 包含 `_batch_timing_seconds`。

## 4. 当前月度执行顺序

```text
刷新长期状态
→ 确保存档随机种子
→ 生成区域状态
→ 生成区域事件
→ 一次性应用局部效果，重大事件创建待议事项
→ 区域事件→情报/外交反应连锁（build_incident_intelligence_reports, generate_incident_diplomatic_reactions）
→ 生成外势内部动态并一次性应用有限效果
→ 生成世界上下文、群臣奏议
→ 推进持续方略、使臣与既有战役计划
→ 外势从合法候选中行动（多槽）
→ 军令、补给、战役、围城、内政等硬规则结算
→ 已结算战役/围城写入军功并结算已下达的军政军令
→ 州、郡、城行政结算（城池围城/驻军 → 郡级既有生产与事件 → 州域统筹与控制权推导）
→ 提取重大战果与条约违约事实（collect_significant_*）
→ 生成并应用地缘反应（generate_geopolitical_reactions, apply_geopolitical_reaction_effects）
→ 生成地缘反应情报（build_geopolitical_intelligence_reports）
→ 受限 AI 裁决批处理
→ 生成情报报告（build_intelligence_reports_for_turn）
→ 核验与过期处理（resolve_intelligence_verification）
→ 战争状态→外交持续漂移（apply_war_diplomatic_drift）
→ 人物/天下反应、记忆、每月总计
```

阶段检查点只能暂停后续阶段，不能回滚或重写已结算事实。

## 5. 开发前检查清单

每个相关任务必须在设计和编码前逐项回答：

1. 该功能属于哪一层？是否能复用上表模块？
2. 它读取哪些数据库事实或已确认情报？证据引用格式是什么？
3. 是否需要随机？若需要，`domain / subject_id / draw_kind` 分别是什么？
4. 它可修改哪些字段？单回合、单事件、累计的数值上限是多少？
5. AI 的候选、权限、禁止字段和失败降级路径是什么？
6. 它的可见性是 `own / rumor / assessment / confirmed` 中哪一种？
7. 如何做到幂等、读档重放和审计？
8. 月报和本月局势如何向玩家解释结果？
9. 要新增哪些后端、迁移、合同、前端和回归测试？

若任一项无法回答，先停在设计阶段，不得直接实现。

## 6. 当前待收口事项（开发时必须注意）

1. **情报来源可继续深化。** 斥候、使者、接壤、俘虏、商旅等来源应统一产出分层情报，并注明可信度与有效期。
2. **连锁可继续扩展。** 当前连锁深度=1（区域事件→情报/外交反应、战果/违约→地缘反应）。后续可考虑：外交违约→连锁制裁、多跳地缘连锁（有界放开深度限制）。

## 7. 验收最低标准

- 固定存档种子下，重复结算得到相同抽取、环境、候选和事实结果。
- 不同存档只在声明的随机维度出现差异。
- 同一事件/行动重试不会重复写入或重复施加效果。
- AI 无法越权写死亡、领土、兵力、条约或结局。
- 无证据的奏议、情报、行动和叙事不能生成或必须进入待核议。
- 情报可见性在数据库、API、前端均保持隔离。
- 后端测试、迁移测试、前端合同测试和构建均通过；涉及新 UI 时另做浏览器可见性检查。

## 8. 相关文件索引

- `ming_sim/world_random.py`
- `ming_sim/world_simulation.py`
- `ming_sim/battle.py`
- `ming_sim/power_ai.py`
- `ming_sim/adjudication.py`
- `ming_sim/query_tools.py` — QueryToolKit + BatchQueryCache（P1/P2/P3 优化）
- `ming_sim/diplomacy.py`
- `ming_sim/session.py`
- `ming_sim/monthly_report.py`
- `ming_sim/db/schema.py`
- `web_app.py`
- `web/src/pages/SituationHub.tsx`
- `web/src/components/monthlyReportPanel.tsx`
- `tests/test_world_random.py`
- `tests/test_world_context_random.py`
- `tests/test_regional_world_simulation.py`
- `tests/test_regional_incidents.py`
- `tests/test_power_ai_slots.py`
- `tests/test_adjudication_perf.py` — 性能优化测试（缓存、N+1、并行）
- `tests/test_power_internal_dynamics.py`
- `tests/test_intelligence_network.py`
- `tests/test_memory_memorials.py`
- `tests/test_regional_diplomacy_chain.py`
- `tests/test_geopolitical_reactions.py`
- `ming_sim/supply.py` — 补给裁决（`_validate_free_supply`）
- `ming_sim/siege.py` — 围城裁决（`_validate_free_siege`）
- `ming_sim/national_focus.py` — 区域投资裁决（`_validate_free_region_investment`）
- `ming_sim/db/secret_orders.py` — 密令裁决（`_validate_free_secret_order`）
- `ming_sim/government.py` — 人事裁决（`_validate_free_personnel`）
- `ming_sim/historical_events.py` — 世界事件裁决（`_validate_free_world_event`）
- `ming_sim/query_tools.py` — QueryToolKit（24 个只读查询工具）
- `tests/test_free_supply_validation.py`
- `tests/test_free_siege_validation.py`
- `tests/test_free_region_investment_validation.py`
- `tests/test_free_secret_order_validation.py`
- `tests/test_free_personnel_validation.py`
- `tests/test_free_power_action_validation.py`
- `tests/test_free_world_event_validation.py`
- `tests/test_free_tactic_validation.py`
- `tests/test_free_diplomacy_validation.py`
