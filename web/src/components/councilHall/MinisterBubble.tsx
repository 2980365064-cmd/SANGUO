/**
 * 廷议簿中的单条陈议：保留群聊节奏，不使用现代聊天气泡。
 */
import React from "react";

export function MinisterBubble({
  role,
  speaker,
  content,
  onAddSuggestion,
}: {
  role: string;
  speaker: string;
  content: string;
  onAddSuggestion: (text: string) => void;
}) {
  const [selectedText, setSelectedText] = React.useState("");

  const handleMouseUp = () => {
    const selection = window.getSelection();
    if (selection && selection.toString().length > 4) {
      setSelectedText(selection.toString());
    } else {
      setSelectedText("");
    }
  };

  const handleAddSuggestion = () => {
    if (selectedText) {
      onAddSuggestion(selectedText);
      setSelectedText("");
      window.getSelection()?.removeAllRanges();
    }
  };

  return (
    <article className={`minister-bubble council-record-entry ${role}`} onMouseUp={handleMouseUp}>
      <header>
        <span className="speaker-monogram" aria-hidden="true">{speaker.slice(0, 1)}</span>
        <small>{role === "emperor" ? "主公所问" : role === "conclusion" ? "书吏结议" : "廷臣陈议"}</small>
        <strong>{speaker}</strong>
        <span className="role-tag">
          {role === "emperor" ? "帝" : role === "conclusion" ? "议" : "臣"}
        </span>
      </header>
      <p className="record-content">{content}</p>
      {selectedText && (
        <div className="suggestion-popup">
          <button onClick={handleAddSuggestion}>
            加入建议库
          </button>
        </div>
      )}
    </article>
  );
}
