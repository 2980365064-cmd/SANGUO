import { Coins, Heart, Landmark, Shield, Users, Wheat } from "lucide-react";

import type { GameState } from "../types";
import { MetricChip, MetricLedger } from './ui';

const METRICS = [
  { key: "军资", icon: Coins }, { key: "粮秣", icon: Wheat },
  { key: "民望", icon: Heart }, { key: "名分", icon: Landmark },
  { key: "军心", icon: Shield }, { key: "士族支持", icon: Users },
] as const;

export function MetricBar({ state }: { state: GameState }) {
  return <header className="metric-bar">
    <div className="campaign-mark"><span>{state.government.title}</span><strong>{state.government.stage}</strong></div>
    <MetricLedger>{METRICS.map(({ key, icon: Icon }) => <MetricChip key={key} icon={<Icon />} label={key} value={state.metrics[key]} trend="steady" />)}</MetricLedger>
    <div className="turn-date"><strong>{state.turn.year}</strong><span>年 {state.turn.period} 月</span><small>第 {state.turn.turn} 回合</small></div>
  </header>;
}
