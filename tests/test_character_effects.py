from dataclasses import replace

import pytest

from ming_sim.character_effects import (
    ATTRIBUTE_CONTEXTS,
    apply_character_modifiers,
    evaluate_character_modifier,
    evaluate_trait_modifiers,
)
from ming_sim.context import character_context_with_db
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import Character


def _character(**overrides) -> Character:
    base = Character(
        name="测试人物",
        office="偏将",
        office_type="军政",
        faction="军中将领",
        aliases=["测试人物"],
        personal_skills=["突击"],
        loyalty=50,
        ability=50,
        integrity=50,
        courage=50,
        style="半文半白",
        power_id="liu_bei",
        martial=50,
        leadership=50,
        intelligence=50,
        politics=50,
        diplomacy=50,
        charisma=50,
        ambition=50,
        closeness_to_liu_bei=50,
    )
    return replace(base, **overrides)


@pytest.mark.parametrize(
    ("attribute", "context", "high_is_better"),
    [
        ("martial", "personal_combat", True),
        ("leadership", "battle_command", True),
        ("intelligence", "scheme", True),
        ("politics", "governance", True),
        ("diplomacy", "negotiation", True),
        ("charisma", "pacification", True),
        ("loyalty", "defection_pressure", False),
        ("integrity", "breach_pressure", False),
        ("ambition", "power_struggle", True),
        ("courage", "raid", True),
        ("closeness_to_liu_bei", "protect_liu_bei", True),
    ],
)
def test_all_eleven_attributes_have_live_rule_effects(attribute, context, high_is_better):
    assert context in ATTRIBUTE_CONTEXTS
    low = evaluate_character_modifier(_character(**{attribute: 20}), context)
    high = evaluate_character_modifier(_character(**{attribute: 90}), context)
    low_delta = next(item.delta for item in low if item.attribute == attribute)
    high_delta = next(item.delta for item in high if item.attribute == attribute)
    if high_is_better:
        assert high_delta > low_delta
    else:
        assert high_delta < low_delta


def test_apply_character_modifiers_clamps_probability_range():
    modifiers = evaluate_character_modifier(_character(martial=100), "personal_combat")
    assert apply_character_modifiers(98, modifiers) == 100
    assert apply_character_modifiers(-10, []) == 0


def test_mifang_loyalty_and_ambition_change_defection_pressure():
    content = GameContent.load()
    mifang = content.characters["糜芳"]
    baseline = apply_character_modifiers(40, evaluate_character_modifier(mifang, "defection_pressure"))
    unstable = replace(mifang, loyalty=35, ambition=82)
    unstable_result = apply_character_modifiers(
        40, evaluate_character_modifier(unstable, "defection_pressure")
    )
    assert unstable_result > baseline


def test_attribute_effects_are_written_to_audit_log(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        modifiers = evaluate_character_modifier(
            _character(name="糜芳", loyalty=65, ambition=58),
            "defection_pressure",
            db=db,
            turn=9,
        )
        rows = db.conn.execute(
            "SELECT character_name, attribute, context, raw_value, delta, turn FROM character_attribute_logs ORDER BY id"
        ).fetchall()
        assert len(rows) == len(modifiers)
        assert {row["attribute"] for row in rows} >= {"loyalty", "ambition"}
        assert all(row["character_name"] == "糜芳" and row["turn"] == 9 for row in rows)
    finally:
        db.close()


def test_twenty_approved_traits_are_data_driven_and_same_category_uses_highest():
    content = GameContent.load()
    assert len(content.character_traits) == 20
    character = _character(personal_skills=["水战", "水战熟练", "突击"])
    modifiers = evaluate_trait_modifiers(character, "river_battle", content.character_traits)
    assert [item.reason for item in modifiers if item.attribute == "trait:water_combat"] == ["水战"]
    assert any(item.reason == "突击" for item in evaluate_trait_modifiers(character, "field_battle", content.character_traits))


def test_all_character_mechanical_traits_are_defined():
    content = GameContent.load()
    defined = set(content.character_traits)
    for character in content.characters.values():
        assert set(character.personal_skills) <= defined, character.name


def test_character_ai_context_contains_recent_effects_relationship_and_action_range(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        character = _character(name="糜芳", loyalty=65, ambition=58, closeness_to_liu_bei=60)
        evaluate_character_modifier(character, "defection_pressure", db=db, turn=4)
        context = character_context_with_db(character, db)
        assert "最近属性影响" in context
        assert "loyalty" in context and "ambition" in context
        assert "与刘备关系" in context
        assert "可行动范围" in context
    finally:
        db.close()
