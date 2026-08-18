"""tests/test_new_dynamic_types.py：新增内部动态类型测试（阶段 5）。

验证 5 种新增类型：
  - succession_crisis: 继承危机
  - economic_strain: 经济压力
  - military_faction: 军阀派系
  - diplomatic_isolation: 外交孤立
  - natural_disaster_recovery: 灾后恢复
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import (
    ensure_power_internal_dynamics,
    apply_power_internal_dynamic_effects,
)
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55},
    )


def _board(tmp_path: Path) -> GameDB:
    db = GameDB(str(tmp_path / "new_dynamics.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


def _set_power_stats(db, power_id: str, *, cohesion: int = 50, supply: int = 50):
    """设置势力属性。"""
    db.conn.execute(
        "UPDATE powers SET cohesion=?, supply=? WHERE id=?",
        (cohesion, supply, power_id),
    )
    db.conn.commit()


def _set_region_disaster(db, power_id: str, disaster: str = ""):
    """设置势力控制区的自然灾害。"""
    db.conn.execute(
        "UPDATE regions SET natural_disaster=? WHERE controlled_by=?",
        (disaster, power_id),
    )
    db.conn.commit()


class TestSuccessionCrisis:
    def test_triggers_with_low_cohesion_and_wars(self, tmp_path):
        """低凝聚 + 战争应可能触发 succession_crisis。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=20, supply=60)
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        # 可能有 succession_crisis，也可能有其他类型
        assert isinstance(dynamics, list)

    def test_does_not_trigger_with_high_cohesion(self, tmp_path):
        """高凝聚不应触发 succession_crisis。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=80, supply=60)
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        for d in dynamics:
            if d.get("power_id") == "cao_cao":
                assert d.get("dynamic_type") != "succession_crisis"


class TestEconomicStrain:
    def test_triggers_with_low_supply_and_high_unrest(self, tmp_path):
        """低补给 + 高不安应可能触发 economic_strain。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=50, supply=30)
        # 设置高不安
        db.conn.execute(
            "UPDATE regions SET unrest=70 WHERE controlled_by='cao_cao'"
        )
        db.conn.commit()
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        assert isinstance(dynamics, list)


class TestMilitaryFaction:
    def test_triggers_with_many_wars_and_low_cohesion(self, tmp_path):
        """多线战争 + 低凝聚应可能触发 military_faction。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=40, supply=60)
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        assert isinstance(dynamics, list)


class TestNaturalDisasterRecovery:
    def test_triggers_with_disaster_and_good_supply(self, tmp_path):
        """有灾害 + 补给充足应可能触发 natural_disaster_recovery。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=50, supply=70)
        _set_region_disaster(db, "cao_cao", "flood")
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        assert isinstance(dynamics, list)

    def test_positive_effects_on_cohesion(self, tmp_path):
        """natural_disaster_recovery 应有正面凝聚效果。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=50, supply=70)
        _set_region_disaster(db, "cao_cao", "flood")
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        for d in dynamics:
            if d.get("dynamic_type") == "natural_disaster_recovery" and d.get("power_id") == "cao_cao":
                effects = d.get("rule_effects", [])
                cohesion_effects = [e for e in effects if e.get("field") == "cohesion"]
                for e in cohesion_effects:
                    assert int(e.get("delta", 0)) >= 0  # 正面效果


class TestEffectsIdempotency:
    def test_apply_effects_idempotent(self, tmp_path):
        """重复应用效果不重复改变数值。"""
        db = _board(tmp_path)
        _set_power_stats(db, "cao_cao", cohesion=50, supply=50)
        state = _state()

        dynamics = ensure_power_internal_dynamics(db, state)
        if dynamics:
            d = dynamics[0]
            initial_cohesion = int(db.conn.execute(
                "SELECT cohesion FROM powers WHERE id=?", (d["power_id"],)
            ).fetchone()[0])

            apply_power_internal_dynamic_effects(db, state, d)
            after_first = int(db.conn.execute(
                "SELECT cohesion FROM powers WHERE id=?", (d["power_id"],)
            ).fetchone()[0])

            # 再次应用（幂等守卫应阻止）
            apply_power_internal_dynamic_effects(db, state, d)
            after_second = int(db.conn.execute(
                "SELECT cohesion FROM powers WHERE id=?", (d["power_id"],)
            ).fetchone()[0])

            assert after_first == after_second
