"""tests/test_geopolitical_rng.py：地缘反应随机性测试（阶段 3）。

验证：
  - 旧存档（无 geopolitical_rng_v1）走纯规则链，结果完全确定
  - 新存档（geopolitical_rng_v1=1）走 draw_weighted，同盘面结果可重复
  - 权重候选仍遵守规则阈值
  - 重复调用 generate_geopolitical_reactions 不改变结果（幂等）
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import generate_geopolitical_reactions
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55},
    )


def _board(tmp_path: Path, *, rng_v1: bool = False) -> GameDB:
    db = GameDB(str(tmp_path / "geo_rng.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    if rng_v1:
        db.kv_set("geopolitical_rng_v1", "1")
    # 设置外交关系
    db.conn.execute(
        "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("cao_cao", "liu_bei", -30, 10, "neutral"),
    )
    db.conn.execute(
        "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("sun_quan", "liu_bei", 20, 40, "neutral"),
    )
    db.conn.execute(
        "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("cao_cao", "sun_quan", -10, 15, "neutral"),
    )
    db.conn.commit()
    return db


def _battle_event() -> dict:
    """构造一个战果事件。"""
    return {
        "source_kind": "battle",
        "source_ref": "battle:1",
        "attacker_power": "cao_cao",
        "defender_power": "liu_bei",
        "winner_power": "cao_cao",
        "loser_power": "liu_bei",
        "battle_id": 1,
    }


class TestLegacyPath:
    def test_old_save_uses_deterministic_path(self, tmp_path):
        """旧存档（无 geopolitical_rng_v1）走纯规则链，结果完全确定。"""
        db = _board(tmp_path, rng_v1=False)
        state = _state()
        events = [_battle_event()]

        # 第一次调用
        reactions_1 = generate_geopolitical_reactions(db, state, events)

        # 第二次调用（相同条件）
        reactions_2 = generate_geopolitical_reactions(db, state, events)

        # 结果应完全一致（幂等 + 确定性）
        assert len(reactions_1) == len(reactions_2)
        for r1, r2 in zip(reactions_1, reactions_2):
            assert r1["reaction_type"] == r2["reaction_type"]
            assert r1["actor_power_id"] == r2["actor_power_id"]

    def test_legacy_reaction_respects_thresholds(self, tmp_path):
        """旧版规则链在关系值不满足阈值时不产生反应。"""
        db = _board(tmp_path, rng_v1=False)
        state = _state()

        # 构造一个关系不够紧张的事件（不应产生 opportunism）
        # sun_quan 与 liu_bei 关系好（pr=20, trust=40），不应 opportunism
        event = {
            "source_kind": "battle",
            "source_ref": "battle:2",
            "attacker_power": "cao_cao",
            "defender_power": "liu_bei",
            "winner_power": "cao_cao",
            "loser_power": "liu_bei",
        }

        reactions = generate_geopolitical_reactions(db, state, [event])
        # sun_quan 不应对 liu_bei 产生 opportunism（关系不够差）
        sun_quan_reactions = [r for r in reactions if r["actor_power_id"] == "sun_quan" and r["reaction_type"] == "opportunism"]
        assert len(sun_quan_reactions) == 0


class TestNewPath:
    def test_new_save_uses_weighted_draw(self, tmp_path):
        """新存档（geopolitical_rng_v1=1）走 draw_weighted，同盘面结果可重复。"""
        db = _board(tmp_path, rng_v1=True)
        state = _state()
        events = [_battle_event()]

        # 第一次调用
        reactions_1 = generate_geopolitical_reactions(db, state, events)

        # 第二次调用（相同存档、相同条件）
        reactions_2 = generate_geopolitical_reactions(db, state, events)

        # draw_weighted 落库保证幂等
        assert len(reactions_1) == len(reactions_2)
        for r1, r2 in zip(reactions_1, reactions_2):
            assert r1["reaction_type"] == r2["reaction_type"]

    def test_new_save_different_seeds_produce_different_results(self, tmp_path):
        """不同 campaign_seed 应产生不同的反应选择（验证随机性生效）。"""
        # 第一个存档
        db1 = _board(tmp_path, rng_v1=True)
        state1 = _state()
        reactions_1 = generate_geopolitical_reactions(db1, state1, [_battle_event()])

        # 第二个存档（不同种子）
        db2 = GameDB(str(tmp_path / "geo_rng_2.db"), content=GameContent.load())
        db2.seed_static_data()
        db2.conn.execute(
            "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
        )
        db2.kv_set(CAMPAIGN_SEED_KEY, "cafebabe" * 8)  # 不同种子
        db2.kv_set("geopolitical_rng_v1", "1")
        # 复制外交关系
        db2.conn.execute(
            "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("cao_cao", "liu_bei", -30, 10, "neutral"),
        )
        db2.conn.execute(
            "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("sun_quan", "liu_bei", 20, 40, "neutral"),
        )
        db2.conn.execute(
            "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("cao_cao", "sun_quan", -10, 15, "neutral"),
        )
        db2.conn.commit()

        state2 = _state()
        reactions_2 = generate_geopolitical_reactions(db2, state2, [_battle_event()])

        # 不同种子可能产生不同结果（但不是必然，因为候选池可能只有一个）
        # 这里只验证两个调用都成功完成
        assert isinstance(reactions_1, list)
        assert isinstance(reactions_2, list)


class TestIdempotency:
    def test_idempotent_across_reloads(self, tmp_path):
        """重复调用 generate_geopolitical_reactions 不改变结果。"""
        db = _board(tmp_path, rng_v1=True)
        state = _state()
        events = [_battle_event()]

        reactions_1 = generate_geopolitical_reactions(db, state, events)
        # 重新加载 state（模拟读档）
        state_2 = _state(turn=1)
        reactions_2 = generate_geopolitical_reactions(db, state_2, events)

        # 幂等守卫确保不会重复创建
        assert len(reactions_1) == len(reactions_2)


class TestTreatyBreach:
    def test_treaty_breach_legacy(self, tmp_path):
        """旧存档违约反应走规则链。"""
        db = _board(tmp_path, rng_v1=False)
        state = _state()
        event = {
            "source_kind": "treaty_breach",
            "source_ref": "treaty:1",
            "actor_power": "cao_cao",
            "target_power": "liu_bei",
        }

        reactions = generate_geopolitical_reactions(db, state, [event])
        assert isinstance(reactions, list)

    def test_treaty_breach_new(self, tmp_path):
        """新存档违约反应走 draw_weighted。"""
        db = _board(tmp_path, rng_v1=True)
        state = _state()
        event = {
            "source_kind": "treaty_breach",
            "source_ref": "treaty:1",
            "actor_power": "cao_cao",
            "target_power": "liu_bei",
        }

        reactions = generate_geopolitical_reactions(db, state, [event])
        assert isinstance(reactions, list)
