from types import SimpleNamespace

import pytest

import ming_sim.adjudication as adjudication_module
from ming_sim.adjudication import attach_adjudication_runtime, run_adjudication
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.government import appoint_office
from ming_sim.national_focus import (
    advance_all_focuses,
    advance_all_region_investments,
    advance_focus,
    advance_region_investment,
    focus_points,
    start_focus,
    start_region_investment,
)
from ming_sim.supply import settle_army_supply


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn=1, **metrics):
    values = {"军资": 80, "粮秣": 60, "民望": 50, "名分": 70, "军心": 70, "士族支持": 40}
    values.update(metrics)
    return SimpleNamespace(turn=turn, year=208, period=turn, metrics=values)


def test_focus_book_has_exactly_eleven_approved_branches(board):
    focuses = board.content.national_focuses
    assert len(focuses) == 11
    counts = {category: sum(1 for item in focuses.values() if item["category"] == category)
              for category in ("政治", "军事", "经济")}
    assert counts == {"政治": 3, "军事": 5, "经济": 3}


def test_focus_points_are_zero_to_three_from_base_excellent_and_key_office(board):
    state = _state(士族支持=40)
    assert focus_points(board, state, "政治") == 1
    state.metrics["士族支持"] = 70
    assert focus_points(board, state, "政治") == 2
    appoint_office(board, state, "civil_chief", "诸葛亮")
    assert focus_points(board, state, "政治") == 3

    military = _state()
    assert focus_points(board, military, "军事") == 1
    board.conn.execute("UPDATE armies SET manpower=25000 WHERE owner_power='liu_bei'")
    assert focus_points(board, military, "军事") == 2
    appoint_office(board, military, "main_commander", "关羽")
    assert focus_points(board, military, "军事") == 3

    economy = _state(民望=70)
    assert focus_points(board, economy, "经济") == 2
    appoint_office(board, economy, "finance_chief", "诸葛亮")
    assert focus_points(board, economy, "经济") == 3


def test_three_categories_can_progress_in_parallel_but_same_category_is_exclusive(board):
    state = _state()
    start_focus(board, state, "han_legitimacy")
    start_focus(board, state, "military_logistics")
    start_focus(board, state, "agriculture_trade")
    active = board.conn.execute(
        "SELECT category, COUNT(*) AS n FROM national_focus_progress WHERE status='active' GROUP BY category"
    ).fetchall()
    assert {row["category"]: row["n"] for row in active} == {"政治": 1, "军事": 1, "经济": 1}
    with pytest.raises(ValueError, match="同类"):
        start_focus(board, state, "jingyi_integration")


def test_focus_prerequisite_and_completion_apply_real_effect_once(board):
    state = _state(士族支持=70)
    with pytest.raises(ValueError, match="前置"):
        start_focus(board, state, "jingyi_integration")
    start_focus(board, state, "han_legitimacy")
    before = state.metrics["名分"]
    result = None
    for turn in range(1, 10):
        state.turn = turn
        result = advance_focus(board, state, "han_legitimacy")
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert state.metrics["名分"] > before
    completed_value = state.metrics["名分"]
    advance_focus(board, state, "han_legitimacy")
    assert state.metrics["名分"] == completed_value
    assert board.conn.execute(
        "SELECT 1 FROM national_focus_effects WHERE focus_id='han_legitimacy' AND effect_key='名分'"
    ).fetchone()


def test_each_region_allows_only_one_investment_and_completion_changes_region(board):
    board.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    state = _state()
    start_region_investment(board, state, "jiangxia", "屯田粮仓")
    with pytest.raises(ValueError, match="同一时间"):
        start_region_investment(board, state, "jiangxia", "城防守备")
    before = board.region_grain_stock("jiangxia")
    result = None
    for turn in range(1, 8):
        state.turn = turn
        result = advance_region_investment(board, state, "jiangxia")
        if result["status"] == "completed":
            break
    assert result["status"] == "completed"
    assert board.region_grain_stock("jiangxia") > before
    assert state.metrics["军资"] < 80
    assert board.conn.execute(
        "SELECT COUNT(*) FROM region_investment_logs WHERE region_id='jiangxia'"
    ).fetchone()[0] >= 4


def test_cannot_invest_in_region_not_controlled_by_liu_bei(board):
    with pytest.raises(ValueError, match="控制"):
        start_region_investment(board, _state(), "chengdu", "民政市易")


def test_family_data_contains_only_historical_political_and_succession_relations(board):
    rows = board.conn.execute("SELECT * FROM family_relations ORDER BY id").fetchall()
    assert rows
    allowed = {"spouse", "child", "adopted_child", "political_marriage", "succession"}
    assert {row["relation_type"] for row in rows} <= allowed
    assert not any("random" in row["source"].lower() or "选妃" in row["source"] for row in rows)
    assert board.conn.execute(
        "SELECT 1 FROM family_relations WHERE person_a='刘备' AND person_b='刘禅' AND relation_type='child'"
    ).fetchone()
    assert board.conn.execute(
        "SELECT 1 FROM family_relations WHERE person_a='刘备' AND person_b='孙尚香' AND relation_type='political_marriage'"
    ).fetchone()


def test_completed_logistics_focus_reduces_real_carried_supply_cost(board):
    state = _state()
    start_focus(board, state, "military_logistics")
    for turn in range(1, 12):
        state.turn = turn
        if advance_focus(board, state, "military_logistics")["status"] == "completed":
            break

    board.conn.execute(
        "UPDATE armies SET station_node='runan', supply=40, supply_last_settled_turn=0 "
        "WHERE id='liubei_main'"
    )
    state.turn = 20
    result = settle_army_supply(board, state, "liubei_main")
    assert result["source"] == "carried"
    assert board.conn.execute(
        "SELECT supply FROM armies WHERE id='liubei_main'"
    ).fetchone()[0] == 22


def test_monthly_batch_helpers_advance_focuses_and_region_investments(board):
    board.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    state = _state(turn=1)
    start_focus(board, state, "han_legitimacy")
    start_focus(board, state, "military_logistics")
    start_focus(board, state, "agriculture_trade")
    start_region_investment(board, state, "jiangxia", "城防守备")

    focus_results = advance_all_focuses(board, state)
    investment_results = advance_all_region_investments(board, state)

    assert {item["focus_id"] for item in focus_results} == {
        "han_legitimacy", "military_logistics", "agriculture_trade"
    }
    assert all(item["progress"] > 0 for item in focus_results)
    assert investment_results == [{
        "region_id": "jiangxia",
        "category": "城防守备",
        "progress": 25,
        "status": "active",
        "resource_cost": 2,
    }]


def test_region_investment_model_adds_audit_note_without_free_resources(board, monkeypatch):
    board.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    state = _state(turn=1, 军资=10)
    attach_adjudication_runtime(state, object(), None)
    start_region_investment(board, state, "jiangxia", "道路粮道")

    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        assert kind == "region_investment"
        return {
            "outcome": "advance_investment",
            "reason": "士民愿服役，粮道本月推进顺畅。",
            "risk_note": "仍耗军资，不可免费。",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)
    result = advance_region_investment(board, state, "jiangxia")

    assert result["progress"] == 25
    assert result["resource_cost"] == 2
    assert state.metrics["军资"] == 8
    log = board.conn.execute(
        "SELECT reason FROM region_investment_logs WHERE region_id='jiangxia' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert "AI裁判依据" in log["reason"]


def test_region_investment_model_cannot_bypass_resource_cost(board, monkeypatch):
    board.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    state = _state(turn=1, 军资=1)
    attach_adjudication_runtime(state, object(), None)
    start_region_investment(board, state, "jiangxia", "道路粮道")

    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        raise AssertionError("军资不足时不应调用模型绕过硬规则")

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)
    with pytest.raises(ValueError, match="军资不足"):
        advance_region_investment(board, state, "jiangxia")

    assert state.metrics["军资"] == 1


def test_personnel_adjudication_is_suggestion_only_without_office_mutation(board, monkeypatch):
    state = _state()

    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        assert kind == "personnel"
        return {
            "outcome": "appoint_candidate",
            "reason": "诸葛亮才略适配军师将军。",
            "recommended_followup": "请主公走正式任事。",
            "changes": [{"kind": "office_assignment", "office_key": "chief_strategist", "character_name": "诸葛亮"}],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)
    result = run_adjudication(
        board,
        state,
        "personnel",
        "chief_strategist",
        llm_config=object(),
        agno_db=None,
        candidate_name="诸葛亮",
    )

    assert result["status"] == "validated"
    assert board.conn.execute(
        "SELECT character_name FROM government_offices WHERE office_key='chief_strategist'"
    ).fetchone() is None
