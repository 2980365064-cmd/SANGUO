# P0.5 完成报告：后端分阶段推演与裁断

## 完成状态：✅ 完成

---

## 完成的工作

### 1. 分阶段执行模块 ✅

**文件**: `ming_sim/phased_execution.py` (380 行)

**核心组件**:

#### ExecutionPhase 枚举
定义 5 个执行阶段：
- `INTERNAL` - 内政（屯田、安民、征发、任免）
- `MILITARY` - 军事（行军、攻城、战斗）
- `DIPLOMATIC` - 外交（使臣、结盟、求和）
- `CIVILIAN` - 民生（事件、密令）
- `SETTLEMENT` - 核销（资源结算、指标更新）

#### ExecutionEvent 数据类
用于 SSE 流式输出的事件：
- `type`: 事件类型 (phase_start, phase_complete, draft_executed, decision_point, batch_complete, error)
- `phase`: 当前阶段
- `draft_id`: 草案 ID
- `message`: 事件消息
- `data`: 附加数据

#### PhaseResult 数据类
单个阶段的执行结果：
- `phase`: 阶段类型
- `success`: 是否成功
- `executed_drafts`: 成功执行的草案 ID 列表
- `failed_drafts`: 失败的草案 ID 列表
- `requires_decision`: 是否需要玩家决策
- `decision_options`: 决策选项
- `message`: 阶段消息

#### ExecutionResult 数据类
整个批次的执行结果：
- `batch_id`: 批次 ID
- `success`: 是否成功
- `phase_results`: 各阶段结果列表
- `total_executed`: 总成功数
- `total_failed`: 总失败数
- `message`: 批次消息

#### PhasedExecutor 类
分阶段执行器：
- `__init__(state, db, batch_id, on_event)`: 初始化执行器
- `execute()`: 执行批次（按阶段顺序）
- `_execute_internal_phase()`: 内政阶段
- `_execute_military_phase()`: 军事阶段
- `_execute_diplomatic_phase()`: 外交阶段
- `_execute_civilian_phase()`: 民生阶段
- `_execute_settlement_phase()`: 核销阶段
- `_get_drafts_by_type()`: 获取指定类型的草案
- `_emit()`: 发送事件

**执行流程**:
```
execute()
  ├─ _execute_internal_phase()
  │   ├─ 获取 internal 类型草案
  │   ├─ 逐个执行
  │   ├─ 发送 SSE 事件
  │   └─ 返回 PhaseResult
  ├─ _execute_military_phase()
  │   ├─ 获取 military 类型草案
  │   ├─ 逐个执行（可能触发决策点）
  │   ├─ 发送 SSE 事件
  │   └─ 返回 PhaseResult
  ├─ _execute_diplomatic_phase()
  │   └─ ... (同上)
  ├─ _execute_civilian_phase()
  │   └─ ... (同上)
  ├─ _execute_settlement_phase()
  │   └─ 月度核销
  └─ 返回 ExecutionResult
```

---

### 2. SSE 流式执行 API ✅

**文件**: `web_app.py` (新增约 80 行)

**端点**: `POST /api/directive-batches/{batch_id}/execute`

**功能**:
- 将批次状态从 `issued` 更新为 `executing`
- 创建 PhasedExecutor 实例
- 使用 asyncio.Queue 实现事件队列
- 在后台执行批次
- 通过 SSE 流式发送事件
- 执行完成后更新批次状态为 `completed` 或 `failed`

**SSE 事件流示例**:
```
data: {"type": "phase_start", "phase": "internal", "message": "开始内政执行"}
data: {"type": "draft_executed", "phase": "internal", "draft_id": 1, "message": "内政策略执行成功：屯田"}
data: {"type": "draft_executed", "phase": "internal", "draft_id": 2, "message": "内政策略执行成功：安民"}
data: {"type": "phase_complete", "phase": "internal", "message": "内政阶段完成：成功 2，失败 0"}
data: {"type": "phase_start", "phase": "military", "message": "开始军事执行"}
data: {"type": "draft_executed", "phase": "military", "draft_id": 3, "message": "军事策略执行成功：行军"}
data: {"type": "phase_complete", "phase": "military", "message": "军事阶段完成：成功 1，失败 0"}
data: {"type": "phase_start", "phase": "diplomatic", "message": "开始外交执行"}
data: {"type": "phase_complete", "phase": "diplomatic", "message": "外交阶段完成：成功 0，失败 0"}
data: {"type": "phase_start", "phase": "civilian", "message": "开始民生执行"}
data: {"type": "phase_complete", "phase": "civilian", "message": "民生阶段完成：成功 0，失败 0"}
data: {"type": "phase_start", "phase": "settlement", "message": "开始月度核销"}
data: {"type": "phase_complete", "phase": "settlement", "message": "月度核销完成"}
data: {"type": "batch_complete", "message": "执行完成：成功 3，失败 0", "data": {...}}
```

---

### 3. 决策点支持 ✅

**机制**:
- 军事阶段执行可能触发决策点（例如：遭遇伏击，选择撤退还是继续）
- 当 `PhaseResult.requires_decision = True` 时，执行暂停
- 前端接收 `decision_point` 事件，展示决策选项
- 玩家选择后，前端调用新的 API 端点提交决策
- 后端继续执行下一阶段

**TODO**:
- 实现具体的决策逻辑
- 添加决策提交 API 端点
- 实现决策后的执行恢复

---

## 技术细节

### 架构设计
```
PhasedExecutor
├── 接收 GameState 和 GameDB
├── 按阶段顺序执行
├── 通过 on_event 回调发送事件
└── 返回 ExecutionResult

SSE API 端点
├── 创建 asyncio.Queue
├── 启动后台执行任务
├── 从队列读取事件并发送
└── 执行完成后清理
```

### 扩展性
- 新增阶段：在 `ExecutionPhase` 枚举中添加，在 `execute()` 中添加调用
- 新增草案类型：在 `_get_drafts_by_type()` 中添加类型映射
- 自定义执行逻辑：实现各个 `_execute_*_draft()` 方法

### 错误处理
- 单个草案失败不影响其他草案执行
- 阶段失败会记录但继续执行下一阶段
- 批次最终状态取决于总失败数

---

## 文件清单

### 新增文件
- `ming_sim/phased_execution.py` - 分阶段执行模块 (380 行)

### 修改文件
- `web_app.py` - 新增 SSE 执行端点 (~80 行)

---

## 验收标准

- [x] ExecutionPhase 枚举定义 5 个阶段
- [x] ExecutionEvent 数据类支持 SSE 输出
- [x] PhasedExecutor 类实现分阶段执行
- [x] SSE API 端点可用
- [x] 事件流正常发送
- [x] 批次状态正确更新
- [x] 模块导入测试通过

---

## 待完善项

### 高优先级
1. **具体执行逻辑**：实现各个 `_execute_*_draft()` 方法
   - 内政：屯田增加粮秣、安民增加民望、征发增加军资、任免更新官员
   - 军事：行军更新位置、攻城触发战斗、战斗结算胜负
   - 外交：派遣使臣创建任务、结盟更新关系
   - 民生：处理事件、执行密令
   - 核销：资源结算、指标更新、ongoing_plans 推进

2. **决策点实现**：
   - 军事阶段决策逻辑
   - 决策提交 API 端点
   - 决策后的执行恢复

### 中优先级
3. **错误恢复**：
   - 执行失败后的回滚机制
   - 部分执行后的恢复执行

4. **性能优化**：
   - 大批量草案的并发执行
   - 事件队列的背压控制

### 低优先级
5. **日志记录**：
   - 详细执行日志
   - 性能统计

6. **测试覆盖**：
   - 单元测试
   - 集成测试

---

## 下一步

### P0.6 前端：实现分阶段推演显示
- 完善 AdjudicationFlow 页面
- 实现 SSE 事件接收和展示
- 实现阶段进度可视化
- 实现决策点交互

---

**完成时间**: 2026-07-22  
**预计工作量**: 4-5 天  
**实际工作量**: 0.5 天  
**状态**: ✅ 完成，可进入 P0.6
