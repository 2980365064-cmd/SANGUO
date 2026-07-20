from types import SimpleNamespace

import pytest

import ming_sim.adjudication as adjudication_module
import ming_sim.battle as battle_module
from ming_sim.battle import (
    build_battle_adjudication_pack,
    preview_battle,
    resolve_battle,
    resolve_battle_orders_for_turn,
    run_battle_ai_choice,
)
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.issues import _guard_structured_battle_deltas


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def test_preview_returns_range_and_all_major_hard_rule_factors(board):
    preview = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "xiangyang")

    assert "win_probability" not in preview
    low, high = preview["win_probability_range"]
    assert 0 <= low < high <= 100
    attacker = preview["army_breakdown"]["attackers"][0]
    assert {
        "manpower", "leadership", "training", "equipment", "morale", "fatigue",
        "supply_multiplier", "hazard_multiplier", "terrain_multiplier", "trait_modifiers",
    } <= set(attacker)
    assert preview["terrain"]["kind"] == "州块"
    assert preview["duration_turns"] == 1


def test_manpower_and_supply_penalty_move_preview_in_expected_direction(board):
    baseline = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "xiangyang")
    board.conn.execute(
        "UPDATE armies SET manpower=manpower*2 WHERE id='guanyu_fleet'"
    )
    stronger = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "xiangyang")
    assert stronger["win_probability_range"][0] > baseline["win_probability_range"][0]

    board.conn.execute(
        "UPDATE armies SET supply_combat_multiplier=0.65 WHERE id='guanyu_fleet'"
    )
    starved = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "xiangyang")
    assert starved["win_probability_range"][0] < stronger["win_probability_range"][0]


def test_resolution_is_sixty_percent_hard_rules_and_forty_percent_whitelisted_ai(board, monkeypatch):
    monkeypatch.setattr(battle_module.random, "randint", lambda _a, _b: 1)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "xiangyang",
        },
        {"tactic": "水战突击", "actor": "关羽", "narrative": "借汉水争先。"},
    )

    assert result["weights"] == {"hard_rules": 0.6, "ai_tactic": 0.4}
    assert result["ai_tactic"]["tactic"] == "水战突击"
    assert result["ai_tactic"]["delta"] > 0
    assert result["adjudication_pack"]["kind"] == "battle"
    assert "unlisted_death" in result["forbidden_outcomes"]
    assert "attacker_minor_win" in result["allowed_outcomes"]
    assert result["random_roll"] == 1
    assert result["winner"] == "attacker"
    assert result["audit"]["army_changes"]
    assert board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 1
    assert board.conn.execute(
        "SELECT 1 FROM character_attribute_logs WHERE character_name='关羽' AND context='battle_command'"
    ).fetchone()


def test_battle_adjudication_pack_limits_ai_to_structured_facts_and_options(board):
    pack = build_battle_adjudication_pack(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "xiangyang",
        },
    )

    assert pack["kind"] == "battle"
    assert pack["facts"]["hard_scores"]["attacker"] > 0
    assert pack["facts"]["army_breakdown"]["attackers"][0]["commander"] == "关羽"
    assert pack["probabilities"]["attacker_base"] == pack["audit"]["hard_probability"]
    assert "territory_change_without_siege" in pack["forbidden_outcomes"]
    assert any(item["tactic"] == "水战突击" and item["actor"] == "关羽" for item in pack["ai_options"])


def test_ai_choice_falls_back_when_narrative_violates_adjudication_pack(board):
    pack = build_battle_adjudication_pack(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "xiangyang",
        },
    )
    before = board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]

    choice = run_battle_ai_choice(
        board,
        pack,
        {"tactic": "水战突击", "actor": "关羽", "narrative": "曹军主将当场阵亡，襄阳立刻易主。"},
    )

    assert choice["tactic"] == "正面交锋"
    assert "ai_choice_rejected_reason" in choice
    assert board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == before


@pytest.mark.parametrize(
    "choice, error",
    [
        ({"tactic": "水战突击", "actor": "刘备", "reinforcements": ["天降神兵"]}, "援军"),
        ({"tactic": "火攻", "actor": "刘备"}, "火攻"),
        ({"tactic": "复活关羽", "actor": "刘备"}, "白名单"),
    ],
)
def test_ai_cannot_invent_reinforcements_revive_or_ignore_trait_requirements(board, choice, error):
    with pytest.raises(ValueError, match=error):
        resolve_battle(
            board,
            _state(1),
            {
                "attacker_ids": ["liubei_main"],
                "defender_ids": ["cao_vanguard"],
                "node_id": "xiangyang",
            },
            choice,
        )
    assert board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 0


def test_core_commander_losing_battle_is_not_killed_without_death_gate(board, monkeypatch):
    monkeypatch.setattr(battle_module.random, "randint", lambda _a, _b: 100)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["liubei_main"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "xiangyang",
        },
        {"tactic": "正面交锋", "actor": "刘备"},
    )

    liubei_fate = next(item for item in result["commander_fates"] if item["name"] == "刘备")
    assert liubei_fate["outcome"] in {"重伤", "被俘", "失势", "撤退"}
    assert liubei_fate["outcome"] != "死亡"
    assert board.conn.execute(
        "SELECT status FROM characters WHERE name='刘备'"
    ).fetchone()[0] != "dead"


def test_battle_order_is_validated_resolved_and_audited(board, monkeypatch):
    monkeypatch.setattr(battle_module.random, "randint", lambda _a, _b: 1)
    order_id = board.issue_army_order(
        _state(1),
        "guanyu_fleet",
        "突袭",
        {
            "target": "xiangyang",
            "defender_ids": ["cao_vanguard"],
            "ai_choice": {"tactic": "水战突击", "actor": "关羽"},
        },
    )

    results = resolve_battle_orders_for_turn(board, _state(1))

    assert results[0]["order_id"] == order_id
    assert results[0]["status"] == "resolved"
    assert board.list_army_orders(1)[0]["result"]["battle_id"] > 0


def test_battle_order_can_use_llm_judge_for_whitelisted_tactic(board, monkeypatch):
    monkeypatch.setattr(battle_module.random, "randint", lambda _a, _b: 1)

    def fake_judge(_llm_config, _agno_db, pack, *, tag):
        assert pack["kind"] == "battle"
        return {"tactic": "水战突击", "actor": "关羽", "narrative": "据汉水水势取胜。"}

    monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
    board.issue_army_order(
        _state(1),
        "guanyu_fleet",
        "突袭",
        {"target": "xiangyang", "defender_ids": ["cao_vanguard"]},
    )

    results = resolve_battle_orders_for_turn(board, _state(1), llm_config=object())

    assert results[0]["status"] == "resolved"
    row = board.conn.execute("SELECT ai_choice FROM battles ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert '"tactic": "水战突击"' in row["ai_choice"]


def test_llm_army_delta_cannot_double_apply_structured_battle_casualties(board, monkeypatch):
    monkeypatch.setattr(battle_module.random, "randint", lambda _a, _b: 1)
    resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "xiangyang",
        },
        {"tactic": "正面交锋", "actor": "关羽"},
    )
    raw = {
        "guanyu_fleet": {"manpower": -9999, "morale": -50, "reason": "战斗伤亡"},
        "sun_jianye": {"morale": 2, "reason": "整训"},
    }

    guarded = _guard_structured_battle_deltas(board, _state(1), raw)

    assert "guanyu_fleet" not in guarded
    assert guarded["sun_jianye"]["morale"] == 2
