import { useState, useEffect } from 'react';
import { ArrowLeft, ScrollText } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { useGameStore } from '../state/gameStore';
import { getHistoricalEventCards, getReactions, type HistoricalEventCard, type ReactionEvent } from '../api';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading } from '../components/ui';

/** 史册 — 查阅历史月报、事件编年 */
export function HistoryBook() {
  const { state, navigate } = useGameStore();
  const [reports, setReports] = useState<any[]>([]);
  const [reactions, setReactions] = useState<ReactionEvent[]>([]);
  const [eventCards, setEventCards] = useState<HistoricalEventCard[]>([]);

  useEffect(() => {
    fetch('/api/history/turns').then(r => r.json()).then(d => setReports(d.turns || [])).catch(()=>{});
    void getReactions({ limit: 20 }).then(({ reactions: rows }) => setReactions(rows.filter((item) => item.reaction_level === 'major'))).catch(() => setReactions([]));
    void getHistoricalEventCards().then(({ events }) => setEventCards(events)).catch(() => setEventCards([]));
  }, []);

  return (
    <SceneShell scene="history">
      <AppFrame className="info-page" title="月度史册" eyebrow="已发生之事 · 天下余波" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft/> 返回局势枢纽</ActionSealButton>}>
        <div className="info-body">
          <PaperPanel><SectionHeading index="月报">历史月报</SectionHeading>
            {reports.length === 0 ? <p className="empty">暂无历史记录</p> : (
              <div className="info-list">
                {reports.map((t: any, i: number) => (
                  <div key={i} className="info-card">
                    <strong>回合 {t.turn}</strong>
                    <span>{t.year}年 · {t.period}月</span>
                  </div>
                ))}
              </div>
            )}
          </PaperPanel>
          <PaperPanel><SectionHeading index="编年">天下反应编年</SectionHeading>
            {reactions.length === 0 ? <p className="empty">暂无重大天下反应。</p> : <div className="info-list">
              {reactions.map((item) => <div key={item.id} className="info-card"><strong>第 {item.turn} 回合 · {item.actor}</strong><span>{item.outcome_summary}</span></div>)}
            </div>}
          </PaperPanel>
          <PaperPanel><SectionHeading index="事件">历史事件卡审计</SectionHeading>
            {eventCards.length === 0 ? <p className="empty">暂无可审计的历史事件卡。</p> : <div className="info-list">
              {eventCards.map((item) => <article key={item.id} className="info-card">
                <strong>{item.title} · {item.window}</strong>
                <span>状态：{item.status}{item.variant_id ? `；玩家结果：${item.variant_id}` : ''}</span>
                <span>人物／势力前提：{item.required_powers.join('、') || '无'}；领土前提：{item.required_regions.join('、') || '无'}。</span>
                <span>替代角色：{Object.entries(item.alternative_roles || {}).map(([role, names]) => `${role}（${names.join('、')}）`).join('；') || '无'}。</span>
                <span>{item.reason ? `改写或失效原因：${item.reason}` : '尚未发生改写或失效。'}{item.changed_turn ? `（关联回合 #${item.changed_turn}）` : ''}</span>
              </article>)}
            </div>}
          </PaperPanel>
          {state.gameState.ending && <PaperPanel><SectionHeading index="封卷">结局依据 · {state.gameState.ending.label}</SectionHeading>
            <div className="info-card"><strong>{state.gameState.ending.summary}</strong><span>结局路径：{state.gameState.ending.route}</span>
              {state.gameState.ending.evidence.length ? <ul>{state.gameState.ending.evidence.map((item: any, index) => <li key={index}>{item.kind || '规则'}：{item.detail || JSON.stringify(item)}</li>)}</ul> : <span>此旧存档未保存结构化依据。</span>}
            </div>
          </PaperPanel>}
        </div>
      </AppFrame>
    </SceneShell>
  );
}
