/**
 * 密谈舞台：背景 bg-secret-chamber.webp，可下密令。
 */
import React from "react";
import { LockKeyhole, Send, X } from "lucide-react";
import type { Character, DialogueMessage } from "../../types";
import { getDialogue, streamDialogue, enterSecretChat, exitSecretChat, createSecretOrder } from "../../api";
import { Portrait } from "../Portrait";
import { GameDialog } from "../GameDialog";
import { ActionSealButton, SectionHeading, StatusMark } from "../ui";

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
      <div className="secret-chat-bg" />
      <div className="secret-chat-inner">
        <header>
          <Portrait character={character} />
          <div>
            <span>密谈</span>
            <h2>{character.name}</h2>
            <p>{character.office || character.political_group}</p>
          </div>
          <button className="close-button" aria-label="结束密谈" onClick={onExit}><X /></button>
        </header>

        <section className="secret-chat-history">
          <SectionHeading index="密录" note="仅限案内阅览">与{character.name}的私谈</SectionHeading>
          {messages.map((msg, idx) => (
            <article key={idx} className={`secret-record ${msg.role === "user" ? "player" : "character"}`}>
              <small>{msg.role === "user" ? "刘备" : character.name}</small>
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

        <footer>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`与${character.name}密谈……`}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            disabled={busy}
          />
          <button className="secret-send" aria-label="录入密谈" onClick={send} disabled={busy}>
            {busy ? "…" : <Send size={18} />}
          </button>
          <ActionSealButton priority="secondary" className="secret-order" onClick={() => setSecretOrderOpen(true)}><LockKeyhole /> 下密令</ActionSealButton>
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
