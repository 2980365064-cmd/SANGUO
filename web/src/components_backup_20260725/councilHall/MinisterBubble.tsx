/**
 * 单位大臣发言气泡 + 立绘。
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
    <article className={`minister-bubble ${role}`} onMouseUp={handleMouseUp}>
      <header>
        <strong>{speaker}</strong>
        <span className="role-tag">
          {role === "emperor" ? "帝" : role === "conclusion" ? "议" : "臣"}
        </span>
      </header>
      <p>{content}</p>
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
