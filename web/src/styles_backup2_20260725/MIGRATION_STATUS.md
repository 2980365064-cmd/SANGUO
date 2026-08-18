# CSS 模块迁移状态

## 当前入口

`web/src/main.tsx` 只加载 `styles/index.css`。入口不再导入旧的 `web/src/styles.css`，也不再使用末尾的 `revival.css` 覆盖层。

存量规则已按原有选择器顺序归档在 `styles/legacy/`：

- `foundation.css`：基础、主菜单与早期通用规则；
- `map.css`：地图交互和历史图层；
- `council.css`：廷议选择、建议库和舞台遗留规则；
- `characters.css`：人物档案和密谈遗留规则；
- `overlays.css`：`PanelRoot` 与旧方略浮层规则。

这些文件仅保证未迁移页面不失样，不得新增规则。新工作必须进入 `tokens/`、`components/`、`scenes/` 或 `utils/`。

## 设计系统层

- `tokens/`：色彩、字体、材质、资源图标和动效令牌；
- `base/`：重置与窄桌面下限；
- `components/`：纸面板、印章行动、表单、通用弹窗、场景壳和核心闭环共享规则；
- `scenes/`：菜单、地图、廷议、密谈、方略、审阅、裁决、月报和局势页；
- `utils/`：动效与响应式收束。

`components/core-loop.css` 是原核心闭环样式的归属文件，位于组件层而非入口末尾；后续场景样式以其为基础局部扩展。

## 后续清理边界

阶段五逐页迁移非核心页面后，才能以实际引用和截图验证为依据删除 `legacy/` 中的规则及原始 `web/src/styles.css` 存档。不得在尚有消费者时直接删除。
