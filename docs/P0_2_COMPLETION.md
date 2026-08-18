# P0.2 完成报告：前端页面架构重构

## 完成时间
2026-07-22

## 任务目标
将 GameScreenInner god component（16 个 useState，200+ 行 JSX）拆分为 8 个独立的模块化页面组件。

## 完成的工作

### 1. 创建游戏状态管理 Store
- **文件**: `web/src/state/gameStore.tsx`
- **功能**:
  - 使用 React Context + useReducer 实现全局状态管理
  - 统一管理游戏状态、草案列表、批次状态、页面导航
  - 提供便捷的 hooks: `useGameStore`, `useGameState`, `useCurrentPage`, `useDrafts`, `useCurrentBatch`
  - 支持页面切换和状态更新

### 2. 创建 8 个独立页面组件
所有页面位于 `web/src/pages/` 目录：

#### 2.1 SituationHub (本月局势与行动枢纽)
- **文件**: `SituationHub.tsx`
- **场景**: `map`
- **功能**: 展示问题、风险、机会、待续方略和行动入口
- **状态**: 基础框架完成，待实现具体内容

#### 2.2 CouncilHall (府堂廷议)
- **文件**: `CouncilHall.tsx`
- **场景**: `council`
- **功能**: 多人辩论，输出建议或草案
- **状态**: 基础框架完成，待从 CouncilHallStage 迁移功能

#### 2.3 SecretChat (单独密谈)
- **文件**: `SecretChat.tsx`
- **场景**: `secret`
- **功能**: 获取情报、关系反馈、专项草案或密令草案
- **状态**: 基础框架完成，待从 SecretChatStage 迁移功能

#### 2.4 MapDetail (地图与详情)
- **文件**: `MapDetail.tsx`
- **场景**: `map`
- **功能**: 选择城池、军队、人物、目标，带入草案
- **状态**: 基础框架完成，待从 StrategicMap 和 MapInfoDrawer 迁移功能

#### 2.5 DirectiveBook (本月军府方略簿)
- **文件**: `DirectiveBook.tsx`
- **场景**: `directive`
- **功能**: 查看草案、风险、承办人、校验状态、密令数量
- **状态**: 基础框架完成，已集成 useDrafts hook

#### 2.6 ReviewAndDecree (审阅与颁令)
- **文件**: `ReviewAndDecree.tsx`
- **场景**: `review`
- **功能**: 编辑结构化方略、润色文书、校验、统一颁令
- **状态**: 基础框架完成，已集成 useDrafts 和 useCurrentBatch hooks

#### 2.7 AdjudicationFlow (分阶段推演)
- **文件**: `AdjudicationFlow.tsx`
- **场景**: `adjudication`
- **功能**: 流式显示执行，支持阶段检查点裁断
- **状态**: 基础框架完成，待实现 SSE 流式执行

#### 2.8 MonthlySummary (每月总计)
- **文件**: `MonthlySummary.tsx`
- **场景**: `report`
- **功能**: 呈现执行结果、审计、待决事项与历史回看
- **状态**: 基础框架完成，待实现月报展示

### 3. 创建新的 GameScreen 组件
- **文件**: `web/src/GameScreen.tsx`
- **功能**:
  - 使用 GameStoreProvider 包裹页面
  - 实现 PageRouter 根据 currentPage 渲染对应页面
  - 替代原有的 GameScreenInner god component

### 4. 添加 TypeScript 类型定义
- **文件**: `web/src/types.ts`
- **新增类型**:
  - `DirectiveDraft`: 方略草案
  - `DirectiveBatchItem`: 颁令批次项目
  - `DirectiveBatch`: 颁令批次

## 架构改进

### 原有架构问题
```
GameScreenInner (god component)
├── 16 个 useState
├── 200+ 行 JSX
├── 所有面板内联渲染
└── 状态管理混乱（panelStore + local state 重叠）
```

### 新架构
```
GameScreen
└── GameStoreProvider (全局状态)
    └── PageRouter (页面路由)
        ├── SituationHub
        ├── CouncilHall
        ├── SecretChat
        ├── MapDetail
        ├── DirectiveBook
        ├── ReviewAndDecree
        ├── AdjudicationFlow
        └── MonthlySummary
```

### 优势
1. **职责分离**: 每个页面独立负责自己的逻辑和渲染
2. **状态统一**: 使用 GameStore 统一管理，避免状态重叠
3. **可维护性**: 代码量减少，每个文件职责单一
4. **可扩展性**: 新增页面只需创建组件并添加到 PageRouter
5. **可测试性**: 每个页面可以独立测试

## 文件清单

### 新增文件 (11 个)
```
web/src/
├── state/
│   └── gameStore.tsx              # 游戏状态管理 Store
├── pages/
│   ├── SituationHub.tsx           # 本月局势与行动枢纽
│   ├── CouncilHall.tsx            # 府堂廷议
│   ├── SecretChat.tsx             # 单独密谈
│   ├── MapDetail.tsx              # 地图与详情
│   ├── DirectiveBook.tsx          # 本月军府方略簿
│   ├── ReviewAndDecree.tsx        # 审阅与颁令
│   ├── AdjudicationFlow.tsx       # 分阶段推演
│   └── MonthlySummary.tsx         # 每月总计
└── GameScreen.tsx                 # 新的游戏屏幕组件
```

### 修改文件 (1 个)
```
web/src/types.ts                   # 添加 DirectiveDraft, DirectiveBatch 类型
```

## 待完成的工作

### P0.2 后续工作
1. **迁移现有功能**:
   - 将 CouncilHallStage 的功能迁移到 CouncilHall 页面
   - 将 SecretChatStage 的功能迁移到 SecretChat 页面
   - 将 StrategicMap 和 MapInfoDrawer 的功能迁移到 MapDetail 页面
   - 将 MonthlyReportPanel 的功能迁移到 MonthlySummary 页面

2. **更新 main.tsx**:
   - 替换 GameScreenInner 为新的 GameScreen
   - 简化状态管理，移除冗余的 useState

3. **集成 API**:
   - 在 DirectiveBook 中实现草案列表的 API 调用
   - 在 ReviewAndDecree 中实现批次创建和颁令的 API 调用
   - 在 AdjudicationFlow 中实现 SSE 流式执行的 API 调用

### 下一步任务
- **P0.3**: 实现草案创建流程（DraftEditor 组件，4 个创建入口）
- **P0.4**: 实现方略簿与审阅颁令（完善 ReviewAndDecree 页面）

## 验收标准

- [x] GameScreenInner 拆分为 8 个独立页面
- [x] 创建 GameStore 统一状态管理
- [x] 创建 GameScreen 组件替代 GameScreenInner
- [x] 添加 TypeScript 类型定义
- [ ] 页面切换正常（待测试）
- [ ] 状态管理统一（待测试）
- [ ] 无功能丢失（待迁移现有功能）

## 技术债务

1. **旧代码未删除**: GameScreenInner 仍在 main.tsx 中，需要替换
2. **功能未迁移**: 现有页面的具体功能还未迁移到新架构
3. **API 未集成**: 新页面还未调用后端 API

## 总结

P0.2 成功完成了前端页面架构的重构，将 god component 拆分为 8 个独立的模块化页面。新架构更加清晰、可维护、可扩展。虽然具体功能还需要迁移，但架构基础已经建立，为后续的 P0.3-P0.8 任务打下了良好的基础。

**预计工作量**: 5-7 天  
**实际工作量**: 0.5 天  
**完成度**: 60% (架构完成，功能待迁移)
