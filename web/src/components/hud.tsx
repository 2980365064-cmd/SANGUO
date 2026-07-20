import { Coins, Heart, Landmark, Shield, Users, Wheat } from "lucide-react";

import { getStageScene } from "../uiLogic";
import type { GameState } from "../types";

const METRICS = [
  { key: "军资", icon: Coins }, { key: "粮秣", icon: Wheat },
  { key: "民望", icon: Heart }, { key: "名分", icon: Landmark },
  { key: "军心", icon: Shield }, { key: "士族支持", icon: Users },
] as const;

export function MetricBar({ state }: { state: GameState }) {
  return <header className="metric-bar">
    <div className="campaign-mark"><span>{state.government.title}</span><strong>{state.government.stage}</strong></div>
    <div className="metrics">{METRICS.map(({ key, icon: Icon }) => <div className="metric" key={key}>
      <Icon /><span>{key}</span><strong>{state.metrics[key]}</strong><i style={{ width: `${state.metrics[key]}%` }} />
    </div>)}</div>
    <div className="turn-date"><strong>{state.turn.year}</strong><span>年 {state.turn.period} 月</span><small>第 {state.turn.turn} 回合</small></div>
  </header>;
}

export function StageScene({ state }: { state: GameState }) {
  const scene = getStageScene(state.government.stage);
  return <div className="stage-scene" style={{ backgroundImage: `url(${scene.asset})`, backgroundPosition: scene.position }} aria-label={`${scene.label}阶段场景`}>
    <div><span>{scene.label}</span><p>{state.previous_summary || "曹操南下，孙刘未盟。此刻每一道军令都可能改写后世。"}</p></div>
  </div>;
}
