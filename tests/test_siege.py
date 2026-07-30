import json
from types import SimpleNamespace

import pytest

import ming_sim.adjudication as adjudication_module
import ming_sim.siege as siege_module
from ming_sim.adjudication import attach_adjudication_runtime
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.siege import (
    advance_siege,
    register_siege_relief,
    resolve_siege_relief,
    resolve_siege_turn,
    start_siege,
    withdraw_siege,
)
from ming_sim.sanguo_rules import ArmyOrderError


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def _siege_row(db, siege_id):
    return db.conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,)).fetchone()


def test_start_siege_accepts_adjacent_enemy_city_without_changing_control(board):
    # zhanglu_hanzhong at city:hanzhong, siege city:changan (cao_cao, adjacent)
    siege_id = start_siege(board, _state(1), "zhanglu_hanzhong", "city:changan")

    row = _siege_row(board, siege_id)
    assert row["status"] == "active"
    assert row["progress"] == 0
    assert row["defender_power"] == "cao_cao"
    assert board.conn.execute(
        "SELECT controlled_by FROM administrative_cities WHERE id='city:changan'"
    ).fetchone()[0] == "cao_cao"


def test_invalid_siege_order_is_rejected_before_it_enters_order_table(board):
    with pytest.raises(ArmyOrderError, match="无直连路线|不存在|必须是城池节点"):
        board.issue_army_order(
            _state(1), "zhanglu_hanzhong", "围城", {"target": "city:jianye"}
        )
    assert board.list_army_orders(1) == []


def test_equal_siege_takes_three_turns_and_only_then_changes_control(board, monkeypatch):
    monkeypatch.setattr(
        siege_module,
        "_siege_scores",
        lambda *_args, **_kwargs: (100, 100, {"attacker": [], "defender": []}),
    )
    siege_id = start_siege(board, _state(1), "zhanglu_hanzhong", "city:changan")

    first = advance_siege(board, _state(1), siege_id)
    second = advance_siege(board, _state(2), siege_id)
    assert first["progress"] == 34
    assert second["progress"] == 68
    assert board.conn.execute(
        "SELECT controlled_by FROM administrative_cities WHERE id='city:changan'"
    ).fetchone()[0] == "cao_cao"

    third = advance_siege(board, _state(3), siege_id)
    assert third["progress"] == 100
    assert third["status"] == "conquered"
    assert board.conn.execute(
        "SELECT controlled_by FROM administrative_cities WHERE id='city:changan'"
    ).fetchone()[0] == "zhang_lu"


def test_fortification_grain_traits_and_relief_all_change_siege_score(board):
    siege_id = start_siege(board, _state(1), "zhanglu_hanzhong", "city:changan")
    base_attacker, base_defender, _ = siege_module._siege_scores(board, siege_id)

    board.conn.execute(
        "UPDATE characters SET personal_skills='[\"攻城\"]' WHERE name='张鲁'"
    )
    trait_attacker, _, _ = siege_module._siege_scores(board, siege_id)
    assert trait_attacker > base_attacker

    board.conn.execute(
        "UPDATE administrative_cities SET fortification=100, grain_stock=999 WHERE id='city:changan'"
    )
    _, fortified_defender, _ = siege_module._siege_scores(board, siege_id)
    assert fortified_defender > base_defender

    # 救援军必须在目标城或相邻节点
    board.conn.execute(
        "UPDATE armies SET station_node='city:hanzhong', station='汉中' WHERE id='mahan_liangqi'"
    )
    # mahan_liangqi is ma_han controlled; changan siege defender is cao_cao
    # Need a cao_cao army to relieve; use a nearby cao army instead
    # Just verify the relief registration works with an adjacent army
    board.conn.execute(
        "UPDATE armies SET station_node='city:hanzhong', station='汉中', owner_power='cao_cao' WHERE id='mahan_liangqi'"
    )
    register_siege_relief(board, siege_id, "mahan_liangqi")
    _, relieved_defender, factors = siege_module._siege_scores(board, siege_id)
    assert relieved_defender > fortified_defender
    assert any("援军" in item for item in factors["defender"])


def test_withdrawal_and_relief_defeat_keep_traceable_history(board):
    withdrawn_id = start_siege(board, _state(1), "zhanglu_hanzhong", "city:changan")
    withdrawn = withdraw_siege(board, _state(2), withdrawn_id, reason="粮道将断")
    assert withdrawn["status"] == "withdrawn"
    assert any(item["event"] == "withdrawn" for item in withdrawn["history"])

    board.conn.execute("UPDATE armies SET status='待命' WHERE id='zhanglu_hanzhong'")
    defeated_id = start_siege(board, _state(3), "zhanglu_hanzhong", "city:changan")
    # 用相邻的 cao_cao 军做救援（tongguan 与 changan 相邻且为 cao_cao 控制）
    board.conn.execute(
        "UPDATE armies SET station_node='city:tongguan', station='弘农', owner_power='cao_cao' WHERE id='mahan_longyou'"
    )
    defeated = resolve_siege_relief(
        board, _state(3), defeated_id, relief_army_id="mahan_longyou", attacker_defeated=True
    )
    assert defeated["status"] == "relief_defeat"
    assert any(item["event"] == "relief_defeat" for item in defeated["history"])


def test_siege_order_starts_and_advances_in_monthly_strategy_resolution(board, monkeypatch):
    monkeypatch.setattr(
        siege_module,
        "_siege_scores",
        lambda *_args, **_kwargs: (100, 100, {"attacker": [], "defender": []}),
    )
    order_id = board.issue_army_order(
        _state(1), "zhanglu_hanzhong", "围城", {"target": "city:changan"}
    )

    results = resolve_siege_turn(board, _state(1))

    assert results[0]["order_id"] == order_id
    order = board.list_army_orders(1)[0]
    assert order["status"] == "resolved"
    siege_id = order["result"]["siege_id"]
    assert _siege_row(board, siege_id)["progress"] == 34


def test_siege_model_adds_audit_history_without_changing_city_before_threshold(board, monkeypatch):
    monkeypatch.setattr(
        siege_module,
        "_siege_scores",
        lambda *_args, **_kwargs: (100, 100, {"attacker": [], "defender": []}),
    )
    state = _state(1)
    attach_adjudication_runtime(state, object(), None)
    siege_id = start_siege(board, state, "zhanglu_hanzhong", "city:changan")

    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        assert kind == "siege"
        return {
            "outcome": "continue_siege",
            "reason": "粮道尚可，宜继续围逼。",
            "risk_note": "城中存粮未尽。",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)
    result = advance_siege(board, state, siege_id)

    assert result["progress"] == 34
    assert board.conn.execute(
        "SELECT controlled_by FROM administrative_cities WHERE id='city:changan'"
    ).fetchone()[0] == "cao_cao"
    assert any(item.get("event") == "ai_judge" for item in result["history"])


def test_siege_model_cannot_conquer_before_progress_threshold(board, monkeypatch):
    monkeypatch.setattr(
        siege_module,
        "_siege_scores",
        lambda *_args, **_kwargs: (100, 100, {"attacker": [], "defender": []}),
    )
    state = _state(1)
    attach_adjudication_runtime(state, object(), None)
    siege_id = start_siege(board, state, "zhanglu_hanzhong", "city:changan")

    def bad_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        return {"outcome": "conquer_city", "reason": "提前易主。", "changes": []}

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", bad_judge)
    result = advance_siege(board, state, siege_id)

    assert result["progress"] == 34
    assert result["status"] == "active"
    assert board.conn.execute(
        "SELECT controlled_by FROM administrative_cities WHERE id='city:changan'"
    ).fetchone()[0] == "cao_cao"
    assert board.conn.execute(
        "SELECT COUNT(*) FROM pending_adjudications WHERE kind='siege'"
    ).fetchone()[0] == 1
