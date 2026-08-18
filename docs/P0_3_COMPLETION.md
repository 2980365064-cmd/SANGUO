# P0.3 完成报告：草案创建流程

## 完成状态：✅ 完成

---

## 完成的工作

### 1. API 层实现 ✅

**文件**: `web/src/api/directiveDrafts.ts`

**功能**:
- `listDirectiveDrafts()` - 列出草案（支持按回合、状态、类型筛选）
- `createDirectiveDraft()` - 创建草案
- `getDirectiveDraft()` - 获取单个草案
- `updateDirectiveDraft()` - 更新草案
- `deleteDirectiveDraft()` - 删除草案
- `validateDirectiveDraft()` - 校验草案

**类型定义**:
- `CreateDraftRequest` - 创建请求
- `UpdateDraftRequest` - 更新请求
- `ValidationResponse` - 校验响应

---

### 2. DraftEditor 组件 ✅

**文件**: `web/src/components/DraftEditor.tsx`

**功能**:
- 创建/编辑方略草案
- 支持 5 种来源类型（council_chat, secret_chat, map_detail, manual, suggestion）
- 支持 5 种方略类型（internal, military, diplomatic, other, secret）
- 表单字段：标题、类型、执行者、目标、时限、优先级、文书说明
- 动态添加约束条件和风险因素
- 实时校验（编辑模式下）
- 错误处理和加载状态

**UI 结构**:
```
DraftEditor
├── 基本信息
│   ├── 标题
│   ├── 方略类型
│   ├── 执行者
│   ├── 目标
│   ├── 时限
│   └── 优先级
├── 文书说明
│   └── 详细说明
├── 约束条件
│   └── 动态列表
├── 风险因素
│   └── 动态列表
├── 校验结果（编辑模式）
└── 操作按钮（取消/校验/创建）
```

---

### 3. 四个创建入口集成 ✅

#### 3.1 SituationHub（手动创建）
**文件**: `web/src/pages/SituationHub.tsx`

**功能**:
- "新建方略"按钮
- 草案列表展示（从 API 加载）
- 自动加载当前回合的草案
- 创建后自动刷新列表

**入口类型**: `manual`

#### 3.2 CouncilHall（府堂廷议）
**文件**: `web/src/pages/CouncilHall.tsx`

**功能**:
- "拟入方略"按钮
- 从廷议结论创建草案
- 提示用户可以将廷议结论转为草案

**入口类型**: `council_chat`

#### 3.3 SecretChat（单独密谈）
**文件**: `web/src/pages/SecretChat.tsx`

**功能**:
- "拟入密令"按钮
- 从密谈结论创建密令草案
- 提示用户可以将密谈结论转为密令

**入口类型**: `secret_chat`

#### 3.4 MapDetail（地图详情）
**文件**: `web/src/pages/MapDetail.tsx`

**功能**:
- "拟入方略"按钮（选择目标后显示）
- 从地图选择创建草案
- 支持选择城池/军队作为目标

**入口类型**: `map_detail`

---

### 4. 类型定义更新 ✅

**文件**: `web/src/types.ts`

**新增类型**:
- `DirectiveDraft` - 方略草案完整类型
- `DirectiveBatchItem` - 批次项目类型
- `DirectiveBatch` - 颁令批次类型

---

### 5. GameStore 集成 ✅

**文件**: `web/src/state/gameStore.tsx`

**已有功能**:
- `drafts: DirectiveDraft[]` - 草案列表状态
- `SET_DRAFTS` - 设置草案列表
- `ADD_DRAFT` - 添加草案
- `UPDATE_DRAFT` - 更新草案
- `REMOVE_DRAFT` - 删除草案
- `useDrafts()` hook - 便捷的草案操作接口

---

## 技术细节

### 数据流
```
用户操作
  ↓
DraftEditor 表单
  ↓
API 调用 (createDirectiveDraft / updateDirectiveDraft)
  ↓
后端处理 (directive_drafts 表)
  ↓
返回草案数据
  ↓
GameStore 更新 (ADD_DRAFT / UPDATE_DRAFT)
  ↓
UI 刷新
```

### 校验逻辑
1. **前端校验**:
   - 必填字段检查（标题）
   - 数值范围检查（时限 1-12，优先级 0-100）

2. **后端校验** (`validate_directive_draft`):
   - 执行者是否存在且属于刘备势力
   - 执行者状态是否为 active
   - 目标区域是否存在
   - 内政策略只能针对己方区域
   - 时限和优先级范围

### 错误处理
- API 错误：显示错误消息
- 网络错误：显示"网络错误"
- 校验错误：显示校验结果列表
- 加载状态：显示"加载中..."

---

## 文件清单

### 新增文件
- `web/src/api/directiveDrafts.ts` - API 层（120 行）
- `web/src/components/DraftEditor.tsx` - 草案编辑器组件（320 行）

### 修改文件
- `web/src/pages/SituationHub.tsx` - 集成手动创建入口
- `web/src/pages/CouncilHall.tsx` - 集成廷议创建入口
- `web/src/pages/SecretChat.tsx` - 集成密谈创建入口
- `web/src/pages/MapDetail.tsx` - 集成地图创建入口
- `web/src/types.ts` - 添加 DirectiveDraft 等类型

---

## 验收标准

- [x] DraftEditor 组件可正常渲染
- [x] 可从 4 个入口创建草案
- [x] 表单字段完整（标题、类型、执行者、目标、时限、优先级、说明、约束、风险）
- [x] 可动态添加/删除约束和风险
- [x] 前端校验正常
- [x] 后端 API 调用正常
- [x] 草案保存到数据库
- [x] GameStore 状态更新正常
- [x] 构建无错误

---

## 待优化项

1. **DraftEditor 样式**: 需要添加 CSS 样式美化表单
2. **执行者选择**: 当前为文本输入，可改为下拉选择（从 characters 列表）
3. **目标选择**: 当前为文本输入，可改为从地图选择
4. **草案预览**: 创建前可预览草案内容
5. **批量操作**: 支持批量删除/更新草案
6. **草案模板**: 提供常用草案模板（如北伐、屯田等）

---

## 下一步

### P0.4 前端：实现方略簿与审阅颁令
- 完善 DirectiveBook 页面（展示草案列表、详情）
- 完善 ReviewAndDecree 页面（审阅、校验、批量颁令）
- 集成 directive_batches API

---

**完成时间**: 2026-07-22  
**预计工作量**: 3-4 天  
**实际工作量**: 0.5 天  
**状态**: ✅ 完成，可进入 P0.4
