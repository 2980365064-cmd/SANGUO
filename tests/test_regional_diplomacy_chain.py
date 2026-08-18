"""tests/test_regional_diplomacy_chain.py：区域/外交/战争连锁合同测试（第四期）。

验证：
  - 重大事件在邻国生成 border_observer 情报
  - 普通事件无使者时不生成情报
  - 普通事件有使者时生成 envoy 情报
  - 同一事件不重复生成情报（幂等）
  - 重大灾害触发 public_relation +3
  - 战乱期间动乱降低 cohesion
  - 刘备控制区的事件不触发连锁
  - 战争状态每月 public_relation -2, trust -1
  - 同一对关系每月只漂移一次
  - 连锁不改变领土控制
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
    build_incident_intelligence_reports,
    generate_incident_diplomatic_reactions,
)
from ming_sim.diplomacy import apply_war_diplomatic_drift
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={
            "军资": 60, "粮秣": 60, "民望": 55,
            "名分": 70, "军心": 65, "士族支持": 40,
        },
    )


def _board(tmp_path: Path, *, tag: str = "chain") -> GameDB:
    db = GameDB(str(tmp_path / f"chain_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


def _make_liu_bei_neighbor_of_changan(db: GameDB) -> None:
    """让刘备控制一个与长安相邻的城池（潼关），使长安事件可被刘备观测。"""
    db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='tongguan'")
    db.conn.execute(
        "UPDATE administrative_cities SET controlled_by='liu_bei' WHERE commandery_id='tongguan'"
    )
    db.conn.commit()


def _insert_incident(
    db: GameDB, *, turn: int = 1, region_id: str, incident_type: str,
    tier: str = "ordinary",
) -> dict:
    """插入一条区域事件并返回其 dict。"""
    cursor = db.conn.execute(
        """INSERT INTO regional_incidents
        (turn, region_id, incident_type, tier, title, summary,
         visibility, risk_snapshot_json, draw_refs_json, local_effects_json, status)
        VALUES (?, ?, ?, ?, ?, ?, 'own', '{}', '[]', '[]', 'resolved_local')""",
        (turn, region_id, incident_type, tier,
         f"{incident_type} in {region_id}", f"测试事件：{incident_type}"),
    )
    db.conn.commit()
    return {
        "id": int(cursor.lastrowid),
        "turn": turn, "region_id": region_id,
        "incident_type": incident_type, "tier": tier,
        "title": f"{incident_type} in {region_id}",
        "summary": f"测试事件：{incident_type}",
    }


# ---------------------------------------------------------------------------
# 区域事件 → 情报报告
# ---------------------------------------------------------------------------


def test_dramatic_incident_generates_border_intel(tmp_path):
    """重大事件在邻国生成 border_observer 情报。"""
    db = _board(tmp_path)
    try:
        # 让刘备控制潼关（与长安相邻），在长安（cao_cao 控制）生成重大旱灾
        _make_liu_bei_neighbor_of_changan(db)
        inc = _insert_incident(db, region_id="changan", incident_type="drought", tier="dramatic")
        reports = build_incident_intelligence_reports(db, _state(), [inc])
        assert len(reports) >= 1
        r = reports[0]
        assert r["power_id"] == "cao_cao"
        assert r["source_type"] == "border_observer"
        assert r["visibility"] == "assessment"
        assert r["reliability"] == 65
    finally:
        db.close()


def test_ordinary_incident_no_intel_without_envoy(tmp_path):
    """普通事件无使者时不生成情报。"""
    db = _board(tmp_path)
    try:
        # 长安是 cao_cao 控制，与刘备不相邻（无使者），不生成情报
        inc = _insert_incident(db, region_id="changan", incident_type="bandit_surge", tier="ordinary")
        reports = build_incident_intelligence_reports(db, _state(), [inc])
        assert len(reports) == 0
    finally:
        db.close()


def test_ordinary_incident_with_envoy_generates_intel(tmp_path):
    """普通事件有使者时生成 envoy 情报。"""
    db = _board(tmp_path)
    try:
        # 为刘备对 cao_cao 创建一个活跃使者
        db.conn.execute(
            """INSERT INTO envoy_missions (turn, year, period, target_power, envoy, goal, status)
            VALUES (1, 208, 8, 'cao_cao', '诸葛亮', '试探', 'active')"""
        )
        db.conn.commit()
        inc = _insert_incident(db, region_id="changan", incident_type="bandit_surge", tier="ordinary")
        reports = build_incident_intelligence_reports(db, _state(), [inc])
        assert len(reports) >= 1
        r = reports[0]
        assert r["power_id"] == "cao_cao"
        assert r["source_type"] == "envoy"
        assert r["visibility"] == "assessment"
    finally:
        db.close()


def test_incident_intel_idempotent(tmp_path):
    """同一事件不重复生成情报。"""
    db = _board(tmp_path)
    try:
        _make_liu_bei_neighbor_of_changan(db)
        inc = _insert_incident(db, region_id="changan", incident_type="drought", tier="dramatic")
        first = build_incident_intelligence_reports(db, _state(), [inc])
        assert len(first) >= 1
        # 第二次调用应该返回空（已记录）
        second = build_incident_intelligence_reports(db, _state(), [inc])
        assert len(second) == 0
    finally:
        db.close()


def test_no_chain_reaction_from_own_incidents(tmp_path):
    """刘备控制区的事件不触发连锁。"""
    db = _board(tmp_path)
    try:
        # 让刘备控制潼关，在潼关生成事件
        db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='tongguan'")
        db.conn.execute(
            "UPDATE administrative_cities SET controlled_by='liu_bei' WHERE commandery_id='tongguan'"
        )
        db.conn.commit()
        inc = _insert_incident(db, region_id="tongguan", incident_type="flood", tier="dramatic")
        reports = build_incident_intelligence_reports(db, _state(), [inc])
        assert len(reports) == 0
        reactions = generate_incident_diplomatic_reactions(db, _state(), [inc])
        assert len(reactions) == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 区域事件 → 外交反应
# ---------------------------------------------------------------------------


def test_dramatic_incident_triggers_diplomacy_pressure(tmp_path):
    """重大灾害触发 public_relation +3。"""
    db = _board(tmp_path)
    try:
        _make_liu_bei_neighbor_of_changan(db)
        # 读取 cao_cao 与 liu_bei 的当前 public_relation
        rel = db.conn.execute(
            "SELECT public_relation FROM diplomatic_relations "
            "WHERE (power_a='cao_cao' AND power_b='liu_bei') OR (power_a='liu_bei' AND power_b='cao_cao')"
        ).fetchone()
        old_pr = int(rel["public_relation"]) if rel else 0

        inc = _insert_incident(db, region_id="changan", incident_type="drought", tier="dramatic")
        reactions = generate_incident_diplomatic_reactions(db, _state(), [inc])

        # 检查反应
        assert len(reactions) >= 1
        assert reactions[0]["reaction_kind"] == "diplomacy_pressure"

        # 检查 public_relation 变化（+3）
        rel_after = db.conn.execute(
            "SELECT public_relation FROM diplomatic_relations "
            "WHERE (power_a='cao_cao' AND power_b='liu_bei') OR (power_a='liu_bei' AND power_b='cao_cao')"
        ).fetchone()
        new_pr = int(rel_after["public_relation"]) if rel_after else 0
        assert new_pr == old_pr + 3
    finally:
        db.close()


def test_bandit_surge_during_war_reduces_cohesion(tmp_path):
    """战乱期间动乱降低 cohesion。"""
    db = _board(tmp_path)
    try:
        _make_liu_bei_neighbor_of_changan(db)
        # 读取 cao_cao 的 cohesion
        power = db.conn.execute(
            "SELECT cohesion FROM powers WHERE id='cao_cao'"
        ).fetchone()
        old_coh = int(power["cohesion"])

        # bandit_surge 在战争期间触发 opportunistic_posture
        inc = _insert_incident(db, region_id="changan", incident_type="bandit_surge", tier="dramatic")
        reactions = generate_incident_diplomatic_reactions(db, _state(), [inc])

        assert len(reactions) >= 1
        assert reactions[0]["reaction_kind"] == "opportunistic_posture"

        # cohesion 应下降 2
        power_after = db.conn.execute(
            "SELECT cohesion FROM powers WHERE id='cao_cao'"
        ).fetchone()
        new_coh = int(power_after["cohesion"])
        assert new_coh == old_coh - 2
    finally:
        db.close()


def test_no_controlled_by_change_from_chain(tmp_path):
    """连锁不改变领土控制。"""
    db = _board(tmp_path)
    try:
        _make_liu_bei_neighbor_of_changan(db)
        # 记录初始 controlled_by
        before = db.conn.execute(
            "SELECT controlled_by FROM regions WHERE id='changan'"
        ).fetchone()["controlled_by"]

        inc = _insert_incident(db, region_id="changan", incident_type="drought", tier="dramatic")
        build_incident_intelligence_reports(db, _state(), [inc])
        generate_incident_diplomatic_reactions(db, _state(), [inc])

        after = db.conn.execute(
            "SELECT controlled_by FROM regions WHERE id='changan'"
        ).fetchone()["controlled_by"]
        assert before == after
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 战争 → 外交漂移
# ---------------------------------------------------------------------------


def test_war_drift_reduces_public_relation(tmp_path):
    """战争状态每月 public_relation -2, trust -1。"""
    db = _board(tmp_path)
    try:
        # cao_cao 与 liu_bei 已处于战争状态
        rel = db.conn.execute(
            "SELECT public_relation, trust FROM diplomatic_relations "
            "WHERE (power_a='cao_cao' AND power_b='liu_bei') OR (power_a='liu_bei' AND power_b='cao_cao')"
        ).fetchone()
        old_pr = int(rel["public_relation"])
        old_trust = int(rel["trust"])

        drifts = apply_war_diplomatic_drift(db, _state())

        assert len(drifts) >= 1
        # public_relation 应下降 2
        rel_after = db.conn.execute(
            "SELECT public_relation, trust FROM diplomatic_relations "
            "WHERE (power_a='cao_cao' AND power_b='liu_bei') OR (power_a='liu_bei' AND power_b='cao_cao')"
        ).fetchone()
        new_pr = int(rel_after["public_relation"])
        new_trust = int(rel_after["trust"])
        assert new_pr == old_pr - 2
        assert new_trust == max(0, old_trust - 1)
    finally:
        db.close()


def test_war_drift_idempotent(tmp_path):
    """同一对关系每月只漂移一次。"""
    db = _board(tmp_path)
    try:
        first = apply_war_diplomatic_drift(db, _state())
        assert len(first) >= 1

        rel_after_first = db.conn.execute(
            "SELECT public_relation FROM diplomatic_relations "
            "WHERE (power_a='cao_cao' AND power_b='liu_bei') OR (power_a='liu_bei' AND power_b='cao_cao')"
        ).fetchone()["public_relation"]

        # 第二次调用应该返回空（已漂移）
        second = apply_war_diplomatic_drift(db, _state())
        assert len(second) == 0

        rel_after_second = db.conn.execute(
            "SELECT public_relation FROM diplomatic_relations "
            "WHERE (power_a='cao_cao' AND power_b='liu_bei') OR (power_a='liu_bei' AND power_b='cao_cao')"
        ).fetchone()["public_relation"]
        assert rel_after_first == rel_after_second
    finally:
        db.close()


def test_chain_depth_limited_to_one(tmp_path):
    """连锁不会进一步触发其他事件（深度=1）。"""
    db = _board(tmp_path)
    try:
        _make_liu_bei_neighbor_of_changan(db)
        inc = _insert_incident(db, region_id="changan", incident_type="drought", tier="dramatic")

        # 生成情报和反应
        build_incident_intelligence_reports(db, _state(), [inc])
        generate_incident_diplomatic_reactions(db, _state(), [inc])

        # 检查没有新的 regional_incidents 被创建
        inc_count = db.conn.execute(
            "SELECT COUNT(*) FROM regional_incidents WHERE turn=1"
        ).fetchone()[0]
        # 只有我们手动插入的那一条
        assert inc_count == 1
    finally:
        db.close()
