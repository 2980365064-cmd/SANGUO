from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.sanguo_rules import (
    ArmyOrderError,
    resolve_army_order,
    resolve_army_orders_for_turn,
    validate_route_move,
)


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def test_validate_route_move_rejects_non_neighboring_province_destination(board):
    with pytest.raises(ArmyOrderError, match="不接壤"):
        validate_route_move(board, "sun_jianye", "jianye", "ji")


def test_neighboring_province_movement_uses_province_block_not_pass_route(board):
    edge = validate_route_move(board, "mahan_longyou", "tianshui", "hanzhong")
    assert edge.kind == "州块"
    assert edge.note == "凉州-益州"


def test_move_order_consumes_one_turn_without_route_hazard(board):
    state = SimpleNamespace(turn=1)
    order_id = board.issue_army_order(state, "sun_jianye", "移动", {"to": "chaisang"})

    result = resolve_army_order(board, state, order_id)

    army = board.conn.execute(
        "SELECT station_node, supply, hazard_turns, hazard_combat_multiplier, "
        "hazard_mobility_multiplier FROM armies WHERE id='sun_jianye'"
    ).fetchone()
    assert dict(army) == {
        "station_node": "chaisang",
        "supply": 100,
        "hazard_turns": 0,
        "hazard_combat_multiplier": 1.0,
        "hazard_mobility_multiplier": 1.0,
    }
    assert result["duration_turns"] == 1
    assert result["route_kind"] == "州块"


def test_same_province_movement_uses_province_block_without_mountain_penalty(board):
    state = SimpleNamespace(turn=1)
    order_id = board.issue_army_order(state, "mahan_longyou", "移动", {"to": "longxi"})

    resolve_army_order(board, state, order_id)

    army = board.conn.execute(
        "SELECT hazard_combat_multiplier, hazard_mobility_multiplier "
        "FROM armies WHERE id='mahan_longyou'"
    ).fetchone()
    assert army["hazard_combat_multiplier"] == 1.0
    assert army["hazard_mobility_multiplier"] == 1.0


def test_low_supply_no_longer_blocks_province_block_movement(board):
    state = SimpleNamespace(turn=1)
    board.conn.execute("UPDATE armies SET supply=19 WHERE id='sun_jianye'")

    order_id = board.issue_army_order(state, "sun_jianye", "移动", {"to": "chaisang"})
    assert order_id > 0


def test_province_block_movement_remains_idempotent_without_hazard_stack(board):
    state = SimpleNamespace(turn=1)
    board.issue_army_order(state, "sun_jianye", "移动", {"to": "chaisang"})
    resolved = resolve_army_orders_for_turn(board, 1)
    assert len(resolved) == 1
    assert board.conn.execute(
        "SELECT hazard_turns FROM armies WHERE id='sun_jianye'"
    ).fetchone()[0] == 0

    resolve_army_orders_for_turn(board, 2)
    resolve_army_orders_for_turn(board, 2)
    assert board.conn.execute(
        "SELECT hazard_turns FROM armies WHERE id='sun_jianye'"
    ).fetchone()[0] == 0


def test_second_primary_order_same_turn_is_still_rejected(board):
    state = SimpleNamespace(turn=1)
    board.issue_army_order(state, "sun_jianye", "驻守", {})
    with pytest.raises(ArmyOrderError, match="本回合已执行主军令"):
        board.issue_army_order(state, "sun_jianye", "移动", {"to": "chaisang"})
