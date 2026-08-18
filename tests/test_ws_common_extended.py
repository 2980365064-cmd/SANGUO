"""tests/test_ws_common_extended.py：第六期公共基础扩展测试（阶段 B）。

验证：
  - iter_active_powers
  - log_power_change / log_diplomacy_change / log_region_change
  - 观察路径扁平化后功能等价
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55},
    )


def _board(tmp_path: Path) -> GameDB:
    db = GameDB(str(tmp_path / "common_ext.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


# ---------------------------------------------------------------------------
# iter_active_powers
# ---------------------------------------------------------------------------

class TestIterActivePowers:
    def test_excludes_liu_bei_by_default(self, tmp_path):
        from ming_sim.ws_common import iter_active_powers
        db = _board(tmp_path)
        powers = iter_active_powers(db)
        ids = [str(p["id"]) for p in powers]
        assert "liu_bei" not in ids
        assert len(ids) > 0

    def test_includes_liu_bei_when_requested(self, tmp_path):
        from ming_sim.ws_common import iter_active_powers
        db = _board(tmp_path)
        powers = iter_active_powers(db, exclude_liu_bei=False)
        ids = [str(p["id"]) for p in powers]
        assert "liu_bei" in ids

    def test_returns_correct_fields(self, tmp_path):
        from ming_sim.ws_common import iter_active_powers
        db = _board(tmp_path)
        powers = iter_active_powers(db)
        for p in powers:
            assert "id" in p.keys()
            assert "cohesion" in p.keys()
            assert "supply" in p.keys()
            assert "status" in p.keys()


# ---------------------------------------------------------------------------
# log_power_change / log_diplomacy_change / log_region_change
# ---------------------------------------------------------------------------

class TestLogPowerChange:
    def test_inserts_power_log(self, tmp_path):
        from ming_sim.ws_common import log_power_change
        db = _board(tmp_path)
        state = _state()

        log_power_change(db, state, "cao_cao", "cohesion", 50, 45, "test reason")
        db.conn.commit()

        row = db.conn.execute(
            "SELECT * FROM power_logs WHERE power_id='cao_cao' AND field='cohesion'"
        ).fetchone()
        assert row is not None
        assert int(row["old_value"]) == 50
        assert int(row["new_value"]) == 45
        assert int(row["delta"]) == -5
        assert str(row["reason"]) == "test reason"

    def test_turn_year_period_from_state(self, tmp_path):
        from ming_sim.ws_common import log_power_change
        db = _board(tmp_path)
        state = _state(turn=5)

        log_power_change(db, state, "sun_quan", "supply", 60, 70, "supply gain")
        db.conn.commit()

        row = db.conn.execute(
            "SELECT turn, year, period FROM power_logs WHERE power_id='sun_quan'"
        ).fetchone()
        assert int(row["turn"]) == 5
        assert int(row["year"]) == 208
        assert int(row["period"]) == 8


class TestLogDiplomacyChange:
    def test_inserts_diplomacy_log(self, tmp_path):
        from ming_sim.ws_common import log_diplomacy_change
        db = _board(tmp_path)
        state = _state()

        log_diplomacy_change(
            db, state, "cao_cao", "liu_bei",
            "public_relation", -30, -27,
            "incident_chain", actor="sun_quan",
        )
        db.conn.commit()

        row = db.conn.execute(
            "SELECT * FROM diplomacy_logs WHERE power_a='cao_cao' AND power_b='liu_bei'"
        ).fetchone()
        assert row is not None
        assert str(row["old_value"]) == "-30"
        assert str(row["new_value"]) == "-27"
        assert str(row["reason"]) == "incident_chain"
        assert str(row["actor"]) == "sun_quan"


class TestLogRegionChange:
    def test_inserts_region_log(self, tmp_path):
        from ming_sim.ws_common import log_region_change
        db = _board(tmp_path)
        state = _state()

        log_region_change(
            db, state, "luoyang", "unrest",
            30, 35, "区域事件即时效果", actor="regional_incident",
        )
        db.conn.commit()

        row = db.conn.execute(
            "SELECT * FROM region_logs WHERE region_id='luoyang'"
        ).fetchone()
        assert row is not None
        assert int(row["old_value"]) == 30
        assert int(row["new_value"]) == 35
        assert int(row["delta"]) == 5


# ---------------------------------------------------------------------------
# 观察路径扁平化回归
# ---------------------------------------------------------------------------

class TestObservationPathFlatten:
    def test_backward_compat_aliases(self, tmp_path):
        """向后兼容别名仍然存在且可调用。"""
        from ming_sim.world_simulation import (
            _is_bordering_liu_bei_via,
            _has_active_envoy_for,
            _can_merchant_network_between,
        )
        # 这些应该是 callable（函数别名）
        assert callable(_is_bordering_liu_bei_via)
        assert callable(_has_active_envoy_for)
        assert callable(_can_merchant_network_between)

    def test_aliases_delegate_to_unified(self, tmp_path):
        """别名应与统一 API 行为一致。"""
        from ming_sim.ws_geopolitics import (
            _is_bordering_liu_bei_via,
            _has_active_envoy_for,
            _can_merchant_network_between,
        )
        from ming_sim.ws_intelligence import (
            is_bordering, has_active_envoy_unified, can_merchant_network_unified,
        )
        # 别名应指向同一函数对象（或等价）
        assert _is_bordering_liu_bei_via is is_bordering
        assert _has_active_envoy_for is has_active_envoy_unified
        assert _can_merchant_network_between is can_merchant_network_unified
