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


def _set_grain(db, region_id, stock):
    row = db.conn.execute("SELECT fiscal FROM regions WHERE id=?", (region_id,)).fetchone()
    fiscal = json.loads(row["fiscal"])
    fiscal["grain_stock"] = stock
    fiscal["granary"] = stock
    db.conn.execute(
        "UPDATE regions SET fiscal=? WHERE id=?",
        (json.dumps(fiscal, ensure_ascii=False), region_id),
    )
    db.conn.commit()


def _state(turn):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def test_reachable_granary_uses_connected_friendly_route(board):
    _set_grain(board, "chaisang", 0)
    assert reachable_friendly_granary(board, "sun_chaisang") == "jianye"


def test_enemy_control_blocks_supply_but_province_block_paths_do_not_use_pass_rules(board):
    _set_grain(board, "chaisang", 0)
    board.conn.execute("UPDATE regions SET controlled_by='cao_cao' WHERE id='jianye'")
    assert reachable_friendly_granary(board, "sun_chaisang") == "wu"

    board.conn.execute(
        "UPDATE armies SET station_node='tianshui', station='天水' WHERE id='zhanglu_hanzhong'"
    )
    board.conn.execute("UPDATE regions SET controlled_by='zhang_lu' WHERE id='tianshui'")
    _set_grain(board, "tianshui", 0)
    _set_grain(board, "hanzhong", 999)
    assert reachable_friendly_granary(board, "zhanglu_hanzhong") == "hanzhong"


def test_xiakou_garrison_right_allows_liu_bei_to_draw_jiangxia_grain(board):
    assert reachable_friendly_granary(board, "liubei_main") == "jiangxia"


def test_granary_feeds_army_before_portable_supply_and_logs_stock_change(board):
    before = board.region_grain_stock("chaisang")
    before_supply = board.conn.execute(
        "SELECT supply FROM armies WHERE id='sun_chaisang'"
    ).fetchone()[0]

    result = settle_army_supply(board, _state(1), "sun_chaisang")

    assert result["source"] == "granary"
    assert result["grain_cost"] == 22  # 2.2 万人，每千人耗 1 单位郡仓粮
    assert board.region_grain_stock("chaisang") == before - 22
    assert board.conn.execute(
        "SELECT supply FROM armies WHERE id='sun_chaisang'"
    ).fetchone()[0] == before_supply
    assert board.conn.execute(
        "SELECT 1 FROM region_logs WHERE region_id='chaisang' AND field='grain_stock'"
    ).fetchone()


def test_remote_army_consumes_twenty_portable_supply(board):
    board.conn.execute("UPDATE armies SET station_node='runan', station='汝南', supply=40 WHERE id='liubei_main'")

    result = settle_army_supply(board, _state(1), "liubei_main")

    assert result["source"] == "carried"
    assert result["supply_after"] == 20
    assert result["starvation_turns"] == 0


def test_starvation_escalates_morale_fatigue_desertion_and_combat_penalty(board):
    board.conn.execute(
        "UPDATE armies SET station_node='runan', station='汝南', supply=0, morale=70, "
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
    board.conn.execute("UPDATE armies SET supply=20 WHERE id='sun_chaisang'")
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
        "UPDATE armies SET station_node='runan', station='汝南', supply=40 WHERE id='liubei_main'"
    )
    session = GameSession.__new__(GameSession)
    session.db = board

    session._resolve_strategic_turn(_state(1))

    assert board.conn.execute(
        "SELECT supply_last_settled_turn, supply FROM armies WHERE id='liubei_main'"
    ).fetchone()[:] == (1, 20)
