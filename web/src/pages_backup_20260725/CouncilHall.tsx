import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, X, BookOpen } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { MinisterSelection } from '../components/councilHall/MinisterSelection';
import { CouncilHallStage } from '../components/councilHall/CouncilHallStage';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';
import { useGameStore } from '../state/gameStore';
import { getSuggestions, createSuggestion, deleteSuggestion } from '../api';
import type { Character } from '../types';

/**
 * 府堂廷议 — 多人辩论，输出建议或草案
 * 流程：选择参与者 → 开始廷议 → 产出建议 → 拟入方略
 */
export function CouncilHall() {
  const { state, navigate } = useGameStore();
  const gameState = state.gameState;

  const [stage, setStage] = useState<'selection' | 'active'>('selection');
  const [ministers, setMinisters] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<Array<{
    id: number; text: string; created_at: string; status: string;
    converted_to_intent_id?: number; source: string;
  }>>([]);
  const [showDraftEditor, setShowDraftEditor] = useState(false);
  const [draftSourceText, setDraftSourceText] = useState('');

  // 刘备势力下 active 人物
  const liuBeiMinisters = gameState.characters.filter(
    (c: Character) => c.power_id === 'liu_bei' && c.status === 'active'
  );

  // 加载建议库
  useEffect(() => {
    getSuggestions()
      .then(r => setSuggestions(r.suggestions.map((s: any) => ({ ...s, source: s.source || '廷议' }))))
      .catch(() => {});
  }, []);

  const startCouncil = (selected: string[]) => {
    setMinisters(selected);
    setStage('active');
  };

  const exitCouncil = () => {
    setStage('selection');
    setMinisters([]);
  };

  const addSuggestion = useCallback(async (text: string) => {
    try {
      const result = await createSuggestion(text, '府堂廷议');
      setSuggestions(prev => [{ ...result.suggestion, source: '府堂廷议' }, ...prev]);
    } catch (e) {
      console.error('Failed to add suggestion:', e);
    }
  }, []);

  const removeSuggestion = useCallback(async (id: number) => {
    try {
      await deleteSuggestion(id);
      setSuggestions(prev => prev.filter(s => s.id !== id));
    } catch (e) {
      console.error('Failed to remove suggestion:', e);
    }
  }, []);

  const draftFromSuggestion = (text: string) => {
    setDraftSourceText(text);
    setShowDraftEditor(true);
  };

  return (
    <SceneShell scene="council">
      <AppFrame className="council-hub" title="府堂廷议" eyebrow="议席—陈议—采纳" back={<ActionSealButton priority="ghost" onClick={() => navigate('map')}><ArrowLeft /> 返回天下舆图</ActionSealButton>} actions={suggestions.length > 0 ? <StatusMark tone="action">{suggestions.length} 条建议待阅</StatusMark> : undefined}>

        {/* 主体内容 */}
        <div className="council-body">
          {/* 廷议阶段 */}
          <div className="council-main">
            {stage === 'selection' && (
              <MinisterSelection
                ministers={liuBeiMinisters}
                onSelect={() => {}}
                onConfirm={startCouncil}
                onCancel={() => navigate('map')}
              />
            )}

            {stage === 'active' && (
              <CouncilHallStage
                ministers={ministers}
                onExit={exitCouncil}
                onAddSuggestion={addSuggestion}
              />
            )}
          </div>

          {/* 右侧建议库 */}
          {suggestions.length > 0 && (
            <aside className="council-suggestions"><PaperPanel tone="floating">
              <SectionHeading index="建议" note="可拟入方略">廷议建议库</SectionHeading>
              <div className="suggestions-list">
                {suggestions.map(s => (
                  <div key={s.id} className={`suggestion-item suggestion-${s.status}`}>
                    <p className="suggestion-text">{s.text}</p>
                    <div className="suggestion-meta">
                      <span className="suggestion-source">{s.source}</span>
                    </div>
                    <div className="suggestion-actions">
                      <ActionSealButton
                        priority="secondary"
                        onClick={() => draftFromSuggestion(s.text)}
                      >
                        <BookOpen /> 拟入方略
                      </ActionSealButton>
                      <button
                        className="remove-btn"
                        onClick={() => removeSuggestion(s.id)}
                        title="删除"
                      >
                        <X />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </PaperPanel></aside>
          )}
        </div>

        {/* 草案编辑器 */}
        {showDraftEditor && (
          <DraftEditor
            source_type="council_chat"
            draft={draftSourceText ? {
              narrative_text: draftSourceText,
              title: '',
              directive_type: 'internal',
              status: 'draft',
            } as any : undefined}
            onClose={() => { setShowDraftEditor(false); setDraftSourceText(''); }}
            onSave={() => { setShowDraftEditor(false); setDraftSourceText(''); }}
          />
        )}
      </AppFrame>
    </SceneShell>
  );
}
