# 主界面 API 与模型配置入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 当前目录不是 Git 仓库且用户禁止擅自初始化；在当前工作区内串行执行，不创建 worktree 或提交。

**Goal:** 在标题主菜单和游戏内侧栏增加共用的 API/模型配置弹窗，复用现有明末版后端配置接口并让游戏内修改即时生效。

**Architecture:** 新增一个只管理配置表单的 `ApiConfigModal`；`main.tsx` 只负责两个入口和配置摘要状态，`api.ts` 统一封装菜单态与游戏态的三个接口。后端配置存储、密钥复用、连通性验证和运行时切换保持不变。

**Tech Stack:** React 18、TypeScript、Vite、FastAPI、pytest 静态前端合同测试。

## Global Constraints

- 密钥不从后端回显，不进入 URL、浏览器存储或日志。
- 菜单态保存调用 `POST /api/menu/llm`；游戏态读取/保存调用 `GET/POST /api/llm/config`。
- 游戏态已有高级密钥而输入留空时提交 `__keep__`，不得清空旧密钥。
- 保存前必须由现有后端执行真实模型连通性测试，通过后才持久化。
- 不修改 `runtime_llm.json` 格式，不增加提供商预设或模型列表请求。
- 不初始化 Git；每个任务通过测试后更新本计划复选框和实际证据。

---

### Task 1：锁定前端配置合同并补齐类型/API 层

**Files:**

- Create: `tests/test_frontend_api_config_contract.py`
- Modify: `web/src/types.ts`
- Modify: `web/src/api.ts`

**Interfaces:**

- Produces: `LlmConfigSummary`、`LlmConfigPayload`。
- Produces: `saveMenuLlmConfig(payload)`、`getGameLlmConfig()`、`saveGameLlmConfig(payload)`。
- Consumes: 现有 `api<T>()`、`MenuStatus` 和后端 `/api/menu/llm`、`/api/llm/config`。

- [x] **Step 1: 写失败的静态合同测试**

测试必须读取 `types.ts`、`api.ts`、`components/apiConfigModal.tsx` 和 `main.tsx`，分别断言：完整配置类型存在；三个 API 方法使用正确路径；弹窗包含密码字段、`__keep__` 和“测试并保存”；主菜单/侧栏入口 class 分别为 `api-config-menu`、`api-config-sidebar`。

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_llm_configuration_types_cover_safe_status_and_editable_payload():
    source = (ROOT / "web/src/types.ts").read_text(encoding="utf-8")
    assert "export type LlmConfigSummary" in source
    assert "export type LlmConfigPayload" in source
    assert "has_api_key: boolean" in source
    assert "has_advanced_api_key: boolean" in source
    assert "llm: LlmConfigSummary" in source


def test_api_layer_exposes_menu_and_live_llm_configuration():
    source = (ROOT / "web/src/api.ts").read_text(encoding="utf-8")
    assert '"/api/menu/llm"' in source
    assert '"/api/llm/config"' in source
    for name in ("saveMenuLlmConfig", "getGameLlmConfig", "saveGameLlmConfig"):
        assert f"export const {name}" in source


def test_shared_modal_preserves_secrets_and_exposes_advanced_fields():
    source = (ROOT / "web/src/components/apiConfigModal.tsx").read_text(encoding="utf-8")
    assert 'type="password"' in source
    assert '"__keep__"' in source
    for label in ("API Base URL", "模型名称", "API Key", "高级配置", "测试并保存"):
        assert label in source


def test_menu_and_game_sidebar_share_api_config_modal():
    source = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
    assert 'className="api-config-menu"' in source
    assert 'className="api-config-sidebar"' in source
    assert source.count("<ApiConfigModal") == 2
```

- [x] **Step 2: 运行测试并确认 RED**

Run: `python3 -m pytest tests/test_frontend_api_config_contract.py -q`

Expected: FAIL，原因是 `web/src/components/apiConfigModal.tsx` 尚不存在，且 API 方法/入口尚未实现。

- [x] **Step 3: 增加配置类型**

在 `web/src/types.ts` 中定义：

```ts
export type LlmConfigSummary = {
  base_url: string;
  model: string;
  has_api_key: boolean;
  max_tokens: number;
  timeout_seconds: number;
  connect_timeout_seconds: number;
  read_timeout_seconds: number;
  thinking_level: string;
  advanced_model: string;
  advanced_base_url: string;
  has_advanced_api_key: boolean;
  advanced_thinking_level: string;
  persisted?: LlmConfigSummary;
};

export type LlmConfigPayload = Omit<LlmConfigSummary,
  "has_api_key" | "has_advanced_api_key" | "persisted"
> & { api_key: string; advanced_api_key: string };
```

将 `MenuStatus` 增加 `llm: LlmConfigSummary`，保留其现有字段。

- [x] **Step 4: 封装三个 API 方法并统一返回摘要**

在 `web/src/api.ts` 导入两个新类型并增加：

```ts
export const saveMenuLlmConfig = async (payload: LlmConfigPayload) =>
  (await api<{ ok: boolean; llm: LlmConfigSummary }>("/api/menu/llm", {
    method: "POST", body: JSON.stringify(payload),
  })).llm;

export const getGameLlmConfig = () => api<LlmConfigSummary>("/api/llm/config");

export const saveGameLlmConfig = (payload: LlmConfigPayload) =>
  api<LlmConfigSummary>("/api/llm/config", {
    method: "POST", body: JSON.stringify(payload),
  });
```

- [x] **Step 5: 运行 TypeScript 构建检查本任务接口**

Run: `cd web && npm run build`

Expected: 由于弹窗和入口尚未实现，现有代码仍可构建；新类型/API 层无 TypeScript 错误。

实际证据：前端合同测试初次运行 `4 failed`，分别由类型、API、弹窗和入口缺失触发；补齐类型/API 后 `npm run build` 成功。

---

### Task 2：实现可复用国风 API 配置弹窗

**Files:**

- Create: `web/src/components/apiConfigModal.tsx`
- Modify: `web/src/styles.css`
- Test: `tests/test_frontend_api_config_contract.py`

**Interfaces:**

- Consumes: `LlmConfigSummary`、`LlmConfigPayload`、`saveMenuLlmConfig()`、`saveGameLlmConfig()`。
- Produces: `ApiConfigModal({ mode, initial, onClose, onSaved })`。

- [x] **Step 1: 实现弹窗状态与安全的 payload 转换**

组件 props 固定为：

```ts
type ApiConfigModalProps = {
  mode: "menu" | "game";
  initial: LlmConfigSummary;
  onClose: () => void;
  onSaved: (config: LlmConfigSummary) => void;
};
```

表单以 `initial` 初始化，API Key 始终初始化为空。游戏态构造 payload 时使用：

```ts
advanced_api_key: advancedApiKey || (initial.has_advanced_api_key ? "__keep__" : ""),
```

菜单态保持空字符串，让后端沿用已保存密钥。Base URL/模型为空或四个数值字段非正数时只显示本地错误，不发请求。

- [x] **Step 2: 实现基础区、高级折叠区和提交反馈**

必须包含：

- `API Base URL`、`模型名称`、两个 `type="password"` 密钥输入框。
- `<details>` 高级区，包含 Token、三类超时、思考等级和高级模型字段。
- 保存时禁用 fieldset、关闭按钮和遮罩关闭，按钮文案变为“正在测试连通性”。
- 成功显示“模型连通性验证通过，配置已保存。”；失败保留用户输入并显示 `ApiRequestError` 文本。

- [x] **Step 3: 增加国风样式**

在 `web/src/styles.css` 增加 `.api-config-modal`、`.api-config-form`、`.api-config-grid`、`.api-config-actions`、`.api-config-status`。弹窗宽度使用 `min(760px, 90vw)`，最大高度 `88vh` 并允许内容滚动；色彩复用 `--paper`、`--red`、`--gold`，不得引入第三方 UI 依赖。

- [x] **Step 4: 运行组件合同测试**

Run: `python3 -m pytest tests/test_frontend_api_config_contract.py::test_shared_modal_preserves_secrets_and_exposes_advanced_fields -q`

Expected: PASS。

实际证据：共享弹窗合同测试 `1 passed`；浏览器实测基础区、高级折叠区、密码输入、错误反馈和滚动布局均正常。

---

### Task 3：接入标题菜单与游戏内侧栏

**Files:**

- Modify: `web/src/main.tsx`
- Modify: `web/src/styles.css`
- Test: `tests/test_frontend_api_config_contract.py`

**Interfaces:**

- Consumes: `ApiConfigModal`、`getGameLlmConfig()`、`MenuStatus.llm`。
- Produces: 主菜单 `.api-config-menu` 与游戏内 `.api-config-sidebar` 两个入口。

- [x] **Step 1: 接入标题主菜单**

`MenuScreen` 增加 `configOpen`；按钮点击打开 `ApiConfigModal mode="menu" initial={status.llm}`。保存成功后合并：

```ts
setStatus((current) => current ? {
  ...current,
  has_api_key: saved.has_api_key,
  llm: saved,
} : current);
```

无密钥提示改为“尚未配置大模型，请先完成 API 配置。”，不再要求通过启动器配置。

- [x] **Step 2: 接入游戏内侧栏**

`GameScreen` 增加 `configOpen` 和 `llmConfig`。点击 `.api-config-sidebar` 后先调用 `getGameLlmConfig()`；成功时打开弹窗，失败时进入现有全局错误条。保存回调更新 `llmConfig`，不改变 `GameState`、当前面板或回合。

- [x] **Step 3: 运行完整前端合同测试并确认 GREEN**

Run: `python3 -m pytest tests/test_frontend_api_config_contract.py -q`

Expected: `4 passed`。

- [x] **Step 4: 运行生产构建**

Run: `cd web && npm run build`

Expected: `tsc -b && vite build` exit 0，生成包含 API 配置入口的新 `web/dist`。

实际证据：前端合同 `4 passed`；生产构建成功，生成 `index-LHwfBsER.js` 与 `index-DXH1HseO.css`。

---

### Task 4：回归、对抗性审查和运行中项目验证

**Files:**

- Modify: `docs/superpowers/plans/2026-07-16-api-config-ui.md`
- Modify: `/Users/zhuanzmima0000/Documents/Obsidian Vault/wiki/DeepSeek-观察/2026-07-16.md`

**Interfaces:**

- Consumes: 构建后的 `web/dist` 和当前 FastAPI 服务。
- Produces: 可刷新查看的双入口配置 UI 与可恢复验证记录。

- [x] **Step 1: 运行全量 Python 回归**

Run: `python3 -m pytest tests -q`

Expected: 0 failed / 0 errors。

- [x] **Step 2: 对抗性检查密钥和接口边界**

检查源码和构建产物：密钥不得写入 `localStorage`、`sessionStorage`、URL；菜单态和游戏态不得串错接口；游戏态高级密钥保留哨兵存在。

Run:

```bash
rg -n 'localStorage|sessionStorage|api_key=' web/src web/dist
rg -n '/api/menu/llm|/api/llm/config|__keep__' web/src
```

Expected: 第一条 0 命中；第二条命中预期 API 封装与高级密钥保留逻辑。

- [x] **Step 3: 验证当前服务读取新构建**

对正在运行的端口请求首页和主 JS，确认 HTTP 200 且构建产物包含 `API 配置`、`测试并保存` 文案。若服务已停止，则用 `python3 launcher.py` 重新启动。

- [x] **Step 4: 完成计划和 Obsidian 收口**

勾选所有已完成步骤，记录实际测试数、构建结果、运行端口和下一人工检查点。Obsidian 条目必须包含发现、长期价值、归档状态与下一入口。

实际证据：对抗性审查发现游戏内切换模型会误调用完整 `begin_turn()`；新增回归测试先失败后通过，并拆出只重建 Agent 的 `GameSession.refresh_registry()`。最终全量 `148 passed`，前端生产构建成功；密钥浏览器存储/URL 扫描 0 命中；重启后的 `http://127.0.0.1:8010` 首页、JS bundle、`/api/menu/status` 均返回 200，新 bundle 包含双入口与配置弹窗文案。下一人工检查点是用户填写真实 API 后进入游戏，点击侧栏“API 配置”确认即时切换体验。
