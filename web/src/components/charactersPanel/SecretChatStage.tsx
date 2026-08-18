/**
 * 密谈舞台：背景 bg-secret-chamber.webp，可下密令。
 */
import React from "react";
import { ArrowLeft, LockKeyhole, Send } from "lucide-react";
import type { Character, DialogueMessage } from "../../types";
import { getDialogue, streamDialogue, enterSecretChat, exitSecretChat, createSecretOrder } from "../../api";
import { GameDialog } from "../GameDialog";
import { ActionSealButton, StatusMark } from "../ui";

export function SecretChatStage({
  character,
  onExit,
}: {
  character: Character;
  onExit: () => void;
}) {
  const [messages, setMessages] = React.useState<DialogueMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [stream, setStream] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    void enterSecretChat(character.name).catch(() => {});
    void getDialogue(character.name)
      .then((r) => setMessages(r.history || []))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    return () => { void exitSecretChat(character.name).catch(() => {}); };
  }, [character.name]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setStream("");
    setBusy(true);
    setError("");
    try {
      const response = await streamDialogue(character.name, text, (delta) => setStream((prev) => prev + delta), "secret");
      const answer = response.answer || "";
      setMessages((prev) => [...prev, { role: "minister", content: answer }]);
      setStream("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const [secretOrderOpen, setSecretOrderOpen] = React.useState(false);
  const [secretOrderTitle, setSecretOrderTitle] = React.useState("");
  const [secretOrderContent, setSecretOrderContent] = React.useState("");
  const [secretOrderBusy, setSecretOrderBusy] = React.useState(false);
  const portraitPath = `/portraits/sanguo/${(character.portrait_id || character.name).split('/').map(encodeURIComponent).join('/')}.webp`;

  const issueSecretOrder = async () => {
    if (!secretOrderTitle.trim() || !secretOrderContent.trim()) return;
    setSecretOrderBusy(true);
    try {
      await createSecretOrder(character.name, {
        title: secretOrderTitle.trim(),
        content: secretOrderContent.trim(),
      });
      setSecretOrderTitle("");
      setSecretOrderContent("");
      setSecretOrderOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSecretOrderBusy(false);
    }
  };

  return (
    <div className="secret-chat-stage">
      <div className="secret-chat-inner">
        <header className="correspondence-header">
          <div className="correspondent-portrait" aria-hidden="true">
            <img src={portraitPath} alt="" onError={(event) => { event.currentTarget.style.opacity = '0'; }} />
          </div>
          <div className="correspondent-identity">
            <span>军府密陈 · 仅限案内阅览</span>
            <h2>{character.name}</h2>
            <p>{character.office || character.political_group || '军府候问'}</p>
          </div>
          <div className="correspondence-seal" aria-hidden="true">密</div>
          <button className="close-button" aria-label="返回单独密谈页面" onClick={onExit}><ArrowLeft /><span>返回名册</span></button>
        </header>

        <section className="secret-chat-history">
          <div className="correspondence-heading"><span>密录往来</span><i /> <small>与{character.name}私下问策</small></div>
          {messages.length === 0 && !stream && <p className="correspondence-empty">此卷尚未落字。可先叙军情、察民生，或问用人之策。</p>}
          {messages.map((msg, idx) => (
            <article key={idx} className={`secret-record ${msg.role === "user" ? "player" : "character"}`}>
              <small>{msg.role === "user" ? "主公手札" : `${character.name}谨陈`}</small>
              <p>{msg.content}</p>
            </article>
          ))}
          {stream && (
            <article className="secret-record character live">
              <small>{character.name}</small>
              <p>{stream}<i className="cursor" /></p>
            </article>
          )}
          {error && <p className="error" role="alert">{error}</p>}
        </section>

        <footer className="correspondence-composer">
          <span className="composer-brush" aria-hidden="true" />
          <label className="composer-sheet">
            <span className="sr-only">密谈内容</span>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`与${character.name}密谈……`}
              onKeyDown={(e) => {
                if (!e.nativeEvent.isComposing && e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              disabled={busy}
            />
            <small className="composer-keyhint">回车落字 · ⇧ 回车换行</small>
          </label>
          <button className="secret-send" aria-label="录入密谈" onClick={send} disabled={busy}>
            {busy ? "…" : <><Send size={17} /><span>落字</span></>}
          </button>
          <ActionSealButton priority="secondary" className="secret-order" onClick={() => setSecretOrderOpen(true)}><LockKeyhole /><span>下密令</span></ActionSealButton>
        </footer>

        <GameDialog
          open={secretOrderOpen}
          onOpenChange={setSecretOrderOpen}
          title="封缄密令"
          description={`此令只交由${character.name}承办；请在下达前确认对象与内容。`}
          tone="decree"
        >
          <div className="secret-order-form">
            <p className="secret-order-recipient">承办人：<strong>{character.name}</strong></p>
            <input
              type="text"
              value={secretOrderTitle}
              onChange={(e) => setSecretOrderTitle(e.target.value)}
              placeholder="密令标题（最多20字）"
              maxLength={20}
              disabled={secretOrderBusy}
            />
            <textarea
              value={secretOrderContent}
              onChange={(e) => setSecretOrderContent(e.target.value)}
              placeholder="密令内容……"
              disabled={secretOrderBusy}
            />
            <StatusMark tone="warning">密令仅生成待审阅草案</StatusMark>
            <ActionSealButton priority="primary" onClick={issueSecretOrder} disabled={secretOrderBusy || !secretOrderTitle.trim() || !secretOrderContent.trim()}>{secretOrderBusy ? "下达中…" : "下达密令"}</ActionSealButton>
          </div>
        </GameDialog>
      </div>
    </div>
  );
}
