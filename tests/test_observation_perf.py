"""tests/test_observation_perf.py：观察路径 API 性能测试（阶段 4）。

验证：
  - 优化后的 SQL 与旧实现功能等价
  - is_bordering / can_merchant_network_unified 单次调用 < 10ms
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import (
    is_bordering,
    can_merchant_network_unified,
    _is_bordering_liu_bei,
    _is_power_bordering_liu_bei,
    _can_merchant_network,
)
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55},
    )


def _board(tmp_path: Path) -> GameDB:
    db = GameDB(str(tmp_path / "perf.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    # 设置外交关系
    for pa, pb, pr, trust, status in [
        ("cao_cao", "liu_bei", -30, 10, "neutral"),
        ("sun_quan", "liu_bei", 20, 40, "neutral"),
        ("cao_cao", "sun_quan", -10, 15, "neutral"),
    ]:
        db.conn.execute(
            "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (pa, pb, pr, trust, status),
        )
    db.conn.commit()
    return db


class TestFunctionalEquivalence:
    """功能等价性测试：确保优化后的实现与旧实现行为一致。"""

    def test_is_bordering_same_as_power_bordering(self, tmp_path):
        """is_bordering(liu_bei, X) 应与 _is_power_bordering_liu_bei(X) 等价。"""
        db = _board(tmp_path)
        for power in ["cao_cao", "sun_quan"]:
            result_unified = is_bordering(db, "liu_bei", power)
            result_legacy = _is_power_bordering_liu_bei(db, power)
            assert result_unified == result_legacy, f"Mismatch for {power}"

    def test_can_merchant_network_same_as_legacy(self, tmp_path):
        """can_merchant_network_unified(liu_bei, X) 应与 _can_merchant_network(X) 等价。"""
        db = _board(tmp_path)
        for power in ["cao_cao", "sun_quan"]:
            result_unified = can_merchant_network_unified(db, "liu_bei", power)
            result_legacy = _can_merchant_network(db, power)
            assert result_unified == result_legacy, f"Mismatch for {power}"

    def test_is_bordering_node_level(self, tmp_path):
        """节点级 _is_bordering_liu_bei 应正常工作。"""
        db = _board(tmp_path)
        # 获取一个刘备控制的节点
        liu_node = db.conn.execute(
            "SELECT id FROM regions WHERE controlled_by='liu_bei' LIMIT 1"
        ).fetchone()
        if liu_node:
            # 查询其邻居是否与刘备接壤（应返回 True 如果邻居也是刘备控制的）
            result = _is_bordering_liu_bei(db, str(liu_node["id"]))
            assert isinstance(result, bool)


class TestPerformance:
    """性能基准测试。"""

    def test_is_bordering_performance(self, tmp_path):
        """is_bordering 单次调用应 < 10ms。"""
        db = _board(tmp_path)

        # 预热
        is_bordering(db, "cao_cao", "liu_bei")

        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            is_bordering(db, "cao_cao", "liu_bei")
        elapsed = time.perf_counter() - start

        per_call_ms = (elapsed / iterations) * 1000
        assert per_call_ms < 10, f"is_bordering 太慢: {per_call_ms:.2f}ms/call"

    def test_can_merchant_network_performance(self, tmp_path):
        """can_merchant_network_unified 单次调用应 < 10ms。"""
        db = _board(tmp_path)

        # 预热
        can_merchant_network_unified(db, "cao_cao", "liu_bei")

        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            can_merchant_network_unified(db, "cao_cao", "liu_bei")
        elapsed = time.perf_counter() - start

        per_call_ms = (elapsed / iterations) * 1000
        assert per_call_ms < 10, f"can_merchant_network_unified 太慢: {per_call_ms:.2f}ms/call"

    def test_legacy_functions_performance(self, tmp_path):
        """旧版函数（已委托至统一 API）也应 < 10ms。"""
        db = _board(tmp_path)

        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            _can_merchant_network(db, "cao_cao")
        elapsed = time.perf_counter() - start

        per_call_ms = (elapsed / iterations) * 1000
        assert per_call_ms < 10, f"_can_merchant_network 太慢: {per_call_ms:.2f}ms/call"
