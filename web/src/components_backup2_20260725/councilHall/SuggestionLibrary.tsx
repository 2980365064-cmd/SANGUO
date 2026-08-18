/**
 * 建议库侧栏：显示已添加的建议，可一键转为将令。
 */
import React from "react";
import { X, ChevronRight } from "lucide-react";

export interface Suggestion {
  id: number;
  text: string;
  created_at: string;
  converted_to_order_id?: number;
}

export function SuggestionLibrary({
  suggestions,
  onRemove,
  onConvertToOrder,
  onClose,
}: {
  suggestions: Suggestion[];
  onRemove: (id: number) => void;
  onConvertToOrder: (id: number) => void;
  onClose: () => void;
}) {
  return (
    <div className="suggestion-library ink-frame-panel">
      <div className="suggestion-library-wash" />
      <div className="suggestion-library-inner">
        <header>
          <h3>建议库</h3>
          <button className="close-button" onClick={onClose}><X /></button>
        </header>
        {suggestions.length === 0 ? (
          <p className="empty-note">
            在廷议中选中文本（超过 4 字），点击"加入建议库"。
          </p>
        ) : (
          <ul>
            {suggestions.map((s) => (
              <li key={s.id}>
                <p>{s.text}</p>
                <footer>
                  <small>{new Date(s.created_at).toLocaleString("zh-CN")}</small>
                  <div className="actions">
                    {s.converted_to_order_id ? (
                      <span className="converted">已转将令</span>
                    ) : (
                      <button onClick={() => onConvertToOrder(s.id)}>
                        <ChevronRight size={12} /> 转将令
                      </button>
                    )}
                    <button className="danger" onClick={() => onRemove(s.id)}>
                      <X size={12} />
                    </button>
                  </div>
                </footer>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
