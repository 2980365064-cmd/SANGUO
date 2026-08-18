import { useState, useEffect } from 'react';
import { ArrowLeft, BookOpen, Handshake, FileText } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { useGameStore } from '../state/gameStore';
import { getReactions, type ReactionEvent } from '../api';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading } from '../components/ui';

/** 外交 — 查阅外交关系、条约、使臣任务 */
export function DiplomacyPage() {
  const { state, navigate } = useGameStore();
  const [showDraft, setShowDraft] = useState(false);
  const [envoys, setEnvoys] = useState<any[]>([]);
  const [alliances, setAlliances] = useState<any[]>([]);
  const [reactions, setReactions] = useState<ReactionEvent[]>([]);

  useEffect(() => {
    fetch('/api/envoys').then(r => r.json()).then(d => setEnvoys(d.missions || [])).catch(()=>{});
    fetch('/api/diplomacy/alliances').then(r => r.json()).then(d => setAlliances(d.alliances || [])).catch(()=>{});
    void getReactions({ directive_type: 'diplomatic', limit: 8 }).then(({ reactions: rows }) => setReactions(rows)).catch(() => setReactions([]));
  }, []);

  return (
    <SceneShell scene="diplomacy">
      <AppFrame className="info-page info-page-diplomacy" title="外交档案" eyebrow="使臣 · 会盟 · 天下反应" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft/> 返回局势枢纽</ActionSealButton>} actions={<ActionSealButton priority="primary" onClick={() => setShowDraft(true)}><BookOpen/> 拟外交方略</ActionSealButton>}>
        <div className="info-body">
          <PaperPanel><SectionHeading index="使臣">使臣任务</SectionHeading>
            {envoys.length === 0 ? <p className="empty">无活跃使臣任务</p> : (
              <div className="info-list">
                {envoys.map((e: any, i: number) => (
                  <div key={i} className="info-card">
                    <strong>{e.envoy} → {e.target_power}</strong>
                    <span>{e.goal} · {e.status}</span>
                  </div>
                ))}
              </div>
            )}
          </PaperPanel>
          <PaperPanel><SectionHeading index="反应">诸侯反应与关系压力</SectionHeading>
            {reactions.length === 0 ? <p className="empty">暂无已发生的外交反应</p> : <div className="info-list">
              {reactions.map((item) => <div key={item.id} className="info-card"><strong>{item.actor} · {item.target || '外交局势'}</strong><span>{item.outcome_summary}（批次 #{item.batch_id}）</span></div>)}
            </div>}
          </PaperPanel>
          <PaperPanel><SectionHeading index="会盟">会盟</SectionHeading>
            {alliances.length === 0 ? <p className="empty">无活跃会盟</p> : (
              <div className="info-list">
                {alliances.map((a: any, i: number) => (
                  <div key={i} className="info-card">
                    <strong>{a.initiator}</strong>
                    <span>{a.status} · 参与方: {(a.participants||[]).join(', ')}</span>
                  </div>
                ))}
              </div>
            )}
          </PaperPanel>
        </div>
        {showDraft && <DraftEditor source_type="manual"
          draft={{ directive_type: 'diplomatic', title: '', status: 'draft' } as any}
          onClose={() => setShowDraft(false)} onSave={() => setShowDraft(false)} />}
      </AppFrame>
    </SceneShell>
  );
}
