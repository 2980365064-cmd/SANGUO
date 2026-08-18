import { api } from '../api';
import type { DirectiveDraft } from '../types';

/**
 * Directive Drafts API - P0 核心
 * 方略草案的 CRUD 操作
 */

export interface CreateDraftRequest {
  source_type: 'council_chat' | 'secret_chat' | 'map_detail' | 'manual' | 'suggestion';
  source_id?: number;
  directive_type: 'internal' | 'military' | 'diplomatic' | 'other' | 'secret';
  title: string;
  assignee?: string;
  target?: string;
  duration_months?: number;
  priority?: number;
  resources_json?: string;
  constraints_json?: string;
  risks_json?: string;
  narrative_text?: string;
  compiled_text?: string;
}

export interface UpdateDraftRequest {
  title?: string;
  assignee?: string;
  target?: string;
  duration_months?: number;
  priority?: number;
  resources_json?: string;
  constraints_json?: string;
  risks_json?: string;
  narrative_text?: string;
  compiled_text?: string;
  status?: string;
}

export interface ValidationResponse {
  valid: boolean;
  errors: string[];
}

/**
 * 列出方略草案
 */
export async function listDirectiveDrafts(params?: {
  turn?: number;
  status?: string;
  directive_type?: string;
}): Promise<{ drafts: DirectiveDraft[] }> {
  const searchParams = new URLSearchParams();
  if (params?.turn !== undefined) searchParams.append('turn', String(params.turn));
  if (params?.status) searchParams.append('status', params.status);
  if (params?.directive_type) searchParams.append('directive_type', params.directive_type);

  const query = searchParams.toString();
  return api(`/api/directive-drafts${query ? `?${query}` : ''}`);
}

/**
 * 创建方略草案
 */
export async function createDirectiveDraft(
  draft: CreateDraftRequest
): Promise<{ draft: DirectiveDraft }> {
  return api('/api/directive-drafts', {
    method: 'POST',
    body: JSON.stringify(draft),
  });
}

/** 只生成可编辑的文风候选稿，不保存草案，也不触发执行。 */
export async function polishDirectiveSections(sections: Record<string, string>): Promise<{ sections: Record<string, string> }> {
  return api('/api/directive-drafts/polish', {
    method: 'POST',
    body: JSON.stringify({ sections }),
  });
}

/**
 * 获取单个方略草案
 */
export async function getDirectiveDraft(id: number): Promise<{ draft: DirectiveDraft }> {
  return api(`/api/directive-drafts/${id}`);
}

/**
 * 更新方略草案
 */
export async function updateDirectiveDraft(
  id: number,
  updates: UpdateDraftRequest
): Promise<{ draft: DirectiveDraft }> {
  return api(`/api/directive-drafts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

/**
 * 删除方略草案
 */
export async function deleteDirectiveDraft(id: number): Promise<{ deleted: boolean; id: number }> {
  return api(`/api/directive-drafts/${id}`, {
    method: 'DELETE',
  });
}

/**
 * 校验方略草案
 */
export async function validateDirectiveDraft(id: number): Promise<ValidationResponse> {
  return api(`/api/directive-drafts/${id}/validate`, {
    method: 'POST',
  });
}
