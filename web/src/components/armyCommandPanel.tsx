import React from "react";
import { Flag, Loader2, MapPin, Send, Swords } from "lucide-react";

import { getRegionDetail, previewBattle, startInvestment, submitArmyOrder } from "../api";
import { getNodeArmies, getReachableTargets } from "../mapLogic";
import type { BattlePreview, GameState, RegionDetail, StrategicNode } from "../types";
import { fiscalNumber, REGION_INVESTMENTS, REGION_LEDGER_ITEMS } from "./regionManagementModel";

function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }
function powerName(state: GameState, powerId: string) { return state.powers.find((power) => power.id === powerId)?.name || powerId || "无主"; }

export function ArmyCommandPanel({ state, node, selectedArmyId, onArmy, onNode, onState }: {
  state: GameState;
  node: StrategicNode;
  selectedArmyId: string;
  onArmy: (id: string) => void;
  onNode: (id: string) => void;
  onState: (state: GameState) => void;
}) {
  const [view, setView] = React.useState<"region" | "army">("region");
  const [target, setTarget] = React.useState("");
  const [orderType, setOrderType] = React.useState("移动");
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [preview, setPreview] = React.useState<BattlePreview | null>(null);
  const [regionDetail, setRegionDetail] = React.useState<RegionDetail | null>(null);
  const armiesHere = getNodeArmies(state.armies, node.id);
  const ownArmy = state.armies.find((army) => army.id === selectedArmyId && army.owner_power === "liu_bei");
  const targets = ownArmy ? getReachableTargets(state.map.nodes, ownArmy.station_node) : [];
  const targetNode = state.map.nodes.find((item) => item.id === (target || node.id));
  const defenders = targetNode ? state.armies.filter((army) => army.station_node === targetNode.id && army.owner_power !== "liu_bei") : [];

  React.useEffect(() => { setTarget(""); setPreview(null); if (selectedArmyId) setView("army"); }, [selectedArmyId]);
  React.useEffect(() => { setPreview(null); }, [target]);
  React.useEffect(() => {
    let alive = true;
    setRegionDetail(null);
    void getRegionDetail(node.id)
      .then((detail) => { if (alive) setRegionDetail(detail); })
      .catch(() => { if (alive) setRegionDetail(null); });
    return () => { alive = false; };
  }, [node.id, state.turn.turn, state.region_investments]);

  const needsTarget = orderType === "移动" || orderType === "撤退" || orderType === "围城" || orderType === "突袭";
  const issue = async () => {
    if (!ownArmy || (needsTarget && !target)) return;
    setBusy("order"); setError("");
    try {
      const payload: Record<string, unknown> = orderType === "围城" || orderType === "突袭" ? { target } :
        orderType === "移动" || orderType === "撤退" ? { to: target } : {};
      const result = await submitArmyOrder(ownArmy.id, orderType, payload);
      onState(result.state);
    } catch (caught) { setError(errorText(caught)); } finally { setBusy(""); }
  };

  const inspectBattle = async () => {
    if (!ownArmy || !targetNode || defenders.length === 0) return;
    setBusy("preview"); setError("");
    try { setPreview(await previewBattle([ownArmy.id], defenders.map((army) => army.id), targetNode.id)); }
    catch (caught) { setError(errorText(caught)); } finally { setBusy(""); }
  };

  const invest = async (category: string) => {
    setBusy(category); setError("");
    try {
      const result = await startInvestment(node.id, category);
      onState(result.state);
      setRegionDetail(await getRegionDetail(node.id));
    } catch (caught) { setError(errorText(caught)); } finally { setBusy(""); }
  };

  return <aside className="node-dossier paper-panel">
    <div className="dossier-tabs">
      <button className={view === "region" ? "active" : ""} onClick={() => setView("region")}>州郡</button>
      <button className={view === "army" ? "active" : ""} onClick={() => setView("army")} disabled={!ownArmy}>军队</button>
    </div>
    {view === "region" && <>
      <div className="panel-title"><span>{node.province}</span><h2>{node.name}</h2><small>{powerName(state, node.controller)}据有</small></div>
      <p className="region-status">{node.status}</p>
      <div className="node-stats">
        <span>民望<strong>{node.public_support}</strong></span><span>动乱<strong>{node.unrest}</strong></span>
        <span>军压<strong>{node.military_pressure}</strong></span><span>户口<strong>{node.population}</strong></span>
      </div>
      <h3>驻军 · {armiesHere.length} 支</h3>
      <div className="army-mini-list">
        {armiesHere.length ? armiesHere.map((army) => <button key={army.id} onClick={() => { onArmy(army.id); setView("army"); }} className={selectedArmyId === army.id ? "active" : ""}>
          <Flag /><span>{army.name}<small>{army.commander} · {army.manpower.toLocaleString()}人 · {powerName(state, army.owner_power)}</small></span>
        </button>) : <p className="empty-note">此地暂无独立部队。</p>}
      </div>
      <section className="region-management">
        <h3>郡县经营</h3>
        <div className="region-ledger">
          {REGION_LEDGER_ITEMS.map((item) => {
            const value = item.key === "gentry_resistance" ? regionDetail?.gentry_resistance ?? node.military_pressure : fiscalNumber(regionDetail, item.key);
            return <span className="region-ledger-item" key={item.key} title={item.description} aria-label={`${item.label} ${value}。${item.description}`}>
              <b>{item.label}</b><strong>{value}</strong><small>{item.short}</small>
            </span>;
          })}
        </div>
        {regionDetail?.investment && <p className="investment-current">正在推进：{String(regionDetail.investment.category)} · {String(regionDetail.investment.progress)}%</p>}
        {!regionDetail && <p className="empty-note">正在调阅郡县簿册。</p>}
        {regionDetail && !regionDetail.can_invest && <p className="empty-note">此地非刘备实际控制，只可问策与观察，不能直接投资。</p>}
        {regionDetail?.can_invest && <div className="investment-actions">{REGION_INVESTMENTS.map((item) => <button key={item.category} onClick={() => void invest(item.category)} disabled={!!busy || !!regionDetail.investment} title={regionDetail.investment ? `已有投资正在推进：${String(regionDetail.investment.category)}` : item.description} aria-label={`${item.category}：${item.description}`}>
          {busy === item.category ? <Loader2 className="spin" /> : null}<span>{item.category}</span><small>{item.hint}</small>
        </button>)}</div>}
      </section>
    </>}
    {view === "army" && ownArmy && <>
      <div className="panel-title"><span>{powerName(state, ownArmy.owner_power)} · {ownArmy.theater}</span><h2>{ownArmy.name}</h2><small>{ownArmy.commander}统领</small></div>
      <div className="army-vitals">
        <span>兵力<strong>{ownArmy.manpower.toLocaleString()}</strong></span><span>粮秣<strong>{ownArmy.supply}</strong><small>{ownArmy.supply_turns}回合</small></span>
        <span>士气<strong>{ownArmy.morale}</strong></span><span>疲劳<strong>{ownArmy.fatigue}</strong></span>
        <span>军资缺额<strong>{ownArmy.starvation_turns}</strong></span><span>训练<strong>{ownArmy.training}</strong></span>
      </div>
      <div className="army-specialties">{ownArmy.specialties.map((item) => <em key={item}>{item}</em>)}</div>
      <div className="order-desk">
        <h3>本月主军令</h3>
        <div className="segmented">{["移动", "驻守", "突袭", "补给", "围城", "撤退"].map((type) => <button className={orderType === type ? "active" : ""} onClick={() => setOrderType(type)} key={type}>{type}</button>)}</div>
        {needsTarget && <div className="province-target-list">
          {targets.map((item) => {
            const candidate = state.map.nodes.find((nodeItem) => nodeItem.id === item.nodeId);
            return <button key={item.nodeId} className={target === item.nodeId ? "active" : ""} onClick={() => { setTarget(item.nodeId); onNode(item.nodeId); }}>
              <MapPin /><span>{candidate?.name || item.nodeId}<small>{item.scope} · {item.province}</small></span>
            </button>;
          })}
        </div>}
        <button className="seal-button" disabled={!!busy || !!ownArmy.current_order || (needsTarget && !target)} onClick={() => void issue()}>
          {busy === "order" ? <Loader2 className="spin" /> : <Send />} {ownArmy.current_order ? `${ownArmy.current_order.order_type}已下` : "核发军令"}
        </button>
      </div>
      {defenders.length > 0 && target && <button className="battle-preview-button" onClick={() => void inspectBattle()} disabled={!!busy}><Swords /> 战前推演 · 敌军 {defenders.length} 支</button>}
      {preview && <div className="battle-preview"><strong>胜算 {preview.win_probability_range[0]}–{preview.win_probability_range[1]}%</strong><span>{preview.terrain.kind} · 预计 {preview.duration_turns} 回合</span><ul>{preview.major_factors.slice(0, 5).map((factor) => <li key={factor}>{factor}</li>)}</ul></div>}
      {ownArmy.current_order?.result && Object.keys(ownArmy.current_order.result).length > 0 && <details className="combat-log"><summary>军令审计日志</summary><pre>{JSON.stringify(ownArmy.current_order.result, null, 2)}</pre></details>}
    </>}
    {error && <p className="inline-error">{error}</p>}
  </aside>;
}
