"""人物属性与特性的统一规则修正入口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class AttributeModifier:
    source_character: str
    attribute: str
    context: str
    raw_value: int
    delta: float
    reason: str


ATTRIBUTE_CONTEXTS: Dict[str, Dict[str, float]] = {
    "personal_combat": {"martial": 0.25},
    "battle_command": {"leadership": 0.20, "intelligence": 0.05},
    "scheme": {"intelligence": 0.22, "courage": 0.04},
    "governance": {"politics": 0.20, "charisma": 0.05},
    "negotiation": {"diplomacy": 0.20, "charisma": 0.06},
    "pacification": {"charisma": 0.20, "politics": 0.05},
    "defection_pressure": {
        "loyalty": -0.20,
        "integrity": -0.08,
        "ambition": 0.18,
        "closeness_to_liu_bei": -0.10,
    },
    "breach_pressure": {"integrity": -0.20, "loyalty": -0.08, "ambition": 0.08},
    "power_struggle": {"ambition": 0.20, "loyalty": -0.08},
    "raid": {"courage": 0.20, "martial": 0.05, "intelligence": 0.04},
    "protect_liu_bei": {"closeness_to_liu_bei": 0.20, "loyalty": 0.10, "martial": 0.05},
}


def evaluate_character_modifier(character, context: str, *, db=None, turn: int = 0) -> List[AttributeModifier]:
    weights = ATTRIBUTE_CONTEXTS.get(context)
    if weights is None:
        raise ValueError(f"未知人物属性场景：{context}")
    modifiers = [
        AttributeModifier(
            source_character=str(character.name),
            attribute=attribute,
            context=context,
            raw_value=max(0, min(100, int(getattr(character, attribute)))),
            delta=round((max(0, min(100, int(getattr(character, attribute)))) - 50) * weight, 2),
            reason=f"{attribute}={max(0, min(100, int(getattr(character, attribute))))}",
        )
        for attribute, weight in weights.items()
    ]
    if db is not None and modifiers:
        db.conn.executemany(
            """
            INSERT INTO character_attribute_logs
            (turn, character_name, attribute, context, raw_value, delta, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (turn, item.source_character, item.attribute, item.context, item.raw_value, item.delta, item.reason)
                for item in modifiers
            ],
        )
        db.conn.commit()
    return modifiers


def apply_character_modifiers(base: float, modifiers: Iterable[AttributeModifier]) -> float:
    value = float(base) + sum(float(item.delta) for item in modifiers)
    return max(0.0, min(100.0, value))


def evaluate_trait_modifiers(character, context: str, traits: Dict[str, object]) -> List[AttributeModifier]:
    by_category: Dict[str, AttributeModifier] = {}
    for trait_name in character.personal_skills:
        definition = traits.get(trait_name)
        if not isinstance(definition, dict):
            continue
        effects = definition.get("effects")
        if not isinstance(effects, list):
            continue
        for effect in effects:
            if not isinstance(effect, dict) or effect.get("context") != context:
                continue
            category = str(effect.get("category") or effect.get("attribute") or trait_name)
            modifier = AttributeModifier(
                source_character=str(character.name),
                attribute=f"trait:{effect.get('attribute')}",
                context=context,
                raw_value=0,
                delta=float(effect.get("delta") or 0),
                reason=str(trait_name),
            )
            current = by_category.get(category)
            if current is None or abs(modifier.delta) > abs(current.delta):
                by_category[category] = modifier
    return list(by_category.values())
