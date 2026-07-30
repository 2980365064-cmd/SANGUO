from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.sanguo_rules import (
    ArmyOrderError,
    find_strategic_route,
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


def test_validate_route_move_rejects_non_adjacent_city(board):
    """非直连城池之间的移动被拒绝。"""
    with pytest.raises(ArmyOrderError, match="无直连路线"):
        validate_route_move(board, "cao_north", "city:ye", "city:jiaozhi")


def test_validate_route_move_rejects_bare_node_id(board):
    """裸 ID（不以 city: 开头）被拒绝。"""
    with pytest.raises(ArmyOrderError, match="必须是城池节点"):
        validate_route_move(board, "cao_north", "ye", "city:nanpi")


def test_adjacent_city_movement_uses_direct_edge(board):
    """相邻城池移动返回直连路线边。"""
    edge = validate_route_move(board, "mahan_longyou", "city:tianshui", "city:longxi")
    assert edge.kind == "普通路"


def test_move_order_consumes_one_turn_without_route_hazard(board):
    """普通路移动消耗一回合，无险路惩罚。"""
    state = SimpleNamespace(turn=1)
    # sun_jianye at city:jianye, move to city:wu (adjacent)
    order_id = board.issue_army_order(state, "sun_jianye", "移动", {"to": "city:wu"})

    result = resolve_army_order(board, state, order_id)

    army = board.conn.execute(
        "SELECT station_node, supply, hazard_turns, hazard_combat_multiplier, "
        "hazard_mobility_multiplier FROM armies WHERE id='sun_jianye'"
    ).fetchone()
    assert army["station_node"] == "city:wu"
    assert army["supply"] == 100
    assert army["hazard_turns"] == 0
    assert army["hazard_combat_multiplier"] == 1.0
    assert army["hazard_mobility_multiplier"] == 1.0
    assert result["duration_turns"] == 1
    assert result["route_kind"] == "普通路"


def test_normal_road_movement_has_no_hazard_penalty(board):
    """普通路移动无山地/险路惩罚。"""
    state = SimpleNamespace(turn=1)
    # mahan_longyou at city:tianshui, move to city:longxi (adjacent, 普通路)
    order_id = board.issue_army_order(state, "mahan_longyou", "移动", {"to": "city:longxi"})

    resolve_army_order(board, state, order_id)

    army = board.conn.execute(
        "SELECT hazard_combat_multiplier, hazard_mobility_multiplier "
        "FROM armies WHERE id='mahan_longyou'"
    ).fetchone()
    assert army["hazard_combat_multiplier"] == 1.0
    assert army["hazard_mobility_multiplier"] == 1.0


def test_low_supply_does_not_block_normal_road_movement(board):
    """低携粮不阻断普通路移动（仅江河/山道有携粮门槛）。"""
    state = SimpleNamespace(turn=1)
    board.conn.execute("UPDATE armies SET supply=5 WHERE id='sun_jianye'")
    order_id = board.issue_army_order(state, "sun_jianye", "移动", {"to": "city:wu"})
    assert order_id > 0


def test_movement_resolution_is_idempotent_without_hazard_stack(board):
    """重复调用月末结算不会重复扣减险路时长。"""
    state = SimpleNamespace(turn=1)
    board.issue_army_order(state, "sun_jianye", "移动", {"to": "city:wu"})
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
    """同一军队同回合不能接收两道主军令。"""
    state = SimpleNamespace(turn=1)
    board.issue_army_order(state, "sun_jianye", "驻守", {})
    with pytest.raises(ArmyOrderError, match="本回合已执行主军令"):
        board.issue_army_order(state, "sun_jianye", "移动", {"to": "city:wu"})


def test_find_strategic_route_returns_edge_for_adjacent_cities(board):
    """find_strategic_route 对相邻城池返回边，对不相邻城池返回 None。"""
    edge = find_strategic_route(board, "city:tianshui", "city:longxi")
    assert edge is not None
    assert edge.kind == "普通路"

    no_edge = find_strategic_route(board, "city:tianshui", "city:ye")
    assert no_edge is None


def test_find_strategic_route_returns_none_for_same_node(board):
    """同节点查询返回 None（无需路线）。"""
    assert find_strategic_route(board, "city:tianshui", "city:tianshui") is None
