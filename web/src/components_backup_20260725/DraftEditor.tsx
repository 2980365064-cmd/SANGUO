import React, { useState, useEffect } from 'react';
import type { DirectiveDraft } from '../types';
import { createDirectiveDraft, updateDirectiveDraft, validateDirectiveDraft } from '../api/directiveDrafts';
import { useGameStore } from '../state/gameStore';
import { SceneShell } from '../components/SceneShell';

/**
 * DraftEditor - 方略草案编辑器
 * 用于创建和编辑方略草案
 */

interface DraftEditorProps {
  draft?: DirectiveDraft; // 如果提供，则为编辑模式
  source_type?: 'council_chat' | 'secret_chat' | 'map_detail' | 'manual' | 'suggestion';
  source_id?: number;
  onClose: () => void;
  onSave?: (draft: DirectiveDraft) => void;
}

export function DraftEditor({ draft, source_type = 'manual', source_id, onClose, onSave }: DraftEditorProps) {
  const { dispatch } = useGameStore();

  // 表单状态
  const [title, setTitle] = useState(draft?.title || '');
  const [directiveType, setDirectiveType] = useState(draft?.directive_type || 'internal');
  const [assignee, setAssignee] = useState(draft?.assignee || '');
  const [target, setTarget] = useState(draft?.target || '');
  const [durationMonths, setDurationMonths] = useState(draft?.duration_months || 1);
  const [priority, setPriority] = useState(draft?.priority || 50);
  const [narrativeText, setNarrativeText] = useState(draft?.narrative_text || '');
  const [constraints, setConstraints] = useState<string[]>(
    draft?.constraints_json ? JSON.parse(draft.constraints_json) : []
  );
  const [risks, setRisks] = useState<string[]>(
    draft?.risks_json ? JSON.parse(draft.risks_json) : []
  );

  // UI 状态
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const isEditMode = !!draft;

  // 提交表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setValidationErrors([]);

    try {
      const draftData = {
        source_type,
        source_id,
        directive_type: directiveType as any,
        title,
        assignee: assignee || undefined,
        target: target || undefined,
        duration_months: durationMonths,
        priority,
        narrative_text: narrativeText,
        constraints_json: JSON.stringify(constraints),
        risks_json: JSON.stringify(risks),
      };

      let result;
      if (isEditMode && draft) {
        result = await updateDirectiveDraft(draft.id, draftData);
      } else {
        result = await createDirectiveDraft(draftData);
      }

      // 更新全局状态
      dispatch({ type: draft ? 'UPDATE_DRAFT' : 'ADD_DRAFT', payload: result.draft as any });

      // 调用回调
      if (onSave) {
        onSave(result.draft);
      }

      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setLoading(false);
    }
  };

  // 校验草案
  const handleValidate = async () => {
    if (!draft) return;

    setValidating(true);
    setValidationErrors([]);

    try {
      const result = await validateDirectiveDraft(draft.id);
      if (!result.valid) {
        setValidationErrors(result.errors);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '校验失败');
    } finally {
      setValidating(false);
    }
  };

  // 添加约束
  const addConstraint = () => {
    setConstraints([...constraints, '']);
  };

  // 更新约束
  const updateConstraint = (index: number, value: string) => {
    const newConstraints = [...constraints];
    newConstraints[index] = value;
    setConstraints(newConstraints);
  };

  // 删除约束
  const removeConstraint = (index: number) => {
    setConstraints(constraints.filter((_, i) => i !== index));
  };

  // 添加风险
  const addRisk = () => {
    setRisks([...risks, '']);
  };

  // 更新风险
  const updateRisk = (index: number, value: string) => {
    const newRisks = [...risks];
    newRisks[index] = value;
    setRisks(newRisks);
  };

  // 删除风险
  const removeRisk = (index: number) => {
    setRisks(risks.filter((_, i) => i !== index));
  };

  return (
    <SceneShell scene="directive">
      <div className="draft-editor">
        <header>
          <h2>{isEditMode ? '编辑方略' : '新建方略'}</h2>
          <button onClick={onClose} disabled={loading}>关闭</button>
        </header>

        <form onSubmit={handleSubmit}>
          {/* 基本信息 */}
          <section className="draft-section">
            <h3>基本信息</h3>

            <div className="form-group">
              <label>标题 *</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                placeholder="例如：北伐中原"
              />
            </div>

            <div className="form-group">
              <label>方略类型 *</label>
              <select
                value={directiveType}
                onChange={(e) => setDirectiveType(e.target.value as 'internal' | 'military' | 'diplomatic' | 'other' | 'secret')}
              >
                <option value="internal">内政</option>
                <option value="military">军事</option>
                <option value="diplomatic">外交</option>
                <option value="other">其他</option>
                <option value="secret">密令</option>
              </select>
            </div>

            <div className="form-group">
              <label>执行者</label>
              <input
                type="text"
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                placeholder="例如：诸葛亮"
              />
            </div>

            <div className="form-group">
              <label>目标</label>
              <input
                type="text"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="例如：长安"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>时限（月）</label>
                <input
                  type="number"
                  value={durationMonths}
                  onChange={(e) => setDurationMonths(parseInt(e.target.value) || 1)}
                  min="1"
                  max="12"
                />
              </div>

              <div className="form-group">
                <label>优先级</label>
                <input
                  type="number"
                  value={priority}
                  onChange={(e) => setPriority(parseInt(e.target.value) || 50)}
                  min="0"
                  max="100"
                />
              </div>
            </div>
          </section>

          {/* 文书说明 */}
          <section className="draft-section">
            <h3>文书说明</h3>
            <div className="form-group">
              <label>详细说明</label>
              <textarea
                value={narrativeText}
                onChange={(e) => setNarrativeText(e.target.value)}
                rows={5}
                placeholder="详细描述方略的背景、目的、预期效果等"
              />
            </div>
          </section>

          {/* 约束条件 */}
          <section className="draft-section">
            <h3>约束条件</h3>
            <p className="section-help">方略执行过程中必须遵守的条件</p>
            {constraints.map((constraint, index) => (
              <div key={index} className="list-item">
                <input
                  type="text"
                  value={constraint}
                  onChange={(e) => updateConstraint(index, e.target.value)}
                  placeholder="例如：不得滥杀百姓"
                />
                <button type="button" onClick={() => removeConstraint(index)}>删除</button>
              </div>
            ))}
            <button type="button" onClick={addConstraint}>添加约束</button>
          </section>

          {/* 风险因素 */}
          <section className="draft-section">
            <h3>风险因素</h3>
            <p className="section-help">方略执行过程中可能面临的风险</p>
            {risks.map((risk, index) => (
              <div key={index} className="list-item">
                <input
                  type="text"
                  value={risk}
                  onChange={(e) => updateRisk(index, e.target.value)}
                  placeholder="例如：补给线过长"
                />
                <button type="button" onClick={() => removeRisk(index)}>删除</button>
              </div>
            ))}
            <button type="button" onClick={addRisk}>添加风险</button>
          </section>

          {/* 校验结果 */}
          {validationErrors.length > 0 && (
            <section className="draft-section validation-errors">
              <h3>校验错误</h3>
              <ul>
                {validationErrors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </section>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="error-message">{error}</div>
          )}

          {/* 操作按钮 */}
          <footer>
            <button type="button" onClick={onClose} disabled={loading}>
              取消
            </button>
            {isEditMode && (
              <button
                type="button"
                onClick={handleValidate}
                disabled={validating || loading}
              >
                {validating ? '校验中...' : '校验'}
              </button>
            )}
            <button type="submit" disabled={loading}>
              {loading ? '保存中...' : isEditMode ? '更新' : '创建'}
            </button>
          </footer>
        </form>
      </div>
    </SceneShell>
  );
}
