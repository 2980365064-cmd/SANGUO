import { useState } from 'react';
import { ArrowLeft, Feather } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { SecretChatStage } from '../components/charactersPanel/SecretChatStage';
import { ActionSealButton, AppFrame } from '../components/ui';
import { useGameStore } from '../state/gameStore';
import type { Character } from '../types';

// 同一人物复用稳定资源位时，更新这里可让已打开的密谈页在刷新后取得新立绘，避免旧图缓存。
const PORTRAIT_REVISIONS: Record<string, string> = {
  'sanguo/core_002': 'dark-ink-20260731',
  'sanguo/core_002_vertical': 'dark-ink-20260731',
  'sanguo/core_003': 'dark-ink-20260801',
  'sanguo/core_003_vertical': 'dark-ink-20260801',
  'sanguo/core_004': 'dark-ink-20260731',
  'sanguo/core_005': 'dark-ink-20260803',
  'sanguo/core_005_vertical': 'dark-ink-20260803',
};

// 密谈左侧为竖向显影区；仅当横版无法清楚呈现人物时，才使用该人物确认过的竖版备用图。
const SECRET_CHAT_PORTRAIT_IDS: Record<string, string> = {
  '关羽': 'sanguo/core_002_vertical',
  '张飞': 'sanguo/core_003_vertical',
  '诸葛亮': 'sanguo/core_005_vertical',
};

/**
 * 单独密谈 — 人物问策、获取情报、产出草案或密令
 * 流程：选择人物 → 密谈对话 → 拟入密令/方略
 */
export function SecretChat() {
  const { state, navigate } = useGameStore();
  const gameState = state.gameState;

  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null);
  const [isInConversation, setIsInConversation] = useState(false);
  const [showDraftEditor, setShowDraftEditor] = useState(false);
  const [filter, setFilter] = useState<'all' | 'active'>('active');

  // 人物列表
  const allCharacters = gameState.characters;
  const characters = filter === 'active'
    ? allCharacters.filter((c: Character) => c.power_id === 'liu_bei' && c.status === 'active')
    : allCharacters.filter((c: Character) => c.status === 'active');
  const portraitUrl = selectedCharacter
    ? (() => {
      const portraitId = SECRET_CHAT_PORTRAIT_IDS[selectedCharacter.name]
        || selectedCharacter.portrait_id
        || selectedCharacter.name;
      const revision = PORTRAIT_REVISIONS[portraitId];
      const path = `/portraits/sanguo/${portraitId.split('/').map(encodeURIComponent).join('/')}.webp`;
      return revision ? `${path}?v=${revision}` : path;
    })()
    : '';
  // 16:9 主视觉进入窄幅宣纸显影区时，按已验收画面重心微调；不以裁切容器或边框补救。
  const portraitPlacementClass = selectedCharacter
    ? ({ '关羽': 'portrait-offset-vertical-hero', '张飞': 'portrait-offset-vertical-hero', '诸葛亮': 'portrait-offset-vertical-hero' }[selectedCharacter.name] || '')
    : '';

  const selectCharacter = (character: Character) => {
    setSelectedCharacter((current) => current?.name === character.name ? null : character);
  };

  return (
    <SceneShell scene="secret">
      <AppFrame className="secret-hub" title="单独密谈" eyebrow="军府私录 · 信任与风险" back={<ActionSealButton priority="ghost" onClick={() => navigate('map')}><ArrowLeft /> 返回天下舆图</ActionSealButton>}>

        {/* 主体 */}
        <div className="secret-body">
          {!isInConversation ? (
            /* 人物选择：素材只承载案卷与札夹材质，所有名册、纸签与状态均由真实数据渲染。 */
            <section className="private-talk-dossier" aria-label="单独密谈人物名册">
              <header className="dossier-intro">
                <p>择一人而密谈，知其所志，察其所心，定策于未形。</p>
                <div className="dossier-filters" aria-label="人物范围">
                  <button className={filter === 'active' ? 'active' : ''} onClick={() => setFilter('active')}>我方名册</button>
                  <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>天下人物</button>
                </div>
              </header>

              <div className="dossier-content">
                <aside className={`minister-portrait-reveal ${selectedCharacter ? 'is-visible' : ''} ${portraitPlacementClass}`} aria-label={selectedCharacter ? `${selectedCharacter.name}立绘` : '人物立绘显影区'}>
                  {selectedCharacter && <img key={portraitUrl} src={portraitUrl} alt={`${selectedCharacter.name}立绘`} onError={(event) => { event.currentTarget.style.opacity = '0'; }} />}
                  {selectedCharacter && <div className="portrait-calligraphy" aria-label={`${selectedCharacter.name}人物题签`}><small>密谈对象</small><strong>{selectedCharacter.name}</strong><span>{selectedCharacter.office || '军府候问'}</span></div>}
                </aside>
                <section className="minister-roster" aria-label="人物名册">
                  <span className="roster-spine">人物 · 择密谈对象</span>
                  <div className="roster-lines">
                    {characters.slice(0, 12).map((c: Character) => {
                      const selected = selectedCharacter?.name === c.name;
                      return <button key={c.name} type="button" className={`minister-slip ${selected ? 'selected' : ''}`} aria-pressed={selected} onClick={() => selectCharacter(c)}>
                        <span className="minister-seal" aria-hidden="true">{c.name.charAt(0)}</span>
                        <span className="minister-slip-copy"><strong>{c.name}</strong><small>{c.office || '府中从事'}</small><em>{c.location ? `驻 · ${c.location}` : '待候军府'}</em></span>
                        <i className="selection-mark" aria-hidden="true">✓</i>
                      </button>;
                    })}
                    {characters.length === 0 && <p className="empty-hint">本卷暂无线可密谈人物</p>}
                  </div>
                </section>

                <aside className="confidential-sleeve" aria-label="密谈札记">
                  <h2>密谈札记</h2>
                  <div className="sleeve-tabs" aria-label="密谈分类"><span>军情</span><span>民生</span><span>用人</span></div>
                  <p>名签已入札夹，所问分列军情、民生、用人三签。</p>
                </aside>
              </div>

              <footer className="dossier-footer">
                <div className="dossier-material-note"><span>密局之事</span><small>言入耳目，慎之又慎</small></div>
                <button type="button" className="seal-action" disabled={!selectedCharacter} onClick={() => selectedCharacter && setIsInConversation(true)}>
                  <span className="seal-knot" aria-hidden="true" /><span><Feather aria-hidden="true" />执笔密谈</span><small>{selectedCharacter ? `与${selectedCharacter.name}私下问策` : '先择一名人物'}</small>
                </button>
              </footer>
            </section>
          ) : (
            /* 对话页：即时往来沿用微信式节奏，但每句都收在同一卷军府私札中。 */
            <SecretChatStage
              character={selectedCharacter!}
              onExit={() => setIsInConversation(false)}
            />
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
