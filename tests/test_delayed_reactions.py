"""tests/test_delayed_reactions.py：延迟反应机制测试（阶段 5）。

验证：
  - 创建延迟反应
  - 到期执行
  - 条件不满足时取消
  - 幂等性
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import (
    generate_geopolitical_reactions,
    resolve_delayed_reactions,
)
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55},
    )


def _board(tmp_path: Path, *, enable_delayed: bool = False) -> GameDB:
    db = GameDB(str(tmp_path / "delayed.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    if enable_delayed:
        db.kv_set("ws_enable_delayed_reactions", "1")
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
    return {
        "source_kind": "battle",
        "source_ref": "battle:1",
        "attacker_power": "cao_cao",
        "defender_power": "liu_bei",
        "winner_power": "cao_cao",
        "loser_power": "liu_bei",
        "battle_id": 1,
    }


class TestDelayedReactionsDisabled:
    def test_no_delayed_when_disabled(self, tmp_path):
        """未启用延迟反应时，不创建延迟记录。"""
        db = _board(tmp_path, enable_delayed=False)
        state = _state()

        # 生成反应
        reactions = generate_geopolitical_reactions(db, state, [_battle_event()])

        # 检查没有延迟记录
        count = db.conn.execute(
            "SELECT COUNT(*) FROM delayed_geopolitical_reactions"
        ).fetchone()[0]
        assert count == 0


class TestDelayedReactionsEnabled:
    def test_resolve_empty_when_no_pending(self, tmp_path):
        """没有待执行的延迟反应时，resolve 返回空列表。"""
        db = _board(tmp_path, enable_delayed=True)
        state = _state()

        fired = resolve_delayed_reactions(db, state)
        assert fired == []

    def test_resolve_executes_due_reactions(self, tmp_path):
        """到期的延迟反应应被执行。"""
        db = _board(tmp_path, enable_delayed=True)

        # 手动插入一条延迟反应（trigger_turn=1, fire_turn=3）
        db.conn.execute(
            """INSERT INTO delayed_geopolitical_reactions
            (trigger_turn, fire_turn, actor_power_id, source_ref,
             reaction_type, target_power_id, severity, condition_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, 3, "sun_quan", "battle:1", "caution", "cao_cao", 2, "{}", "pending"),
        )
        db.conn.commit()

        # turn=1 不应执行
        state_1 = _state(turn=1)
        fired_1 = resolve_delayed_reactions(db, state_1)
        assert fired_1 == []

        # turn=3 应执行
        state_3 = _state(turn=3)
        fired_3 = resolve_delayed_reactions(db, state_3)
        assert len(fired_3) == 1
        assert fired_3[0]["reaction_type"] == "caution"

    def test_resolve_cancels_when_condition_not_met(self, tmp_path):
        """条件不满足时，延迟反应应被取消。"""
        db = _board(tmp_path, enable_delayed=True)

        # 插入一条需要非战争条件的延迟反应
        import json
        condition = json.dumps({"requires_non_war": True})
        db.conn.execute(
            """INSERT INTO delayed_geopolitical_reactions
            (trigger_turn, fire_turn, actor_power_id, source_ref,
             reaction_type, target_power_id, severity, condition_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, 3, "sun_quan", "battle:1", "balancing", "cao_cao", 2, condition, "pending"),
        )
        db.conn.commit()

        # 设置 sun_quan 与 cao_cao 为战争状态
        db.conn.execute(
            "UPDATE diplomatic_relations SET status='war' WHERE power_a='cao_cao' AND power_b='sun_quan'"
        )
        db.conn.commit()

        # turn=3 应取消（战争状态不满足 requires_non_war）
        state_3 = _state(turn=3)
        fired_3 = resolve_delayed_reactions(db, state_3)
        assert fired_3 == []

        # 检查状态为 cancelled
        status = db.conn.execute(
            "SELECT status FROM delayed_geopolitical_reactions WHERE fire_turn=3"
        ).fetchone()[0]
        assert status == "cancelled"


class TestIdempotency:
    def test_resolve_idempotent(self, tmp_path):
        """重复调用 resolve 不重复执行。"""
        db = _board(tmp_path, enable_delayed=True)

        db.conn.execute(
            """INSERT INTO delayed_geopolitical_reactions
            (trigger_turn, fire_turn, actor_power_id, source_ref,
             reaction_type, target_power_id, severity, condition_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, 3, "sun_quan", "battle:1", "caution", "cao_cao", 2, "{}", "pending"),
        )
        db.conn.commit()

        state = _state(turn=3)

        # 第一次执行
        fired_1 = resolve_delayed_reactions(db, state)
        assert len(fired_1) == 1

        # 第二次执行（应返回空，因为已执行）
        fired_2 = resolve_delayed_reactions(db, state)
        assert fired_2 == []
