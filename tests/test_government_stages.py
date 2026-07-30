from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.government import (
    appoint_office,
    government_stage,
    office_effect,
    stage_semantics,
)


def test_government_stage_uses_world_state_not_calendar_force():
    assert government_stage(208, 7, {}) == "流亡军"
    assert government_stage(209, 1, {"controlled_nodes": ["jiangxia"]}) == "荆州立足"
    assert government_stage(214, 7, {"controlled_nodes": ["chengdu"]}) == "益州治蜀"
    assert government_stage(219, 7, {"titles": ["汉中王"]}) == "汉中王"
    assert government_stage(221, 4, {"proclaimed_emperor": True}) == "称帝后"
    assert government_stage(223, 1, {"titles": ["汉中王"]}) == "汉中王"


def test_208_semantics_never_use_emperor_or_court_language():
    semantics = stage_semantics("流亡军")
    assert semantics["address"] == "主公"
    assert semantics["meeting"] == "军议"
    assert semantics["imperial"] is False
    assert "皇帝" not in semantics["scene"] and "朝会" not in semantics["scene"]


def test_only_proclaimed_emperor_stage_switches_to_shuhan_court_semantics():
    semantics = stage_semantics("称帝后")
    assert semantics == {
        "address": "陛下",
        "meeting": "朝会",
        "scene": "蜀汉宫城",
        "imperial": True,
    }


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def test_simplified_government_has_exactly_ten_locked_roles(board):
    assert set(board.content.sanguo_offices) == {
        "chief_strategist", "military_chief", "civil_chief", "finance_chief",
        "diplomacy_chief", "intelligence_chief", "main_commander", "guard_commander",
        "governor", "theater_governor",
    }


def test_vacancy_reduces_efficiency_but_never_blocks_action(board):
    effect = office_effect(board, "chief_strategist")
    assert effect["vacant"] is True
    assert effect["efficiency"] < 100
    assert effect["action_blocked"] is False


def test_player_appointment_persists_and_uses_relevant_character_ability(board):
    low = appoint_office(board, _state(1), "chief_strategist", "张飞")
    high = appoint_office(board, _state(2), "chief_strategist", "诸葛亮")
    assert high["efficiency"] > low["efficiency"]
    assert high["character_name"] == "诸葛亮"
    assert board.conn.execute(
        "SELECT character_name FROM government_offices WHERE office_key='chief_strategist'"
    ).fetchone()[0] == "诸葛亮"


def _state(turn):
    return SimpleNamespace(turn=turn, year=208, period=turn, stage="流亡军")


def test_session_stage_sync_follows_actual_liu_bei_control(board):
    from ming_sim.session import GameSession

    session = GameSession.__new__(GameSession)
    session.db = board
    session.state = _state(1)
    session._sync_government_stage()
    assert session.state.stage == "流亡军"

    board.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    session._sync_government_stage()
    assert session.state.stage == "荆州立足"
