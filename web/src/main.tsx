import React from "react";
import { createRoot } from "react-dom/client";
import {
  Castle, FolderOpen, Loader2, Play, Settings, SlidersHorizontal, X,
} from "lucide-react";
import {
  getMenuStatus, newGame, continueGame, getState, getGameSettings, saveGameSettings,
} from "./api";
import type { GameState } from "./types";
import { errorText } from "./utils/errorText";
import { ApiConfigModal } from "./components/apiConfigModal";
import { GameScreen } from "./GameScreen";
import "./styles/index.css";

function MenuScreen({ onEnter }: { onEnter: (state: GameState) => void }) {
  const [status, setStatus] = React.useState<Awaited<ReturnType<typeof getMenuStatus>> | null>(null);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [configOpen, setConfigOpen] = React.useState(false);
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [denseInk, setDenseInk] = React.useState(false);
  const [reactionIntensity, setReactionIntensity] = React.useState<"restrained" | "standard" | "stormy">("standard");

  React.useEffect(() => { void getMenuStatus().then(setStatus).catch((e) => setError(errorText(e))); }, []);
  React.useEffect(() => {
    if (!settingsOpen) return;
    void getGameSettings().then(({ game_settings }) => setReactionIntensity(game_settings.world_reaction_intensity || "standard"))
      .catch((e) => setError(errorText(e)));
  }, [settingsOpen]);

  const changeReactionIntensity = async (value: "restrained" | "standard" | "stormy") => {
    setReactionIntensity(value);
    try {
      const { game_settings } = await getGameSettings();
      await saveGameSettings({ ...game_settings, world_reaction_intensity: value });
    } catch (e) { setError(errorText(e)); }
  };

  const enter = async (mode: "new" | "continue") => {
    setBusy(mode); setError("");
    try {
      const result = mode === "new" ? await newGame() : await continueGame();
      onEnter(result.state);
    } catch (e) { setError(errorText(e)); } finally { setBusy(""); }
  };

  return <main className={`menu-screen ink-home ${denseInk ? "dense-ink" : "light-ink"}`}>
    <div className="ink-menu-wash" />
    <aside className="ink-side-menu" aria-label="游戏主菜单">
      <div className="ink-side-mark"><span>刘备传</span><i>汉</i></div>
      <nav>
        <button className="primary" type="button" onClick={() => void enter("new")} disabled={!!busy}>
          {busy === "new" ? <Loader2 className="spin" /> : <Play />}<span>新开游戏</span>
        </button>
        <button type="button" onClick={() => void enter("continue")} disabled={!!busy || !status?.has_main_db}>
          {busy === "continue" ? <Loader2 className="spin" /> : <FolderOpen />}<span>加载存档</span>
        </button>
        <button type="button" onClick={() => setConfigOpen(true)} disabled={!status || !!busy}>
          <Settings /><span>API配置</span>
        </button>
        <button type="button" onClick={() => setSettingsOpen((open) => !open)} disabled={!!busy}>
          <SlidersHorizontal /><span>设置</span>
        </button>
      </nav>
      <div className="ink-side-footer">
        <small>建安十三年</small>
        <strong>公元二〇八</strong>
      </div>
    </aside>
    {settingsOpen && <section className="menu-settings-panel" aria-label="设置">
      <header><span>设置</span><button type="button" aria-label="关闭设置" onClick={() => setSettingsOpen(false)}><X /></button></header>
      <label><input type="checkbox" checked={denseInk} onChange={(event) => setDenseInk(event.target.checked)} />水墨遮罩</label>
      <label>天下反应强度
        <select value={reactionIntensity} onChange={(event) => void changeReactionIntensity(event.target.value as "restrained" | "standard" | "stormy") }>
          <option value="restrained">克制：较少杂音与建议</option>
          <option value="standard">标准：默认天下反馈</option>
          <option value="stormy">风云：更多机会与分歧</option>
        </select>
        <small>只影响微小与中等反应频率；重大待决与硬规则不变。</small>
      </label>
    </section>}
    <section className="ink-menu-caption" aria-label="当前局势">
      <p>曹军已据荆襄，江水连营。你无一郡之土，唯有未竟的汉室之志与身边可托生死之人。</p>
      {!status?.has_api_key && status && <small>尚未配置大模型</small>}
      {error && <strong>{error}</strong>}
    </section>
    {configOpen && status && <ApiConfigModal mode="menu" initial={status.llm} onClose={() => setConfigOpen(false)} onSaved={(saved) => {
      setStatus((current) => current ? { ...current, has_api_key: saved.has_api_key, llm: saved } : current);
    }} />}
  </main>;
}

function App() {
  const [state, setState] = React.useState<GameState | null>(null);
  const [checking, setChecking] = React.useState(true);
  React.useEffect(() => {
    void getState().then(setState).catch(() => setState(null)).finally(() => setChecking(false));
  }, []);
  if (checking) return <div className="loading-screen"><Castle /><span>展开天下舆图……</span></div>;
  return state ? <GameScreen initial={state} /> : <MenuScreen onEnter={setState} />;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
