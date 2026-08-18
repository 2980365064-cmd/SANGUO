import { useState } from 'react';
import { ArrowLeft, BookOpen, Building2 } from 'lucide-react';
import { SceneShell } from '../components/SceneShell';
import { DraftEditor } from '../components/DraftEditor';
import { useGameStore } from '../state/gameStore';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';

/** 城池治理 — 查阅各城人口、支持度、治理状态 */
export function CityGovernance() {
  const { state, navigate } = useGameStore();
  const gameState = state.gameState;
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [showDraft, setShowDraft] = useState(false);

  const regions = gameState.map?.nodes?.filter((n: any) => n.kind === 'city') || [];

  return (
    <SceneShell scene="city">
      <AppFrame className="info-page" title="城池治理" eyebrow="地方档案 · 治理待议" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft/> 返回局势枢纽</ActionSealButton>} actions={selectedRegion ? <ActionSealButton priority="primary" onClick={() => setShowDraft(true)}><BookOpen/> 拟入方略</ActionSealButton> : <StatusMark tone="neutral">选择一座城池</StatusMark>}>
        <div className="info-body">
          <PaperPanel className="info-list" tone="floating"><SectionHeading index="州郡" note={`${regions.length} 处`}>城池目录</SectionHeading>
            {regions.map((node: any) => (
              <button key={node.id} className={`info-card ${selectedRegion === node.id ? 'selected' : ''}`}
                onClick={() => setSelectedRegion(node.id)}>
                <div className="card-icon"><Building2/></div>
                <div className="card-info">
                  <strong>{node.name}</strong>
                  <span>{node.province || ''} · {node.controlled_by || ''}</span>
                </div>
              </button>
            ))}
          </PaperPanel>
          {selectedRegion && (
            <PaperPanel className="info-detail" tone="focus">
              <SectionHeading index="治理">{regions.find((n: any) => n.id === selectedRegion)?.name || selectedRegion}</SectionHeading>
              <p>人口、支持度、治理状态等详情将在 P1 后续版本中展示。</p>
            </PaperPanel>
          )}
        </div>
        {showDraft && <DraftEditor source_type="map_detail"
          draft={selectedRegion ? { target: selectedRegion, directive_type: 'internal', title: '', status: 'draft' } as any : undefined}
          onClose={() => setShowDraft(false)} onSave={() => setShowDraft(false)} />}
      </AppFrame>
    </SceneShell>
  );
}
