import { BookOpen, ChevronRight, ScrollText, ShieldAlert, Sparkles, Swords, X } from "lucide-react";

import type { MonthlyReport, MonthlyReportItem } from "../types";

const SECTION_ICONS: Record<string, typeof Swords> = {
  military: Swords,
  internal: ScrollText,
  diplomacy: BookOpen,
  personnel: Sparkles,
  secret: ShieldAlert,
  world: BookOpen,
  reputation: Sparkles,
};

const SECTION_LABELS: Record<string, string> = {
  military: "军事",
  internal: "内政",
  diplomacy: "外交",
  personnel: "人事",
  secret: "密令暗流",
  world: "天下动向",
  reputation: "仁义口碑",
};

function formatAuditValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "无";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.length ? `${value.length} 项` : "无";
  if (typeof value === "object") return Object.keys(value).length ? `${Object.keys(value).length} 项` : "无";
  return String(value);
}

function BattleAudit({ item }: { item: MonthlyReportItem }) {
  const audit = item.audit || {};
  const tactic = audit.ai_tactic && typeof audit.ai_tactic === "object" && !Array.isArray(audit.ai_tactic)
    ? audit.ai_tactic as Record<string, unknown>
    : {};
  return <div className="monthly-battle-audit">
    <dl>
      <div><dt>最终概率</dt><dd>{formatAuditValue(audit.final_probability)}%</dd></div>
      <div><dt>硬规则</dt><dd>{formatAuditValue(audit.hard_probability)}%</dd></div>
      <div><dt>随机值</dt><dd>{formatAuditValue(audit.random_roll)}</dd></div>
      <div><dt>计策贡献</dt><dd>{String(tactic.tactic || "无")} {tactic.delta !== undefined ? `+${String(tactic.delta)}` : ""}</dd></div>
    </dl>
    <details>
      <summary>兵力、统率、士气、补给、地形、特性细目</summary>
      <pre>{JSON.stringify({
        weights: audit.weights,
        terrain: audit.terrain,
        army_breakdown: audit.army_breakdown,
        army_changes: audit.army_changes,
        commander_fates: audit.commander_fates,
      }, null, 2)}</pre>
    </details>
  </div>;
}

export function MonthlyReportPanel({ report, onClose, onOpenEntry }: {
  report: MonthlyReport;
  onClose: () => void;
  onOpenEntry: (entry: string) => void;
}) {
  return <section className="monthly-report-panel paper-panel" aria-label="每月总计">
    <header>
      <div><span>每月总计</span><h2>{report.title}</h2></div>
      <button type="button" aria-label="收起每月总计" onClick={onClose}><X /></button>
    </header>
    <div className="monthly-report-grid">
      {report.sections.map((section) => {
        const Icon = SECTION_ICONS[section.id] || ScrollText;
        const title = section.title || SECTION_LABELS[section.id] || "军政";
        return <article key={section.id} className={`monthly-section monthly-${section.id}`}>
          <h3><Icon />{title}</h3>
          <p>{section.summary}</p>
          <div className="monthly-items">
            {section.items.length ? section.items.map((item) => <details key={item.id} className="monthly-item">
              <summary>
                <span>{item.kind}</span>
                <strong>{item.title}</strong>
                <small>{item.summary}</small>
              </summary>
              {item.kind === "战役" ? <BattleAudit item={item} /> : <pre>{JSON.stringify(item.audit, null, 2)}</pre>}
              {item.action?.entry && <button type="button" onClick={() => onOpenEntry(item.action.entry)}>
                {item.action.label || item.action.entry}<ChevronRight />
              </button>}
            </details>) : <small className="monthly-empty">暂无明确条目。</small>}
          </div>
        </article>;
      })}
    </div>
  </section>;
}
