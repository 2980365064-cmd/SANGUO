import type {
  ApiErrorDetail,
  ActionIntent,
  BattlePreview,
  CourtChatMessage,
  DialogueResponse,
  GameState,
  EnvoyMission,
  LlmConfigPayload,
  LlmConfigSummary,
  MenuStatus,
  MonthAgendaItem,
  MonthlyReport,
  OngoingPlan,
  GovernmentOfficeEffect,
  ReputationSummary,
  RegionDetail,
  AdministrativeDetail,
  AdministrativeScope,
  StrategyEvent,
} from "./types";

declare global {
  interface Window { SANGUO_API_BASE?: string; }
}

export class ApiRequestError extends Error {
  detail: ApiErrorDetail;
  constructor(detail: ApiErrorDetail, fallback: string) {
    super(detail.message || detail.detail || fallback);
    this.detail = detail;
  }
}

const normalizeApiBase = (value: string) => value.trim().replace(/\/+$/, "");

export const apiBase = () => {
  const params = new URLSearchParams(window.location.search);
  return normalizeApiBase(
    params.get("api") || params.get("api_base") || window.SANGUO_API_BASE || import.meta.env.VITE_API_BASE || "",
  );
};

export const apiUrl = (path: string) => {
  if (/^https?:\/\//i.test(path)) return path;
  const base = apiBase();
  return base ? `${base}${path.startsWith("/") ? path : `/${path}`}` : path;
};

export const api = async <T,>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const raw = payload?.detail ?? payload;
    const detail: ApiErrorDetail = typeof raw === "object" ? raw : { message: String(raw) };
    throw new ApiRequestError(detail, response.statusText);
  }
  return response.json() as Promise<T>;
};

export const getState = () => api<GameState>("/api/game/state");
export const getMenuStatus = () => api<MenuStatus>("/api/menu/status");
export const newGame = () => api<{ state: GameState }>("/api/menu/new_game", { method: "POST" });
export const continueGame = () => api<{ state: GameState }>("/api/menu/continue", { method: "POST" });

export type GameSettings = Record<string, string | number> & { world_reaction_intensity: "restrained" | "standard" | "stormy" };
export const getGameSettings = () => api<{ game_settings: GameSettings }>("/api/menu/game_settings");
export const saveGameSettings = (payload: GameSettings) => api<{ ok: boolean; game_settings: GameSettings }>("/api/menu/game_settings", {
  method: "POST", body: JSON.stringify(payload),
});

export const resolveMajorReaction = (reactionId: number, choice: string) =>
  api<{ ok: boolean; reaction: { id: number; status: string; choice: string; outcome_summary: string } }>(
    `/api/reactions/${reactionId}/decision`, { method: "POST", body: JSON.stringify({ choice }) },
  );

export type ReactionEvent = {
  id: number; turn: number; batch_id: number; actor: string; target: string; reaction_level: string;
  reaction_kind: string; status: string; outcome_summary: string; rule_facts_snapshot: Record<string, unknown>;
  applied_effects: Array<Record<string, unknown>>;
};
export const getReactions = (params: { character?: string; target?: string; directive_type?: string; limit?: number } = {}) => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value) query.set(key, String(value)); });
  return api<{ reactions: ReactionEvent[] }>(`/api/reactions${query.size ? `?${query}` : ""}`);
};

export type HistoricalEventCard = { id: string; title: string; window: string; status: string; participants: Record<string, string>; variant_id: string; reason: string; changed_turn: number; resolved_turn: number; required_powers: string[]; required_regions: string[]; alternative_roles: Record<string, string[]> };
export const getHistoricalEventCards = () => api<{ events: HistoricalEventCard[] }>('/api/history/events');

export const submitBatchDecision = (batchId: number, draftId: number, choice: string) =>
  api<{ message: string; batch_id: number; choice: string }>(`/api/directive-batches/${batchId}/decisions`, {
    method: "POST", body: JSON.stringify({ draft_id: draftId, choice }),
  });

export const saveMenuLlmConfig = async (payload: LlmConfigPayload) =>
  (await api<{ ok: boolean; llm: LlmConfigSummary }>("/api/menu/llm", {
    method: "POST",
    body: JSON.stringify(payload),
  })).llm;

export const getGameLlmConfig = () => api<LlmConfigSummary>("/api/llm/config");

export const saveGameLlmConfig = (payload: LlmConfigPayload) =>
  api<LlmConfigSummary>("/api/llm/config", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const previewBattle = (attackerIds: string[], defenderIds: string[], nodeId: string) =>
  api<BattlePreview>("/api/battles/preview", {
    method: "POST",
    body: JSON.stringify({ attacker_ids: attackerIds, defender_ids: defenderIds, node_id: nodeId }),
  });

/**
 * 旧面板尚在源码中以便迁移，但不能再向服务器提交即时世界修改。
 * 保留同名导出只为让历史组件编译；任何调用都会在浏览器端明确失败。
 */
const legacyDirectWriteDisabled = <T,>(message: string): Promise<T> =>
  Promise.reject(new Error(`该入口已弃用：${message} 请先拟入方略并颁令。`));

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const submitArmyOrder = (_armyId: string, _orderType: string, _payload: Record<string, unknown>) =>
  legacyDirectWriteDisabled<{ order_id: number; state: GameState }>("即时军队命令");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const startFocus = (_focusId: string) =>
  legacyDirectWriteDisabled<{ state: GameState }>("即时国策");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const startInvestment = (_regionId: string, _category: string) =>
  legacyDirectWriteDisabled<{ state: GameState }>("即时经营");

export const getRegionDetail = (regionId: string) =>
  api<RegionDetail>(`/api/regions/${encodeURIComponent(regionId)}/detail`);

export const getAdministrativeDetail = (scope: AdministrativeScope, entityId: string) =>
  api<AdministrativeDetail>(`/api/administrative/${scope}/${encodeURIComponent(entityId)}/detail`);

export const getGovernmentOffices = () =>
  api<{ offices: GovernmentOfficeEffect[] }>("/api/government/offices");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const appointGovernmentOffice = (_officeKey: string, _characterName: string, _targetId = "") =>
  legacyDirectWriteDisabled<{ office: GovernmentOfficeEffect; offices: GovernmentOfficeEffect[]; state: GameState }>("即时任命");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const resolveTurn = () =>
  legacyDirectWriteDisabled<{ state: GameState; report?: string; awaiting_decision?: boolean; decisions?: unknown[] }>("旧月末结算");

export const getMonthAgenda = () => api<{ items: MonthAgendaItem[] }>("/api/month_agenda");

export const getMonthlyReport = () => api<MonthlyReport>("/api/monthly-report");

export const getStrategyEvents = () => api<{ events: StrategyEvent[]; turn: object }>("/api/strategy-events");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const createActionIntent = (_text: string, _source = "自由命令") =>
  legacyDirectWriteDisabled<{ intent: ActionIntent }>("旧自由命令");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const confirmActionIntent = (_id: number) =>
  legacyDirectWriteDisabled<{ plan?: OngoingPlan; intent?: ActionIntent; result: Record<string, unknown> }>("旧行动意图确认");

export const getSuggestions = (status?: string) =>
  api<{ suggestions: Array<{ id: number; text: string; created_at: string; status: string; converted_to_intent_id?: number; source: string }> }>(
    `/api/suggestions${status ? `?status=${encodeURIComponent(status)}` : ""}`
  );

export const getCharactersList = (params?: { scope?: string; province?: string; role?: string; sort?: string; limit?: number }) => {
  const qs = new URLSearchParams();
  if (params?.scope) qs.set("scope", params.scope);
  if (params?.province) qs.set("province", params.province);
  if (params?.role) qs.set("role", params.role);
  if (params?.sort) qs.set("sort", params.sort);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return api<{ characters: Array<Record<string, unknown>> }>(`/api/characters${query ? `?${query}` : ""}`);
};

export const getProvinceSummary = (provinceName: string) =>
  api<{ province: string; nodes: Array<Record<string, unknown>>; governors: Array<Record<string, unknown>>; total_nodes: number }>(
    `/api/provinces/${encodeURIComponent(provinceName)}/summary`
  );

export const enterSecretChat = (characterName: string) =>
  api<{ character: string; secret_chat_active: boolean }>(
    `/api/characters/${encodeURIComponent(characterName)}/secret_chat/enter`,
    { method: "POST", body: JSON.stringify({}) }
  );

export const exitSecretChat = (characterName: string) =>
  api<{ character: string; secret_chat_active: boolean }>(
    `/api/characters/${encodeURIComponent(characterName)}/secret_chat/exit`,
    { method: "POST", body: JSON.stringify({}) }
  );

export const createSecretOrder = (characterName: string, payload: { title: string; content: string; tags?: string[]; deadline_months?: number }) =>
  api<{ order_id: number; character_name: string; title: string; status: string }>(
    `/api/characters/${encodeURIComponent(characterName)}/secret-order`,
    { method: "POST", body: JSON.stringify(payload) }
  );

export const createSuggestion = (text: string, source = "") =>
  api<{ suggestion: { id: number; text: string; created_at: string; status: string } }>("/api/suggestions", {
    method: "POST",
    body: JSON.stringify({ text, source }),
  });

export const deleteSuggestion = (id: number) =>
  api<{ deleted: boolean; id: number }>(`/api/suggestions/${id}`, { method: "DELETE" });

/** @deprecated 仅用于旧组件兼容，建议必须先拟入方略。 */
export const convertSuggestionToOrder = (_id: number) =>
  legacyDirectWriteDisabled<{ suggestion: { id: number; status: string; converted_to_intent_id: number }; intent: Record<string, unknown> }>("旧建议转行动意图");

export const getOngoingPlans = () => api<{ plans: OngoingPlan[] }>("/api/ongoing_plans");

export const updateOngoingPlan = (id: number, payload: Partial<Pick<OngoingPlan, "status" | "assignee" | "last_result" | "next_check_turn" | "progress">>) =>
  api<{ plan: OngoingPlan }>(`/api/ongoing_plans/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });


export const getEnvoyMissions = () => api<{ missions: EnvoyMission[] }>("/api/envoys");

/** @deprecated 仅用于旧组件兼容，不能修改世界。 */
export const createEnvoyMission = (_payload: { target_power: string; envoy: string; goal: string; boundaries: string }) =>
  legacyDirectWriteDisabled<{ mission: EnvoyMission }>("即时派遣使臣");

export const getReputation = () => api<{ summary: ReputationSummary }>("/api/reputation");

export const getDialogue = (name: string) =>
  api<DialogueResponse>(`/api/characters/${encodeURIComponent(name)}/dialogue`);

const parseSse = (block: string) => {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length ? { event, data: JSON.parse(data.join("\n")) } : null;
};

export const streamDialogue = async (
  name: string,
  message: string,
  onDelta: (text: string) => void,
  mode: "open" | "secret" = "open",
): Promise<DialogueResponse> => {
  const response = await fetch(apiUrl(`/api/characters/${encodeURIComponent(name)}/dialogue/stream`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiRequestError({ message: String(payload.detail || response.statusText) }, response.statusText);
  }
  if (!response.body) throw new Error("浏览器不支持流式对话。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const parsed = parseSse(block);
      if (!parsed) continue;
      if (parsed.event === "delta") onDelta(String(parsed.data.content || ""));
      if (parsed.event === "done") return parsed.data as DialogueResponse;
      if (parsed.event === "error") throw new Error(String(parsed.data.message || "对话失败"));
    }
    if (done) break;
  }
  throw new Error("对话中断。");
};

export const streamCourtChat = async (
  message: string,
  ministers: string[],
  onEvent: (event: { type: string; message?: CourtChatMessage; speaker?: string; content?: string; options?: string[] }) => void,
): Promise<{ history?: CourtChatMessage[] }> => {
  const response = await fetch(apiUrl("/api/court_chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, ministers }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiRequestError({ message: String(payload.detail || response.statusText) }, response.statusText);
  }
  if (!response.body) throw new Error("浏览器不支持流式廷议。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const parsed = parseSse(block);
      if (!parsed) continue;
      if (parsed.event === "speaker") onEvent({ type: "speaker", speaker: String(parsed.data.speaker || "") });
      if (parsed.event === "delta") onEvent({ type: "delta", speaker: String(parsed.data.speaker || ""), content: String(parsed.data.content || "") });
      if (parsed.event === "reply") onEvent({ type: "reply", message: parsed.data as CourtChatMessage });
      if (parsed.event === "conclusion") onEvent({ type: "conclusion", message: parsed.data as CourtChatMessage, options: (parsed.data.options || []) as string[] });
      if (parsed.event === "done") return parsed.data as { history?: CourtChatMessage[] };
      if (parsed.event === "error") throw new Error(String(parsed.data.message || "廷议失败"));
    }
    if (done) break;
  }
  return {};
};
