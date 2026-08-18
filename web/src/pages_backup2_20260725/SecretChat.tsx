import { useState } from 'react';
import { ArrowLeft, BookOpen } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { SecretChatStage } from '../components/charactersPanel/SecretChatStage';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';
import { useGameStore } from '../state/gameStore';
import type { Character } from '../types';

/**
 * 单独密谈 — 人物问策、获取情报、产出草案或密令
 * 流程：选择人物 → 密谈对话 → 拟入密令/方略
 */
export function SecretChat() {
  const { state, navigate } = useGameStore();
  const gameState = state.gameState;

  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null);
  const [showDraftEditor, setShowDraftEditor] = useState(false);
  const [filter, setFilter] = useState<'all' | 'active'>('active');

  // 人物列表
  const allCharacters = gameState.characters;
  const characters = filter === 'active'
    ? allCharacters.filter((c: Character) => c.power_id === 'liu_bei' && c.status === 'active')
    : allCharacters.filter((c: Character) => c.status === 'active');

  return (
    <SceneShell scene="secret">
      <AppFrame className="secret-hub" title="单独密谈" eyebrow="书案私录 · 信任与风险" back={<ActionSealButton priority="ghost" onClick={() => navigate('map')}><ArrowLeft /> 返回天下舆图</ActionSealButton>} actions={selectedCharacter ? <ActionSealButton priority="secondary" onClick={() => setShowDraftEditor(true)}><BookOpen /> 拟入方略</ActionSealButton> : <StatusMark tone="neutral">选择一人入席</StatusMark>}>

        {/* 主体 */}
        <div className="secret-body">
          {!selectedCharacter ? (
            /* 人物选择 */
            <PaperPanel className="character-select" tone="floating">
              <div className="select-header">
                <SectionHeading index="人物" note={`${characters.length} 人可见`}>选择密谈对象</SectionHeading>
                <div className="filter-tabs">
                  <button
                    className={filter === 'active' ? 'active' : ''}
                    onClick={() => setFilter('active')}
                  >
                    我方人物
                  </button>
                  <button
                    className={filter === 'all' ? 'active' : ''}
                    onClick={() => setFilter('all')}
                  >
                    天下人物
                  </button>
                </div>
              </div>
              <div className="character-grid">
                {characters.map((c: Character) => (
                  <button
                    key={c.name}
                    className="character-card"
                    onClick={() => setSelectedCharacter(c)}
                  >
                    <div className="char-avatar">
                      {c.name.charAt(0)}
                    </div>
                    <div className="char-info">
                      <strong>{c.name}</strong>
                      <span>{c.office || '无职'}</span>
                      <span className="char-location">{c.location || ''}</span>
                    </div>
                  </button>
                ))}
                {characters.length === 0 && (
                  <p className="empty-hint">暂无可选人物</p>
                )}
              </div>
            </PaperPanel>
          ) : (
            /* 密谈对话 */
            <div className="chat-area">
              <div className="chat-character-bar">
                <div className="char-badge">
                  <span className="char-avatar-sm">{selectedCharacter.name.charAt(0)}</span>
                  <div>
                    <strong>{selectedCharacter.name}</strong>
                    <span>{selectedCharacter.office || ''} · {selectedCharacter.location || ''}</span>
                  </div>
                </div>
                <button className="change-char-btn" onClick={() => setSelectedCharacter(null)}>
                  更换人物
                </button>
              </div>
              <SecretChatStage
                character={selectedCharacter}
                onExit={() => setSelectedCharacter(null)}
              />
            </div>
          )}
        </div>

        {/* 草案编辑器 */}
        {showDraftEditor && (
          <DraftEditor
            source_type="secret_chat"
            draft={selectedCharacter ? {
              assignee: selectedCharacter.name,
              title: '',
              directive_type: 'secret',
              status: 'draft',
            } as any : undefined}
            onClose={() => setShowDraftEditor(false)}
            onSave={() => setShowDraftEditor(false)}
          />
        )}
      </AppFrame>
    </SceneShell>
  );
}
