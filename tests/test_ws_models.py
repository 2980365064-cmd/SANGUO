"""tests/test_ws_models.py：dataclass 领域模型测试（阶段 C）。

验证：
  - WorldContext / BattleEnvironment / ReactionCandidate 构造
  - as_dict() 兼容性
  - frozen=True 不可变性
"""
from __future__ import annotations

import pytest

from ming_sim.ws_models import WorldContext, BattleEnvironment, ReactionCandidate


class TestWorldContext:
    def test_basic_construction(self):
        ctx = WorldContext(turn=1, seed="abc", season="春")
        assert ctx.turn == 1
        assert ctx.seed == "abc"
        assert ctx.season == "春"
        assert ctx.weather == {}

    def test_default_fields(self):
        ctx = WorldContext(turn=1, seed="abc", season="夏")
        assert ctx.regional_conditions == {}
        assert ctx.public_mood == {}
        assert ctx.power_budgets == {}

    def test_as_dict_compatible(self):
        ctx = WorldContext(turn=1, seed="abc", season="秋",
                           weather={"kind": "晴"}, power_budgets={"cao_cao": 2})
        d = ctx.as_dict()
        assert isinstance(d, dict)
        assert d["turn"] == 1
        assert d["weather"] == {"kind": "晴"}
        assert d["power_budgets"]["cao_cao"] == 2

    def test_frozen_immutability(self):
        ctx = WorldContext(turn=1, seed="abc", season="冬")
        with pytest.raises(AttributeError):
            ctx.turn = 2  # type: ignore[misc]


class TestBattleEnvironment:
    def test_basic_construction(self):
        env = BattleEnvironment(seed="abc", season="春")
        assert env.seed == "abc"
        assert env.probability_delta == 0
        assert env.battlefield == {}

    def test_as_dict_compatible(self):
        env = BattleEnvironment(
            seed="abc", season="夏",
            weather={"kind": "暴雨"},
            probability_delta=-3,
            regional_state_refs=["region:luoyang:turn:1"],
        )
        d = env.as_dict()
        assert d["probability_delta"] == -3
        assert d["regional_state_refs"] == ["region:luoyang:turn:1"]


class TestReactionCandidate:
    def test_basic_construction(self):
        c = ReactionCandidate(key="opportunism", weight=60.0)
        assert c.key == "opportunism"
        assert c.weight == 60.0
        assert c.target == ""
        assert c.severity == 0

    def test_full_construction(self):
        c = ReactionCandidate(key="caution", weight=40.0, target="cao_cao", severity=3)
        assert c.target == "cao_cao"
        assert c.severity == 3

    def test_as_dict(self):
        c = ReactionCandidate(key="balancing", weight=50.0, target="sun_quan", severity=2)
        d = c.as_dict()
        assert d == {"key": "balancing", "weight": 50.0, "target": "sun_quan", "severity": 2}
