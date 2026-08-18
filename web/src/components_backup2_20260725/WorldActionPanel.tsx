import React from "react";
import { ChevronRight, Loader2, ScrollText, X } from "lucide-react";
import { confirmActionIntent, createActionIntent, getMonthAgenda, getOngoingPlans, getReputation } from "../api";
import type { ActionIntent, MonthAgendaItem, OngoingPlan, ReputationSummary } from "../types";
import { errorText } from "../utils/errorText";

type Panel = "朝议" | "军令" | "任事" | "外交" | "国策" | "家族" | "史册";

export function WorldActionPanel({ compact, onOpenPanel }: { compact: boolean; onOpenPanel: (panel: Panel) => void }) {
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
    return (
      <button
        className="world-action-panel world-action-panel-collapsed paper-panel"
        type="button"
        onClick={() => onOpenPanel((primary?.entry || "朝议") as Panel)}
      >
        <span>本月要议</span>
        <strong>{primary?.title || "召群臣问策"}</strong>
      </button>
    );
  }

  return (
    <section className="world-action-panel paper-panel">
      <header><span>本月要议</span><small>从问题进入裁断</small></header>
      <div className="agenda-strip">
        {agenda.map((item) => (
          <button type="button" key={item.id} onClick={() => onOpenPanel((item.entry as Panel) || "朝议")}>
            <strong>{item.title}</strong><span>{item.kind} · 急 {item.urgency}</span><small>{item.summary}</small>
          </button>
        ))}
      </div>
      <div className="free-command">
        <label>自由命令</label>
        <textarea value={command} onChange={(event) => setCommand(event.target.value)} />
        <button type="button" onClick={() => void draft()} disabled={busy === "draft" || !command.trim()}>
          {busy === "draft" ? <Loader2 className="spin" /> : <ScrollText />} 转为方略草案
        </button>
      </div>
      {intent && (
        <article className={`action-draft ${intent.draft.executable ? "ok" : "blocked"}`}>
          <h3>{intent.draft.action_type}</h3>
          <p>{intent.draft.title}</p>
          <dl><div><dt>执行</dt><dd>{intent.draft.assignee || "未定"}</dd></div><div><dt>周期</dt><dd>{intent.draft.duration_months} 月</dd></div></dl>
          {intent.draft.risks.length ? <small>风险：{intent.draft.risks.join("、")}</small> : null}
          {!intent.draft.executable && <small>{intent.draft.reasons.join("；") || intent.draft.rewrite_suggestion}</small>}
          <button type="button" onClick={() => void confirm()} disabled={!intent.draft.executable || busy === "confirm"}>
            {busy === "confirm" ? <Loader2 className="spin" /> : <ChevronRight />} 确认入账
          </button>
        </article>
      )}
      <div className="ongoing-ledger">
        <h3>持续方略</h3>
        {plans.length ? plans.slice(0, 4).map((plan) => (
          <article key={plan.id}>
            <strong>{plan.title}</strong><span>{plan.status} · {plan.progress}% · {plan.assignee}</span>
            <small>{plan.last_result || "等待月末推进"}</small>
          </article>
        )) : <p>暂无持续方略。</p>}
      </div>
      {reputation && <div className="reputation-chip"><span>仁义口碑</span><strong>{reputation.score}</strong></div>}
      {error && <p className="inline-error">{error}</p>}
    </section>
  );
}
