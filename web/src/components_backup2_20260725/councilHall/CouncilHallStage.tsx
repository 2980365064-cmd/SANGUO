/**
 * 廷议主舞台：背景 bg-hall.webp，流式输出对话。
 */
import React from "react";
import { X } from "lucide-react";
import type { CourtChatMessage } from "../../types";
import { streamCourtChat } from "../../api";
import { MinisterBubble } from "./MinisterBubble";
import { StreamingTranscript } from "./StreamingTranscript";
import { ActionSealButton, PaperPanel, SectionHeading, StatusMark } from "../ui";

export function CouncilHallStage({
  ministers,
  onExit,
  onAddSuggestion,
}: {
  ministers: string[];
  onExit: () => void;
  onAddSuggestion: (text: string) => void;
}) {
  const [topic, setTopic] = React.useState("");
  const [messages, setMessages] = React.useState<CourtChatMessage[]>([]);
  const [liveText, setLiveText] = React.useState("");
  const [liveSpeaker, setLiveSpeaker] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

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
          <div><small className="council-kicker">府堂廷议</small><h2>本月军政议席</h2></div>
          <button className="close-button" aria-label="结束廷议" onClick={onExit}><X /></button>
        </header>

        <div className="council-stage-layout">
        <aside className="council-attendance"><small>入席大臣</small>{ministers.map((minister) => <span key={minister}>{minister}</span>)}</aside>
        <main>
        <PaperPanel className="council-topic" tone="focus">
          <SectionHeading index="议题" note={`${ministers.length} 人入席`}>请陈军政利害</SectionHeading>
          <label>议题</label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="提出本月必须裁断的军政问题..."
            disabled={busy}
          />
          <ActionSealButton
            priority="primary"
            onClick={startCouncil}
            disabled={busy || !topic.trim()}
          >{busy ? "廷议中..." : "请诸臣陈议"}</ActionSealButton>
        </PaperPanel>

        {/* 对话历史 */}
        <PaperPanel className="council-transcript" tone="archive">
          <SectionHeading index="录入" note={busy ? "书吏录入中" : "廷议记录"}>议席发言</SectionHeading>
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
        </PaperPanel>
        </main>
        </div>
      </div>
    </div>
  );
}
