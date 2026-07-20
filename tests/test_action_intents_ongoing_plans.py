from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import GameState


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn: int = 1):
    return GameState(
        year=208,
        period=8 + turn - 1,
        turn=turn,
        stage="流亡军",
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
    )


def test_free_order_creates_executable_ongoing_plan_draft(board):
    intent = board.create_action_intent(
        _state(),
        source="自由命令",
        text="让张飞率军平定江夏叛军，三个月内完成，不得滥杀百姓。",
    )

    assert intent["status"] == "draft"
    assert intent["draft"]["executable"] is True
    assert intent["draft"]["action_type"] == "长期方略"
    assert intent["draft"]["assignee"] == "张飞"
    assert intent["draft"]["duration_months"] == 3
    assert "不得滥杀百姓" in intent["draft"]["constraints"]


def test_unexecutable_order_returns_reason_and_rewrite(board):
    intent = board.create_action_intent(
        _state(),
        source="自由命令",
        text="让曹操率军投降刘备并交出许都。",
    )

    assert intent["draft"]["executable"] is False
    assert "不属刘备军府" in "；".join(intent["draft"]["reasons"])
    assert intent["draft"]["rewrite_suggestion"]


def test_confirmed_long_order_is_advanced_without_player_reasking(board):
    state = _state()
    intent = board.create_action_intent(
        state,
        source="自由命令",
        text="让张飞率军平定江夏叛军，三个月内完成，不得滥杀百姓。",
    )
    result = board.confirm_action_intent(state, intent["id"])

    assert result["kind"] == "ongoing_plan"
    plan = board.get_ongoing_plan(result["plan_id"])
    assert plan["status"] == "active"
    assert plan["progress"] == 0

    first = board.advance_ongoing_plans(_state(turn=1))
    second = board.advance_ongoing_plans(_state(turn=2))
    third = board.advance_ongoing_plans(_state(turn=3))

    assert [item["status"] for item in first + second + third][-1] in {"done", "pending_review"}
    refreshed = board.get_ongoing_plan(result["plan_id"])
    assert refreshed["progress"] >= 100
    logs = board.list_ongoing_plan_logs(result["plan_id"])
    assert [log["turn"] for log in logs] == [1, 2, 3]


def test_ongoing_plan_blocks_when_assignee_becomes_unavailable(board):
    state = _state()
    intent = board.create_action_intent(
        state,
        source="自由命令",
        text="让张飞率军平定江夏叛军，三个月内完成，不得滥杀百姓。",
    )
    plan_id = board.confirm_action_intent(state, intent["id"])["plan_id"]
    board.conn.execute("UPDATE characters SET status='dead' WHERE name='张飞'")
    board.conn.commit()

    result = board.advance_ongoing_plans(_state(turn=2))[0]

    assert result["status"] == "blocked"
    assert "执行者" in result["narrative"]
    assert board.get_ongoing_plan(plan_id)["status"] == "blocked"


def test_blocked_ongoing_plan_enters_month_agenda(board):
    state = _state()
    intent = board.create_action_intent(
        state,
        source="自由命令",
        text="让张飞率军平定江夏叛军，三个月内完成，不得滥杀百姓。",
    )
    plan_id = board.confirm_action_intent(state, intent["id"])["plan_id"]
    board.update_ongoing_plan(plan_id, status="blocked", last_result="粮道受扰，需主公裁断。")

    agenda = board.month_agenda(_state(turn=2))

    assert any(item["kind"] == "长期方略受阻" and item["ref_id"] == plan_id for item in agenda)


def test_reputation_log_summary_tracks_sources(board):
    board.add_reputation_log(
        _state(),
        source_kind="ongoing_plan",
        source_id="7",
        metric="仁义",
        delta=4,
        summary="护民平叛，地方百姓愿附。",
    )

    summary = board.reputation_summary(limit=5)

    assert summary["score"] >= 50
    assert summary["recent"][0]["summary"] == "护民平叛，地方百姓愿附。"
