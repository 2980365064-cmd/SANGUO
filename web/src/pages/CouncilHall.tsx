import { useState, useEffect, useCallback } from 'react';
import { DraftEditor } from '../components/DraftEditor';
import { MinisterSelection } from '../components/councilHall/MinisterSelection';
import { CouncilHallStage } from '../components/councilHall/CouncilHallStage';
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
  const [councilTopic, setCouncilTopic] = useState('');
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

  const startCouncil = (selected: string[], topic: string) => {
    setMinisters(selected);
    setCouncilTopic(topic);
    setStage('active');
  };

  const exitCouncil = () => {
    setStage('selection');
    setMinisters([]);
    setCouncilTopic('');
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

  // 正式廷议不再落在天下舆图的工作窗中，而是进入完整府堂场景。
  if (stage === 'active') {
    return <>
      <CouncilHallStage
        ministers={ministers}
        initialTopic={councilTopic}
        onExit={exitCouncil}
        onAddSuggestion={addSuggestion}
        suggestions={suggestions}
        onRemoveSuggestion={removeSuggestion}
        onDraftSuggestion={draftFromSuggestion}
      />
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
    </>;
  }

  return <main className="council-scroll-page">
    <MinisterSelection
      ministers={liuBeiMinisters}
      onSelect={() => {}}
      onConfirm={startCouncil}
      onCancel={() => navigate('map')}
    />
  </main>;
}
