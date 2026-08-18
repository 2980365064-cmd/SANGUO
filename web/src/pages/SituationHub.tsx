import { useEffect, useMemo, useState } from 'react';
import { getReactions, type ReactionEvent } from '../api';
import { useCurrentPage, useGameStore } from '../state/gameStore';
import type { ExternalIntelligence } from '../types';

type LedgerMark = 'confirmed' | 'assessment' | 'rumor';
type LedgerEntry = { id: string; title: string; summary: string; source: string; mark: LedgerMark };

const MARK_LABEL: Record<LedgerMark, string> = {
  confirmed: '已证实',
  assessment: '有据研判',
  rumor: '商旅传闻',
};

/** 天下推演录：只读呈现已过滤的世界结果与证据，不提供世界写入入口。 */
export function SituationHub() {
  const { state } = useGameStore();
  const { navigate } = useCurrentPage();
  const gameState = state.gameState;
  const [reactions, setReactions] = useState<ReactionEvent[]>([]);
  const world = (gameState as any).world || { incidents: [], memorials: [], intelligence: [] };

  useEffect(() => {
    getReactions({ limit: 5 }).then(({ reactions: rows }) => setReactions(rows)).catch(() => setReactions([]));
  }, [gameState.turn.turn]);

  const entries = useMemo<LedgerEntry[]>(() => {
    const rows: LedgerEntry[] = [];
    (world.incidents || []).forEach((item: any) => rows.push({
      id: `incident-${item.id}`,
      title: item.title || '区域局势变动',
      summary: item.summary || '该地出现了值得收入本月推演的环境变化。',
      source: item.tier === 'dramatic' ? '区域重大纪事' : '区域状态记录',
      mark: 'confirmed',
    }));
    (world.memorials || []).forEach((item: any) => rows.push({
      id: `memorial-${item.id}`,
      title: `${item.minister_name}《${item.title}》`,
      summary: item.summary || item.risk_note || '已有奏议写入本月记录。',
      source: '廷臣奏议',
      mark: 'assessment',
    }));
    (world.intelligence as ExternalIntelligence[] || []).filter((item) => item.verification_status !== 'refuted' && item.verification_status !== 'expired').forEach((item) => rows.push({
      id: `intel-${item.id}`,
      title: item.title,
      summary: item.summary || item.resolution_summary || '外部动向已收入情报簿。',
      source: `${item.source_type} · 可信度 ${item.reliability}`,
      mark: item.visibility === 'confirmed' ? 'confirmed' : item.visibility === 'assessment' ? 'assessment' : 'rumor',
    }));
    reactions.forEach((item) => rows.push({
      id: `reaction-${item.id}`,
      title: item.target || '天下反应',
      summary: item.outcome_summary || '外势对既有事实产生新的可见反应。',
      source: '天下反应记录',
      mark: 'assessment',
    }));
    return rows.slice(0, 5);
  }, [reactions, world.incidents, world.intelligence, world.memorials]);

  const conclusion = entries[0]?.summary || '本月未见足以改写天下格局的已知变局。军府仍须留意可见的区域环境与外势动向。';
  const regionEntries = entries.filter((item) => item.id.startsWith('incident-')).slice(0, 5);

  return <main className="situation-hub-root world-analysis-root" aria-label="天下推演录场景">
    <article className="world-analysis-ledger" aria-label="天下推演录">
      <header className="world-ledger-title">
        <div className="world-ledger-date">建安 {gameState.turn.year} 年 · {gameState.turn.period} 月<br />第 {gameState.turn.turn} 回合</div>
        <h1>天下推演录</h1>
        <button className="world-ledger-close" type="button" onClick={() => navigate('map')} aria-label="收卷返回天下舆图"><i aria-hidden="true">←</i> 收卷归图</button>
      </header>

      <section className="world-ledger-conclusion">
        <div><small>本月总断</small><h2>天下大势，仍待审观</h2></div>
        <p>{conclusion}</p>
      </section>

      <div className="world-ledger-mainline">
        <section className="world-ledger-events">
          <header><small>天下变局</small><p>本月可见世界变化及其来处</p></header>
          {entries.length ? <ol>{entries.map((entry, index) => <li key={entry.id} className={`ledger-${entry.mark}`}>
            <div className="ledger-turn">{String(index + 1).padStart(2, '0')}<i /></div>
            <div><strong>{entry.title}</strong><p>{entry.summary}</p><small>推演依据：{entry.source}</small></div>
            <em>{MARK_LABEL[entry.mark]}</em>
          </li>)}</ol> : <p className="world-ledger-empty">本月尚无可写入推演卷的公开记录。</p>}
        </section>
        <aside className="world-ledger-marks" aria-label="势力研判与推演依据">
          <header><small>势力研判</small><h2>推演依据</h2></header>
          {(Object.keys(MARK_LABEL) as LedgerMark[]).map((mark) => <section key={mark} className={`mark-${mark}`}><b>{MARK_LABEL[mark]}</b><p>{mark === 'confirmed' ? '来自已确认的事实、正式文书与实际结果。' : mark === 'assessment' ? '来自有来源的情报与规则允许的分析判断。' : '来自商旅、乡谈或未经核验的外部消息。'}</p></section>)}
        </aside>
      </div>

      <section className="world-ledger-fronts">
        <header><small>区域战线</small><p>本月与天下态势有关的地方变化</p></header>
        <div>{(regionEntries.length ? regionEntries : entries.slice(0, 5)).map((entry) => <article key={`front-${entry.id}`}><h3>{entry.title}</h3><p>{entry.summary}</p><small>局势变化：{MARK_LABEL[entry.mark]}</small></article>)}</div>
      </section>
    </article>
  </main>;
}
