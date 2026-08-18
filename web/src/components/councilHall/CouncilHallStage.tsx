/**
 * 廷议主舞台：背景 bg-hall.webp，流式输出对话。
 */
import React from "react";
import { X } from "lucide-react";
import type { CourtChatMessage } from "../../types";
import { streamCourtChat } from "../../api";
import { MinisterBubble } from "./MinisterBubble";
import { StreamingTranscript } from "./StreamingTranscript";
import { ActionSealButton, StatusMark } from "../ui";

type CouncilSuggestion = {
  id: number;
  text: string;
  created_at: string;
  status: string;
  source: string;
};

export function CouncilHallStage({
  ministers,
  initialTopic: _initialTopic = "",
  onExit,
  onAddSuggestion,
  suggestions = [],
  onRemoveSuggestion = () => {},
  onDraftSuggestion = () => {},
}: {
  ministers: string[];
  initialTopic?: string;
  onExit: () => void;
  onAddSuggestion: (text: string) => void;
  suggestions?: CouncilSuggestion[];
  onRemoveSuggestion?: (id: number) => void;
  onDraftSuggestion?: (text: string) => void;
}) {
  const [topic, setTopic] = React.useState("");
  const [messages, setMessages] = React.useState<CourtChatMessage[]>([]);
  const [liveText, setLiveText] = React.useState("");
  const [liveSpeaker, setLiveSpeaker] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const transcriptRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: busy ? "auto" : "smooth" });
  }, [messages, liveText, busy]);

  const startCouncil = async () => {
    if (!topic.trim() || busy) return;
    setBusy(true);
    setError("");
    setLiveText("");
    setLiveSpeaker("");
    setMessages([{ role: "emperor", speaker: "刘备", content: topic.trim() }]);

    try {
      await streamCourtChat(topic.trim(), ministers, (event) => {
        if (event.type === "speaker") {
          setLiveSpeaker(event.speaker || "");
          setLiveText("");
        }
        if (event.type === "delta") {
          setLiveText((prev) => prev + (event.content || ""));
        }
        if (event.type === "reply" && event.message) {
          setMessages((prev) => [...prev, event.message!]);
          setLiveText("");
        }
        if (event.type === "conclusion" && event.message) {
          setMessages((prev) => [...prev, event.message!]);
          setLiveText("");
        }
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="council-hall-stage">
      <div className="council-hall-bg" />
      <div className="council-hall-inner">
        <header>
          <button className="close-button" aria-label="结束廷议" onClick={onExit}><X /></button>
        </header>

        <div className="council-stage-layout">
        <aside className="council-attendance"><small>在席名簿</small><strong>{ministers.length} 人入席</strong><ol>{ministers.map((minister, index) => <li key={minister}><i>{String(index + 1).padStart(2, "0")}</i><span>{minister}</span><em>{liveSpeaker === minister ? "陈议中" : messages.some((message) => message.speaker === minister) ? "已陈" : "候问"}</em></li>)}</ol></aside>
        <main>
        <section className="council-transcript" aria-label="廷议记录">
          <div className="council-dialogue-title">军政议席</div>
          <div className="council-record-scroll" ref={transcriptRef}>
          {!messages.length && !liveText && <div className="council-record-empty"><i>问</i><strong>尚未开议</strong><p>请在案前写下今日所问，入席诸臣将按次序陈述利害。</p></div>}
          {messages.map((msg, idx) => (
            <MinisterBubble
              key={idx}
              role={msg.role}
              speaker={msg.speaker || (msg.role === "emperor" ? "刘备" : "臣将")}
              content={msg.content}
              onAddSuggestion={onAddSuggestion}
            />
          ))}
          {liveText && (
            <StreamingTranscript
              speaker={liveSpeaker}
              text={liveText}
              onAddSuggestion={onAddSuggestion}
            />
          )}
          {error && <p className="council-error" role="alert"><StatusMark tone="danger">廷议中断</StatusMark>{error}</p>}
          </div>
        </section>
        <section className="council-composer" aria-label="主公发问">
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={busy}
          />
          <ActionSealButton priority="primary" onClick={startCouncil} disabled={busy || !topic.trim()}>{busy ? "诸臣陈议中" : "发问廷臣"}</ActionSealButton>
        </section>
        </main>
        <aside className="council-advice-ledger" aria-label="廷议建议库">
          <header><small>摘录入卷</small><h3>廷议建议库</h3><span>{suggestions.length} 则</span></header>
          {suggestions.length === 0 ? (
            <div className="council-advice-empty"><i>录</i><strong>尚无摘录</strong><p>在左侧陈议中长按拖选文字，松开后即可加入此卷。</p></div>
          ) : (
            <ol>
              {suggestions.map((suggestion) => (
                <li key={suggestion.id}>
                  <p>{suggestion.text}</p>
                  <footer><small>{suggestion.source}</small><div><button onClick={() => onDraftSuggestion(suggestion.text)}>拟入方略</button><button className="council-advice-remove" aria-label="移除此建议" onClick={() => onRemoveSuggestion(suggestion.id)}>×</button></div></footer>
                </li>
              ))}
            </ol>
          )}
        </aside>
        </div>
      </div>
    </div>
  );
}
