/**
 * 流式文本 + 可选中文本检测。
 */
import React from "react";

export function StreamingTranscript({
  speaker,
  text,
  onAddSuggestion,
}: {
  speaker: string;
  text: string;
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
    <article className="minister-bubble council-record-entry streaming" onMouseUp={handleMouseUp}>
      <header>
        <span className="speaker-monogram" aria-hidden="true">{(speaker || "臣").slice(0, 1)}</span>
        <small>廷臣陈议</small>
        <strong>{speaker || "臣将"}</strong>
        <span className="role-tag">臣</span>
        <span className="live-indicator">●</span>
      </header>
      <p className="record-content">{text}<i className="cursor" /></p>
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
