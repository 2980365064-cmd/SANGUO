import { useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, BookOpen, Handshake, Map as MapIcon, ScrollText, Shield, Swords, UserRoundCog, Users } from 'lucide-react';
import { getReactions, type ReactionEvent } from '../api';
import { listDirectiveDrafts } from '../api/directiveDrafts';
import { DisplaySettingsPanel } from '../components/DisplaySettings';
import { DraftEditor } from '../components/DraftEditor';
import { MetricBar } from '../components/hud';
import { SceneShell } from '../components/SceneShell';
import { ActionSealButton, PaperPanel, SectionHeading, StatusMark } from '../components/ui';
import { useGameStore } from '../state/gameStore';
import type { ExternalIntelligence } from '../types';
import type { PageType } from '../state/gameStore';

type AgendaItem = { id: string; title: string; summary: string; tone: 'action' | 'warning' | 'danger'; action: string; page?: PageType; draft?: any };

/** 玩家每月由待议事项进入廷议、密谈、方略与月结；不在本页直接结算世界事实。 */
export function SituationHub() {
  const { state, dispatch, navigate } = useGameStore();
  const gameState = state.gameState;
  const [showDraftEditor, setShowDraftEditor] = useState(false);
  const [identityDraft, setIdentityDraft] = useState<any>(null);
  const [reactions, setReactions] = useState<ReactionEvent[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const ended = Boolean(gameState.ending);
  const world = (gameState as any).world || { incidents: [], memorials: [], intelligence: [] };

  useEffect(() => {
    listDirectiveDrafts({ turn: gameState.turn.turn }).then((result) => dispatch({ type: 'SET_DRAFTS', payload: result.drafts })).catch(() => undefined);
    getReactions({ limit: 3 }).then(({ reactions: rows }) => setReactions(rows)).catch(() => setReactions([]));
  }, [dispatch, gameState.turn.turn]);

  const agenda = useMemo<AgendaItem[]>(() => {
    const rows: AgendaItem[] = [];
    const pendingReaction = reactions.find((item) => item.status === 'pending_decision');
    const incident = (world.incidents || []).find((item: any) => item.policy_pending || item.tier === 'dramatic');
    const memorial = (world.memorials || [])[0];
    if (pendingReaction) rows.push({ id: `reaction-${pendingReaction.id}`, title: '天下反应待裁断', summary: pendingReaction.outcome_summary || '已有重大反应等待军府定夺。', tone: 'warning', action: '查看月报与裁断', page: 'report' });
    if (incident) rows.push({ id: `incident-${incident.id}`, title: incident.title, summary: incident.summary || '区域局势需要军府审视。', tone: incident.tier === 'dramatic' ? 'danger' : 'warning', action: '入廷议', page: 'council' });
    if (memorial) rows.push({ id: `memorial-${memorial.id}`, title: `${memorial.minister_name}《${memorial.title}》`, summary: memorial.summary, tone: 'action', action: '请诸臣陈议', page: 'council' });
    if (!rows.length && !ended) rows.push({ id: 'default', title: '军府本月待议', summary: '暂无紧急奏议。可据地图、廷议或密谈形成下一道方略。', tone: 'action', action: '拟定方略' });
    return rows.slice(0, 3);
  }, [ended, reactions, world.incidents, world.memorials]);

  const intel = world.intelligence as ExternalIntelligence[];
  const chronicle = [
    ...(world.memorials || []).slice(0, 2).map((item: any) => ({ id: `memorial-${item.id}`, label: '奏议', title: `${item.minister_name}《${item.title}》`, summary: item.summary, tone: 'action' as const })),
    ...intel.filter((item) => item.verification_status !== 'refuted' && item.verification_status !== 'expired').slice(0, 2).map((item) => ({ id: `intel-${item.id}`, label: item.visibility === 'confirmed' ? '确报' : item.visibility === 'assessment' ? '研判' : '传闻', title: item.title, summary: `可信度 ${item.reliability} · ${item.source_type}`, tone: item.visibility === 'confirmed' ? 'complete' as const : 'warning' as const })),
    ...reactions.slice(0, 1).map((item) => ({ id: `reaction-log-${item.id}`, label: '天下反应', title: item.target, summary: item.outcome_summary || '近月暂无显著反应。', tone: item.status === 'pending_decision' ? 'warning' as const : 'neutral' as const })),
  ].slice(0, 5);
  const activeFactions = gameState.long_term.factions.filter((item) => item.status === 'active');
  const activeDrafts = state.drafts.filter((draft) => draft.status !== 'issued');

  const openAgenda = (item: AgendaItem) => {
    if (item.page) { navigate(item.page); return; }
    if (item.draft) setIdentityDraft(item.draft);
    setShowDraftEditor(true);
  };

  return <SceneShell scene="map"><div className="situation-hub-root">
    <MetricBar state={gameState} />
    <div className="situation-hub-body situation-hub-rebuild">
      <main className="situation-main">
        <header className="situation-header"><div><small>局势枢纽</small><h2>本月要议</h2><span className="situation-date">{gameState.turn.year}年{gameState.turn.period}月 · 第{gameState.turn.turn}回合</span></div><ActionSealButton priority="ghost" onClick={() => setShowSettings(true)}>显示设置</ActionSealButton></header>
        {ended && <PaperPanel className="ending-notice" tone="archive"><SectionHeading index="封卷">结局 · {gameState.ending?.label}</SectionHeading><p>{gameState.ending?.summary}</p><p>此局已封卷：仍可查阅史册，但不能再新建、审阅或颁行方略。</p><ActionSealButton priority="secondary" onClick={() => navigate('history')}>查看结局依据与史册</ActionSealButton></PaperPanel>}
        <PaperPanel className="monthly-agenda" tone="focus"><SectionHeading index="当月" note={`${agenda.length} 项待议`}>军府案头</SectionHeading><div className="agenda-list">{agenda.map((item, index) => <article key={item.id} className={index === 0 ? 'agenda-item agenda-primary' : 'agenda-item'}><StatusMark tone={item.tone}>{index === 0 ? '首要待议' : '待议'}</StatusMark><div><h3>{item.title}</h3><p>{item.summary}</p></div><ActionSealButton priority={index === 0 ? 'primary' : 'secondary'} disabled={ended} onClick={() => openAgenda(item)}>{item.action}</ActionSealButton></article>)}</div></PaperPanel>
        <PaperPanel className="situation-reputation"><SectionHeading index="天下口碑" note={`当前 ${gameState.long_term.reputation.score}`}>仁义与名分</SectionHeading><p>{gameState.long_term.reputation.recent[0]?.summary || '尚无足以传遍天下的口碑变动。'}</p><p className="overview-hint">{gameState.identity.stage} · {gameState.identity.legitimacy}。{gameState.identity.political_pressure}</p>{!ended && gameState.identity.available_action && <ActionSealButton priority="secondary" onClick={() => { const emperor = gameState.identity.available_action === 'proclaim_emperor'; setIdentityDraft({ title: emperor ? '宣告即帝位' : '进位汉中王', directive_type: 'other', narrative_text: `宣称${gameState.identity.next_stage}。${gameState.identity.political_pressure}`, resources_json: JSON.stringify({ sub_type: 'identity_promotion', identity_action: gameState.identity.available_action }), status: 'draft' }); setShowDraftEditor(true); }}>拟定{gameState.identity.next_stage}方略</ActionSealButton>}</PaperPanel>
        <section className="situation-actions"><SectionHeading index="行动">印章行动栏</SectionHeading><div className="action-grid"><button className="action-btn" disabled={ended} onClick={() => navigate('council')}><Users /><span>府堂廷议</span><small>群臣辩论，形成建议</small></button><button className="action-btn" disabled={ended} onClick={() => navigate('secret')}><UserRoundCog /><span>单独密谈</span><small>私下问策，获取情报</small></button><button className="action-btn" onClick={() => navigate('map')}><MapIcon /><span>察看地图</span><small>查阅城池、军政态势</small></button><ActionSealButton priority="primary" className="action-btn" disabled={ended} onClick={() => setShowDraftEditor(true)}><BookOpen /><span>拟定方略</span><small>本月唯一主行动</small></ActionSealButton></div></section>
      </main>
      <aside className="situation-side-chronicle"><PaperPanel className="chronicle-panel" tone="floating"><SectionHeading index="编年">朝局与情报</SectionHeading>{chronicle.length ? <ol>{chronicle.map((item) => <li key={item.id}><StatusMark tone={item.tone}>{item.label}</StatusMark><strong>{item.title}</strong><p>{item.summary}</p></li>)}</ol> : <p className="empty-state">本月暂无新近奏议或外势报告。</p>}</PaperPanel><PaperPanel className="faction-panel"><SectionHeading index="人物">朝局概览</SectionHeading><p>{activeFactions.map((item) => item.label).join('、') || '朝局尚待形成'}</p><p className="overview-hint">{gameState.long_term.loyalty_risks.length ? `需留意：${gameState.long_term.loyalty_risks.map((item) => item.name).join('、')}` : '暂未发现明显的忠诚风险。'}</p></PaperPanel><PaperPanel className="situation-book" tone="archive"><SectionHeading index="方略">本月草案</SectionHeading><p>{activeDrafts.length ? `尚有 ${activeDrafts.length} 项草案待审阅。` : '尚未拟定军府方略。'}</p><ActionSealButton priority="secondary" disabled={ended} onClick={() => navigate(activeDrafts.length ? 'directive' : 'directive')}>{activeDrafts.length ? '查阅方略簿' : '新建方略'}</ActionSealButton><ActionSealButton priority="ghost" disabled={!activeDrafts.length || ended} onClick={() => navigate('review')}>审阅与颁令</ActionSealButton></PaperPanel></aside>
    </div>
    <nav className="situation-dock" aria-label="功能入口"><button onClick={() => navigate('council')} title="府堂廷议"><Users /><span>廷议</span></button><button onClick={() => navigate('secret')} title="单独密谈"><UserRoundCog /><span>密谈</span></button><button onClick={() => navigate('map')} title="地图详情"><MapIcon /><span>地图</span></button><button onClick={() => navigate('directive')} title="方略簿"><ScrollText /><span>方略</span></button><button onClick={() => navigate('review')} title="审阅与颁令"><Swords /><span>颁令</span></button><button onClick={() => navigate('report')} title="每月总计"><Activity /><span>月报</span></button><button onClick={() => navigate('army')} title="军队信息"><Shield /><span>军队</span></button><button onClick={() => navigate('diplomacy')} title="外交"><Handshake /><span>外交</span></button><button onClick={() => navigate('event')} title="事件"><AlertTriangle /><span>事件</span></button></nav>
    {showDraftEditor && <DraftEditor source_type="manual" draft={identityDraft || undefined} onClose={() => { setShowDraftEditor(false); setIdentityDraft(null); }} onSave={() => { setIdentityDraft(null); setShowDraftEditor(false); void listDirectiveDrafts({ turn: gameState.turn.turn }).then((result) => dispatch({ type: 'SET_DRAFTS', payload: result.drafts })); }} />}
    {showSettings && <DisplaySettingsPanel onClose={() => setShowSettings(false)} />}
  </div></SceneShell>;
}
