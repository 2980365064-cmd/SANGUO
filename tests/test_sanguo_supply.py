import json
from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.supply import (
    reachable_friendly_granary,
    resolve_supply_orders_for_turn,
    settle_army_supply,
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


def _set_city_grain(db, city_id, stock):
    """Set grain_stock on a city directly."""
    db.conn.execute(
        "UPDATE administrative_cities SET grain_stock=? WHERE id=?",
        (stock, city_id),
    )
    db.conn.commit()


def _set_commandery_grain(db, commandery_id, stock):
    """Set grain on all cities in a commandery."""
    db.conn.execute(
        "UPDATE administrative_cities SET grain_stock=? WHERE commandery_id=?",
        (stock, commandery_id),
    )
    db.conn.commit()


def _state(turn):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def test_reachable_granary_uses_connected_friendly_route(board):
    # sun_chaisang (sun_quan) is at city:chaisang. Set its grain to 0.
    # BFS should find grain at an adjacent sun_quan city (shouchun or wanling).
    _set_city_grain(board, "city:chaisang", 0)
    result = reachable_friendly_granary(board, "sun_chaisang")
    assert result is not None
    assert result.startswith("city:")


def test_enemy_control_blocks_supply_but_province_block_paths_do_not_use_pass_rules(board):
    # Part 1: sun_chaisang at city:chaisang, block ALL reachable sun_quan grain
    # chaisang neighbors: jiangxia(liu_qi), jingnan(cao), nanchang(sun), nanhai(shi_xie),
    #   runan(cao), shouchun(sun), wanling(sun)
    # Block ALL adjacent sun_quan cities by flipping their commanderies to cao_cao
    board.conn.execute("UPDATE regions SET controlled_by='cao_cao' WHERE id IN ('jiujiang','danyang','yuzhang','nanhai')")
    board.conn.execute(
        "UPDATE administrative_cities SET controlled_by='cao_cao' "
        "WHERE commandery_id IN ('jiujiang','danyang','yuzhang','nanhai')"
    )
    # Restore chaisang itself to sun_quan so the army has a valid start
    board.conn.execute(
        "UPDATE administrative_cities SET controlled_by='sun_quan' WHERE id='city:chaisang'"
    )
    _set_city_grain(board, "city:chaisang", 0)
    # BFS from chaisang: all sun_quan neighbors are now cao_cao
    result = reachable_friendly_granary(board, "sun_chaisang")
    assert result is None

    # Part 2: zhang_lu at city:shangyong (same commandery as hanzhong), hanzhong has grain
    board.conn.execute(
        "UPDATE armies SET station_node='city:shangyong', station='上庸' WHERE id='zhanglu_hanzhong'"
    )
    _set_commandery_grain(board, "hanzhong", 999)
    # BFS from shangyong finds grain at shangyong itself (same commandery, grain=999)
    result = reachable_friendly_granary(board, "zhanglu_hanzhong")
    assert result in ("city:shangyong", "city:hanzhong")


def test_xiakou_garrison_right_allows_liu_bei_to_draw_jiangxia_grain(board):
    # liubei_main is at city:jiangxia (liu_qi controlled, but liu_bei has garrison right)
    _set_commandery_grain(board, "jiangxia", 999)
    result = reachable_friendly_granary(board, "liubei_main")
    assert result == "city:jiangxia"


def test_granary_feeds_army_before_portable_supply_and_logs_stock_change(board):
    # sun_chaisang at city:chaisang, which is in yuzhang commandery
    _set_commandery_grain(board, "yuzhang", 999)
    before = board.region_grain_stock("yuzhang")
    before_supply = board.conn.execute(
        "SELECT supply FROM armies WHERE id='sun_chaisang'"
    ).fetchone()[0]

    result = settle_army_supply(board, _state(1), "sun_chaisang")

    assert result["source"] == "granary"
    assert result["grain_cost"] == 22  # 2.2 万人，每千人耗 1 单位郡仓粮
    assert board.region_grain_stock("yuzhang") == before - 22
    assert board.conn.execute(
        "SELECT supply FROM armies WHERE id='sun_chaisang'"
    ).fetchone()[0] == before_supply


def test_remote_army_consumes_twenty_portable_supply(board):
    # liubei_main moved to a cao_cao-controlled city with no garrison right
    board.conn.execute("UPDATE armies SET station_node='city:runan', station='汝南', supply=40 WHERE id='liubei_main'")

    result = settle_army_supply(board, _state(1), "liubei_main")

    assert result["source"] == "carried"
    assert result["supply_after"] == 20
    assert result["starvation_turns"] == 0


def test_starvation_escalates_morale_fatigue_desertion_and_combat_penalty(board):
    board.conn.execute(
        "UPDATE armies SET station_node='city:runan', station='汝南', supply=0, morale=70, "
        "fatigue=0, manpower=10000 WHERE id='liubei_main'"
    )

    first = settle_army_supply(board, _state(1), "liubei_main")
    second = settle_army_supply(board, _state(2), "liubei_main")
    third = settle_army_supply(board, _state(3), "liubei_main")

    assert first["starvation_turns"] == 1
    assert second["fatigue_delta"] == 12
    assert third["deserted"] == 200
    army = board.conn.execute(
        "SELECT morale, fatigue, manpower, starvation_turns, supply_combat_multiplier "
        "FROM armies WHERE id='liubei_main'"
    ).fetchone()
    assert army["morale"] == 46
    assert army["fatigue"] == 24
    assert army["manpower"] == 9800
    assert army["starvation_turns"] == 3
    assert army["supply_combat_multiplier"] == 0.65
    logged = {
        row["field"]
        for row in board.conn.execute(
            "SELECT field FROM army_logs WHERE army_id='liubei_main'"
        ).fetchall()
    }
    assert {"morale", "fatigue", "manpower", "supply_combat_multiplier"} <= logged


def test_supply_order_transfers_grain_to_carried_supply(board):
    # sun_chaisang at city:chaisang (yuzhang commandery) so reachable_friendly_granary works
    _set_commandery_grain(board, "yuzhang", 999)
    board.conn.execute(
        "UPDATE armies SET station_node='city:chaisang', station='柴桑', supply=20 WHERE id='sun_chaisang'"
    )
    order_id = board.issue_army_order(_state(1), "sun_chaisang", "补给", {"amount": 40})

    results = resolve_supply_orders_for_turn(board, _state(1))

    assert results[0]["order_id"] == order_id
    assert results[0]["supply_added"] == 40
    assert board.conn.execute(
        "SELECT supply FROM armies WHERE id='sun_chaisang'"
    ).fetchone()[0] == 60
    assert board.list_army_orders(1)[0]["status"] == "resolved"


def test_game_session_strategic_settlement_runs_supply_each_month(board):
    from ming_sim.session import GameSession

    board.conn.execute(
        "UPDATE armies SET station_node='city:runan', station='汝南', supply=40 WHERE id='liubei_main'"
    )
    session = GameSession.__new__(GameSession)
    session.db = board

    session._resolve_strategic_turn(_state(1))

    assert board.conn.execute(
        "SELECT supply_last_settled_turn, supply FROM armies WHERE id='liubei_main'"
    ).fetchone()[:] == (1, 20)
