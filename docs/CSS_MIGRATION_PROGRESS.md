# CSS 迁移进度追踪

## 当前状态
- ✅ 模块化结构已创建
- ✅ Token 系统已统一
- ✅ 关键组件样式已迁移（buttons, panels, scene-shell）
- ⏳ 场景样式待迁移（1832 行 → 模块化）
- ⏳ 向后兼容：保留 styles.css 导入

## 已迁移的样式

### tokens/colors.css ✅
- 统一两套 :root 系统
- RGB 组件变量
- 命名颜色 token
- 背景场景 URL
- 纹理 URL

### tokens/typography.css ✅
- @font-face 声明

### base/reset.css ✅
- 基础重置样式

### components/buttons.css ✅
- .seal-button
- .menu-actions button
- .primary

### components/panels.css ✅
- .paper-panel
- .ink-frame-panel
- .right-panel

### components/scene-shell.css ✅
- .scene-shell
- .scene-background
- .scene-wash
- .scene-content
- 24 种场景背景映射

### utils/animations.css ✅
- @keyframes spin
- .spin

### utils/responsive.css ✅
- 3 个断点的响应式规则

## 待迁移的样式（按优先级）

### 高优先级（P0 页面需要）
1. **地图样式** → scenes/map.css (~200 行)
   - .strategic-map
   - .map-node, .node-halo, .node-core
   - .route-line, .route-江河, .route-山道, .route-关隘
   - .map-controls, .map-legend
   - .army-marker

2. **HUD 样式** → components/hud.css (~50 行)
   - .metric-bar
   - .metrics, .metric
   - .campaign-mark
   - .turn-date

3. **面板样式** → components/panels.css (~100 行)
   - .floating-panel
   - .floating-close
   - .panel-content
   - .panel-title

4. **表单样式** → components/forms.css (~80 行)
   - input, select, textarea
   - .segmented
   - 表单布局

### 中优先级（现有功能）
5. **菜单样式** → scenes/menu.css (~150 行)
   - .menu-screen, .ink-home
   - .ink-side-menu
   - .menu-scroll
   - .menu-actions

6. **人物样式** → components/characters.css (~200 行)
   - .character-book
   - .portrait-grid, .portrait
   - .character-dossier
   - .ability-grid, .traits

7. **军队样式** → components/army.css (~100 行)
   - .army-ledger
   - .army-mini-list

8. **外交样式** → components/diplomacy.css (~80 行)
   - .diplomacy-panel
   - .treaty-scroll

9. **国策样式** → components/focus.css (~80 行)
   - .focus-book
   - .focus-column
   - .focus-progress

10. **对话框样式** → components/modals.css (~150 行)
    - .modal-backdrop
    - .dialogue-modal
    - .dialogue-history

### 低优先级（可延后）
11. **历史时间线** → components/timeline.css (~100 行)
12. **家族面板** → components/family.css (~80 行)
13. **API 配置** → components/api-config.css (~150 行)
14. **其他杂项** → utils/misc.css (~100 行)

## 迁移策略

### 渐进式迁移
1. **P0 阶段**：每构建一个新页面，迁移该页面需要的样式
2. **测试驱动**：每次迁移后运行 `npm run build` 验证
3. **向后兼容**：保留 styles.css 直到所有样式迁移完成
4. **删除冗余**：迁移完成后删除 styles.css

### 迁移步骤
```bash
# 1. 读取 styles.css 中的特定样式块
sed -n 'START,ENDp' web/src/styles.css

# 2. 复制到目标文件
# 3. 格式化并添加注释
# 4. 从 styles.css 中删除已迁移的样式
# 5. 构建验证
npm run build
```

## 验收标准
- [ ] 所有样式迁移到模块化结构
- [ ] 删除 styles.css
- [ ] 更新 main.tsx 只导入 styles/index.css
- [ ] 构建无错误
- [ ] 所有现有页面样式正常

## 预计工作量
- **高优先级**: 2-3 天
- **中优先级**: 2-3 天
- **低优先级**: 1-2 天
- **总计**: 5-8 天

---

**最后更新**: 2026-07-22  
**当前进度**: 10% (基础结构完成)  
**下一步**: P0 阶段逐步迁移
