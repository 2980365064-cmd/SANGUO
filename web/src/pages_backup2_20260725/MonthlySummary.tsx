import { useEffect, useState } from 'react';
import { getMonthlyReport, resolveMajorReaction } from '../api';
import { getDirectiveBatch } from '../api/directiveBatches';
import { GameDialog } from '../components/GameDialog';
import { SceneShell } from '../components/SceneShell';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';
import { useCurrentBatch, useGameStore } from '../state/gameStore';
import { getSystemName } from '../utils/decreeTitles';

const executionLabel: Record<string, string> = { pending: '待执行', success: '已成', partial: '部分达成', failed: '未成' };
const executionTone: Record<string, 'neutral' | 'complete' | 'warning' | 'danger'> = { pending: 'neutral', success: 'complete', partial: 'warning', failed: 'danger' };

/** 月报只解释既有结算；进入下月仍通过原有 API 与规则链路。 */
export function MonthlySummary() {
  const { state, navigate } = useGameStore();
  const { currentBatch, setCurrentBatch } = useCurrentBatch();
  const [monthlyReport, setMonthlyReport] = useState<any>(null);
  const [batchDetails, setBatchDetails] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmNextMonth, setConfirmNextMonth] = useState(false);
  const [resolvingReaction, setResolvingReaction] = useState<number | null>(null);
  const gameState = state.gameState;

  const loadData = async () => {
    setLoading(true); setError(null);
    try {
      const report = await getMonthlyReport();
      setMonthlyReport(report);
      setBatchDetails(currentBatch ? await getDirectiveBatch(currentBatch.id) : null);
    } catch (err) { setError(err instanceof Error ? err.message : '加载失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => { void loadData(); }, [currentBatch, gameState.turn.turn]);

  const handleNextMonth = async () => {
    setError(null);
    try {
      const response = await fetch('/api/turn/next', { method: 'POST' });
      if (!response.ok) throw new Error(`进入下月失败: ${response.statusText}`);
      setConfirmed(true); setCurrentBatch(null); setConfirmNextMonth(false); navigate('map');
    } catch (err) { setError(err instanceof Error ? err.message : '进入下月失败'); setConfirmNextMonth(false); }
  };

  const handleReactionDecision = async (reactionId: number, choice: string) => {
    setResolvingReaction(reactionId); setError(null);
    try { await resolveMajorReaction(reactionId, choice); setMonthlyReport(await getMonthlyReport()); }
    catch (err) { setError(err instanceof Error ? err.message : '核定天下反应失败'); }
    finally { setResolvingReaction(null); }
  };

  const title = `${getSystemName(gameState.turn.year, gameState.identity.stage)} · 每月总计`;
  const date = `${gameState.turn.year}年${gameState.turn.period}月 · 第${gameState.turn.turn}回合`;
  const pendingReactions = monthlyReport?.sections?.flatMap((section: any) => section.items || []).filter((item: any) => item.level === 'major' && item.status === 'pending_decision') || [];

  return <SceneShell scene="report">
    <AppFrame className="monthly-summary" title={title} eyebrow={date} back={<ActionSealButton priority="ghost" onClick={() => navigate('map')}>返回天下舆图</ActionSealButton>}>
      {loading ? <PaperPanel className="monthly-state" tone="floating"><SectionHeading index="史册">正在整理本月纪事</SectionHeading><p>月报与颁令记录载入中。</p></PaperPanel> : error ? <PaperPanel className="monthly-state" tone="floating" role="alert"><SectionHeading index="史册">月报暂不可读</SectionHeading><p>{error}</p><ActionSealButton priority="secondary" onClick={() => void loadData()}>重试</ActionSealButton></PaperPanel> : <div className="monthly-ledger">
        <PaperPanel className="monthly-conclusion" tone="focus"><SectionHeading index="本月结论" note={date}>结算摘录</SectionHeading><p>{monthlyReport?.summary || '本月无特殊事件，军府仍可据现有事实筹划下月。'}</p>{pendingReactions.length > 0 && <StatusMark tone="warning">尚有 {pendingReactions.length} 项天下反应待裁断</StatusMark>}</PaperPanel>
        <div className="monthly-ledger-columns">
          <main>
            <PaperPanel className="batch-results" tone="archive"><SectionHeading index="已发生之事">方略执行</SectionHeading>{batchDetails ? <><div className="batch-info"><strong>{batchDetails.batch_title}</strong><p>本批收录 {batchDetails.total_drafts} 项方略 · {batchDetails.status}</p>{batchDetails.decree_text && <blockquote className="decree-text">{batchDetails.decree_text}</blockquote>}</div><ol className="execution-timeline">{batchDetails.items?.map((item: any) => <li key={item.id}><div><strong>{item.draft_title}</strong><small>{item.directive_type} · {item.assignee || '未指定执行者'}</small></div><StatusMark tone={executionTone[item.execution_status] || 'neutral'}>{executionLabel[item.execution_status] || item.execution_status}</StatusMark></li>)}</ol></> : <p className="empty-state">本月无颁令批次。可返回军府方略簿继续拟定与审阅。</p>}</PaperPanel>
            <PaperPanel className="monthly-report" tone="archive"><SectionHeading index="纪事">本月月报</SectionHeading>{monthlyReport ? <><h3>{monthlyReport.turn?.title || `${date}月报`}</h3><p className="report-summary">{monthlyReport.summary || '本月无特殊事件。'}</p>{monthlyReport.sections?.map((section: any, index: number) => <section key={`${section.title}-${index}`} className="report-section"><h4>{section.title}</h4><p>{section.summary}</p>{section.items?.map((item: any) => <article key={item.id} className="report-item"><strong>{item.title}</strong><p>{item.summary}</p>{item.level === 'major' && item.status === 'pending_decision' && <div className="reaction-decision" aria-label="重大天下反应裁断"><StatusMark tone="warning">进入下月前须裁断</StatusMark>{['安定朝议', '坚持颁行', '暂缓解释'].map((choice) => <ActionSealButton key={choice} priority="secondary" disabled={resolvingReaction === item.audit?.id} onClick={() => void handleReactionDecision(Number(item.audit?.id), choice)}>{choice}</ActionSealButton>)}</div>}{item.audit && <details><summary>查看规则依据与审计</summary><pre>{JSON.stringify(item.audit, null, 2)}</pre></details>}</article>)}</section>)}</> : <p className="empty-state">月报将在推演完成后自动生成。</p>}</PaperPanel>
          </main>
          <aside>
            <PaperPanel className="political-summary"><SectionHeading index="天下余波">人物与朝局</SectionHeading><p>当前活跃群体：{gameState.long_term.factions.filter((item) => item.status === 'active').map((item) => item.label).join('、') || '暂无'}。</p><p>{gameState.long_term.loyalty_risks.length ? `忠诚风险：${gameState.long_term.loyalty_risks.map((item) => `${item.name}（${item.loyalty}）`).join('、')}。` : '本月暂无需特别裁断的忠诚风险。'}</p></PaperPanel>
            <PaperPanel className="reputation-summary"><SectionHeading index="编年">天下口碑</SectionHeading><p>口碑趋势：{gameState.long_term.reputation.score}。</p>{gameState.long_term.reputation.recent.length > 0 ? <ul>{gameState.long_term.reputation.recent.slice(0, 4).map((item, index) => <li key={`${item.id || index}-${item.summary}`}>{item.summary}</li>)}</ul> : <p>本月尚无新的口碑记载。</p>}</PaperPanel>
          </aside>
        </div>
        <PaperPanel className="summary-actions" tone="focus"><div><SectionHeading index="下月待议">月结确认</SectionHeading><p>{pendingReactions.length ? '请先完成上方待裁断的天下反应，方可进入下月。' : '确认后将推进回合并结算下月世界状态；此操作不可撤回。'}</p></div>{confirmed ? <ActionSealButton priority="primary" onClick={() => navigate('map')}>返回天下舆图</ActionSealButton> : <ActionSealButton priority="primary" disabled={pendingReactions.length > 0} onClick={() => setConfirmNextMonth(true)}>确认阅毕并进入下月</ActionSealButton>}</PaperPanel>
      </div>}
      <GameDialog open={confirmNextMonth} onOpenChange={setConfirmNextMonth} title="封存本月纪事，进入下月" description="月结会推进回合并触发既有的规则结算；请确认所有待议事项已经处理。" tone="decree"><div className="monthly-next-confirmation"><p><strong>{date}</strong></p><p>本月方略、天下反应与月报将作为史册留存。进入下月后不能撤回本次月结。</p><div className="decree-confirmation-actions"><ActionSealButton priority="ghost" onClick={() => setConfirmNextMonth(false)}>返回查阅</ActionSealButton><ActionSealButton priority="primary" onClick={() => void handleNextMonth()}>确认月结</ActionSealButton></div></div></GameDialog>
    </AppFrame>
  </SceneShell>;
}
