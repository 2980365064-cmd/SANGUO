import { useState } from 'react';
import { ArrowLeft, BookOpen, MapPinned, Shield, Users } from 'lucide-react';
import { DraftEditor } from '../components/DraftEditor';
import { StrategicMap } from '../components/map';
import { SceneShell } from '../components/SceneShell';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';
import { useGameStore } from '../state/gameStore';

/** 地图保持主体；选中节点仅生成可读的地方档案，所有变化仍经方略下达。 */
export function MapDetail() {
  const { state, dispatch, navigate } = useGameStore();
  const gameState = state.gameState;
  const [selectedNode, setSelectedNode] = useState(state.mapFocusNodeId || gameState.map.nodes.find((node) => node.id === 'jiangxia')?.id || gameState.map.nodes[0]?.id || '');
  const [selectedArmyId, setSelectedArmyId] = useState('');
  const [showDraftEditor, setShowDraftEditor] = useState(false);
  const node = gameState.map.nodes.find((item) => item.id === selectedNode);
  const armies = gameState.armies.filter((army) => army.station_node === selectedNode);
  const relatedCharacters = gameState.characters.filter((character) => node && character.status === 'active' && character.location.includes(node.name));
  const power = gameState.powers.find((item) => item.id === node?.controller);
  const canDraft = Boolean(node);

  return <SceneShell scene="map"><AppFrame className="map-hub" title="天下态势" eyebrow="天下舆图 · 地方档案" back={<ActionSealButton priority="ghost" onClick={() => navigate('situation')}><ArrowLeft /> 返回局势枢纽</ActionSealButton>} actions={canDraft ? <ActionSealButton priority="primary" onClick={() => setShowDraftEditor(true)}><BookOpen /> 拟入方略</ActionSealButton> : undefined}>
    <div className="map-area"><StrategicMap state={gameState} selectedId={selectedNode} selectedArmyId={selectedArmyId} onSelect={(id) => { setSelectedNode(id); setSelectedArmyId(''); }} onState={(next) => dispatch({ type: 'SET_GAME_STATE', payload: next })} /></div>
    <aside className="map-dossier" aria-label="地方档案">
      <PaperPanel tone="floating"><SectionHeading index="概况" note={node?.province || '未选择'}>{node?.name || '请选择地图节点'}</SectionHeading>{node ? <><p className="map-dossier-status"><StatusMark tone={node.controller === 'liu_bei' ? 'complete' : 'neutral'}>{power?.name || '无主'}据有</StatusMark></p><p>{node.status || '暂无地方纪事。'}</p><dl><div><dt>民心</dt><dd>{node.public_support}</dd></div><div><dt>动乱</dt><dd>{node.unrest}</dd></div><div><dt>军压</dt><dd>{node.military_pressure}</dd></div></dl></> : <p className="empty-state">从州、郡或城镇图层选择一个节点。</p>}</PaperPanel>
      <PaperPanel><SectionHeading index="人物" note={`${relatedCharacters.length} 人相关`}>相关人物</SectionHeading>{relatedCharacters.length ? <ul className="map-dossier-people">{relatedCharacters.map((character) => <li key={character.name}><strong>{character.name}</strong><small>{character.office || character.political_group || '待察身份'}</small></li>)}</ul> : <p className="empty-state">本地官佐与人物关系尚无可核记录。</p>}</PaperPanel>
      <PaperPanel><SectionHeading index="军政" note={`${armies.length} 支驻军`}>驻军与军压</SectionHeading>{armies.length ? <ul className="map-dossier-armies">{armies.map((army) => <li key={army.id}><button type="button" onClick={() => setSelectedArmyId(army.id)} aria-pressed={selectedArmyId === army.id}><span><strong>{army.name}</strong><small>{army.commander} · {army.manpower.toLocaleString()} 人</small></span><Shield /></button></li>)}</ul> : <p className="empty-state">此地暂无已知驻军。</p>}</PaperPanel>
      <PaperPanel tone="archive"><SectionHeading index="行动">军府处置</SectionHeading><p>地图只提供已知地方事实；行军、经营、外交与任命均须先拟入方略。</p><ActionSealButton priority="primary" disabled={!canDraft} onClick={() => setShowDraftEditor(true)}><MapPinned /> 以此为目标拟定方略</ActionSealButton></PaperPanel>
    </aside>
    {showDraftEditor && <DraftEditor source_type="map_detail" draft={node ? { target: node.name, title: '', directive_type: 'internal', status: 'draft' } as any : undefined} onClose={() => setShowDraftEditor(false)} onSave={() => setShowDraftEditor(false)} />}
  </AppFrame></SceneShell>;
}
