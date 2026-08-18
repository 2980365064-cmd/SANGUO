/**
 * 人物卡片：立绘 + 姓名 + 职务 + 操作按钮。
 */
import React from "react";
import { MessageCircle, User } from "lucide-react";
import type { Character } from "../../types";
import { Portrait } from "../Portrait";

export function CharacterCard({
  character,
  onViewDetails,
  onSecretChat,
}: {
  character: Character;
  onViewDetails: (character: Character) => void;
  onSecretChat: (character: Character) => void;
}) {
  return (
    <article className="character-card ink-frame-card">
      <Portrait character={character} />
      <div className="character-card-info">
        <strong>{character.name}</strong>
        <small>{character.office || character.political_group}</small>
      </div>
      <div className="character-card-actions">
        <button onClick={() => onViewDetails(character)} title="查看详情">
          <User size={14} />
        </button>
        {character.power_id === "liu_bei" && character.status === "active" && (
          <button onClick={() => onSecretChat(character)} title="密谈">
            <MessageCircle size={14} />
          </button>
        )}
      </div>
    </article>
  );
}
