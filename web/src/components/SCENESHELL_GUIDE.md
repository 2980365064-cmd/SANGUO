# SceneShell 组件使用指南

## 概述
`SceneShell` 是轻水墨三国风格的统一场景壳层组件，实现三层结构：
1. **场景图** - 全幅背景图片
2. **调节层** - 墨洗纹理，可调节透明度
3. **内容层** - 宣纸质感内容区域，保证可读性

## 导入方式
```tsx
import { SceneShell } from './components/SceneShell';
import type { SceneType } from './components/SceneShell';
```

## 基础用法
```tsx
function MyPage() {
  return (
    <SceneShell scene="council">
      <div className="my-content">
        <h2>府堂廷议</h2>
        <p>页面内容...</p>
      </div>
    </SceneShell>
  );
}
```

## 可用的场景类型

| 场景 | 说明 | 背景图 |
|------|------|--------|
| `map` | 战略地图 | bg-map.webp |
| `council` | 府堂廷议 | bg-hall.webp |
| `secret` | 密谈 | bg-secret-chamber.webp |
| `city` | 城池治理 | bg-city.webp |
| `province` | 州郡详情 | bg-province.webp |
| `army` | 军队信息 | bg-army.webp |
| `character` | 人物详情 | bg-character.webp |
| `diplomacy` | 外交 | bg-diplomacy.webp |
| `strategy` | 方略 | bg-strategy.webp |
| `history` | 史册 | bg-history.webp |
| `family` | 家族 | bg-family.webp |
| `directive` | 方略草案 | bg-strategy.webp |
| `review` | 审阅颁令 | bg-hall.webp |
| `adjudication` | 推演裁断 | bg-dock-right.webp |
| `adjudication-march` | 行军 | bg-adjudication-march.webp |
| `adjudication-naval` | 水战 | bg-adjudication-naval.webp |
| `adjudication-siege` | 攻城 | bg-adjudication-siege.webp |
| `adjudication-camp` | 军营 | bg-adjudication-camp.webp |
| `adjudication-envoy` | 使臣 | bg-adjudication-envoy.webp |
| `adjudication-disaster` | 灾荒 | bg-adjudication-disaster.webp |
| `event-urgent` | 急报 | bg-event-urgent.webp |
| `event-disaster` | 灾荒 | bg-event-disaster.webp |
| `event-harvest` | 丰收 | bg-event-harvest.webp |
| `report` | 月报 | bg-history.webp |

## 高级用法

### 调节透明度
```tsx
<SceneShell
  scene="map"
  washOpacity={0.2}      // 调节层透明度（默认 0.15）
  contentOpacity={0.85}  // 内容层背景透明度（默认 0.92）
>
  {/* 地图内容 */}
</SceneShell>
```

### 添加额外 CSS 类
```tsx
<SceneShell scene="council" className="custom-class">
  {/* 内容 */}
</SceneShell>
```

### 在 P0 页面中的使用示例

#### 局势与行动枢纽
```tsx
function SituationHub() {
  return (
    <SceneShell scene="map">
      <div className="situation-hub">
        <h2>本月局势与行动枢纽</h2>
        {/* 局势内容 */}
      </div>
    </SceneShell>
  );
}
```

#### 府堂廷议
```tsx
function CouncilHall() {
  return (
    <SceneShell scene="council">
      <div className="council-hall">
        <h2>府堂廷议</h2>
        {/* 廷议内容 */}
      </div>
    </SceneShell>
  );
}
```

#### 审阅与颁令
```tsx
function ReviewAndDecree() {
  return (
    <SceneShell scene="review">
      <div className="review-page">
        <h2>审阅与颁令</h2>
        {/* 审阅内容 */}
      </div>
    </SceneShell>
  );
}
```

#### 分阶段推演
```tsx
function AdjudicationFlow() {
  return (
    <SceneShell scene="adjudication">
      <div className="adjudication-flow">
        <h2>分阶段推演</h2>
        {/* 推演内容 */}
      </div>
    </SceneShell>
  );
}
```

#### 每月总计
```tsx
function MonthlySummary() {
  return (
    <SceneShell scene="report">
      <div className="monthly-summary">
        <h2>每月总计</h2>
        {/* 月报内容 */}
      </div>
    </SceneShell>
  );
}
```

## 样式说明
- 场景图使用 CSS 变量 `var(--ink-bg-{scene})`
- 调节层使用 `var(--ink-tex-wash)` + `mix-blend-mode: multiply`
- 内容层使用 `var(--ink-paper-rgb)` + 可调节透明度
- 所有场景样式定义在 `styles/components/scene-shell.css`

## 注意事项
1. 确保背景图片已生成并放置在 `web/public/assets/ui/` 目录
2. 内容层背景透明度不应过低，否则影响可读性
3. 调节层透明度建议保持在 0.1-0.3 之间
4. 所有页面必须使用 `SceneShell` 包裹，不允许裸色背景

## 相关文档
- CSS 模块化重构: `web/src/styles/MIGRATION_STATUS.md`
- 素材生成指南: `docs/asset-generation-guide.md`
- 分阶段改造计划: `/Users/zhuanzmima0000/.claude/plans/kind-stirring-beaver.md`

---

**创建时间**: 2026-07-22  
**状态**: ✅ 完成
