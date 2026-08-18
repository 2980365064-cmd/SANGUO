/**
 * 文书称谓系统 — 根据年份和阶段动态切换
 *
 * 208-219（汉中王前）：军府方略 / 左将军府令
 * 219-221（汉中王）：汉中王令
 * 221+（称帝后）：朝廷方略 / 诏令
 */

export type DecreeEra = 'junfu' | 'hanzhong' | 'chaoting';

export function getDecreeEra(year: number, stage = ''): DecreeEra {
  if (stage === '称帝后') return 'chaoting';
  if (stage === '汉中王') return 'hanzhong';
  if (year < 219) return 'junfu';
  if (year < 221) return 'hanzhong';
  return 'chaoting';
}

/** 系统名称（用于页面标题、导航等） */
export function getSystemName(year: number, stage = ''): string {
  switch (getDecreeEra(year, stage)) {
    case 'junfu': return '军府方略';
    case 'hanzhong': return '汉中王府';
    case 'chaoting': return '朝廷方略';
  }
}

/** 文书名称（用于草案标题、颁令按钮等） */
export function getDecreeName(year: number, stage = ''): string {
  switch (getDecreeEra(year, stage)) {
    case 'junfu': return '左将军府令';
    case 'hanzhong': return '汉中王令';
    case 'chaoting': return '诏令';
  }
}

/** 方略簿名称 */
export function getDirectiveBookName(year: number, stage = ''): string {
  switch (getDecreeEra(year, stage)) {
    case 'junfu': return '本月军府方略簿';
    case 'hanzhong': return '本月王府方略簿';
    case 'chaoting': return '本月朝廷方略簿';
  }
}

/** 颁令按钮文字 */
export function getIssueButtonLabel(year: number, stage = ''): string {
  switch (getDecreeEra(year, stage)) {
    case 'junfu': return '颁令';
    case 'hanzhong': return '颁令';
    case 'chaoting': return '下诏';
  }
}

/** 审阅页面标题 */
export function getReviewPageTitle(year: number, stage = ''): string {
  return `审阅与${getDecreeName(year, stage)}`;
}
