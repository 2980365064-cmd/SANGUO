import { useEffect, useState } from 'react';
import { GameDialog } from './GameDialog';

type DisplaySettings = {
  fontScale: 'small' | 'normal' | 'large';
  motion: 'full' | 'reduced' | 'none';
  simulationSpeed: 'calm' | 'normal' | 'fast';
  narrativeDetail: 'brief' | 'standard' | 'detailed';
  backgroundStrength: 'low' | 'normal' | 'strong';
  lowPerformance: boolean;
};

const KEY = 'sanguo.display-settings.v1';
const DEFAULTS: DisplaySettings = {
  fontScale: 'normal', motion: 'full', simulationSpeed: 'normal', narrativeDetail: 'standard', backgroundStrength: 'normal', lowPerformance: false,
};

function load(): DisplaySettings {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return DEFAULTS; }
}

function apply(value: DisplaySettings) {
  const root = document.documentElement;
  root.dataset.fontScale = value.fontScale;
  root.dataset.motion = value.motion;
  root.dataset.backgroundStrength = value.backgroundStrength;
  root.dataset.performance = value.lowPerformance ? 'low' : 'normal';
  root.style.setProperty('--simulation-speed', value.simulationSpeed === 'fast' ? '.55' : value.simulationSpeed === 'calm' ? '1.55' : '1');
}

/** 仅保存显示和叙事偏好；不调用世界规则接口，也不会改变裁决结果。 */
export function DisplaySettingsPanel({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<DisplaySettings>(load);
  useEffect(() => { apply(settings); localStorage.setItem(KEY, JSON.stringify(settings)); }, [settings]);
  const set = <K extends keyof DisplaySettings>(key: K, value: DisplaySettings[K]) => setSettings((old) => ({ ...old, [key]: value }));
  return <GameDialog open onOpenChange={(open) => { if (!open) onClose(); }} title="显示与叙事" description="以下选项只改变阅读与播放方式，不改变方略、裁决或世界结果。" tone="default">
    <label>字体大小<select value={settings.fontScale} onChange={(e) => set('fontScale', e.target.value as DisplaySettings['fontScale'])}><option value="small">紧凑</option><option value="normal">标准</option><option value="large">大字</option></select></label>
    <label>动画强度<select value={settings.motion} onChange={(e) => set('motion', e.target.value as DisplaySettings['motion'])}><option value="full">完整</option><option value="reduced">减弱</option><option value="none">关闭</option></select></label>
    <label>推演速度<select value={settings.simulationSpeed} onChange={(e) => set('simulationSpeed', e.target.value as DisplaySettings['simulationSpeed'])}><option value="calm">从容</option><option value="normal">标准</option><option value="fast">快速</option></select></label>
    <label>AI 叙事详略<select value={settings.narrativeDetail} onChange={(e) => set('narrativeDetail', e.target.value as DisplaySettings['narrativeDetail'])}><option value="brief">简略</option><option value="standard">标准</option><option value="detailed">详尽</option></select></label>
    <label>背景显示强度<select value={settings.backgroundStrength} onChange={(e) => set('backgroundStrength', e.target.value as DisplaySettings['backgroundStrength'])}><option value="low">低</option><option value="normal">标准</option><option value="strong">高</option></select></label>
    <label className="settings-check"><input type="checkbox" checked={settings.lowPerformance} onChange={(e) => set('lowPerformance', e.target.checked)} />低性能模式（关闭模糊与非必要动画）</label>
  </GameDialog>;
}
