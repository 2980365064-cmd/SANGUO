import { api } from '../api';
import type { DirectiveBatch } from '../types';

/**
 * Directive Batches API - P0 核心
 * 颁令批次的创建、查询和颁令操作
 */

export interface CreateBatchRequest {
  batch_title: string;
  draft_ids: number[];
  decree_text?: string;
}

export interface BatchListParams {
  turn?: number;
  status?: string;
}

/**
 * 列出颁令批次
 */
export async function listDirectiveBatches(params?: BatchListParams): Promise<{ batches: DirectiveBatch[] }> {
  const searchParams = new URLSearchParams();
  if (params?.turn !== undefined) searchParams.append('turn', String(params.turn));
  if (params?.status) searchParams.append('status', params.status);

  const query = searchParams.toString();
  return api(`/api/directive-batches${query ? `?${query}` : ''}`);
}

/**
 * 创建颁令批次
 */
export async function createDirectiveBatch(
  batch: CreateBatchRequest
): Promise<{ batch: DirectiveBatch }> {
  return api('/api/directive-batches', {
    method: 'POST',
    body: JSON.stringify(batch),
  });
}

/**
 * 获取单个颁令批次
 */
export async function getDirectiveBatch(id: number): Promise<{ batch: DirectiveBatch }> {
  return api(`/api/directive-batches/${id}`);
}

/**
 * 颁令（将批次状态从 pending 改为 issued）
 */
export async function issueDirectiveBatch(id: number): Promise<{ batch: DirectiveBatch }> {
  return api(`/api/directive-batches/${id}/issue`, {
    method: 'POST',
  });
}

/** 执行既有的分阶段批次推演；前端只消费审计事件，不自行结算世界。 */
export async function executeDirectiveBatch(
  id: number,
  onEvent?: (event: { type: string; message?: string }) => void,
): Promise<void> {
  const response = await fetch(`/api/directive-batches/${id}/execute`, { method: 'POST' });
  if (!response.ok) throw new Error(await response.text() || `执行军令失败: ${response.status}`);
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';
    for (const chunk of chunks) {
      const raw = chunk.split('\n').find((line) => line.startsWith('data: '))?.slice(6);
      if (!raw) continue;
      try { onEvent?.(JSON.parse(raw)); } catch { /* 单条流事件损坏时继续等待后续结果。 */ }
    }
    if (done) break;
  }
}
