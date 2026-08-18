import type { SceneType } from './SceneShell';

export type SceneAssetStatus = 'ready' | 'missing';

export const SCENE_ASSETS: Record<SceneType, { token: string; status: SceneAssetStatus; label: string }> = {
  map: { token: '--ink-bg-map', status: 'ready', label: '战略地图' },
  council: { token: '--archive-scene-council-record-v2', status: 'ready', label: '府堂议录' },
  secret: { token: '--archive-scene-secret-letter-v2', status: 'ready', label: '密谈私札' },
  city: { token: '--archive-scene-city-ledger-v2', status: 'ready', label: '地方治理簿' }, province: { token: '--ink-bg-province', status: 'ready', label: '州郡详情' },
  army: { token: '--archive-scene-army-register-v2', status: 'ready', label: '军籍补给簿' }, character: { token: '--archive-scene-character-biography-v2', status: 'ready', label: '人物传记页' },
  diplomacy: { token: '--archive-scene-diplomacy-correspondence-v2', status: 'ready', label: '使节往来档' }, strategy: { token: '--ink-bg-strategy', status: 'ready', label: '方略' },
  history: { token: '--archive-scene-history-book-v2', status: 'ready', label: '编年史册' }, family: { token: '--ink-bg-family', status: 'ready', label: '宗族' },
  directive: { token: '--archive-scene-directive-ledger-v2', status: 'ready', label: '军府方略簿' }, review: { token: '--archive-scene-decree-review-v2', status: 'ready', label: '颁令校阅卷' },
  adjudication: { token: '--archive-scene-adjudication-record-v2', status: 'ready', label: '行止推演录' }, 'adjudication-march': { token: '--ink-bg-adjudication-march', status: 'ready', label: '行军' },
  'adjudication-naval': { token: '--ink-bg-adjudication-naval', status: 'ready', label: '水战' }, 'adjudication-siege': { token: '--ink-bg-adjudication-siege', status: 'ready', label: '攻城' },
  'adjudication-camp': { token: '--ink-bg-adjudication-camp', status: 'ready', label: '军营' }, 'adjudication-envoy': { token: '--ink-bg-adjudication-envoy', status: 'ready', label: '使臣道路' },
  'adjudication-disaster': { token: '--ink-bg-adjudication-disaster', status: 'ready', label: '灾荒推演' }, 'event-urgent': { token: '--archive-scene-event-memorial-v2', status: 'ready', label: '急报奏报' },
  'event-disaster': { token: '--ink-bg-event-disaster', status: 'ready', label: '灾荒事件' }, 'event-harvest': { token: '--ink-bg-event-harvest', status: 'ready', label: '丰收事件' },
  report: { token: '--archive-scene-monthly-chronicle-v2', status: 'ready', label: '月度总计册' },
};
