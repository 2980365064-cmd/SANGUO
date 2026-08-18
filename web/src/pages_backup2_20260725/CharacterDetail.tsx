import { useState, useEffect } from 'react';
import { ArrowLeft, BookOpen, UserRoundCog } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { useGameStore } from '../state/gameStore';
import type { Character } from '../types';
import { getReactions, type ReactionEvent } from '../api';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';

/** 人物详情 — 查阅人物档案 */
export function CharacterDetail() {
  const { state, navigate } = useGameStore();
  const gameState = state.gameState;
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [showDraft, setShowDraft] = useState(false);
  const [filter, setFilter] = useState<'all' | 'liu_bei'>('liu_bei');
  const [reactions, setReactions] = useState<ReactionEvent[]>([]);

  useEffect(() => {
    if (!selectedChar) { setReactions([]); return; }
    void getReactions({ character: selectedChar.name, limit: 6 }).then(({ reactions: rows }) => setReactions(rows)).catch(() => setReactions([]));
  }, [selectedChar?.name]);

  const chars = filter === 'liu_bei'
    ? gameState.characters.filter((c: Character) => c.power_id === 'liu_bei' && c.status === 'active')
    : gameState.characters.filter((c: Character) => c.status === 'active');

  return (
    <SceneShell scene="character">
      <AppFrame className="info-page info-page-character" title="人物档案" eyebrow="人物关系 · 心迹与反应" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft/> 返回局势枢纽</ActionSealButton>} actions={<div className="filter-tabs">
            <button className={filter==='liu_bei'?'active':''} onClick={()=>setFilter('liu_bei')}>我方</button>
            <button className={filter==='all'?'active':''} onClick={()=>setFilter('all')}>全部</button>
          </div>}>
        <div className="info-body">
          <PaperPanel className="info-list" tone="floating"><SectionHeading index="人物" note={`${chars.length} 人`}>可见人物</SectionHeading>
            {chars.map((c: Character) => (
              <button key={c.name} className={`info-card ${selectedChar?.name===c.name?'selected':''}`}
                onClick={() => setSelectedChar(c)}>
                <div className="card-icon"><UserRoundCog/></div>
                <div className="card-info">
                  <strong>{c.name}</strong>
                  <span>{c.office || '无职'} · {c.location || ''}</span>
                </div>
              </button>
            ))}
          </PaperPanel>
          {selectedChar && (
            <PaperPanel className="info-detail" tone="focus">
              <div className="info-detail-heading"><SectionHeading index="档案">{selectedChar.name}</SectionHeading><ActionSealButton priority="secondary" onClick={() => setShowDraft(true)}><BookOpen/> 拟入方略</ActionSealButton></div>
              <dl>
                <dt>职务</dt><dd>{selectedChar.office || '无'}</dd>
                <dt>所在地</dt><dd>{selectedChar.location || '未知'}</dd>
                <dt>势力</dt><dd>{selectedChar.power_id || ''}</dd>
                <dt>状态</dt><dd>{selectedChar.status || ''}</dd>
                <dt>忠诚</dt><dd>{selectedChar.loyalty_status ?? '未详'}</dd>
              </dl>
              {selectedChar.loyalty_recent?.length ? <section className="character-recent-loyalty">
                <h3>近日心迹</h3>
                {selectedChar.loyalty_recent.map((item: any, index: number) => <p key={index}>{item.delta > 0 ? '+' : ''}{item.delta} · {item.reason}</p>)}
              </section> : null}
              <section className="character-recent-loyalty">
                <h3>近日天下反应</h3>
                {reactions.length ? reactions.map((item) => <p key={item.id}>{item.outcome_summary}（批次 #{item.batch_id}）</p>) : <p>暂无可见反应。</p>}
              </section>
            </PaperPanel>
          )}
        </div>
        {showDraft && <DraftEditor source_type="manual"
          draft={selectedChar ? { assignee: selectedChar.name, directive_type: 'internal', title: '', status: 'draft' } as any : undefined}
          onClose={() => setShowDraft(false)} onSave={() => setShowDraft(false)} />}
      </AppFrame>
    </SceneShell>
  );
}
