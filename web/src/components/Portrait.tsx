import React from "react";
import type { Character } from "../types";

export function Portrait({ character }: { character: Character }) {
  const [failed, setFailed] = React.useState(false);
  const file = encodeURIComponent(character.portrait_id || character.name);
  return (
    <div className={`portrait ${failed ? "portrait-fallback" : ""}`}>
      {!failed && <img src={`/portraits/sanguo/${file}.webp`} alt={`${character.name}立绘`} onError={() => setFailed(true)} />}
      {failed && <><span>{character.name.slice(0, 1)}</span><small>{character.name}</small></>}
      <i>{character.core_tier}</i>
    </div>
  );
}
