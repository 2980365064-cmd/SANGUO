# P0.1 完成报告：后端数据库表创建

## 完成状态：✅ 完成

---

## 完成的工作

### 1. 数据库表结构 ✅

**新增 3 张表**（`ming_sim/db/schema.py`）：

#### directive_drafts - 方略草案表
- 存储方略草案（不可改变世界）
- 支持多种来源：council_chat, secret_chat, map_detail, manual, suggestion
- 结构化字段：类型、标题、执行者、目标、时限、优先级
- JSON 字段：资源、约束、风险、校验结果
- 状态流转：draft → validated → issued / rejected

#### directive_batches - 颁令批次表
- 存储颁令批次（不可变快照）
- 包含批次标题、邸报正文、总草案数
- 状态流转：pending → issued → executing → completed / failed
- 时间戳：创建、颁令、完成

#### directive_batch_items - 批次项目关联表
- 存储批次与草案的关联
- 执行顺序（execution_order）
- 执行状态和结果（JSON）
- 外键约束：级联删除

### 2. 数据库访问层 ✅

**新增模块**（`ming_sim/db/directive_drafts.py`）：

#### _DirectiveDraftsMixin
- `create_directive_draft()` - 创建草案
- `get_directive_draft()` - 获取单个草案
- `list_directive_drafts()` - 列出草案（支持筛选）
- `update_directive_draft()` - 更新草案
- `delete_directive_draft()` - 删除草案
- `validate_directive_draft()` - 校验草案（检查执行者、目标、时限等）

#### _DirectiveBatchesMixin
- `create_directive_batch()` - 创建批次（从草案列表）
- `get_directive_batch()` - 获取批次（含项目详情）
- `list_directive_batches()` - 列出批次
- `update_directive_batch()` - 更新批次
- `update_batch_item_execution()` - 更新项目执行状态

### 3. API 端点 ✅

**新增 11 个 API 端点**（`web_app.py`）：

#### 草案管理（6 个）
- `GET /api/directive-drafts` - 列出草案
- `POST /api/directive-drafts` - 创建草案
- `GET /api/directive-drafts/{id}` - 获取草案详情
- `PATCH /api/directive-drafts/{id}` - 更新草案
- `DELETE /api/directive-drafts/{id}` - 删除草案
- `POST /api/directive-drafts/{id}/validate` - 校验草案

#### 批次管理（4 个）
- `GET /api/directive-batches` - 列出批次
- `POST /api/directive-batches` - 创建批次
- `GET /api/directive-batches/{id}` - 获取批次详情
- `POST /api/directive-batches/{id}/issue` - 颁令

#### 请求模型（3 个）
- `DirectiveDraftRequest` - 创建草案请求
- `DirectiveDraftUpdateRequest` - 更新草案请求
- `DirectiveBatchRequest` - 创建批次请求

### 4. 集成与测试 ✅

- ✅ 将新 Mixin 集成到 GameDB 类
- ✅ 添加 datetime 导入
- ✅ 数据库表创建测试通过
- ✅ CRUD 操作测试通过
- ✅ 校验逻辑测试通过
- ✅ 批次创建测试通过
- ✅ web_app.py 语法检查通过

---

## 技术细节

### 数据库索引
```sql
-- 草案索引
CREATE INDEX idx_directive_drafts_turn ON directive_drafts(turn, status);
CREATE INDEX idx_directive_drafts_type ON directive_drafts(directive_type, status);

-- 批次索引
CREATE INDEX idx_directive_batches_turn ON directive_batches(turn, status);

-- 批次项目索引
CREATE INDEX idx_directive_batch_items_batch ON directive_batch_items(batch_id, execution_order);
```

### 校验逻辑
`validate_directive_draft()` 检查：
1. 执行者是否存在且属于刘备势力
2. 执行者状态是否为 active
3. 目标区域是否存在
4. 内政策略只能针对己方区域
5. 时限在 1-12 个月之间
6. 优先级在 0-100 之间

### 状态流转
**草案**：
- `draft` → `validated`（校验通过）
- `draft` → `invalid`（校验失败）
- `draft` / `validated` → `issued`（加入批次）
- `draft` → `rejected`（手动拒绝）

**批次**：
- `pending` → `issued`（颁令）
- `issued` → `executing`（开始执行）
- `executing` → `completed`（执行完成）
- `executing` → `failed`（执行失败）

---

## 文件清单

### 新增文件
- `ming_sim/db/directive_drafts.py` - 数据库访问层（242 行）

### 修改文件
- `ming_sim/db/schema.py` - 新增 3 张表和 4 个索引
- `ming_sim/db/__init__.py` - 集成新 Mixin
- `web_app.py` - 新增 11 个 API 端点和 3 个请求模型

---

## 验收标准

- [x] 表结构创建完成
- [x] CRUD API 可用
- [x] 校验逻辑实现
- [x] 批次创建和颁令 API 可用
- [x] 数据库操作测试通过
- [x] API 语法检查通过

---

## 下一步

### P0.2 前端：重构 GameScreenInner 为模块化页面
- 创建 8 个独立页面组件
- 实现页面切换逻辑
- 统一状态管理

### P0.3 前端：实现草案创建流程
- 创建 DraftEditor 组件
- 实现 4 个草案创建入口
- 集成校验 API

---

**完成时间**: 2026-07-22  
**预计工作量**: 4-5 天  
**实际工作量**: 0.5 天  
**状态**: ✅ 完成，可进入 P0.2
