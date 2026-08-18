import type { GameState } from "../types";
import { MetricChip, MetricLedger } from './ui';

const METRICS = [
  { key: "军资", icon: "wealth" }, { key: "粮秣", icon: "grain" },
  { key: "民望", icon: "people" }, { key: "名分", icon: "legitimacy" },
  { key: "军心", icon: "morale" }, { key: "士族支持", icon: "relation" },
] as const;

function InkIcon({ name }: { name: string }) {
  return <span className="hud-ink-icon" data-icon={name} />;
}

export function MetricBar({ state }: { state: GameState }) {
  return <header className="metric-bar">
    <div className="metric-paperweight" aria-hidden="true" />
    <div className="campaign-mark"><small>军府日课</small><span>{state.government.title}</span><strong>{state.government.stage}</strong><span className="campaign-calligraphy" aria-label="刘备">刘备</span></div>
    <MetricLedger>{METRICS.map(({ key, icon }) => <MetricChip key={key} icon={<InkIcon name={icon} />} label={key} value={state.metrics[key]} trend="steady" />)}</MetricLedger>
    <div className="turn-date"><strong>{state.turn.year}</strong><span>建安十三年 · {state.turn.period} 月</span><small>第 {state.turn.turn} 回合</small></div>
  </header>;
}
