"""tests/test_power_ai_slots.py：外势多槽行动合同测试。

验证：
  - 预算 0/1/2 分别执行 0/1/最多 2 项行动。
  - 第二槽不会重复第一槽军队、节点、外交对象。
  - 同一势力同月不超过一次进攻/围城/宣战。
  - 读档后重复结算不产生重复槽位记录。
  - 旧记录默认 action_slot=1。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.power_ai import resolve_power_ai_turn
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
    )


def _board_with_power(*, cohesion: int, supply: int, status: str = "active") -> GameDB:
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    # 设置 cao_cao 的 cohesion 和 supply
    db.conn.execute(
        "UPDATE powers SET cohesion=?, supply=?, status=? WHERE id='cao_cao'",
        (cohesion, supply, status),
    )
    # 其他非 liu_bei 势力设为灭亡，避免干扰
    db.conn.execute(
        "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


# ---------------------------------------------------------------------------
# 预算与执行数量
# ---------------------------------------------------------------------------


def test_budget_0_executes_0_actions():
    """灭亡势力 budget=0，不执行任何行动。"""
    db = _board_with_power(cohesion=50, supply=50, status="defeated")
    try:
        results = resolve_power_ai_turn(db, _state())
        cao_actions = [r for r in results if r["power_id"] == "cao_cao"]
        assert len(cao_actions) == 0
    finally:
        db.close()


def test_budget_1_executes_1_action():
    """cohesion<75 或 supply<70 时 budget=1，最多执行 1 项行动。"""
    db = _board_with_power(cohesion=60, supply=60)
    try:
        results = resolve_power_ai_turn(db, _state())
        cao_actions = [r for r in results if r["power_id"] == "cao_cao"]
        assert len(cao_actions) <= 1
        # 如果执行了，action_slot 应为 1
        if cao_actions:
            row = db.conn.execute(
                "SELECT action_slot FROM power_ai_actions WHERE id=?",
                (cao_actions[0]["id"],),
            ).fetchone()
            assert int(row["action_slot"]) == 1
    finally:
        db.close()


def test_budget_2_executes_up_to_2_actions():
    """cohesion>=75 且 supply>=70 时 budget=2，最多执行 2 项行动。"""
    db = _board_with_power(cohesion=80, supply=80)
    try:
        results = resolve_power_ai_turn(db, _state())
        cao_actions = [r for r in results if r["power_id"] == "cao_cao"]
        assert len(cao_actions) <= 2
        # 如果执行了 2 项，action_slot 应分别为 1 和 2
        if len(cao_actions) == 2:
            slots = sorted(int(r.get("action_slot", 0)) for r in cao_actions)
            assert slots == [1, 2]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 第二槽去重
# ---------------------------------------------------------------------------


def test_slot_2_does_not_reuse_slot_1_army():
    """第二槽不得复用第一槽的 army_id。"""
    db = _board_with_power(cohesion=80, supply=80)
    try:
        results = resolve_power_ai_turn(db, _state())
        cao_actions = [r for r in results if r["power_id"] == "cao_cao"]
        if len(cao_actions) < 2:
            pytest.skip("budget=2 但只产生 1 项行动（候选不足）")
        # 读取两条记录的 action_json
        rows = db.conn.execute(
            "SELECT action_slot, action_json FROM power_ai_actions "
            "WHERE turn=1 AND power_id='cao_cao' ORDER BY action_slot"
        ).fetchall()
        assert len(rows) == 2
        act1 = json.loads(rows[0]["action_json"])
        act2 = json.loads(rows[1]["action_json"])
        army1 = act1.get("army_id")
        army2 = act2.get("army_id")
        # 如果两槽都有 army_id，则不能相同
        if army1 and army2:
            assert army1 != army2, "第二槽不得复用第一槽的 army_id"
    finally:
        db.close()


def test_slot_2_does_not_reuse_slot_1_target():
    """第二槽不得复用第一槽的 target_node 或 target_power。"""
    db = _board_with_power(cohesion=80, supply=80)
    try:
        results = resolve_power_ai_turn(db, _state())
        cao_actions = [r for r in results if r["power_id"] == "cao_cao"]
        if len(cao_actions) < 2:
            pytest.skip("budget=2 但只产生 1 项行动（候选不足）")
        rows = db.conn.execute(
            "SELECT action_slot, action_json FROM power_ai_actions "
            "WHERE turn=1 AND power_id='cao_cao' ORDER BY action_slot"
        ).fetchall()
        assert len(rows) == 2
        act1 = json.loads(rows[0]["action_json"])
        act2 = json.loads(rows[1]["action_json"])
        # target_node 去重
        node1 = act1.get("target_node")
        node2 = act2.get("target_node")
        if node1 and node2:
            assert node1 != node2, "第二槽不得复用第一槽的 target_node"
        # target_power 去重
        power1 = act1.get("target_power")
        power2 = act2.get("target_power")
        if power1 and power2:
            assert power1 != power2, "第二槽不得复用第一槽的 target_power"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 进攻上限
# ---------------------------------------------------------------------------


def test_same_power_at_most_one_attack_per_month():
    """同一势力同月不超过一次 attack/siege/declare_war。"""
    db = _board_with_power(cohesion=80, supply=80)
    try:
        results = resolve_power_ai_turn(db, _state())
        cao_actions = [r for r in results if r["power_id"] == "cao_cao"]
        # 读取所有 action_type
        rows = db.conn.execute(
            "SELECT action_type FROM power_ai_actions WHERE turn=1 AND power_id='cao_cao'"
        ).fetchall()
        offensive = [r for r in rows if r["action_type"] in {"attack", "siege", "declare_war"}]
        assert len(offensive) <= 1, "同一势力同月最多一次进攻类型行动"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 幂等性
# ---------------------------------------------------------------------------


def test_resolve_idempotent_no_duplicate_slots():
    """读档后重复结算不产生重复槽位记录。"""
    db = _board_with_power(cohesion=80, supply=80)
    try:
        first = resolve_power_ai_turn(db, _state())
        count_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM power_ai_actions WHERE turn=1 AND power_id='cao_cao'"
        ).fetchone()[0]
        second = resolve_power_ai_turn(db, _state())
        count_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM power_ai_actions WHERE turn=1 AND power_id='cao_cao'"
        ).fetchone()[0]
        # 第二次调用不应新增记录
        assert count_after_first == count_after_second
        # 第二次调用应返回空（所有槽位已填满）
        cao_second = [r for r in second if r["power_id"] == "cao_cao"]
        assert len(cao_second) == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 旧档兼容
# ---------------------------------------------------------------------------


def test_old_records_default_slot_1():
    """旧记录 action_slot 默认为 1。"""
    db = _board_with_power(cohesion=80, supply=80)
    try:
        # 手动插入一条旧格式记录（不指定 action_slot，依赖 DEFAULT 1）
        db.conn.execute(
            """INSERT INTO power_ai_actions
            (turn, year, period, power_id, action_type, action_json, score, status, result)
            VALUES (1, 208, 8, 'cao_cao', 'fortify', '{}', 0, 'executed', '{}')"""
        )
        db.conn.commit()
        row = db.conn.execute(
            "SELECT action_slot FROM power_ai_actions WHERE turn=1 AND power_id='cao_cao' LIMIT 1"
        ).fetchone()
        assert int(row["action_slot"]) == 1, "旧记录 action_slot 应默认为 1"
    finally:
        db.close()
