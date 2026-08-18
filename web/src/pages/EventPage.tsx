import { useState, useEffect } from 'react';
import { ArrowLeft, BookOpen, AlertTriangle, CheckCircle } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { useGameStore } from '../state/gameStore';
import { createDirectiveDraft } from '../api/directiveDrafts';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';

/** 事件详情 — 查看活跃事件并处理 */
export function EventPage() {
  const { navigate } = useGameStore();
  const [events, setEvents] = useState<any[]>([]);
  const [showDraft, setShowDraft] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);

  useEffect(() => {
    fetch('/api/random-events').then(r => r.json()).then(d => setEvents(d.events || [])).catch(()=>{});
  }, []);

  const handleSelectOption = async (event: any, choice: number) => {
    const option = String(event.options?.[choice - 1] || `方案 ${choice}`);
    await createDirectiveDraft({
      source_type: 'manual',
      directive_type: 'other',
      title: `处理事件：${event.title}`,
      target: `随机事件#${event.id}`,
      narrative_text: `${event.description}\n拟采用：${option}`,
      resources_json: JSON.stringify({
        sub_type: 'random_event_resolution',
        random_event_id: event.id,
        choice,
      }),
    });
    setSelectedEvent(null);
    navigate('directive');
  };

  return (
    <SceneShell scene="event-urgent">
      <AppFrame className="info-page info-page-event" title="待议事件" eyebrow="事实已载 · 处置须拟入方略" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft/> 返回局势枢纽</ActionSealButton>} actions={selectedEvent ? <ActionSealButton priority="primary" onClick={() => setShowDraft(true)}><BookOpen/> 拟入草案</ActionSealButton> : <StatusMark tone="neutral">选择一项事件</StatusMark>}>
        <div className="info-body">
          <PaperPanel className="info-list" tone="floating"><SectionHeading index="待议" note={`${events.length} 项`}>本月事件</SectionHeading>
            {events.length === 0 ? (
              <p className="empty"><CheckCircle/> 暂无活跃事件</p>
            ) : events.map((ev: any) => (
              <div key={ev.id} className={`info-card ${selectedEvent?.id===ev.id?'selected':''}`}
                onClick={() => setSelectedEvent(ev)}>
                <div className="card-icon"><AlertTriangle/></div>
                <div className="card-info">
                  <strong>{ev.title}</strong>
                  <span>{ev.description}</span>
                </div>
              </div>
            ))}
          </PaperPanel>
          {selectedEvent && (
            <PaperPanel className="info-detail" tone="focus">
              <SectionHeading index="裁处">{selectedEvent.title}</SectionHeading>
              <p>{selectedEvent.description}</p>
              {selectedEvent.options?.length > 0 && (
                <div className="event-options">
                  {selectedEvent.options.map((opt: string, i: number) => (
                    <button key={i} className="option-btn primary"
                      onClick={() => void handleSelectOption(selectedEvent, i + 1)}>
                      拟定：{opt}
                    </button>
                  ))}
                </div>
              )}
            </PaperPanel>
          )}
        </div>
        {showDraft && <DraftEditor source_type="manual"
          draft={selectedEvent ? { title: `处理：${selectedEvent.title}`, directive_type: 'other', status: 'draft' } as any : undefined}
          onClose={() => setShowDraft(false)} onSave={() => setShowDraft(false)} />}
      </AppFrame>
    </SceneShell>
  );
}
