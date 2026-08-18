import { History } from "lucide-react";

import { buildFutureMonthLine, timelineStatusLabel } from "../uiLogic";
import type { GameState } from "../types";

export function HistoryTimeline({ state, onOpenHistory }: { state: GameState; onOpenHistory: () => void }) {
  const slots = buildFutureMonthLine(state.turn, state.timeline);
  return <section className="history-ribbon" aria-label="未来十二个月重大史势">
    <button className="history-ribbon-title" onClick={onOpenHistory}><History /><span>未来十二月<small>悬停看大事</small></span></button>
    <div className="month-line" role="list">
      {slots.map((slot) => <button
        key={slot.key}
        className={slot.events.length ? "month-dot has-event" : "month-dot"}
        type="button"
        onClick={slot.events.length ? onOpenHistory : undefined}
        aria-label={`${slot.label}${slot.events.length ? `：${slot.events.map((event) => event.title).join("、")}` : "：无大事"}`}
        role="listitem"
      >
        <i />
        <small>{slot.month}</small>
        {slot.events.length > 0 && <span className="month-tooltip">
          <b>{slot.label}</b>
          {slot.events.map((event) => <em key={event.id}>{event.title}<small>{timelineStatusLabel(event.status)} · {event.window}</small></em>)}
        </span>}
      </button>)}
    </div>
  </section>;
}
