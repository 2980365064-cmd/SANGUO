/**
 * 人物面板主容器：左栏筛选 + 右栏卡片网格。
 */
import React from "react";
import type { Character } from "../../types";
import { CharactersFilterBar, type FilterState } from "./CharactersFilterBar";
import { CharacterCard } from "./CharacterCard";
import { GameDialog } from "../GameDialog";
import { PaperPanel, SectionHeading } from "../ui";

export function CharactersPanel({
  characters,
  onClose,
  onViewDetails,
  onSecretChat,
}: {
  characters: Character[];
  onClose: () => void;
  onViewDetails: (character: Character) => void;
  onSecretChat: (character: Character) => void;
}) {
  const [filter, setFilter] = React.useState<FilterState>({
    scope: "liu_bei",
    province: null,
    role: null,
    sortBy: null,
  });

  const filtered = React.useMemo(() => {
    let result = characters;

    // 势力筛选
    if (filter.scope === "liu_bei") {
      result = result.filter((c) => c.power_id === "liu_bei");
    }
    // 其他势力筛选可以扩展

    // 州筛选
    if (filter.province) {
      result = result.filter((c) => c.location === filter.province);
    }

    // 文武筛选
    if (filter.role === "civil") {
      result = result.filter((c) => c.office_type === "政务" || c.office_type === "军师");
    } else if (filter.role === "military") {
      result = result.filter((c) => c.office_type === "军政" || c.office_type === "武将");
    }

    // 排序
    if (filter.sortBy) {
      result = [...result].sort((a, b) => {
        const aVal = a.abilities.values[filter.sortBy!] as number || 0;
        const bVal = b.abilities.values[filter.sortBy!] as number || 0;
        return bVal - aVal;
      });
    }

    return result;
  }, [characters, filter]);

  return (
    <GameDialog open onOpenChange={(open) => { if (!open) onClose(); }} title="人物档案" description="按势力、所在地与职能检索人物；密谈与方略仍在对应流程中处理。">
      <div className="characters-panel-inner">
        <div className="characters-layout">
          <CharactersFilterBar filter={filter} onChange={setFilter} />
          <PaperPanel className="characters-grid" tone="floating"><SectionHeading index="人物" note={`${filtered.length} 人`}>档案名录</SectionHeading>
            {filtered.length === 0 ? (
              <p className="empty-note">无符合条件的人物。</p>
            ) : (
              filtered.map((char) => (
                <CharacterCard
                  key={char.name}
                  character={char}
                  onViewDetails={onViewDetails}
                  onSecretChat={onSecretChat}
                />
              ))
            )}
          </PaperPanel>
        </div>
      </div>
    </GameDialog>
  );
}
