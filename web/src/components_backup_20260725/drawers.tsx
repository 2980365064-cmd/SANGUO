import { BookOpen, Users } from "lucide-react";

import { timelineStatusLabel } from "../uiLogic";
import type { GameState } from "../types";

export function FamilyPanel({ state }: { state: GameState }) {
  return <div className="family-panel">
    <header><Users /><div><h3>宗亲与家国</h3><p>只保留历史配偶、子嗣、政治婚姻、联姻盟约与继承风险。</p></div></header>
    {state.families.length ? <div className="family-ledger">{state.families.map((relation, index) => {
      const source = String(relation.source_name || relation.person_a || relation.parent || relation.character || "宗亲");
      const target = String(relation.target_name || relation.person_b || relation.child || relation.related_character || "家属");
      const kind = String(relation.relation_type || relation.kind || relation.relationship || "亲属");
      return <article key={String(relation.id || index)}><span>{kind}</span><strong>{source}</strong><i>—</i><strong>{target}</strong></article>;
    })}</div> : <p className="empty-scroll">当前宗亲簿尚无可公开条目。</p>}
  </div>;
}

export function HistoryPanel({ state }: { state: GameState }) {
  return <div className="history-panel">
    <div className="timeline-warning"><BookOpen />未来只显示事件窗口与标题；事件改写、失效与变体仍会留在史册。</div>
    {state.timeline.map((event, index) => <article key={event.id}><i>{index + 1}</i><div><time>{event.window}</time><h3>{event.title}</h3><span>{timelineStatusLabel(event.status)}</span></div></article>)}
    {(state.last_report || state.previous_summary) && <section className="latest-annals"><span>近月纪事</span><p>{state.last_report || state.previous_summary}</p></section>}
  </div>;
}
