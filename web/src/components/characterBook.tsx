import React from "react";
import { BookOpen, ChevronRight, Handshake, Loader2, MessageCircle, Send, Users } from "lucide-react";
import { getDialogue, streamCourtChat, streamDialogue } from "../api";
import type { Army, Character, CourtChatMessage, DialogueMessage, FocusDefinition, GameState, IntelValue } from "../types";
import { Portrait } from "./Portrait";
import { POWER_COLORS } from "../constants/powerColors";
import { GameDialog } from "./GameDialog";

function displayIntel(value: IntelValue) {
  if (typeof value === "object") return `${value.min}–${value.max}`;
  return String(value);
}

export function CharacterBook({ state, onDialogue }: { state: GameState; onDialogue: (c: Character) => void }) {
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
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); } finally { setBusy(false); }
  };

  return (
    <div className="character-book">
      <div className="book-toolbar">
        <button className={mode === "council" ? "active" : ""} onClick={() => setMode("council")}>群臣廷议</button>
        <button className={mode === "private" ? "active" : ""} onClick={() => setMode("private")}>私下召见</button>
      </div>

      {mode === "council" && (
        <section className="council-board">
          <div className="council-ministers">
            {liuBeiMinisters.slice(0, 12).map((character) => (
              <button key={character.name} className={councilMinisters.includes(character.name) ? "active" : ""} onClick={() => toggleMinister(character.name)}>
                <Portrait character={character} /><span>{character.name}</span><small>{character.office || character.political_group}</small>
              </button>
            ))}
          </div>
          <div className="council-session">
            <header><span>军议议题</span><strong>军府方略</strong></header>
            <textarea value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="提出本月必须裁断的军政问题" />
            <button className="seal-button" onClick={() => void startCouncil()} disabled={busy || !topic.trim() || councilMinisters.length === 0}>
              {busy ? <Loader2 className="spin" /> : <Users />} 开始廷议
            </button>
            {error && <p className="inline-error">{error}</p>}
            <div className="council-history">
              {councilMessages.map((message, index) => (
                <article key={index} className={message.role === "conclusion" ? "conclusion" : message.role === "emperor" ? "player" : ""}>
                  <small>{message.speaker || (message.role === "emperor" ? "刘备" : "臣将")}</small>
                  <p>{message.content}</p>
                  {message.options?.length ? <ul>{message.options.map((option) => <li key={option}>{option}</li>)}</ul> : null}
                </article>
              ))}
              {liveText && <article className="live"><small>{liveSpeaker || "臣将"}</small><p>{liveText}<i /></p></article>}
            </div>
          </div>
        </section>
      )}

      {mode === "private" && (
        <>
          <div className="book-toolbar private-toolbar">
            <button className={filter === "刘备" ? "active" : ""} onClick={() => setFilter("刘备")}>麾下</button>
            <button className={filter === "天下" ? "active" : ""} onClick={() => setFilter("天下")}>天下人物</button>
          </div>
          <div className="portrait-grid">
            {list.map((character) => (
              <button key={character.name} className={current?.name === character.name ? "active" : ""} onClick={() => setSelected(character.name)}>
                <Portrait character={character} /><strong>{character.name}</strong><small>{character.office || character.political_group}</small>
              </button>
            ))}
          </div>
          {current && (
            <div className="character-dossier">
              <Portrait character={current} />
              <div className="character-heading">
                <span>{current.political_group} · 情报 {current.intel_level}</span>
                <h3>{current.name}</h3>
                <p>{current.office || current.style}</p>
                <blockquote>{current.summary || `${current.political_group}，${current.style}`}</blockquote>
              </div>
              <div className="ability-grid">
                {Object.entries(current.abilities.values).map(([name, value]) => (
                  <span key={name}>{name}<strong>{displayIntel(value)}</strong></span>
                ))}
              </div>
              <div className="traits">{current.traits.map((trait) => <em key={trait}>{trait}</em>)}</div>
              <div className="personality-line">人格情报：{current.personality.visibility} · {Object.entries(current.personality.values).map(([k, v]) => `${k}${displayIntel(v)}`).join(" / ")}</div>
              {current.power_id === "liu_bei" && current.status === "active" && (
                <button className="seal-button" onClick={() => onDialogue(current)}><MessageCircle /> 私下召见</button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function FocusBook({ state, onState }: { state: GameState; onState: (s: GameState) => void }) {
  const [error, setError] = React.useState("");
  const progress = new Map(state.national_focus.progress.map((item) => [item.focus_id, item]));

  return (
    <div className="focus-book">
      {(["政治", "军事", "经济"] as const).map((category) => (
        <section key={category} className={`focus-column focus-${category}`}>
          <header><span>{category}</span><strong>+{state.national_focus.points_per_turn[category] || 0} 点 / 回合</strong></header>
          {Object.entries(state.national_focus.definitions).filter(([, value]) => value.category === category).map(([id, definition]: [string, FocusDefinition]) => {
            const row = progress.get(id);
            const value = row?.progress || 0;
            return (
              <article key={id} className={row?.status === "completed" ? "completed" : ""}>
                <h3>{definition.name || definition.title || id}</h3>
                <p>{definition.summary || "完成后改变政权的长期能力与历史选择。"}</p>
                <div className="focus-progress">
                  <i style={{ width: `${Math.min(100, value / definition.cost * 100)}%` }} />
                  <span>{value}/{definition.cost}</span>
                </div>
                <button disabled={row?.status === "active" || row?.status === "completed"} onClick={() => {
                  setError("");
                  void import("../api").then(({ startFocus }) => startFocus(id)).then((r) => onState(r.state)).catch((e) => setError(String(e instanceof Error ? e.message : e)));
                }}>
                  {row?.status === "completed" ? "已成" : row?.status === "active" ? "推行中" : "开始推行"}
                </button>
              </article>
            );
          })}
        </section>
      ))}
      {error && <p className="inline-error">{error}</p>}
    </div>
  );
}

export function ArmyPanel({ state, onSelect }: { state: GameState; onSelect: (army: Army) => void }) {
  const powerName = (powerId: string) => state.powers.find((power) => power.id === powerId)?.name || powerId || "无主";

  return (
    <div className="army-ledger">
      {state.armies.map((army) => (
        <button key={army.id} onClick={() => onSelect(army)}>
          <i style={{ background: POWER_COLORS[army.owner_power] }} />
          <div><strong>{army.name}</strong><span>{army.commander} · {powerName(army.owner_power)}</span></div>
          <dl><span>兵 {army.manpower.toLocaleString()}</span><span>粮 {army.supply}</span><span>气 {army.morale}</span></dl>
          <small>{army.current_order ? `${army.current_order.order_type}已下` : army.status}</small>
          <ChevronRight />
        </button>
      ))}
    </div>
  );
}

export function DiplomacyPanel({ state }: { state: GameState }) {
  const liuBeiMinisters = state.characters.filter((character) => character.power_id === "liu_bei" && character.status === "active");
  const foreignPowers = state.powers.filter((power) => power.id !== "liu_bei");
  const [targetPower, setTargetPower] = React.useState(foreignPowers[0]?.id || "sun_quan");
  const [envoy, setEnvoy] = React.useState("诸葛亮");
  const [goal, setGoal] = React.useState("续盟并借粮");
  const [boundaries, setBoundaries] = React.useState("不得割让江夏，不得背盟。");
  const [missions, setMissions] = React.useState<any[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    void import("../api").then(({ getEnvoyMissions }) => getEnvoyMissions()).then((payload) => setMissions(payload.missions || [])).catch((e) => setError(String(e instanceof Error ? e.message : e)));
  }, []);

  const sendEnvoy = async () => {
    if (busy || !targetPower || !envoy || !goal.trim()) return;
    setBusy(true); setError("");
    try {
      const { createEnvoyMission } = await import("../api");
      const payload = await createEnvoyMission({ target_power: targetPower, envoy, goal, boundaries });
      setMissions((current) => [payload.mission, ...current]);
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); } finally { setBusy(false); }
  };

  const relationFor = (id: string) => state.diplomacy.relations.find((r) =>
    (r.power_a === "liu_bei" && r.power_b === id) || (r.power_b === "liu_bei" && r.power_a === id));

  return (
    <div className="diplomacy-panel">
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
        <button type="button" onClick={() => void sendEnvoy()} disabled={busy}>
          {busy ? <Loader2 className="spin" /> : <Handshake />} 派遣使臣
        </button>
        {error && <p className="inline-error">{error}</p>}
      </section>
      {foreignPowers.map((power) => {
        const relation = relationFor(power.id);
        return (
          <article key={power.id}>
            <i style={{ background: POWER_COLORS[power.id] }} />
            <div><h3>{power.name}<small>{power.leader}</small></h3><p>{power.agenda}</p></div>
            <dl>
              <div><dt>公开关系</dt><dd>{String(relation?.public_relation ?? "未建档")}</dd></div>
              <div><dt>互信</dt><dd>{String(relation?.trust ?? "未建档")}</dd></div>
              <div><dt>军力</dt><dd>{power.military_strength}</dd></div>
            </dl>
          </article>
        );
      })}
      <section className="treaty-scroll"><h3>盟约与联姻</h3>{state.diplomacy.treaties.length ? state.diplomacy.treaties.map((treaty, index) => <p key={index}>{String(treaty.treaty_type)} · {String(treaty.status)}</p>) : <p>尚无正式盟约。</p>}</section>
      <section className="treaty-scroll"><h3>使臣在途</h3>{missions.length ? missions.map((mission) => <p key={mission.id}>{mission.envoy}赴{mission.target_power} · {mission.goal}</p>) : <p>尚无使臣任务。</p>}</section>
    </div>
  );
}

export function DialogueModal({ character, onClose }: { character: Character; onClose: () => void }) {
  const [messages, setMessages] = React.useState<DialogueMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [stream, setStream] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    void getDialogue(character.name).then((r) => setMessages(r.history || [])).catch((e) => setError(String(e instanceof Error ? e.message : e)));
  }, [character.name]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setMessages((current) => [...current, { role: "user", content: text }]);
    setInput(""); setStream(""); setBusy(true); setError("");
    try {
      const response = await streamDialogue(character.name, text, (delta) => setStream((current) => current + delta));
      const answer = response.answer || "";
      setMessages((current) => [...current, { role: "minister", content: answer }]);
      setStream("");
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); } finally { setBusy(false); }
  };

  return (
    <GameDialog open onOpenChange={(open) => { if (!open) onClose(); }} title={`${character.name} · 军帐召对`} description={character.office || character.political_group} tone="default">
      <div className="dialogue-modal">
        <header><Portrait character={character} /><div><span>军帐召对</span><p>{character.office || character.political_group}</p></div></header>
        <div className="dialogue-history">
          {messages.map((message, index) => (
            <p className={message.role === "user" ? "player" : "character"} key={index}>
              <small>{message.role === "user" ? "刘备" : character.name}</small>{message.content}
            </p>
          ))}
          {stream && <p className="character live"><small>{character.name}</small>{stream}<i /></p>}
        </div>
        {error && <p className="inline-error">{error}</p>}
        <footer>
          <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder={`与${character.name}商议军国大事……`} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} />
          <button onClick={() => void send()} disabled={busy}>{busy ? <Loader2 className="spin" /> : <Send />}</button>
        </footer>
      </div>
    </GameDialog>
  );
}
