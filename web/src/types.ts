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
  investment: null | Record<string, unknown>;
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
  metrics: Record<"军资" | "粮秣" | "民望" | "名分" | "军心" | "士族支持", number>;
  previous_summary: string;
  map: { nodes: StrategicNode[]; routes: StrategicRoute[] };
  armies: Army[];
  army_orders: ArmyOrder[];
  sieges: Array<Record<string, unknown>>;
  battles: Array<Record<string, unknown>>;
  diplomacy: {
    relations: Array<Record<string, unknown>>;
    treaties: Array<Record<string, unknown>>;
  };
  national_focus: {
    definitions: Record<string, FocusDefinition>;
    progress: FocusProgress[];
    effects: Array<Record<string, unknown>>;
    points_per_turn: Record<string, number>;
  };
  region_investments: Array<Record<string, unknown>>;
  timeline: TimelineItem[];
  characters: Character[];
  offices: Array<Record<string, unknown>>;
  families: Array<Record<string, unknown>>;
  powers: Power[];
  victory_status: Record<string, unknown>;
  ending: null | { status: string; label: string; summary: string; timeline: unknown[] };
  structured_directives: unknown[];
  pending_count: number;
  pending_decisions: unknown[];
  last_decree: string;
  last_report: string;
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

export type ReputationSummary = {
  score: number;
  recent: Array<Record<string, unknown>>;
};

export type SteamEvent = { type: string; [key: string]: unknown };
