import type { SceneType } from './SceneShell';

export type SceneAssetStatus = 'ready' | 'missing';

export const SCENE_ASSETS: Record<SceneType, { token: string; status: SceneAssetStatus; label: string }> = {
  map: { token: '--ink-bg-map', status: 'ready', label: '战略地图' },
  council: { token: '--ink-bg-hall', status: 'ready', label: '府堂廷议' },
  secret: { token: '--ink-bg-secret', status: 'ready', label: '单独密谈' },
  city: { token: '--ink-bg-city', status: 'ready', label: '城池治理' }, province: { token: '--ink-bg-province', status: 'ready', label: '州郡详情' },
  army: { token: '--ink-bg-army', status: 'ready', label: '军队信息' }, character: { token: '--ink-bg-character', status: 'ready', label: '人物档案' },
  diplomacy: { token: '--ink-bg-diplomacy', status: 'ready', label: '外交' }, strategy: { token: '--ink-bg-strategy', status: 'ready', label: '方略' },
  history: { token: '--ink-bg-history', status: 'ready', label: '史册' }, family: { token: '--ink-bg-family', status: 'ready', label: '宗族' },
  directive: { token: '--ink-bg-strategy', status: 'ready', label: '方略簿' }, review: { token: '--ink-bg-review', status: 'ready', label: '审阅颁令' },
  adjudication: { token: '--ink-bg-adjudication', status: 'ready', label: '推演总览' }, 'adjudication-march': { token: '--ink-bg-adjudication-march', status: 'ready', label: '行军' },
  'adjudication-naval': { token: '--ink-bg-adjudication-naval', status: 'ready', label: '水战' }, 'adjudication-siege': { token: '--ink-bg-adjudication-siege', status: 'ready', label: '攻城' },
  'adjudication-camp': { token: '--ink-bg-adjudication-camp', status: 'ready', label: '军营' }, 'adjudication-envoy': { token: '--ink-bg-adjudication-envoy', status: 'ready', label: '使臣道路' },
  'adjudication-disaster': { token: '--ink-bg-adjudication-disaster', status: 'ready', label: '灾荒推演' }, 'event-urgent': { token: '--ink-bg-event-urgent', status: 'ready', label: '雨夜急报' },
  'event-disaster': { token: '--ink-bg-event-disaster', status: 'ready', label: '灾荒事件' }, 'event-harvest': { token: '--ink-bg-event-harvest', status: 'ready', label: '丰收事件' },
  report: { token: '--ink-bg-report', status: 'ready', label: '每月总计' },
};
