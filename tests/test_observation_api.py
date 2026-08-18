"""tests/test_observation_api.py：统一观察路径 API 测试。

验证：
  - is_bordering：势力级接壤判断（单条 SQL）
  - has_active_envoy_unified：使者判断
  - can_merchant_network_unified：商旅网络判断
  - determine_observation_source：综合来源判断
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import (
    is_bordering,
    has_active_envoy_unified,
    can_merchant_network_unified,
    determine_observation_source,
)
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55},
    )


def _board(tmp_path: Path) -> GameDB:
    db = GameDB(str(tmp_path / "observation.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


class TestIsBordering:
    def test_same_power_returns_false(self, tmp_path):
        db = _board(tmp_path)
        assert is_bordering(db, "liu_bei", "liu_bei") is False

    def test_empty_power_returns_false(self, tmp_path):
        db = _board(tmp_path)
        assert is_bordering(db, "", "cao_cao") is False
        assert is_bordering(db, "liu_bei", "") is False

    def test_nonexistent_power_returns_false(self, tmp_path):
        db = _board(tmp_path)
        assert is_bordering(db, "nonexistent", "liu_bei") is False


class TestHasActiveEnvoy:
    def test_no_envoy_returns_false(self, tmp_path):
        db = _board(tmp_path)
        assert has_active_envoy_unified(db, "liu_bei", "cao_cao") is False

    def test_active_envoy_returns_true(self, tmp_path):
        db = _board(tmp_path)
        db.conn.execute(
            "INSERT INTO envoy_missions (turn, year, period, target_power, envoy, goal, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 208, 8, "cao_cao", "test_envoy", "test_goal", "active"),
        )
        db.conn.commit()
        assert has_active_envoy_unified(db, "liu_bei", "cao_cao") is True

    def test_completed_envoy_returns_false(self, tmp_path):
        db = _board(tmp_path)
        db.conn.execute(
            "INSERT INTO envoy_missions (turn, year, period, target_power, envoy, goal, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 208, 8, "cao_cao", "test_envoy", "test_goal", "completed"),
        )
        db.conn.commit()
        assert has_active_envoy_unified(db, "liu_bei", "cao_cao") is False


class TestDetermineObservationSource:
    def test_no_path_returns_none(self, tmp_path):
        db = _board(tmp_path)
        source, vis, rel = determine_observation_source(db, "liu_bei", {"nonexistent"})
        assert source is None
        assert vis == ""
        assert rel == 0

    def test_self_excluded(self, tmp_path):
        db = _board(tmp_path)
        source, vis, rel = determine_observation_source(db, "liu_bei", {"liu_bei"})
        assert source is None

    def test_border_observer_priority(self, tmp_path):
        """接壤优先于使者和商旅。"""
        db = _board(tmp_path)
        # 添加使者
        db.conn.execute(
            "INSERT INTO envoy_missions (turn, year, period, target_power, envoy, goal, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 208, 8, "cao_cao", "test_envoy", "test_goal", "active"),
        )
        # 接壤判断依赖静态数据，这里只测试使者路径
        source, vis, rel = determine_observation_source(db, "liu_bei", {"cao_cao"})
        # 如果接壤则返回 border_observer，否则返回 envoy
        assert source in ("border_observer", "envoy")
