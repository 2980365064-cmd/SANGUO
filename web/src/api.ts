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

export const submitArmyOrder = (armyId: string, orderType: string, payload: Record<string, unknown>) =>
  api<{ order_id: number; state: GameState }>(`/api/armies/${encodeURIComponent(armyId)}/orders`, {
    method: "POST",
    body: JSON.stringify({ order_type: orderType, payload }),
  });

export const previewBattle = (attackerIds: string[], defenderIds: string[], nodeId: string) =>
  api<BattlePreview>("/api/battles/preview", {
    method: "POST",
    body: JSON.stringify({ attacker_ids: attackerIds, defender_ids: defenderIds, node_id: nodeId }),
  });

export const startFocus = (focusId: string) =>
  api<{ state: GameState }>("/api/national-focus/start", {
    method: "POST", body: JSON.stringify({ focus_id: focusId }),
  });

export const startInvestment = (regionId: string, category: string) =>
  api<{ state: GameState }>(`/api/regions/${encodeURIComponent(regionId)}/investment`, {
    method: "POST", body: JSON.stringify({ category }),
  });

export const getRegionDetail = (regionId: string) =>
  api<RegionDetail>(`/api/regions/${encodeURIComponent(regionId)}/detail`);

export const getGovernmentOffices = () =>
  api<{ offices: GovernmentOfficeEffect[] }>("/api/government/offices");

export const appointGovernmentOffice = (officeKey: string, characterName: string, targetId = "") =>
  api<{ office: GovernmentOfficeEffect; offices: GovernmentOfficeEffect[]; state: GameState }>(`/api/government/offices/${encodeURIComponent(officeKey)}/appoint`, {
    method: "POST",
    body: JSON.stringify({ character_name: characterName, target_id: targetId }),
  });

export const resolveTurn = () =>
  api<{ state: GameState; report?: string; awaiting_decision?: boolean; decisions?: unknown[] }>("/api/turn/resolve", {
    method: "POST", body: JSON.stringify({}),
  });

export const getMonthAgenda = () => api<{ items: MonthAgendaItem[] }>("/api/month_agenda");

export const getMonthlyReport = () => api<MonthlyReport>("/api/monthly-report");

export const createActionIntent = (text: string, source = "自由命令") =>
  api<{ intent: ActionIntent }>("/api/action_intents", {
    method: "POST",
    body: JSON.stringify({ text, source }),
  });

export const confirmActionIntent = (id: number) =>
  api<{ plan?: OngoingPlan; intent?: ActionIntent; result: Record<string, unknown> }>(`/api/action_intents/${id}/confirm`, {
    method: "POST",
    body: JSON.stringify({}),
  });

export const getOngoingPlans = () => api<{ plans: OngoingPlan[] }>("/api/ongoing_plans");

export const updateOngoingPlan = (id: number, payload: Partial<Pick<OngoingPlan, "status" | "assignee" | "last_result" | "next_check_turn" | "progress">>) =>
  api<{ plan: OngoingPlan }>(`/api/ongoing_plans/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const createEnvoyMission = (payload: { target_power: string; envoy: string; goal: string; boundaries: string }) =>
  api<{ mission: EnvoyMission }>("/api/envoys", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getEnvoyMissions = () => api<{ missions: EnvoyMission[] }>("/api/envoys");

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
): Promise<DialogueResponse> => {
  const response = await fetch(apiUrl(`/api/characters/${encodeURIComponent(name)}/dialogue/stream`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
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
