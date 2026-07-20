import React from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, BookOpen, Castle, ChevronRight, FolderOpen, Handshake, Home,
  Loader2, MessageCircle, Play, ScrollText, Send, Settings, SlidersHorizontal, Swords, UserRoundCog, Users, X,
} from "lucide-react";
import {
  ApiRequestError, confirmActionIntent, continueGame, createActionIntent, createEnvoyMission,
  getDialogue, getEnvoyMissions, getGameLlmConfig, getMenuStatus, getMonthAgenda, getMonthlyReport, getOngoingPlans,
  getReputation, getState, newGame, resolveTurn, startFocus, streamCourtChat, streamDialogue,
} from "./api";
import type {
  ActionIntent, Army, Character, CourtChatMessage, DialogueMessage, EnvoyMission,
  FocusDefinition, GameState, IntelValue, LlmConfigSummary, MonthAgendaItem, MonthlyReport, OngoingPlan, ReputationSummary,
} from "./types";
import { ApiConfigModal } from "./components/apiConfigModal";
import { ArmyCommandPanel } from "./components/armyCommandPanel";
import { FamilyPanel, HistoryPanel } from "./components/drawers";
import { HistoryTimeline } from "./components/historyTimeline";
import { MetricBar } from "./components/hud";
import { StrategicMap } from "./components/map";
import { MonthlyReportPanel } from "./components/monthlyReportPanel";
import { PersonnelOfficePanel } from "./components/personnelOfficePanel";
import { COMMAND_DOCK_ITEMS } from "./uiLogic";
import "./styles.css";

type Panel = "朝议" | "军令" | "任事" | "外交" | "国策" | "家族" | "史册";

const POWER_COLORS: Record<string, string> = {
  liu_bei: "#b88a3a", cao_cao: "#4c5661", sun_quan: "#2f7580",
  liu_qi: "#8d6d3d", liu_zhang: "#9d7047", zhang_lu: "#76815d",
  ma_han: "#7d5f78", gongsun_kang: "#5e7182", shi_xie: "#6f7c4c",
};

const PANEL_ICONS = { 朝议: Users, 军令: Swords, 任事: UserRoundCog, 外交: Handshake, 国策: BookOpen, 家族: Home, 史册: ScrollText } as const;

function panelSubtitle(panel: Panel) {
  return panel === "军令" ? "二十五军独立行止" : panel === "朝议" ? "知人、任事、察心" :
    panel === "任事" ? "职位、效率、换任" : panel === "国策" ? "三策并行，同类唯一" :
      panel === "外交" ? "盟可违，信义有价" : panel === "家族" ? "宗亲、联姻、继承" : "史势可改，因果留痕";
}

function errorText(error: unknown) {
  if (error instanceof ApiRequestError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function displayIntel(value: IntelValue) {
  if (typeof value === "object") return `${value.min}–${value.max}`;
  return String(value);
}

function powerName(state: GameState, powerId: string) {
  return state.powers.find((power) => power.id === powerId)?.name || powerId || "无主";
}

function MenuScreen({ onEnter }: { onEnter: (state: GameState) => void }) {
  const [status, setStatus] = React.useState<Awaited<ReturnType<typeof getMenuStatus>> | null>(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [configOpen, setConfigOpen] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [denseInk, setDenseInk] = React.useState(false);

  React.useEffect(() => { void getMenuStatus().then(setStatus).catch((e) => setError(errorText(e))); }, []);

  const enter = async (mode: "new" | "continue") => {
    setBusy(mode); setError("");
    try {
      const result = mode === "new" ? await newGame() : await continueGame();
      onEnter(result.state);
    } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };

  return <main className={`menu-screen ink-home ${denseInk ? "dense-ink" : "light-ink"}`}>
    <div className="ink-menu-wash" />
    <aside className="ink-side-menu" aria-label="游戏主菜单">
      <div className="ink-side-mark"><span>刘备传</span><i>汉</i></div>
      <nav>
        <button className="primary" type="button" onClick={() => void enter("new")} disabled={!!busy}>
          {busy === "new" ? <Loader2 className="spin" /> : <Play />}<span>新开游戏</span>
        </button>
        <button type="button" onClick={() => void enter("continue")} disabled={!!busy || !status?.has_main_db}>
          {busy === "continue" ? <Loader2 className="spin" /> : <FolderOpen />}<span>加载存档</span>
        </button>
        <button type="button" onClick={() => setConfigOpen(true)} disabled={!status || !!busy}>
          <Settings /><span>API配置</span>
        </button>
        <button type="button" onClick={() => setSettingsOpen((open) => !open)} disabled={!!busy}>
          <SlidersHorizontal /><span>设置</span>
        </button>
      </nav>
      <div className="ink-side-footer">
        <small>建安十三年</small>
        <strong>公元二〇八</strong>
      </div>
    </aside>
    {settingsOpen && <section className="menu-settings-panel" aria-label="设置">
      <header><span>设置</span><button type="button" aria-label="关闭设置" onClick={() => setSettingsOpen(false)}><X /></button></header>
      <label><input type="checkbox" checked={denseInk} onChange={(event) => setDenseInk(event.target.checked)} />水墨遮罩</label>
    </section>}
    <section className="ink-menu-caption" aria-label="当前局势">
      <p>曹军已据荆襄，江水连营。你无一郡之土，唯有未竟的汉室之志与身边可托生死之人。</p>
      {!status?.has_api_key && status && <small>尚未配置大模型</small>}
      {error && <strong>{error}</strong>}
    </section>
    {configOpen && status && <ApiConfigModal mode="menu" initial={status.llm} onClose={() => setConfigOpen(false)} onSaved={(saved) => {
      setStatus((current) => current ? { ...current, has_api_key: saved.has_api_key, llm: saved } : current);
    }} />}
  </main>;
}

function Portrait({ character }: { character: Character }) {
  const [failed, setFailed] = React.useState(false);
  const file = encodeURIComponent(character.portrait_id || character.name);
  return <div className={`portrait ${failed ? "portrait-fallback" : ""}`}>
    {!failed && <img src={`/portraits/sanguo/${file}.webp`} alt={`${character.name}立绘`} onError={() => setFailed(true)} />}
    {failed && <><span>{character.name.slice(0, 1)}</span><small>{character.name}</small></>}
    <i>{character.core_tier}</i>
  </div>;
}

function CharacterBook({ state, onDialogue }: { state: GameState; onDialogue: (c: Character) => void }) {
  const [mode, setMode] = React.useState<"council" | "private">("council");
  const [selected, setSelected] = React.useState("刘备");
  const [filter, setFilter] = React.useState("刘备");
  const liuBeiMinisters = state.characters.filter((character) => character.power_id === "liu_bei" && character.status === "active");
  const defaultCouncil = liuBeiMinisters.filter((character) => ["S", "1"].includes(character.core_tier)).slice(0, 5).map((character) => character.name);
  const [councilMinisters, setCouncilMinisters] = React.useState<string[]>(defaultCouncil);
  const [topic, setTopic] = React.useState("曹军南下，孙刘联盟与夏口防务如何取舍？");
  const [councilMessages, setCouncilMessages] = React.useState<CourtChatMessage[]>([]);
  const [liveSpeaker, setLiveSpeaker] = React.useState("");
  const [liveText, setLiveText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const list = state.characters.filter((character) => filter === "天下" || character.power_id === "liu_bei");
  const current = state.characters.find((character) => character.name === selected) || list[0];
  React.useEffect(() => {
    setCouncilMinisters((currentList) => currentList.length ? currentList : defaultCouncil);
  }, [defaultCouncil.join("|")]);
  const toggleMinister = (name: string) => {
    setCouncilMinisters((currentList) => currentList.includes(name) ? currentList.filter((item) => item !== name) : [...currentList, name]);
  };
  const startCouncil = async () => {
    const text = topic.trim();
    if (!text || busy) return;
    setBusy(true); setError(""); setLiveSpeaker(""); setLiveText("");
    setCouncilMessages([{ role: "emperor", speaker: "刘备", content: text }]);
    try {
      await streamCourtChat(text, councilMinisters, (event) => {
        if (event.type === "speaker") {
          setLiveSpeaker(event.speaker || "");
          setLiveText("");
        }
        if (event.type === "delta") {
          setLiveSpeaker(event.speaker || liveSpeaker);
          setLiveText((currentText) => currentText + (event.content || ""));
        }
        if (event.type === "reply" && event.message) {
          setCouncilMessages((currentMessages) => [...currentMessages, event.message!]);
          setLiveText("");
        }
        if (event.type === "conclusion" && event.message) {
          setCouncilMessages((currentMessages) => [...currentMessages, event.message!]);
          setLiveText("");
        }
      });
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <div className="character-book">
    <div className="book-toolbar">
      <button className={mode === "council" ? "active" : ""} onClick={() => setMode("council")}>群臣廷议</button>
      <button className={mode === "private" ? "active" : ""} onClick={() => setMode("private")}>私下召见</button>
    </div>
    {mode === "council" && <section className="council-board">
      <div className="council-ministers">
        {liuBeiMinisters.slice(0, 12).map((character) => <button key={character.name} className={councilMinisters.includes(character.name) ? "active" : ""} onClick={() => toggleMinister(character.name)}>
          <Portrait character={character} /><span>{character.name}</span><small>{character.office || character.political_group}</small>
        </button>)}
      </div>
      <div className="council-session">
        <header><span>军议议题</span><strong>军府方略</strong></header>
        <textarea value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="提出本月必须裁断的军政问题" />
        <button className="seal-button" onClick={() => void startCouncil()} disabled={busy || !topic.trim() || councilMinisters.length === 0}>{busy ? <Loader2 className="spin" /> : <Users />} 开始廷议</button>
        {error && <p className="inline-error">{error}</p>}
        <div className="council-history">
          {councilMessages.map((message, index) => <article key={index} className={message.role === "conclusion" ? "conclusion" : message.role === "emperor" ? "player" : ""}>
            <small>{message.speaker || (message.role === "emperor" ? "刘备" : "臣将")}</small>
            <p>{message.content}</p>
            {message.options?.length ? <ul>{message.options.map((option) => <li key={option}>{option}</li>)}</ul> : null}
          </article>)}
          {liveText && <article className="live"><small>{liveSpeaker || "臣将"}</small><p>{liveText}<i /></p></article>}
        </div>
      </div>
    </section>}
    {mode === "private" && <>
    <div className="book-toolbar private-toolbar">
      <button className={filter === "刘备" ? "active" : ""} onClick={() => setFilter("刘备")}>麾下</button>
      <button className={filter === "天下" ? "active" : ""} onClick={() => setFilter("天下")}>天下人物</button>
    </div>
    <div className="portrait-grid">
      {list.map((character) => <button key={character.name} className={current?.name === character.name ? "active" : ""} onClick={() => setSelected(character.name)}>
        <Portrait character={character} /><strong>{character.name}</strong><small>{character.office || character.political_group}</small>
      </button>)}
    </div>
    {current && <div className="character-dossier">
      <Portrait character={current} />
      <div className="character-heading"><span>{current.political_group} · 情报 {current.intel_level}</span><h3>{current.name}</h3><p>{current.office || current.style}</p><blockquote>{current.summary || `${current.political_group}，${current.style}`}</blockquote></div>
      <div className="ability-grid">{Object.entries(current.abilities.values).map(([name, value]) => <span key={name}>{name}<strong>{displayIntel(value)}</strong></span>)}</div>
      <div className="traits">{current.traits.map((trait) => <em key={trait}>{trait}</em>)}</div>
      <div className="personality-line">人格情报：{current.personality.visibility} · {Object.entries(current.personality.values).map(([k, v]) => `${k}${displayIntel(v)}`).join(" / ")}</div>
      {current.power_id === "liu_bei" && current.status === "active" && <button className="seal-button" onClick={() => onDialogue(current)}><MessageCircle /> 私下召见</button>}
    </div>}
    </>}
  </div>;
}

function FocusBook({ state, onState }: { state: GameState; onState: (s: GameState) => void }) {
  const [error, setError] = React.useState("");
  const progress = new Map(state.national_focus.progress.map((item) => [item.focus_id, item]));
  return <div className="focus-book">
    {(["政治", "军事", "经济"] as const).map((category) => <section key={category} className={`focus-column focus-${category}`}>
      <header><span>{category}</span><strong>+{state.national_focus.points_per_turn[category] || 0} 点 / 回合</strong></header>
      {Object.entries(state.national_focus.definitions).filter(([, value]) => value.category === category).map(([id, definition]: [string, FocusDefinition]) => {
        const row = progress.get(id); const value = row?.progress || 0;
        return <article key={id} className={row?.status === "completed" ? "completed" : ""}>
          <h3>{definition.name || definition.title || id}</h3>
          <p>{definition.summary || "完成后改变政权的长期能力与历史选择。"}</p>
          <div className="focus-progress"><i style={{ width: `${Math.min(100, value / definition.cost * 100)}%` }} /><span>{value}/{definition.cost}</span></div>
          <button disabled={row?.status === "active" || row?.status === "completed"} onClick={() => {
            setError(""); void startFocus(id).then((r) => onState(r.state)).catch((e) => setError(errorText(e)));
          }}>{row?.status === "completed" ? "已成" : row?.status === "active" ? "推行中" : "开始推行"}</button>
        </article>;
      })}
    </section>)}
    {error && <p className="inline-error">{error}</p>}
  </div>;
}

function WorldActionPanel({ compact, onOpenPanel }: { compact: boolean; onOpenPanel: (panel: Panel) => void }) {
  const [agenda, setAgenda] = React.useState<MonthAgendaItem[]>([]);
  const [plans, setPlans] = React.useState<OngoingPlan[]>([]);
  const [reputation, setReputation] = React.useState<ReputationSummary | null>(null);
  const [command, setCommand] = React.useState("让张飞率军平定江夏叛军，三个月内完成，不得滥杀百姓。");
  const [intent, setIntent] = React.useState<ActionIntent | null>(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const refresh = async () => {
    const [agendaPayload, plansPayload, reputationPayload] = await Promise.all([
      getMonthAgenda(),
      getOngoingPlans(),
      getReputation(),
    ]);
    setAgenda(agendaPayload.items || []);
    setPlans(plansPayload.plans || []);
    setReputation(reputationPayload.summary);
  };
  React.useEffect(() => {
    void refresh().catch((e) => setError(errorText(e)));
  }, []);
  const draft = async () => {
    const text = command.trim();
    if (!text || busy) return;
    setBusy("draft"); setError("");
    try {
      const payload = await createActionIntent(text);
      setIntent(payload.intent);
    } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  const confirm = async () => {
    if (!intent || busy) return;
    setBusy("confirm"); setError("");
    try {
      await confirmActionIntent(intent.id);
      setIntent(null);
      await refresh();
    } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };
  if (compact) {
    const primary = agenda[0];
    return <button
      className="world-action-panel world-action-panel-collapsed paper-panel"
      type="button"
      onClick={() => onOpenPanel(((primary?.entry || "朝议") as Panel))}
    >
      <span>本月要议</span>
      <strong>{primary?.title || "召群臣问策"}</strong>
    </button>;
  }
  return <section className="world-action-panel paper-panel">
    <header><span>本月要议</span><small>从问题进入裁断</small></header>
    <div className="agenda-strip">
      {agenda.map((item) => <button type="button" key={item.id} onClick={() => onOpenPanel((item.entry as Panel) || "朝议")}>
        <strong>{item.title}</strong><span>{item.kind} · 急 {item.urgency}</span><small>{item.summary}</small>
      </button>)}
    </div>
    <div className="free-command">
      <label>自由命令</label>
      <textarea value={command} onChange={(event) => setCommand(event.target.value)} />
      <button type="button" onClick={() => void draft()} disabled={busy === "draft" || !command.trim()}>{busy === "draft" ? <Loader2 className="spin" /> : <ScrollText />} 转为方略草案</button>
    </div>
    {intent && <article className={`action-draft ${intent.draft.executable ? "ok" : "blocked"}`}>
      <h3>{intent.draft.action_type}</h3>
      <p>{intent.draft.title}</p>
      <dl><div><dt>执行</dt><dd>{intent.draft.assignee || "未定"}</dd></div><div><dt>周期</dt><dd>{intent.draft.duration_months} 月</dd></div></dl>
      {intent.draft.risks.length ? <small>风险：{intent.draft.risks.join("、")}</small> : null}
      {!intent.draft.executable && <small>{intent.draft.reasons.join("；") || intent.draft.rewrite_suggestion}</small>}
      <button type="button" onClick={() => void confirm()} disabled={!intent.draft.executable || busy === "confirm"}>{busy === "confirm" ? <Loader2 className="spin" /> : <ChevronRight />} 确认入账</button>
    </article>}
    <div className="ongoing-ledger">
      <h3>持续方略</h3>
      {plans.length ? plans.slice(0, 4).map((plan) => <article key={plan.id}>
        <strong>{plan.title}</strong><span>{plan.status} · {plan.progress}% · {plan.assignee}</span>
        <small>{plan.last_result || "等待月末推进"}</small>
      </article>) : <p>暂无持续方略。</p>}
    </div>
    {reputation && <div className="reputation-chip"><span>仁义口碑</span><strong>{reputation.score}</strong></div>}
    {error && <p className="inline-error">{error}</p>}
  </section>;
}

function DiplomacyPanel({ state }: { state: GameState }) {
  const liuBeiMinisters = state.characters.filter((character) => character.power_id === "liu_bei" && character.status === "active");
  const foreignPowers = state.powers.filter((power) => power.id !== "liu_bei");
  const [targetPower, setTargetPower] = React.useState(foreignPowers[0]?.id || "sun_quan");
  const [envoy, setEnvoy] = React.useState("诸葛亮");
  const [goal, setGoal] = React.useState("续盟并借粮");
  const [boundaries, setBoundaries] = React.useState("不得割让江夏，不得背盟。");
  const [missions, setMissions] = React.useState<EnvoyMission[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    void getEnvoyMissions().then((payload) => setMissions(payload.missions || [])).catch((e) => setError(errorText(e)));
  }, []);
  const sendEnvoy = async () => {
    if (busy || !targetPower || !envoy || !goal.trim()) return;
    setBusy(true); setError("");
    try {
      const payload = await createEnvoyMission({ target_power: targetPower, envoy, goal, boundaries });
      setMissions((current) => [payload.mission, ...current]);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const relationFor = (id: string) => state.diplomacy.relations.find((r) =>
    (r.power_a === "liu_bei" && r.power_b === id) || (r.power_b === "liu_bei" && r.power_a === id));
  return <div className="diplomacy-panel">
    <section className="envoy-form">
      <h3>派遣使臣</h3>
      <select value={targetPower} onChange={(event) => setTargetPower(event.target.value)}>
        {foreignPowers.map((power) => <option key={power.id} value={power.id}>{power.name}</option>)}
      </select>
      <select value={envoy} onChange={(event) => setEnvoy(event.target.value)}>
        {liuBeiMinisters.map((character) => <option key={character.name} value={character.name}>{character.name}</option>)}
      </select>
      <input value={goal} onChange={(event) => setGoal(event.target.value)} />
      <textarea value={boundaries} onChange={(event) => setBoundaries(event.target.value)} />
      <button type="button" onClick={() => void sendEnvoy()} disabled={busy}>{busy ? <Loader2 className="spin" /> : <Handshake />} 派遣使臣</button>
      {error && <p className="inline-error">{error}</p>}
    </section>
    {foreignPowers.map((power) => {
      const relation = relationFor(power.id);
      return <article key={power.id}>
        <i style={{ background: POWER_COLORS[power.id] }} /><div><h3>{power.name}<small>{power.leader}</small></h3><p>{power.agenda}</p></div>
        <dl><div><dt>公开关系</dt><dd>{String(relation?.public_relation ?? "未建档")}</dd></div><div><dt>互信</dt><dd>{String(relation?.trust ?? "未建档")}</dd></div><div><dt>军力</dt><dd>{power.military_strength}</dd></div></dl>
      </article>;
    })}
    <section className="treaty-scroll"><h3>盟约与联姻</h3>{state.diplomacy.treaties.length ? state.diplomacy.treaties.map((treaty, index) => <p key={index}>{String(treaty.treaty_type)} · {String(treaty.status)}</p>) : <p>尚无正式盟约。</p>}</section>
    <section className="treaty-scroll"><h3>使臣在途</h3>{missions.length ? missions.map((mission) => <p key={mission.id}>{mission.envoy}赴{mission.target_power} · {mission.goal}</p>) : <p>尚无使臣任务。</p>}</section>
  </div>;
}

function ArmyPanel({ state, onSelect }: { state: GameState; onSelect: (army: Army) => void }) {
  return <div className="army-ledger">
    {state.armies.map((army) => <button key={army.id} onClick={() => onSelect(army)}>
      <i style={{ background: POWER_COLORS[army.owner_power] }} /><div><strong>{army.name}</strong><span>{army.commander} · {powerName(state, army.owner_power)}</span></div>
      <dl><span>兵 {army.manpower.toLocaleString()}</span><span>粮 {army.supply}</span><span>气 {army.morale}</span></dl>
      <small>{army.current_order ? `${army.current_order.order_type}已下` : army.status}</small><ChevronRight />
    </button>)}
  </div>;
}

function DialogueModal({ character, onClose }: { character: Character; onClose: () => void }) {
  const [messages, setMessages] = React.useState<DialogueMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [stream, setStream] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  React.useEffect(() => { void getDialogue(character.name).then((r) => setMessages(r.history || [])).catch((e) => setError(errorText(e))); }, [character.name]);
  const send = async () => {
    const text = input.trim(); if (!text || busy) return;
    setMessages((current) => [...current, { role: "user", content: text }]); setInput(""); setStream(""); setBusy(true); setError("");
    try {
      const response = await streamDialogue(character.name, text, (delta) => setStream((current) => current + delta));
      const answer = response.answer || "";
      setMessages((current) => [...current, { role: "minister", content: answer }]); setStream("");
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <div className="modal-backdrop" onMouseDown={onClose}><section className="dialogue-modal" onMouseDown={(e) => e.stopPropagation()}>
    <button className="close-button" onClick={onClose}><X /></button>
    <header><Portrait character={character} /><div><span>军帐召对</span><h2>{character.name}</h2><p>{character.office || character.political_group}</p></div></header>
    <div className="dialogue-history">
      {messages.map((message, index) => <p className={message.role === "user" ? "player" : "character"} key={index}><small>{message.role === "user" ? "刘备" : character.name}</small>{message.content}</p>)}
      {stream && <p className="character live"><small>{character.name}</small>{stream}<i /></p>}
    </div>
    {error && <p className="inline-error">{error}</p>}
    <footer><textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder={`与${character.name}商议军国大事……`} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} /><button onClick={() => void send()} disabled={busy}>{busy ? <Loader2 className="spin" /> : <Send />}</button></footer>
  </section></div>;
}

function GameScreen({ initial }: { initial: GameState }) {
  const [state, setState] = React.useState(initial);
  const [panel, setPanel] = React.useState<Panel>("军令");
  const [panelOpen, setPanelOpen] = React.useState(false);
  const [infoOpen, setInfoOpen] = React.useState(false);
  const [selectedNode, setSelectedNode] = React.useState(initial.map.nodes.find((n) => n.id === "jiangxia")?.id || initial.map.nodes[0]?.id || "");
  const [selectedArmy, setSelectedArmy] = React.useState("");
  const [dialogue, setDialogue] = React.useState<Character | null>(null);
  const [resolving, setResolving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [configOpen, setConfigOpen] = React.useState(false);
  const [configLoading, setConfigLoading] = React.useState(false);
  const [llmConfig, setLlmConfig] = React.useState<LlmConfigSummary | null>(null);
  const [monthlyReport, setMonthlyReport] = React.useState<MonthlyReport | null>(null);
  const [monthlyReportOpen, setMonthlyReportOpen] = React.useState(true);
  const node = state.map.nodes.find((item) => item.id === selectedNode) || state.map.nodes[0];

  React.useEffect(() => {
    void getMonthlyReport().then(setMonthlyReport).catch(() => setMonthlyReport(null));
  }, []);

  const resolve = async () => {
    setResolving(true); setError("");
    try {
      const result = await resolveTurn(); setState(result.state);
      const report = await getMonthlyReport();
      setMonthlyReport(report);
      setMonthlyReportOpen(true);
      if (result.awaiting_decision) setError("本月出现必须亲裁的决策点，决策界面将在后续阶段接入。");
    } catch (e) { setError(errorText(e)); } finally { setResolving(false); }
  };

  const openConfig = async () => {
    if (configLoading) return;
    setConfigLoading(true); setError("");
    try {
      setLlmConfig(await getGameLlmConfig());
      setConfigOpen(true);
    } catch (e) { setError(errorText(e)); } finally { setConfigLoading(false); }
  };

  const openPanel = (next: Panel) => { setPanel(next); setPanelOpen(true); };
  const openReportEntry = (entry: string) => {
    if (entry in PANEL_ICONS) {
      openPanel(entry as Panel);
      setMonthlyReportOpen(false);
    }
  };
  const selectArmy = (army: Army) => { setSelectedArmy(army.id); setSelectedNode(army.station_node); setInfoOpen(true); };
  return <main className={`game-shell map-layout ${infoOpen ? "map-info-open" : ""}`}>
    <StrategicMap state={state} selectedId={selectedNode} selectedArmyId={selectedArmy} onSelect={(id) => { setSelectedNode(id); setInfoOpen(false); }} onState={setState} />
    <MetricBar state={state} />
    <HistoryTimeline state={state} onOpenHistory={() => openPanel("史册")} />
    <WorldActionPanel compact={infoOpen} onOpenPanel={openPanel} />
    {monthlyReport && monthlyReportOpen && <MonthlyReportPanel report={monthlyReport} onClose={() => setMonthlyReportOpen(false)} onOpenEntry={openReportEntry} />}
    {monthlyReport && !monthlyReportOpen && <button className="monthly-report-chip paper-panel" type="button" onClick={() => setMonthlyReportOpen(true)}>
      <span>每月总计</span><strong>{monthlyReport.title}</strong>
    </button>}
    {node && <div className={`map-info-dock ${infoOpen ? "open" : ""}`}>
      {!infoOpen && <button className="map-info-chip paper-panel" type="button" onClick={() => setInfoOpen(true)}>
        <span>{node.province}</span><strong>{node.name}</strong><small>{powerName(state, node.controller)}据有 · 驻军 {node.stationed_army_ids.length} 支</small>
      </button>}
      {infoOpen && <>
        <button className="floating-close info-close" type="button" aria-label="收起州郡信息" onClick={() => setInfoOpen(false)}><X /></button>
        <ArmyCommandPanel state={state} node={node} selectedArmyId={selectedArmy} onArmy={setSelectedArmy} onNode={setSelectedNode} onState={setState} />
      </>}
    </div>}
    <nav className="command-dock" aria-label="军政功能入口">
      {COMMAND_DOCK_ITEMS.map((item) => {
        if (item.key === "API 配置") return <button key={item.key} className="api-config-sidebar" type="button" onClick={() => void openConfig()} disabled={configLoading} title={item.key}>{configLoading ? <Loader2 className="spin" /> : <Settings />}<span>{item.key}</span></button>;
        if (item.key === "月末推演") return <button key={item.key} className="resolve-turn" type="button" onClick={() => void resolve()} disabled={resolving || !!state.ending} title={item.key}>{resolving ? <Loader2 className="spin" /> : <Activity />}<span>{item.key}</span></button>;
        const name = item.key as Panel;
        const Icon = PANEL_ICONS[name];
        return <button className={panelOpen && panel === name ? "active" : ""} key={name} onClick={() => openPanel(name)} title={name}><Icon /><span>{name}</span></button>;
      })}
    </nav>
    {panelOpen && <section className="right-panel paper-panel floating-panel">
      <header><span>{panel}</span><small>{panelSubtitle(panel)}</small><button className="floating-close" type="button" aria-label="收起功能面板" onClick={() => setPanelOpen(false)}><X /></button></header>
      <div className="panel-content">
        {panel === "军令" && <ArmyPanel state={state} onSelect={selectArmy} />}
        {panel === "朝议" && <CharacterBook state={state} onDialogue={setDialogue} />}
        {panel === "任事" && <PersonnelOfficePanel state={state} onState={setState} />}
        {panel === "国策" && <FocusBook state={state} onState={setState} />}
        {panel === "外交" && <DiplomacyPanel state={state} />}
        {panel === "家族" && <FamilyPanel state={state} />}
        {panel === "史册" && <HistoryPanel state={state} />}
      </div>
    </section>}
    {error && <div className="global-error" onClick={() => setError("")}>{error}<X /></div>}
    {dialogue && <DialogueModal character={dialogue} onClose={() => setDialogue(null)} />}
    {configOpen && llmConfig && <ApiConfigModal mode="game" initial={llmConfig} onClose={() => setConfigOpen(false)} onSaved={setLlmConfig} />}
    {state.ending && <div className="ending-curtain"><section><span>国史终章</span><h2>{state.ending.label}</h2><p>{state.ending.summary}</p></section></div>}
  </main>;
}

function App() {
  const [state, setState] = React.useState<GameState | null>(null);
  const [checking, setChecking] = React.useState(true);
  React.useEffect(() => {
    void getState().then(setState).catch(() => setState(null)).finally(() => setChecking(false));
  }, []);
  if (checking) return <div className="loading-screen"><Castle /><span>展开天下舆图……</span></div>;
  return state ? <GameScreen initial={state} /> : <MenuScreen onEnter={setState} />;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
