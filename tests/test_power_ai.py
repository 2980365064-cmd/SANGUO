from types import SimpleNamespace

import pytest

import ming_sim.adjudication as adjudication_module
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.power_ai import (
    available_power_actions,
    resolve_power_ai_turn,
    validate_power_action,
)
from ming_sim.session import GameSession


@pytest.fixture
def board():
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=8, metrics={"军心": 60, "粮秣": 60})


def test_actions_are_generated_from_real_armies_routes_relations_and_intelligence(board):
    actions = available_power_actions(board, _state(), "cao_cao")
    assert actions
    assert all(action["power_id"] == "cao_cao" for action in actions)
    assert all(action["score"] >= 0 and action["reasons"] for action in actions)
    assert all("intelligence_confidence" in action["factors"] for action in actions)
    assert any(action["action_type"] in {"attack", "siege"} for action in actions)
    for action in actions:
        assert validate_power_action(board, _state(), action)["valid"] is True


def test_low_supply_makes_resupply_or_defensive_action_more_attractive(board):
    board.conn.execute(
        "UPDATE armies SET supply=5, morale=35 WHERE owner_power='cao_cao' AND active=1"
    )
    actions = available_power_actions(board, _state(), "cao_cao")
    best = max(actions, key=lambda item: item["score"])
    assert best["action_type"] in {"resupply", "fortify", "seek_peace"}
    assert any("补给" in reason or "军心" in reason for reason in best["reasons"])


def test_adjacent_powers_without_opening_relation_can_act_from_geography_and_agenda(board):
    assert _relation_missing(board, "liu_zhang", "zhang_lu")
    actions = available_power_actions(board, _state(), "liu_zhang")
    declaration = next(
        item for item in actions
        if item["action_type"] == "declare_war" and item["target_power"] == "zhang_lu"
    )
    assert "战略意图" in "".join(declaration["reasons"])
    assert validate_power_action(board, _state(), declaration)["valid"] is True


def _relation_missing(board, first, second):
    a, b = board._relation_pair(first, second)
    return board.conn.execute(
        "SELECT 1 FROM diplomatic_relations WHERE power_a=? AND power_b=?", (a, b)
    ).fetchone() is None


def test_validator_rejects_fabricated_routes_armies_and_direct_world_mutation(board):
    with pytest.raises(ValueError, match="不属于"):
        validate_power_action(board, _state(), {
            "power_id": "cao_cao", "action_type": "move", "army_id": "liubei_main", "target_node": "city:xiangyang"
        })
    with pytest.raises(ValueError, match="非法字段"):
        validate_power_action(board, _state(), {
            "power_id": "cao_cao", "action_type": "annex", "region_control": {"jiangxia": "cao_cao"},
            "kill_character": "刘备"
        })


def test_monthly_ai_queues_only_structured_orders_and_is_idempotent(board):
    state = _state()
    first = resolve_power_ai_turn(board, state)
    second = resolve_power_ai_turn(board, state)
    assert first
    assert second == []
    assert all(item["power_id"] != "liu_bei" for item in first)
    assert board.conn.execute("SELECT COUNT(*) FROM power_ai_actions WHERE turn=1").fetchone()[0] == len(first)
    assert not board.conn.execute(
        "SELECT 1 FROM power_ai_actions WHERE action_json LIKE '%region_control%' OR action_json LIKE '%kill_character%'"
    ).fetchone()
    # 军事行动只能转成结构化军令，不直接改领土或人物状态。
    assert board.conn.execute(
        "SELECT COUNT(*) FROM army_orders WHERE turn=1 AND army_id NOT LIKE 'liu%'").fetchone()[0] >= 1
    assert board.conn.execute("SELECT status FROM characters WHERE name='刘备'").fetchone()[0] == "active"


def test_monthly_ai_can_use_llm_judge_to_choose_legal_candidate(board, monkeypatch):
    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        assert kind == "power_action"
        actions = available_power_actions(db, state, subject_id)
        selected = actions[-1] if actions else {"action_type": "fortify", "power_id": subject_id, "reasons": []}
        return {
            "outcome": selected["action_type"],
            "action": selected,
            "reason": "模型择机选择规则层候选。",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)

    results = resolve_power_ai_turn(board, _state(), llm_config=object())

    assert results
    assert all(item["status"] in {"executed", "rejected"} for item in results)
    assert any(item.get("ai_proposal", {}).get("reason") == "模型择机选择规则层候选。" for item in results)
    assert not board.conn.execute(
        "SELECT 1 FROM power_ai_actions WHERE action_json LIKE '%region_control%' OR action_json LIKE '%kill_character%'"
    ).fetchone()


def test_session_strategic_settlement_runs_external_ai_before_hard_rule_resolution(board):
    state = _state()
    state.metrics.update({"军资": 60, "民望": 50, "名分": 65, "士族支持": 40})
    session = GameSession.__new__(GameSession)
    session.db = board
    session.state = state

    session._resolve_strategic_turn(state)

    assert board.conn.execute("SELECT COUNT(*) FROM power_ai_actions WHERE turn=1").fetchone()[0] > 0
    assert not board.conn.execute(
        "SELECT 1 FROM army_orders WHERE turn=1 AND status='issued' AND order_type IN ('移动','驻守','补给','围城','突袭')"
    ).fetchone()
