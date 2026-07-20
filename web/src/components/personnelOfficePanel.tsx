import React from "react";
import { Loader2, UserRoundCog } from "lucide-react";

import { appointGovernmentOffice, getGovernmentOffices } from "../api";
import type { Character, GameState, GovernmentOfficeEffect } from "../types";

const ABILITY_LABELS: Record<string, string> = {
  martial: "武力",
  leadership: "统率",
  intelligence: "智略",
  politics: "政治",
  diplomacy: "外交",
  charisma: "魅力",
};

function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }

function candidateLabel(character: Character) {
  return `${character.name} · ${character.office || character.political_group}`;
}

export function PersonnelOfficePanel({ state, onState }: {
  state: GameState;
  onState: (state: GameState) => void;
}) {
  const [offices, setOffices] = React.useState<GovernmentOfficeEffect[]>([]);
  const [choices, setChoices] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const candidates = state.characters.filter((character) => character.power_id === "liu_bei" && character.status === "active");

  const refresh = React.useCallback(async () => {
    const payload = await getGovernmentOffices();
    setOffices(payload.offices || []);
  }, []);

  React.useEffect(() => { void refresh().catch((caught) => setError(errorText(caught))); }, [refresh, state.turn.turn]);

  const appoint = async (office: GovernmentOfficeEffect) => {
    const fallback = office.character_name || candidates[0]?.name || "";
    const character = choices[office.office_key] || fallback;
    if (!character) return;
    setBusy(office.office_key); setError("");
    try {
      const payload = await appointGovernmentOffice(office.office_key, character, office.target_id || "");
      setOffices(payload.offices);
      onState(payload.state);
    } catch (caught) { setError(errorText(caught)); } finally { setBusy(""); }
  };

  return <div className="office-panel">
    <header className="office-panel-heading">
      <UserRoundCog />
      <div><h3>军府任事</h3><p>职位影响国策、外交、军令执行与地方治理；换任后即写入本回合人事日志。</p></div>
    </header>
    <div className="office-grid">
      {offices.map((office) => {
        const selected = choices[office.office_key] || office.character_name || candidates[0]?.name || "";
        return <article key={office.office_key} className={office.vacant ? "vacant" : ""}>
          <div className="office-title">
            <span>{office.vacant ? "空缺" : "在任"}</span>
            <h3>{office.name}</h3>
            <strong>{office.efficiency}</strong>
          </div>
          <p>{office.effect}</p>
          <dl>
            <div><dt>当前</dt><dd>{office.character_name || "未任命"}</dd></div>
            <div><dt>主能力</dt><dd>{ABILITY_LABELS[office.ability_field || ""] || office.ability_field || "未定"} {office.ability_value ?? "-"}</dd></div>
            <div><dt>空缺惩罚</dt><dd>{office.vacancy_penalty}</dd></div>
          </dl>
          <div className="office-appoint-row">
            <select value={selected} onChange={(event) => setChoices((current) => ({ ...current, [office.office_key]: event.target.value }))}>
              {candidates.map((character) => <option key={character.name} value={character.name}>{candidateLabel(character)}</option>)}
            </select>
            <button type="button" onClick={() => void appoint(office)} disabled={!!busy || !selected}>
              {busy === office.office_key ? <Loader2 className="spin" /> : null}任命
            </button>
          </div>
        </article>;
      })}
    </div>
    {error && <p className="inline-error">{error}</p>}
  </div>;
}
