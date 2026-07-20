import React from "react";
import { CheckCircle2, KeyRound, Loader2, Settings2, X } from "lucide-react";

import {
  ApiRequestError,
  saveGameLlmConfig,
  saveMenuLlmConfig,
} from "../api";
import type { LlmConfigPayload, LlmConfigSummary } from "../types";

type ApiConfigModalProps = {
  mode: "menu" | "game";
  initial: LlmConfigSummary;
  onClose: () => void;
  onSaved: (config: LlmConfigSummary) => void;
};

const thinkingOptions = ["", "minimal", "low", "medium", "high", "adaptive", "disabled"];

function configErrorText(error: unknown) {
  if (error instanceof ApiRequestError) {
    const provider = error.detail.provider_message?.trim();
    return provider && provider !== error.message ? `${error.message}（${provider}）` : error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

export function ApiConfigModal({ mode, initial, onClose, onSaved }: ApiConfigModalProps) {
  const [baseUrl, setBaseUrl] = React.useState(initial.base_url || "https://api.openai.com/v1");
  const [model, setModel] = React.useState(initial.model || "gpt-4o-mini");
  const [apiKey, setApiKey] = React.useState("");
  const [maxTokens, setMaxTokens] = React.useState(String(initial.max_tokens || 8000));
  const [timeout, setTimeoutValue] = React.useState(String(initial.timeout_seconds || 180));
  const [connectTimeout, setConnectTimeout] = React.useState(String(initial.connect_timeout_seconds || 60));
  const [readTimeout, setReadTimeout] = React.useState(String(initial.read_timeout_seconds || 120));
  const [thinkingLevel, setThinkingLevel] = React.useState(initial.thinking_level || "");
  const [advancedModel, setAdvancedModel] = React.useState(initial.advanced_model || "");
  const [advancedBaseUrl, setAdvancedBaseUrl] = React.useState(initial.advanced_base_url || "");
  const [advancedApiKey, setAdvancedApiKey] = React.useState("");
  const [advancedThinkingLevel, setAdvancedThinkingLevel] = React.useState(initial.advanced_thinking_level || "");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [success, setSuccess] = React.useState("");

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError("");
    setSuccess("");

    const numbers = [maxTokens, timeout, connectTimeout, readTimeout].map(Number);
    if (!baseUrl.trim() || !model.trim()) {
      setError("API Base URL 和模型名称不能为空。");
      return;
    }
    if (numbers.some((value) => !Number.isFinite(value) || value <= 0)) {
      setError("最大 Token 和三个超时值必须是大于 0 的数字。");
      return;
    }

    const payload: LlmConfigPayload = {
      base_url: baseUrl.trim(),
      model: model.trim(),
      api_key: apiKey.trim(),
      max_tokens: Math.round(numbers[0]),
      timeout_seconds: numbers[1],
      connect_timeout_seconds: numbers[2],
      read_timeout_seconds: numbers[3],
      thinking_level: thinkingLevel,
      advanced_model: advancedModel.trim(),
      advanced_base_url: advancedBaseUrl.trim(),
      advanced_api_key: mode === "game"
        ? advancedApiKey.trim() || (initial.has_advanced_api_key ? "__keep__" : "")
        : advancedApiKey.trim(),
      advanced_thinking_level: advancedThinkingLevel,
    };

    setBusy(true);
    try {
      const saved = mode === "menu"
        ? await saveMenuLlmConfig(payload)
        : await saveGameLlmConfig(payload);
      onSaved(saved);
      setApiKey("");
      setAdvancedApiKey("");
      setSuccess("模型连通性验证通过，配置已保存。");
    } catch (saveError) {
      setError(configErrorText(saveError));
    } finally {
      setBusy(false);
    }
  };

  return <div className="modal-backdrop api-config-backdrop" onMouseDown={() => { if (!busy) onClose(); }}>
    <section className="api-config-modal" role="dialog" aria-modal="true" aria-labelledby="api-config-title" onMouseDown={(event) => event.stopPropagation()}>
      <button className="close-button" type="button" aria-label="关闭 API 配置" onClick={onClose} disabled={busy}><X /></button>
      <header>
        <span><Settings2 /></span>
        <div><small>{mode === "menu" ? "入局前设置" : "当前游戏即时生效"}</small><h2 id="api-config-title">API 与模型配置</h2><p>保存前会测试模型连通性；验证失败不会覆盖当前配置。</p></div>
      </header>
      <form className="api-config-form" onSubmit={(event) => void submit(event)}>
        <fieldset disabled={busy}>
          <div className="api-config-grid api-config-basic">
            <label className="wide"><span>API Base URL</span><input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" autoComplete="url" /></label>
            <label><span>模型名称</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="gpt-4o-mini" autoComplete="off" /></label>
            <label><span>API Key</span><input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={initial.has_api_key ? "已配置，留空继续使用" : "请输入 API Key"} autoComplete="new-password" /><small><KeyRound />{initial.has_api_key ? "当前已有密钥" : "尚未配置密钥"}</small></label>
          </div>
          <details className="api-config-advanced">
            <summary>高级配置 <span>Token、超时与独立推演模型</span></summary>
            <div className="api-config-grid">
              <label><span>最大 Token</span><input type="number" min="1" step="1" value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} /></label>
              <label><span>思考等级</span><select value={thinkingLevel} onChange={(event) => setThinkingLevel(event.target.value)}>{thinkingOptions.map((value) => <option key={value || "default"} value={value}>{value || "服务商默认"}</option>)}</select></label>
              <label><span>总超时（秒）</span><input type="number" min="1" value={timeout} onChange={(event) => setTimeoutValue(event.target.value)} /></label>
              <label><span>连接超时（秒）</span><input type="number" min="1" value={connectTimeout} onChange={(event) => setConnectTimeout(event.target.value)} /></label>
              <label><span>读取超时（秒）</span><input type="number" min="1" value={readTimeout} onChange={(event) => setReadTimeout(event.target.value)} /></label>
              <label><span>高级模型名称</span><input value={advancedModel} onChange={(event) => setAdvancedModel(event.target.value)} placeholder="留空则全部使用主模型" autoComplete="off" /></label>
              <label className="wide"><span>高级模型 Base URL</span><input value={advancedBaseUrl} onChange={(event) => setAdvancedBaseUrl(event.target.value)} placeholder="留空则沿用主模型地址" autoComplete="url" /></label>
              <label><span>高级模型 API Key</span><input type="password" value={advancedApiKey} onChange={(event) => setAdvancedApiKey(event.target.value)} placeholder={initial.has_advanced_api_key ? "已配置，留空继续使用" : "留空则沿用主密钥"} autoComplete="new-password" /></label>
              <label><span>高级模型思考等级</span><select value={advancedThinkingLevel} onChange={(event) => setAdvancedThinkingLevel(event.target.value)}>{thinkingOptions.map((value) => <option key={value || "advanced-default"} value={value}>{value || "服务商默认"}</option>)}</select></label>
            </div>
          </details>
        </fieldset>
        {error && <p className="api-config-status error" role="alert">{error}</p>}
        {success && <p className="api-config-status success"><CheckCircle2 />{success}</p>}
        <div className="api-config-actions">
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>取消</button>
          <button type="submit" disabled={busy}>{busy ? <><Loader2 className="spin" />正在测试连通性</> : <><KeyRound />测试并保存</>}</button>
        </div>
      </form>
    </section>
  </div>;
}
