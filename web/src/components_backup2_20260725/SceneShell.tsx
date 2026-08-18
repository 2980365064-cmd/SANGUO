import React from 'react';
import { SCENE_ASSETS } from './sceneAssets';

/**
 * SceneShell - 场景壳层组件
 * 实现三层结构：场景图 + 调节层 + 内容层
 *
 * @param scene - 场景类型，决定背景图片
 * @param children - 内容层组件
 * @param className - 额外的 CSS 类名
 * @param density - 预定义阅读密度，防止页面任意覆盖层造成风格漂移
 */

export type SceneType =
  | 'map'
  | 'council'
  | 'secret'
  | 'city'
  | 'province'
  | 'army'
  | 'character'
  | 'diplomacy'
  | 'strategy'
  | 'history'
  | 'family'
  | 'directive'
  | 'review'
  | 'adjudication'
  | 'adjudication-march'
  | 'adjudication-naval'
  | 'adjudication-siege'
  | 'adjudication-camp'
  | 'adjudication-envoy'
  | 'adjudication-disaster'
  | 'event-urgent'
  | 'event-disaster'
  | 'event-harvest'
  | 'report';

interface SceneShellProps {
  scene: SceneType;
  children: React.ReactNode;
  className?: string;
  density?: 'open' | 'standard' | 'focused';
}

export function SceneShell({
  scene,
  children,
  className = '',
  density = 'standard',
}: SceneShellProps) {
  const asset = SCENE_ASSETS[scene];
  const missing = asset.status === 'missing';
  return (
    <div className={`scene-shell scene-${scene} scene-density-${density} ${missing ? 'scene-asset-missing' : ''} ${className}`.trim()} data-scene={scene} data-scene-asset-status={asset.status}>
      {/* Layer 1: 全幅场景图 */}
      <div className="scene-background" />
      {missing && import.meta.env.DEV && <span className="scene-asset-notice">待接入百炼场景：{asset.label}</span>}

      {/* Layer 2: 低强度墨洗、暗角或宣纸颗粒调节层 */}
      <div className="scene-wash" />

      {/* Layer 3: 可读内容层（宣纸/绢帛/木牌） */}
      <div className="scene-content">
        {children}
      </div>
    </div>
  );
}

/**
 * SceneShell 使用示例：
 *
 * ```tsx
 * import { SceneShell } from './components/SceneShell';
 *
 * function CouncilHallPage() {
 *   return (
 *     <SceneShell scene="council">
 *       <div className="council-content">
 *         <h2>府堂廷议</h2>
 *         {/* 廷议内容 *}
 *       </div>
 *     </SceneShell>
 *   );
 * }
 * ```
 *
 * 预定义密度的示例：
 *
 * ```tsx
 * <SceneShell
 *   scene="map"
 *   density="focused"
 * >
 *   {/* 地图内容 *}
 * </SceneShell>
 * ```
 */
