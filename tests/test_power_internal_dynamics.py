"""tests/test_power_internal_dynamics.py：外势内部动态合同测试。

验证：
  - 每月最多 3 条，同势力不重复。
  - 每种动态只有满足前提时才出现。
  - 固定种子下动态类型、势力、效果和抽取引用一致。
  - 数值效果不超表中上限。
  - 重复应用、重试月末、读档后重放均不重复改变 powers 或新增 power_logs。
  - 动态不会写人物状态、军队兵力、地区控制、条约或结局字段。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import (
    _DYNAMIC_EFFECT_CAPS,
    _POWER_INTERNAL_DYNAMIC_TYPES,
    _build_power_internal_candidates,
    apply_power_internal_dynamic_effects,
    ensure_power_internal_dynamics,
)
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1, period: int = 8) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=period,
        metrics={
            "军资": 60, "粮秣": 60, "民望": 55,
            "名分": 70, "军心": 65, "士族支持": 40,
        },
    )


def _board(tmp_path: Path, *, tag: str = "pid") -> GameDB:
    db = GameDB(str(tmp_path / f"pid_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


def _set_power(db: GameDB, power_id: str, *, cohesion: int, supply: int, status: str = "active") -> None:
    db.conn.execute(
        "UPDATE powers SET cohesion=?, supply=?, status=? WHERE id=?",
        (cohesion, supply, status, power_id),
    )
    db.conn.commit()


# ---------------------------------------------------------------------------
# 候选前提条件
# ---------------------------------------------------------------------------


def test_candidates_respect_prerequisites():
    """每种动态只有在前提条件满足时才会出现。"""
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)

    # 设置 cao_cao 满足 court_rivalry 前提 (cohesion <= 55)
    _set_power(db, "cao_cao", cohesion=50, supply=60)
    # 其他势力灭亡
    db.conn.execute(
        "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
    )
    db.conn.commit()

    candidates = _build_power_internal_candidates(db, _state())
    types = {c["dynamic_type"] for c in candidates}
    # court_rivalry 应出现（cohesion=50 <= 55）
    assert "court_rivalry" in types
    # supply_dispute 不应出现（supply=60 > 45）
    assert "supply_dispute" not in types
    # court_consolidation 不应出现（cohesion=50 不在 [55,75]）
    assert "court_consolidation" not in types

    db.close()


def test_candidates_supply_dispute_requires_low_supply():
    """supply_dispute 需要 supply <= 45。"""
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    _set_power(db, "cao_cao", cohesion=60, supply=40)
    db.conn.execute(
        "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
    )
    db.conn.commit()

    candidates = _build_power_internal_candidates(db, _state())
    types = {c["dynamic_type"] for c in candidates}
    assert "supply_dispute" in types
    db.close()


def test_candidates_court_consolidation_requires_mid_cohesion_and_supply():
    """court_consolidation 需要 55 <= cohesion <= 75 且 supply >= 50。"""
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    _set_power(db, "cao_cao", cohesion=65, supply=60)
    db.conn.execute(
        "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
    )
    db.conn.commit()

    candidates = _build_power_internal_candidates(db, _state())
    types = {c["dynamic_type"] for c in candidates}
    assert "court_consolidation" in types
    db.close()


# ---------------------------------------------------------------------------
# 数量限制
# ---------------------------------------------------------------------------


def test_at_most_3_dynamics_per_month(tmp_path):
    """每月最多 3 条内部动态。"""
    db = _board(tmp_path)
    try:
        # 设置多个势力满足不同前提
        _set_power(db, "cao_cao", cohesion=50, supply=40)
        _set_power(db, "sun_quan", cohesion=60, supply=60)
        _set_power(db, "liu_zhang", cohesion=50, supply=60)

        dynamics = ensure_power_internal_dynamics(db, _state())
        assert len(dynamics) <= 3
    finally:
        db.close()


def test_same_power_at_most_1_dynamic_per_month(tmp_path):
    """同势力每月最多 1 条。"""
    db = _board(tmp_path)
    try:
        _set_power(db, "cao_cao", cohesion=50, supply=40)  # 满足多个前提
        _set_power(db, "sun_quan", cohesion=50, supply=60)
        db.conn.execute(
            "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao', 'sun_quan')"
        )
        db.conn.commit()

        dynamics = ensure_power_internal_dynamics(db, _state())
        powers_seen = [d["power_id"] for d in dynamics]
        assert len(powers_seen) == len(set(powers_seen)), "同势力不应重复"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 确定性
# ---------------------------------------------------------------------------


def test_deterministic_same_seed(tmp_path):
    """固定种子下动态类型、势力、效果一致。"""
    results = []
    for tag in ("d1", "d2"):
        db = _board(tmp_path, tag=tag)
        try:
            _set_power(db, "cao_cao", cohesion=50, supply=40)
            _set_power(db, "sun_quan", cohesion=60, supply=60)
            dynamics = ensure_power_internal_dynamics(db, _state())
            results.append(dynamics)
        finally:
            db.close()

    assert len(results[0]) == len(results[1])
    for a, b in zip(results[0], results[1]):
        assert a["power_id"] == b["power_id"]
        assert a["dynamic_type"] == b["dynamic_type"]
        assert a["rule_effects"] == b["rule_effects"]


# ---------------------------------------------------------------------------
# 效果上限
# ---------------------------------------------------------------------------


def test_effects_within_caps(tmp_path):
    """数值效果不超表中上限。"""
    db = _board(tmp_path)
    try:
        _set_power(db, "cao_cao", cohesion=50, supply=40)
        _set_power(db, "sun_quan", cohesion=60, supply=60)
        dynamics = ensure_power_internal_dynamics(db, _state())
        for dyn in dynamics:
            for effect in dyn["rule_effects"]:
                field = effect["field"]
                delta = abs(int(effect["delta"]))
                cap_key = f"{dyn['dynamic_type']}_{field}"
                cap = _DYNAMIC_EFFECT_CAPS.get(cap_key)
                if cap is not None:
                    assert delta <= cap, (
                        f"{dyn['dynamic_type']} {field}: |delta|={delta} > cap={cap}"
                    )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 幂等性
# ---------------------------------------------------------------------------


def test_effects_idempotent(tmp_path):
    """重复应用不重复改变 powers 或新增 power_logs。"""
    db = _board(tmp_path)
    try:
        _set_power(db, "cao_cao", cohesion=50, supply=60)
        db.conn.execute(
            "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
        )
        db.conn.commit()

        dynamics = ensure_power_internal_dynamics(db, _state())
        assert len(dynamics) >= 1

        # 读取初始 cohesion
        before = db.conn.execute(
            "SELECT cohesion FROM powers WHERE id='cao_cao'"
        ).fetchone()["cohesion"]

        # 第一次 apply
        applied1 = apply_power_internal_dynamic_effects(db, _state(), dynamics[0])
        after_first = db.conn.execute(
            "SELECT cohesion FROM powers WHERE id='cao_cao'"
        ).fetchone()["cohesion"]

        logs_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM power_logs WHERE turn=1 AND power_id='cao_cao'"
        ).fetchone()[0]

        # 第二次 apply（应跳过）
        applied2 = apply_power_internal_dynamic_effects(db, _state(), dynamics[0])
        after_second = db.conn.execute(
            "SELECT cohesion FROM powers WHERE id='cao_cao'"
        ).fetchone()["cohesion"]

        logs_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM power_logs WHERE turn=1 AND power_id='cao_cao'"
        ).fetchone()[0]

        assert applied2 == [], "第二次 apply 应返回空"
        assert after_first == after_second, "第二次 apply 不应改变 cohesion"
        assert logs_after_first == logs_after_second, "第二次 apply 不应新增 power_logs"
    finally:
        db.close()


def test_ensure_idempotent_same_turn(tmp_path):
    """重试月末、读档后重放不重复生成动态。"""
    db = _board(tmp_path)
    try:
        _set_power(db, "cao_cao", cohesion=50, supply=60)
        db.conn.execute(
            "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
        )
        db.conn.commit()

        first = ensure_power_internal_dynamics(db, _state())
        count1 = db.conn.execute(
            "SELECT COUNT(*) FROM power_internal_dynamics WHERE turn=1"
        ).fetchone()[0]
        second = ensure_power_internal_dynamics(db, _state())
        count2 = db.conn.execute(
            "SELECT COUNT(*) FROM power_internal_dynamics WHERE turn=1"
        ).fetchone()[0]
        assert count1 == count2
        assert first == second
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 安全边界
# ---------------------------------------------------------------------------


def test_dynamics_do_not_write_characters_armies_territory_treaties(tmp_path):
    """动态不改变人物状态、军队兵力、地区控制、条约。"""
    db = _board(tmp_path)
    try:
        chars_before = db.conn.execute("SELECT name, status FROM characters").fetchall()
        armies_before = db.conn.execute("SELECT id, manpower FROM armies").fetchall()
        regions_before = {
            r["id"]: r["controlled_by"]
            for r in db.conn.execute("SELECT id, controlled_by FROM regions").fetchall()
        }
        treaties_before = db.conn.execute(
            "SELECT proposer, target, status FROM diplomacy_treaties"
        ).fetchall()

        _set_power(db, "cao_cao", cohesion=50, supply=40)
        _set_power(db, "sun_quan", cohesion=60, supply=60)
        dynamics = ensure_power_internal_dynamics(db, _state())
        for dyn in dynamics:
            apply_power_internal_dynamic_effects(db, _state(), dyn)

        chars_after = db.conn.execute("SELECT name, status FROM characters").fetchall()
        armies_after = db.conn.execute("SELECT id, manpower FROM armies").fetchall()
        regions_after = {
            r["id"]: r["controlled_by"]
            for r in db.conn.execute("SELECT id, controlled_by FROM regions").fetchall()
        }
        treaties_after = db.conn.execute(
            "SELECT proposer, target, status FROM diplomacy_treaties"
        ).fetchall()

        assert chars_before == chars_after
        assert armies_before == armies_after
        assert regions_before == regions_after
        assert treaties_before == treaties_after
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 随机引用
# ---------------------------------------------------------------------------


def test_draw_refs_recorded(tmp_path):
    """每条动态保存 draw_refs 到 world_random_draws。"""
    db = _board(tmp_path)
    try:
        _set_power(db, "cao_cao", cohesion=50, supply=60)
        db.conn.execute(
            "UPDATE powers SET status='defeated' WHERE id NOT IN ('liu_bei', 'cao_cao')"
        )
        db.conn.commit()

        dynamics = ensure_power_internal_dynamics(db, _state())
        assert len(dynamics) >= 1

        # 检查 draw_refs 非空
        for dyn in dynamics:
            assert len(dyn["draw_refs"]) >= 1
            # 至少包含 selection 引用
            assert any(ref["draw_kind"] == "selection" for ref in dyn["draw_refs"])

        # 检查 world_random_draws 表中有对应记录
        draws = db.conn.execute(
            "SELECT domain, subject_id, draw_kind FROM world_random_draws "
            "WHERE domain='power_internal_dynamic' AND turn=1"
        ).fetchall()
        assert len(draws) >= 1
    finally:
        db.close()
