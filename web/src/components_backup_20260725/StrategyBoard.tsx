import { AlertTriangle, BookOpen, ChevronRight, Lightbulb, ScrollText, Shield, Sparkles, Swords, X } from "lucide-react";

import type { StrategyEvent, StrategyEventSeverity } from "../types";

const SEVERITY_CONFIG: Record<StrategyEventSeverity, { icon: typeof Swords; color: string; label: string }> = {
  urgent: { icon: AlertTriangle, color: "#8a2a20", label: "紧急" },
  important: { icon: Shield, color: "#7d5a2a", label: "重要" },
  suggestion: { icon: Lightbulb, color: "#3e6b5e", label: "建议" },
  opportunity: { icon: Sparkles, color: "#4a6a8a", label: "机遇" },
};

const CATEGORY_ICONS: Record<string, typeof Swords> = {
  military: Swords,
  internal: ScrollText,
  diplomacy: BookOpen,
  personnel: Sparkles,
  secret: Shield,
  world: BookOpen,
  reputation: Sparkles,
  decision: AlertTriangle,
  suggestion: Lightbulb,
  agenda: ScrollText,
};

export function StrategyBoard({ events, onClose, onAction }: {
  events: StrategyEvent[];
  onClose: () => void;
  onAction: (event: StrategyEvent) => void;
}) {
  if (!events.length) {
    return <section className="strategy-board paper-panel" aria-label="方略">
      <header>
        <div><span>方 略</span><h2>本月无紧急事项</h2></div>
        <button type="button" aria-label="关闭方略" onClick={onClose}><X /></button>
      </header>
      <div className="strategy-empty">
        <p>天下暂安，无须裁断之事。可自由部署军政或推进至下月。</p>
      </div>
    </section>;
  }

  // 按 severity 分组
  const grouped: Record<StrategyEventSeverity, StrategyEvent[]> = {
    urgent: [], important: [], suggestion: [], opportunity: [],
  };
  for (const event of events) {
    const bucket = grouped[event.severity] || grouped.suggestion;
    bucket.push(event);
  }

  return <section className="strategy-board paper-panel" aria-label="方略">
    <header>
      <div><span>方 略</span><h2>本月军政要务</h2></div>
      <button type="button" aria-label="关闭方略" onClick={onClose}><X /></button>
    </header>
    <div className="strategy-grid">
      {(["urgent", "important", "opportunity", "suggestion"] as const).map((severity) => {
        const items = grouped[severity];
        if (!items.length) return null;
        const config = SEVERITY_CONFIG[severity];
        const Icon = config.icon;
        return <div key={severity} className={`strategy-group strategy-${severity}`}>
          <h3 style={{ borderColor: config.color }}>
            <Icon />{config.label}<small>{items.length} 项</small>
          </h3>
          <div className="strategy-cards">
            {items.map((event) => {
              const CatIcon = CATEGORY_ICONS[event.category] || ScrollText;
              return <article key={event.id} className="strategy-card">
                <div className="strategy-card-header">
                  <CatIcon />
                  <div>
                    <strong>{event.title}</strong>
                    <small>{event.section_title}</small>
                  </div>
                </div>
                {event.summary && <p>{event.summary}</p>}
                <button type="button" onClick={() => onAction(event)}>
                  {event.action_label}<ChevronRight />
                </button>
              </article>;
            })}
          </div>
        </div>;
      })}
    </div>
  </section>;
}
