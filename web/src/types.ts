export type IntelRange = { min: number; max: number };
export type IntelValue = number | string | IntelRange;

export type IntelBlock = {
  visibility: "exact" | "assessment" | "range" | "tendency";
  values: Record<string, IntelValue>;
};

export type Turn = {
  year: number;
  period: number;
  turn: number;
  phase: string;
};

export type Government = {
  stage: string;
  title: string;
  scene: string;
};

export type StrategicNode = {
  id: string;
  commandery_id?: string;
  city_id?: string;
  province_id?: string;
  name: string;
  province: string;
  x: number;
  y: number;
  controller: string;
  public_support: number;
  unrest: number;
  military_pressure: number;
  population: number;
  status: string;
  stationed_army_ids: string[];
  is_capital?: boolean;  // 是否州治/首都
};

export type StrategicCity = {
  id: string;
  name: string;
  commandery_id: string;
  province_id: string;
  province: string;
  x: number;
  y: number;
  controller: string;
  strategic_role: string;
  is_commandery_capital: boolean;
  fortification: number;
  grain_stock: number;
  siege_status: string;
  population: number;
  public_support: number;
  unrest: number;
  military_pressure: number;
  status: string;
  stationed_army_ids: string[];
};

export type AdministrativeScope = "province" | "commandery" | "city";
export type AdministrativeDetail = {
  scope: AdministrativeScope;
  id: string;
  name: string;
  controlled_by: string;
  province_id?: string;
  commandery_id?: string;
  status: string;
  population?: number;
  public_support?: number;
  unrest?: number;
  military_pressure?: number;
  tax_per_turn?: number;
  fiscal?: Record<string, number | string | null>;
  gentry_resistance?: number;
  city?: { id: string; name: string; controlled_by: string; fortification: number; grain_stock: number } | null;
  cities?: Array<{ id: string; name: string; controlled_by: string; fortification: number; grain_stock: number; is_commandery_capital: number; strategic_role: string; siege_status: string }>;
  commanderies?: Array<{ id: string; name: string; controlled_by: string }>;
  commandery_count?: number;
  city_count?: number;
  transport?: number;
  mobilization?: number;
  security_coordination?: number;
  strategic_role?: string;
  order_score?: number;
  grain_stock?: number;
  market_capacity?: number;
  fortification?: number;
  garrison_capacity?: number;
  siege_status?: string;
  available_grain?: number;
  stationed_manpower?: number;
  summary?: string;
  risk_notes?: string[];
  recent_history?: Array<{ turn: number; kind: string; text: string }>;
  stationed_armies?: Army[];
};

// 城池节点 - 最小行政单位
export type CityNode = {
  id: string;           // 如 "chengdu"
  name: string;         // 如 "成都"
  province: string;     // 所属州，如 "益州"
  x: number;            // SVG 坐标 X
  y: number;            // SVG 坐标 Y
  controller: string;   // 控制势力 ID
  population: number;   // 人口
  military_strength: number; // 军力
  is_capital: boolean;  // 是否州治/首都
  stationed_army_ids: string[]; // 驻军 ID 列表
};

// 城池势力范围块
export type CityBlock = {
  city: string;
  d: string;            // 城池势力范围 SVG 路径
  cx: number;
  cy: number;
  node: CityNode;
};

export type StrategicRoute = {
  id: number;
  source: string;
  target: string;
  kind: "普通路" | "江河" | "山道" | "关隘" | string;
  note: string;
};

export type ArmyOrder = {
  id: number;
  army_id: string;
  turn: number;
  order_type: string;
  payload: Record<string, unknown>;
  status: string;
  result: Record<string, unknown>;
};

export type Army = {
  id: string;
  name: string;
  owner_power: string;
  station_node: string;
  commander: string;
  deputy_commander?: string;
  military_adjutant?: string;
  controller: string;
  theater: string;
  troop_type: string;
  troop_composition: Record<string, number>;
  manpower: number;
  supply: number;
  supply_turns: number;
  morale: number;
  training: number;
  equipment: number;
  mobility: number;
  loyalty: number;
  fatigue: number;
  experience: number;
  discipline: number;
  hazard_turns: number;
  hazard_combat_multiplier: number;
  hazard_mobility_multiplier: number;
  starvation_turns: number;
  supply_combat_multiplier: number;
  specialties: string[];
  status: string;
  current_order: ArmyOrder | null;
  military_record?: { rank: string; merit: number; recent_merits: Array<{ delta: number; source: string }> };
};

export type RegionDetail = {
  id: string;
  name: string;
  kind: string;
  controlled_by: string;
  can_invest: boolean;
  population: number;
  public_support: number;
  unrest: number;
  military_pressure: number;
  gentry_resistance: number;
  tax_per_turn: number;
  status: string;
  natural_disaster: string;
  human_disaster: string;
  fiscal: Record<string, number | string | null>;
  investment: null | InvestmentDetail;
  investment_logs: Array<Record<string, unknown>>;
  stationed_armies: Army[];
};

export type Character = {
  name: string;
  office: string;
  office_type: string;
  political_group: string;
  power_id: string;
  location: string;
  status: string;
  status_reason: string;
  core_tier: string;
  traits: string[];
  style: string;
  summary: string;
  portrait_id: string;
  abilities: IntelBlock;
  personality: IntelBlock;
  intel_level: number;
  favorite: boolean;
  loyalty_status: number;
  loyalty_recent: Array<{ delta: number; reason: string; turn: number }>;
};

export type GovernmentOfficeEffect = {
  office_key: string;
  name: string;
  character_name: string;
  target_id: string;
  vacant: boolean;
  efficiency: number;
  ability_field?: string;
  ability_value?: number;
  vacancy_penalty: number;
  action_blocked: boolean;
  effect: string;
};

export type Power = {
  id: string;
  name: string;
  kind: string;
  leader: string;
  stance: string;
  leverage: number;
  satisfaction: number;
  military_strength: number;
  cohesion: number;
  supply: number;
  agenda: string;
  status: string;
  last_action: string;
};

export type TimelineItem = {
  id: string;
  title: string;
  window: string;
  status: string;
};

export type FocusDefinition = {
  id?: string;
  name?: string;
  title?: string;
  category: "政治" | "军事" | "经济" | string;
  cost: number;
  description?: string;
  summary?: string;
  prerequisites?: string[];
  effects?: Record<string, unknown>;
};

export type FocusProgress = {
  focus_id: string;
  category: string;
  progress: number;
  status: string;
  started_turn: number;
};

export type BattlePreview = {
  node_id: string;
  attacker_ids: string[];
  defender_ids: string[];
  win_probability_range: [number, number];
  major_factors: string[];
  hard_scores: { attacker: number; defender: number };
  terrain: { kind: string; attacker_routes: string[] };
  duration_turns: number;
};

export type GameState = {
  scenario_id: "sanguo_liubei_208";
  turn: Turn;
  government: Government;
  long_term: {
    reputation: { score: number; recent: Array<{ id?: number; metric: string; delta: number; summary: string; turn?: number }> };
    factions: Array<{ faction_key: string; label: string; agenda: string; status: string; activated_turn: number; support: number }>;
    loyalty_risks: Array<{ name: string; loyalty: number }>;
    identity: string;
  };
  identity: {
    stage: string;
    next_stage: string;
    eligible: boolean;
    legitimacy: string;
    in_window: boolean;
    unmet_conditions: string[];
    available_action: string;
    political_pressure: string;
    external_pressure: number;
    consequence_preview: string[];
  };
  metrics: Record<"军资" | "粮秣" | "民望" | "名分" | "军心" | "士族支持", number>;
  previous_summary: string;
  map: { nodes: StrategicNode[]; cities?: StrategicCity[]; routes: StrategicRoute[] };
  armies: Army[];
  army_orders: ArmyOrder[];
  sieges: Siege[];
  battles: Battle[];
  diplomacy: {
    relations: DiplomaticRelation[];
    treaties: Treaty[];
  };
  national_focus: {
    definitions: Record<string, FocusDefinition>;
    progress: FocusProgress[];
    effects: FocusEffect[];
    points_per_turn: Record<string, number>;
  };
  region_investments: RegionInvestment[];
  timeline: TimelineItem[];
  characters: Character[];
  offices: Office[];
  families: Family[];
  powers: Power[];
  victory_status: VictoryStatus;
  ending: null | { status: string; label: string; summary: string; route: string; evidence: Array<Record<string, unknown>>; timeline: Array<Record<string, unknown>> };
  structured_directives: StructuredDirective[];
  pending_count: number;
  pending_decisions: PendingDecision[];
  last_decree: string;
  last_report: string;
  world: WorldState;
};

// === 第二阶段：区域局势类型 ===

export type RegionalVisibility = "own" | "rumor" | "assessment" | "confirmed";

export type RegionalState = {
  region_id: string;
  name: string;
  visibility: RegionalVisibility;
  road_condition: number | null;
  grain_transport_pressure: number | null;
  harvest_outlook: number | null;
  epidemic_pressure: number | null;
  public_mood_delta: number | null;
  incident_ids: number[];
};

export type RegionalIncident = {
  id: number;
  region_id: string;
  title: string;
  tier: "ordinary" | "dramatic";
  visibility: RegionalVisibility;
  summary: string;
  status: string;
  local_effects: Array<Record<string, unknown>>;
  policy_pending: boolean;
};

export type MinisterMemorial = {
  id: number;
  minister_name: string;
  memorial_kind: string;
  title: string;
  summary: string;
  subject_ref: string;
  risk_note: string;
  evidence_json: string;
  suggested_action_json: string;
  status: string;
};

export type ExternalIntelligence = {
  id: number;
  power_id: string;
  visibility: "rumor" | "assessment" | "confirmed";
  title: string;
  summary: string;
  source_type: string;
  reliability: number;
  verification_status: "unverified" | "confirmed" | "refuted" | "expired";
  valid_until_turn: number;
  resolution_summary: string;
  evidence_refs: string[];
  usable_as_fact: number;
};

export type WorldState = {
  campaign: {
    season: string;
    weather_summary: string;
    turn: number;
  };
  regions: RegionalState[];
  incidents: RegionalIncident[];
  memorials: MinisterMemorial[];
  intelligence: ExternalIntelligence[];
};

export type ApiErrorDetail = {
  code?: string;
  message?: string;
  detail?: string;
  provider_message?: string;
  status_code?: number;
};

export type LlmConfigSummary = {
  base_url: string;
  model: string;
  has_api_key: boolean;
  max_tokens: number;
  timeout_seconds: number;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  thinking_level: string;
  advanced_model: string;
  advanced_base_url: string;
  has_advanced_api_key: boolean;
  advanced_thinking_level: string;
  persisted?: LlmConfigSummary;
};

export type LlmConfigPayload = Omit<
  LlmConfigSummary,
  "has_api_key" | "has_advanced_api_key" | "persisted"
> & {
  api_key: string;
  advanced_api_key: string;
};

export type MenuStatus = {
  has_api_key: boolean;
  has_running_game: boolean;
  has_main_db: boolean;
  saves: Array<{ name: string; size: number; mtime: number }>;
  llm: LlmConfigSummary;
};

export type DialogueMessage = { role: "user" | "minister" | string; content: string };
export type DialogueResponse = {
  character?: Character;
  history: DialogueMessage[];
  answer?: string;
  suggestions?: Array<{ label: string; text: string }>;
};

export type CourtChatMessage = {
  role: "emperor" | "minister" | "conclusion" | string;
  speaker: string;
  content: string;
  options?: string[];
};

export type ExecutableActionDraft = {
  executable: boolean;
  action_type: string;
  title: string;
  assignee: string;
  target: string;
  duration_months: number;
  resources: Record<string, number>;
  constraints: string;
  risks: string[];
  reasons: string[];
  rewrite_suggestion: string;
  source: string;
};

export type ActionIntent = {
  id: number;
  turn: number;
  year: number;
  period: number;
  source: string;
  text: string;
  draft: ExecutableActionDraft;
  status: string;
};

export type OngoingPlanLog = {
  id: number;
  plan_id: number;
  turn: number;
  year: number;
  period: number;
  status: string;
  progress: number;
  narrative: string;
};

export type OngoingPlan = {
  id: number;
  origin_turn: number;
  title: string;
  action_type: string;
  assignee: string;
  target: string;
  duration_months: number;
  progress: number;
  resources: Record<string, unknown>;
  constraints: string[];
  risks: string[];
  status: string;
  last_result: string;
  next_check_turn: number;
  logs: OngoingPlanLog[];
};

export type MonthAgendaItem = {
  id: string;
  kind: string;
  title: string;
  summary: string;
  ref_id: number;
  entry: string;
  urgency: number;
};

export type EnvoyMission = {
  id: number;
  turn: number;
  target_power: string;
  envoy: string;
  goal: string;
  boundaries: string;
  status: string;
  result: string;
};

export type MonthlyReportAction = {
  entry: string;
  label: string;
};

export type MonthlyReportItem = {
  id: string;
  kind: string;
  title: string;
  summary: string;
  action: MonthlyReportAction;
  audit: Record<string, unknown>;
};

export type MonthlyReportSection = {
  id: "military" | "internal" | "diplomacy" | "personnel" | "secret" | "world" | "reputation" | string;
  title: string;
  summary: string;
  items: MonthlyReportItem[];
};

export type MonthlyReport = {
  turn: number;
  year: number;
  period: number;
  title: string;
  source_report: string;
  sections: MonthlyReportSection[];
};

export type StrategyEventSeverity = "urgent" | "important" | "suggestion" | "opportunity";

export type StrategyEvent = {
  id: string;
  title: string;
  summary: string;
  severity: StrategyEventSeverity;
  category: string;
  section_title: string;
  action_label: string;
  action_type: "court_chat" | "secret_chat" | "detail" | "decision" | "dismiss";
  action_entry: string;
};

export type ReputationSummary = {
  score: number;
  recent: Array<Record<string, unknown>>;
};

export type SteamEvent = { type: string; [key: string]: unknown };

// ---------- 补全类型：消除 Record<string, unknown> ----------

export type Siege = {
  id?: number | string;
  attacker?: string;
  defender?: string;
  target_node?: string;
  status?: string;
  start_turn?: number;
  end_turn?: number;
  result?: string;
  [key: string]: unknown;
};

export type Battle = {
  id?: number | string;
  attacker_power?: string;
  defender_power?: string;
  node?: string;
  status?: string;
  turn?: number;
  result?: string;
  [key: string]: unknown;
};

export type DiplomaticRelation = {
  power_a?: string;
  power_b?: string;
  relation_type?: string;
  trust?: number;
  tension?: number;
  [key: string]: unknown;
};

export type Treaty = {
  id?: number | string;
  parties?: string[];
  treaty_type?: string;
  status?: string;
  signed_turn?: number;
  expires_turn?: number;
  [key: string]: unknown;
};

export type FocusEffect = {
  focus_id?: string;
  label?: string;
  value?: string | number;
  [key: string]: unknown;
};

export type RegionInvestment = {
  id?: number | string;
  region?: string;
  category?: string;
  level?: number;
  progress?: number;
  [key: string]: unknown;
};

export type Office = {
  key?: string;
  name?: string;
  holder?: string;
  office_type?: string;
  efficiency?: number;
  [key: string]: unknown;
};

export type Family = {
  id?: string;
  name?: string;
  members?: string[];
  power_id?: string;
  [key: string]: unknown;
};

export type VictoryStatus = {
  status?: string;
  progress?: Record<string, number>;
  conditions?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type StructuredDirective = {
  id?: number | string;
  template_id?: string;
  text?: string;
  status?: string;
  [key: string]: unknown;
};

export type PendingDecision = {
  id?: number | string;
  kind?: string;
  title?: string;
  description?: string;
  options?: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type InvestmentDetail = {
  category?: string;
  progress?: number;
  level?: number;
  [key: string]: unknown;
};

// P0: 方略草案
export type DirectiveDraft = {
  id: number;
  turn: number;
  year: number;
  period: number;

  // 草案来源
  source_type: 'council_chat' | 'secret_chat' | 'map_detail' | 'manual' | 'suggestion';
  source_id?: number;

  // 结构化行动字段
  directive_type: 'internal' | 'military' | 'diplomatic' | 'other' | 'secret';
  title: string;
  assignee?: string;
  target?: string;
  duration_months: number;
  priority: number;

  // 资源与约束
  resources_json: string;
  constraints_json: string;
  risks_json: string;

  // 文书说明
  narrative_text: string;
  compiled_text: string;

  // 状态
  status: 'draft' | 'validated' | 'invalid' | 'issued' | 'rejected';
  validation_result_json: string;
  created_at: string;
  updated_at: string;
};

// P0: 颁令批次项目
export type DirectiveBatchItem = {
  id: number;
  batch_id: number;
  draft_id: number;
  execution_order: number;
  execution_status: 'pending' | 'success' | 'partial' | 'failed';
  execution_result_json: string;

  // 关联的草案信息（查询时填充）
  draft_title?: string;
  directive_type?: string;
  assignee?: string;
  target?: string;
};

// P0: 颁令批次
export type DirectiveBatch = {
  id: number;
  turn: number;
  year: number;
  period: number;

  batch_title: string;
  decree_text: string;
  total_drafts: number;

  status: 'pending' | 'issued' | 'executing' | 'completed' | 'failed';
  created_at: string;
  issued_at?: string;
  completed_at?: string;

  // 批次项目（查询时填充）
  items: DirectiveBatchItem[];
};
