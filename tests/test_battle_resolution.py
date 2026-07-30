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
    preview = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")

    assert "win_probability" not in preview
    low, high = preview["win_probability_range"]
    assert 0 <= low < high <= 100
    attacker = preview["army_breakdown"]["attackers"][0]
    assert {
        "manpower", "leadership", "training", "equipment", "morale", "fatigue",
        "supply_multiplier", "hazard_multiplier", "terrain_multiplier", "trait_modifiers",
    } <= set(attacker)
    assert preview["terrain"]["kind"] == "普通路"
    assert preview["duration_turns"] == 1


def test_manpower_and_supply_penalty_move_preview_in_expected_direction(board):
    baseline = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    board.conn.execute(
        "UPDATE armies SET manpower=manpower*2 WHERE id='guanyu_fleet'"
    )
    stronger = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    assert stronger["win_probability_range"][0] > baseline["win_probability_range"][0]

    board.conn.execute(
        "UPDATE armies SET supply_combat_multiplier=0.65 WHERE id='guanyu_fleet'"
    )
    starved = preview_battle(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    assert starved["win_probability_range"][0] < stronger["win_probability_range"][0]


def test_resolution_is_sixty_percent_hard_rules_and_forty_percent_ai_tactic(board, monkeypatch):
    # 固定存档种子以确保 draw_int 结果可复现
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "battle_test_seed" + "0" * 45)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {"tactic": "正面交锋", "actor": "关羽", "delta": 5, "narrative": "借汉水争先。"},
    )

    assert result["weights"] == {"hard_rules": 0.6, "ai_tactic": 0.4}
    assert result["ai_tactic"]["tactic"] == "正面交锋"
    assert result["ai_tactic"]["delta"] == 5
    assert result["adjudication_pack"]["kind"] == "battle"
    assert "unlisted_death" in result["forbidden_outcomes"]
    assert "attacker_minor_win" in result["allowed_outcomes"]
    # 掷骰通过 draw_int 确定性抽取，同种子同结果
    assert 1 <= result["random_roll"] <= 100
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
            "node_id": "city:xiangyang",
        },
    )

    assert pack["kind"] == "battle"
    assert pack["facts"]["hard_scores"]["attacker"] > 0
    assert pack["facts"]["army_breakdown"]["attackers"][0]["commander"] == "关羽"
    assert pack["probabilities"]["attacker_base"] == pack["audit"]["hard_probability"]
    assert "territory_change_without_siege" in pack["forbidden_outcomes"]
    assert any(item["tactic"] == "正面交锋" and item["actor"] == "关羽" for item in pack["ai_options"])


def test_ai_choice_falls_back_when_narrative_violates_adjudication_pack(board):
    pack = build_battle_adjudication_pack(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
    )
    before = board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]

    choice = run_battle_ai_choice(
        board,
        pack,
        {"tactic": "正面交锋", "actor": "关羽", "narrative": "曹军主将当场阵亡，襄阳立刻易主。"},
    )

    assert choice["tactic"] == "正面交锋"
    assert "ai_choice_rejected_reason" in choice
    assert board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == before


@pytest.mark.parametrize(
    "choice, error",
    [
        # 禁止字段：reinforcements
        ({"tactic": "正面交锋", "actor": "刘备", "reinforcements": ["天降神兵"]}, "非法字段"),
        # 执行者必须是参战统帅：关羽不是 liubei_main 的统帅
        ({"tactic": "火攻", "actor": "关羽"}, "攻方统帅"),
        # 禁止文本：narrative 中包含"阵亡"
        ({"tactic": "复活关羽", "actor": "刘备", "narrative": "关羽阵亡后复活"}, "人物死亡"),
    ],
)
def test_ai_cannot_invent_reinforcements_or_use_invalid_actor(board, choice, error):
    with pytest.raises(ValueError, match=error):
        resolve_battle(
            board,
            _state(1),
            {
                "attacker_ids": ["liubei_main"],
                "defender_ids": ["cao_vanguard"],
                "node_id": "city:xiangyang",
            },
            choice,
        )
    assert board.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 0


def test_core_commander_losing_battle_is_not_killed_without_death_gate(board, monkeypatch):
    # 固定种子确保可复现；不依赖具体掷骰值
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "commander_fate_test" + "0" * 44)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["liubei_main"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {"tactic": "正面交锋", "actor": "刘备"},
    )

    liubei_fate = next(item for item in result["commander_fates"] if item["name"] == "刘备")
    # 无论攻守，刘备核心指挥官不会死亡（无 death_authority 授权）
    assert liubei_fate["outcome"] != "死亡"
    assert board.conn.execute(
        "SELECT status FROM characters WHERE name='刘备'"
    ).fetchone()[0] != "dead"


def test_battle_order_is_validated_resolved_and_audited(board, monkeypatch):
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "battle_order_test_seed" + "0" * 41)
    order_id = board.issue_army_order(
        _state(1),
        "guanyu_fleet",
        "突袭",
        {
            "target": "city:xiangyang",
            "defender_ids": ["cao_vanguard"],
            "ai_choice": {"tactic": "正面交锋", "actor": "关羽"},
        },
    )

    results = resolve_battle_orders_for_turn(board, _state(1))

    assert results[0]["order_id"] == order_id
    assert results[0]["status"] == "resolved"
    assert board.list_army_orders(1)[0]["result"]["battle_id"] > 0


def test_battle_order_can_use_llm_judge_for_whitelisted_tactic(board, monkeypatch):
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "llm_judge_test_seed" + "0" * 42)

    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        assert kind == "battle"
        return {"tactic": "正面交锋", "actor": "关羽", "narrative": "据汉水水势取胜。"}

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)
    board.issue_army_order(
        _state(1),
        "guanyu_fleet",
        "突袭",
        {"target": "city:xiangyang", "defender_ids": ["cao_vanguard"]},
    )

    results = resolve_battle_orders_for_turn(board, _state(1), llm_config=object())

    assert results[0]["status"] == "resolved"
    row = board.conn.execute("SELECT ai_choice FROM battles ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert '"tactic": "正面交锋"' in row["ai_choice"]


def test_llm_army_delta_cannot_double_apply_structured_battle_casualties(board, monkeypatch):
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "delta_test_seed" + "0" * 45)
    resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
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
