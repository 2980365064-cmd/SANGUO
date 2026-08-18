import { useState, useEffect } from 'react';
import { SceneShell } from '../components/SceneShell';
import { useGameStore, useDrafts, useCurrentBatch } from '../state/gameStore';
import { listDirectiveDrafts, validateDirectiveDraft } from '../api/directiveDrafts';
import { createDirectiveBatch, issueDirectiveBatch } from '../api/directiveBatches';
import { getReviewPageTitle, getIssueButtonLabel } from '../utils/decreeTitles';
import type { DirectiveDraft, DirectiveBatch } from '../types';
import { GameDialog } from '../components/GameDialog';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading, StatusMark } from '../components/ui';

/**
 * 审阅与颁令 - P0 唯一提交页
 * 编辑结构化方略、润色文书、校验、统一颁令
 */
export function ReviewAndDecree() {
  const { state, navigate } = useGameStore();
  const { drafts, setDrafts } = useDrafts();
  const { currentBatch, setCurrentBatch } = useCurrentBatch();
  const gameState = state.gameState;

  // 选择状态
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<number>>(new Set());
  const [batchTitle, setBatchTitle] = useState('');
  const [decreeText, setDecreeText] = useState('');

  // UI 状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationResults, setValidationResults] = useState<Map<number, { valid: boolean; errors: string[] }>>(new Map());
  const [confirmation, setConfirmation] = useState<'batch' | 'issue' | null>(null);

  // 加载草案列表
  const loadDrafts = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await listDirectiveDrafts({
        turn: gameState.turn.turn,
        status: 'validated', // 只显示已校验的草案
      });
      setDrafts(result.drafts);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDrafts();
  }, []);

  // 选择/取消选择草案
  const toggleDraft = (id: number) => {
    const newSelected = new Set(selectedDraftIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedDraftIds(newSelected);
  };

  // 全选/取消全选
  const toggleAll = () => {
    if (selectedDraftIds.size === drafts.length) {
      setSelectedDraftIds(new Set());
    } else {
      setSelectedDraftIds(new Set(drafts.map(d => d.id)));
    }
  };

  // 批量校验
  const validateSelected = async () => {
    setLoading(true);
    setError(null);
    const results = new Map<number, { valid: boolean; errors: string[] }>();

    for (const id of selectedDraftIds) {
      try {
        const result = await validateDirectiveDraft(id);
        results.set(id, result);
      } catch (err) {
        results.set(id, { valid: false, errors: [err instanceof Error ? err.message : '校验失败'] });
      }
    }

    setValidationResults(results);
    setLoading(false);
  };

  // 创建批次
  const handleCreateBatch = async () => {
    if (selectedDraftIds.size === 0) {
      setError('请至少选择一个草案');
      return;
    }

    if (!batchTitle.trim()) {
      setError('请输入批次标题');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await createDirectiveBatch({
        batch_title: batchTitle.trim(),
        draft_ids: Array.from(selectedDraftIds),
        decree_text: decreeText.trim(),
      });

      setCurrentBatch(result.batch);
      setSelectedDraftIds(new Set());
      setBatchTitle('');
      setDecreeText('');
      loadDrafts(); // 刷新列表（已选择的草案状态会变为 issued）
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建批次失败');
    } finally {
      setLoading(false);
    }
  };

  // 颁令
  const handleIssueDecree = async () => {
    if (!currentBatch) return;

    setLoading(true);
    setError(null);

    try {
      const result = await issueDirectiveBatch(currentBatch.id);
      setCurrentBatch(result.batch);
      loadDrafts(); // 刷新列表
    } catch (err) {
      setError(err instanceof Error ? err.message : '颁令失败');
    } finally {
      setLoading(false);
    }
  };

  // 可选择的草案（未颁令的）
  const selectableDrafts = drafts.filter(d => d.status !== 'issued');

  return (
    <SceneShell scene="review">
      <AppFrame className="review-decree" title={getReviewPageTitle(gameState.turn.year, gameState.identity.stage)} eyebrow="军府方略 · 二审阅—三下达" back={<ActionSealButton priority="ghost" onClick={() => navigate('directive')}>返回方略簿</ActionSealButton>} actions={<StatusMark tone={currentBatch ? 'action' : 'neutral'}>{currentBatch ? '待颁令批次' : '编选待审草案'}</StatusMark>}>

        {/* 错误提示 */}
        {error && <div className="error-message">{error}</div>}

        {!currentBatch ? (
          <>
            {/* 批次信息 */}
            <PaperPanel className="batch-info" tone="focus">
              <SectionHeading index="批次">批次信息</SectionHeading>
              <div className="form-group">
                <label>批次标题 *</label>
                <input
                  type="text"
                  value={batchTitle}
                  onChange={(e) => setBatchTitle(e.target.value)}
                  placeholder="例如：建安十三年一月军政方略"
                />
              </div>
              <div className="form-group">
                <label>邸报正文（可选）</label>
                <textarea
                  value={decreeText}
                  onChange={(e) => setDecreeText(e.target.value)}
                  rows={4}
                  placeholder="描述本次颁令的总体方针和预期效果"
                />
              </div>
            </PaperPanel>

            {/* 草案选择 */}
            <PaperPanel className="draft-selection">
              <SectionHeading index="审阅" note={`${selectedDraftIds.size}/${selectableDrafts.length}`}>选择草案</SectionHeading>
              <div className="selection-actions">
                <button onClick={toggleAll}>
                  {selectedDraftIds.size === selectableDrafts.length ? '取消全选' : '全选'}
                </button>
                <button onClick={validateSelected} disabled={selectedDraftIds.size === 0 || loading}>
                  {loading ? '校验中...' : '批量校验'}
                </button>
              </div>

              {selectableDrafts.length === 0 ? (
                <p className="empty-state">暂无可选择的草案。请先在方略簿中校验草案。</p>
              ) : (
                <div className="draft-select-list">
                  {selectableDrafts.map(draft => {
                    const validationResult = validationResults.get(draft.id);
                    return (
                      <div
                        key={draft.id}
                        className={`draft-select-item ${selectedDraftIds.has(draft.id) ? 'selected' : ''}`}
                        onClick={() => toggleDraft(draft.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedDraftIds.has(draft.id)}
                          onChange={() => {}}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="draft-info">
                          <h3>{draft.title}</h3>
                          <div className="draft-meta">
                            <span>类型: {draft.directive_type}</span>
                            <span>执行者: {draft.assignee || '未指定'}</span>
                            <span>目标: {draft.target || '未指定'}</span>
                            <span>时限: {draft.duration_months}个月</span>
                          </div>
                          {validationResult && (
                            <div className={`validation-result ${validationResult.valid ? 'valid' : 'invalid'}`}>
                              {validationResult.valid ? (
                                <span className="valid-badge">✓ 校验通过</span>
                              ) : (
                                <div className="error-list">
                                  <span className="invalid-badge">✗ 校验失败</span>
                                  <ul>
                                    {validationResult.errors.map((err, i) => (
                                      <li key={i}>{err}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </PaperPanel>

            {/* 创建批次 */}
            <section className="batch-actions">
              <ActionSealButton
                onClick={() => setConfirmation('batch')}
                disabled={selectedDraftIds.size === 0 || !batchTitle.trim() || loading}
                priority="primary"
              >
                {loading ? '创建中...' : '创建颁令批次'}
              </ActionSealButton>
            </section>
          </>
        ) : (
          <>
            {/* 批次审阅 */}
            <PaperPanel className="batch-review" tone="focus">
              <SectionHeading index="批次" note="待最终确认">{currentBatch.batch_title}</SectionHeading>
              <div className="batch-info">
                <p><strong>总方略数：</strong>{currentBatch.total_drafts}</p>
                <p><strong>状态：</strong>
                  {currentBatch.status === 'pending' && '待颁令'}
                  {currentBatch.status === 'issued' && '已颁令'}
                  {currentBatch.status === 'executing' && '执行中'}
                  {currentBatch.status === 'completed' && '已完成'}
                  {currentBatch.status === 'failed' && '执行失败'}
                </p>
                {currentBatch.decree_text && (
                  <div className="decree-text">
                    <h3>邸报正文</h3>
                    <p>{currentBatch.decree_text}</p>
                  </div>
                )}
              </div>

              <div className="batch-items">
                <h3>包含方略</h3>
                <ul>
                  {currentBatch.items?.map(item => (
                    <li key={item.id}>
                      <strong>{item.draft_title}</strong>
                      <span> - {item.directive_type} - {item.assignee || '未指定'}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </PaperPanel>

            {/* 颁令操作 */}
            <section className="decree-actions">
              {currentBatch.status === 'pending' && (
                <>
                  <button onClick={() => navigate('directive')}>返回修改</button>
                  <button
                    onClick={() => setConfirmation('issue')}
                    disabled={loading}
                    className="primary seal-button"
                  >
                    {loading ? `${getIssueButtonLabel(gameState.turn.year, gameState.identity.stage)}中...` : getIssueButtonLabel(gameState.turn.year, gameState.identity.stage)}
                  </button>
                </>
              )}
              {currentBatch.status === 'issued' && (
                <button onClick={() => navigate('adjudication')} className="primary">
                  查看推演
                </button>
              )}
            </section>
          </>
        )}
        <GameDialog
          open={confirmation !== null}
          onOpenChange={(open) => { if (!open) setConfirmation(null); }}
          title={confirmation === 'issue' ? getIssueButtonLabel(gameState.turn.year, gameState.identity.stage) : '封存颁令批次'}
          description={confirmation === 'issue' ? '颁令后，本批方略将进入规则推演；世界事实仍由推演与硬规则决定。' : '批次封存后可统一审阅，再决定是否正式颁令。'}
          tone="decree"
          bgAsset="var(--archive-scene-decree-review-v2)"
        >
          <div className="decree-confirmation">
            <p><strong>{confirmation === 'issue' ? currentBatch?.batch_title : batchTitle}</strong></p>
            <p>收录方略：{confirmation === 'issue' ? currentBatch?.total_drafts || 0 : selectedDraftIds.size} 项</p>
            {confirmation === 'batch' && decreeText.trim() && <p className="decree-confirmation-note">邸报正文已随批次封存。</p>}
            <div className="decree-confirmation-actions">
              <button className="secondary" onClick={() => setConfirmation(null)} disabled={loading}>返回修改</button>
              <button className="primary" onClick={() => {
                if (confirmation === 'issue') void handleIssueDecree(); else void handleCreateBatch();
                setConfirmation(null);
              }} disabled={loading}>
                {confirmation === 'issue' ? getIssueButtonLabel(gameState.turn.year, gameState.identity.stage) : '确认封存'}
              </button>
            </div>
          </div>
        </GameDialog>
      </AppFrame>
    </SceneShell>
  );
}
