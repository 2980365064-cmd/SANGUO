import { useState } from 'react';
import { ArrowLeft, BookOpen, Shield, Swords } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { useGameStore } from '../state/gameStore';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';
import type { Army } from '../types';

/** 军队信息 — 查阅军力、编制、位置 */
export function ArmyInfo() {
  const { state, navigate } = useGameStore();
  const gameState = state.gameState;
  const [selectedArmy, setSelectedArmy] = useState<Army | null>(null);
  const [showDraft, setShowDraft] = useState(false);

  const armies = gameState.armies || [];

  return (
    <SceneShell scene="army">
      <AppFrame className="info-page" title="军队信息" eyebrow="军府档案 · 编制与补给" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft/> 返回局势枢纽</ActionSealButton>} actions={selectedArmy ? <ActionSealButton priority="primary" onClick={() => setShowDraft(true)}><BookOpen/> 拟入方略</ActionSealButton> : <StatusMark tone="neutral">选择一支军队</StatusMark>}>
        <div className="info-body">
          <PaperPanel className="info-list" tone="floating"><SectionHeading index="军府" note={`${armies.length} 支`}>军队名录</SectionHeading>
            {armies.map((army: Army) => (
              <button key={army.id} className={`info-card ${selectedArmy?.id === army.id ? 'selected' : ''}`}
                onClick={() => setSelectedArmy(army)}>
                <div className="card-icon"><Shield/></div>
                <div className="card-info">
                  <strong>{army.name || army.id}</strong>
                  <span>{army.station_node || ''} · 兵力 {army.manpower || 0}</span>
                  <span className="card-stat">士气 {army.morale || 0} · 补给 {army.supply || 0}</span>
                </div>
              </button>
            ))}
          </PaperPanel>
          {selectedArmy && (
            <PaperPanel className="info-detail" tone="focus">
              <SectionHeading index="编制">{selectedArmy.name || selectedArmy.id}</SectionHeading>
              <dl>
                <dt>驻地</dt><dd>{selectedArmy.station_node || '未知'}</dd>
                <dt>兵力</dt><dd>{selectedArmy.manpower || 0}</dd>
                <dt>士气</dt><dd>{selectedArmy.morale || 0}</dd>
                <dt>训练</dt><dd>{selectedArmy.training || 0}</dd>
                <dt>补给</dt><dd>{selectedArmy.supply || 0}</dd>
                <dt>装备</dt><dd>{selectedArmy.equipment || 0}</dd>
              </dl>
            </PaperPanel>
          )}
        </div>
        {showDraft && <DraftEditor source_type="map_detail"
          draft={selectedArmy ? { assignee: selectedArmy.id, target: selectedArmy.station_node || '', directive_type: 'military', title: '', status: 'draft' } as any : undefined}
          onClose={() => setShowDraft(false)} onSave={() => setShowDraft(false)} />}
      </AppFrame>
    </SceneShell>
  );
}
