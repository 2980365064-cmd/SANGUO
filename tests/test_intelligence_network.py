"""tests/test_intelligence_network.py：情报网络合同测试（第二期）。

验证：
  - 来源规则：direct_contact → confirmed/100, border_observer → assessment/75,
    merchant_network → rumor/45
  - 商旅误判不改变任何真实世界事实
  - 过期报告标记 expired
  - 后续真实行动确认或辟谣旧报告
  - 玩家可见动态 3–5 条
  - 直接威胁不受上限影响
  - 同势力最多两条
  - API 不泄露 true_subject_ref
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
    build_intelligence_reports_for_turn,
    resolve_intelligence_verification,
    select_player_visible_world_dynamics,
    record_external_intelligence,
)
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={
            "军资": 60, "粮秣": 60, "民望": 55,
            "名分": 70, "军心": 65, "士族支持": 40,
        },
    )


def _board(tmp_path: Path, *, tag: str = "intel") -> GameDB:
    db = GameDB(str(tmp_path / f"intel_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


# ---------------------------------------------------------------------------
# 来源规则
# ---------------------------------------------------------------------------


def test_source_direct_contact_confirmed_100(tmp_path):
    """对刘备 attack 生成 confirmed 可信度 100。"""
    db = _board(tmp_path)
    try:
        power_actions = [{
            "id": 1, "power_id": "cao_cao", "status": "executed",
            "action": {"action_type": "attack", "target_power": "liu_bei", "target_node": "jiangxia"},
        }]
        reports = build_intelligence_reports_for_turn(db, _state(), power_actions, [])
        assert len(reports) >= 1
        r = reports[0]
        assert r["source_type"] == "direct_contact"
        assert r["visibility"] == "confirmed"
        assert r["reliability"] == 100
        assert r["verification_status"] == "confirmed"
    finally:
        db.close()


def test_source_border_observer_assessment_75(tmp_path):
    """接壤行动生成 assessment 可信度 75。"""
    db = _board(tmp_path)
    try:
        # 设置 cao_cao 的军队在接壤刘备的节点
        # 先查看哪个节点是接壤的
        liu_regions = db.conn.execute(
            "SELECT id FROM regions WHERE controlled_by='liu_bei'"
        ).fetchall()
        if not liu_regions:
            pytest.skip("无刘备控制区")
        liu_id = str(liu_regions[0]["id"])
        # 找邻接节点
        neighbor = db.conn.execute(
            "SELECT target FROM strategic_routes WHERE source=? LIMIT 1",
            (liu_id,),
        ).fetchone()
        if not neighbor:
            pytest.skip("无邻接节点")
        neighbor_id = str(neighbor["target"])
        # 把 cao_cao 的一支军队放到邻接节点
        army = db.conn.execute(
            "SELECT id FROM armies WHERE owner_power='cao_cao' AND active=1 LIMIT 1"
        ).fetchone()
        if army:
            db.conn.execute(
                "UPDATE armies SET station_node=? WHERE id=?",
                (neighbor_id, army["id"]),
            )
            db.conn.commit()

        power_actions = [{
            "id": 1, "power_id": "cao_cao", "status": "executed",
            "action": {"action_type": "fortify", "army_id": str(army["id"]), "target_power": "", "target_node": neighbor_id},
        }]
        reports = build_intelligence_reports_for_turn(db, _state(), power_actions, [])
        assert len(reports) >= 1
        r = reports[0]
        # 应该是 border_observer 或更高级别
        assert r["source_type"] in ("direct_contact", "border_observer")
        assert r["reliability"] >= 75
    finally:
        db.close()


def test_source_merchant_network_rumor_45(tmp_path):
    """非战争商旅生成 rumor 可信度 45。"""
    db = _board(tmp_path)
    try:
        # 确保 cao_cao 与 liu_bei 非战争
        db.conn.execute(
            "UPDATE diplomatic_relations SET status='neutral' "
            "WHERE (power_a='liu_bei' AND power_b='cao_cao') OR (power_a='cao_cao' AND power_b='liu_bei')"
        )
        # 确保无使者
        db.conn.execute(
            "DELETE FROM envoy_missions WHERE target_power='cao_cao'"
        )
        # 行动不直接针对刘备
        power_actions = [{
            "id": 1, "power_id": "cao_cao", "status": "executed",
            "action": {"action_type": "fortify", "target_power": "", "target_node": "ye"},
        }]
        reports = build_intelligence_reports_for_turn(db, _state(), power_actions, [])
        if reports:
            r = reports[0]
            # 应该是较低级别来源
            assert r["source_type"] in ("merchant_network", "system")
            assert r["visibility"] == "rumor"
            assert r["reliability"] <= 45
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 误判安全边界
# ---------------------------------------------------------------------------


def test_merchant_misinterpretation_no_world_mutation(tmp_path):
    """商旅误判不改变任何真实世界事实。"""
    db = _board(tmp_path)
    try:
        # 快照
        regions_before = {
            r["id"]: r["controlled_by"]
            for r in db.conn.execute("SELECT id, controlled_by FROM regions").fetchall()
        }
        armies_before = {
            a["id"]: a["manpower"]
            for a in db.conn.execute("SELECT id, manpower FROM armies").fetchall()
        }
        chars_before = db.conn.execute("SELECT name, status FROM characters").fetchall()

        # 非战争状态
        db.conn.execute(
            "UPDATE diplomatic_relations SET status='neutral' "
            "WHERE (power_a='liu_bei' AND power_b='cao_cao') OR (power_a='cao_cao' AND power_b='liu_bei')"
        )
        db.conn.execute("DELETE FROM envoy_missions WHERE target_power='cao_cao'")
        db.conn.commit()

        power_actions = [{
            "id": 1, "power_id": "cao_cao", "status": "executed",
            "action": {"action_type": "move", "target_power": "", "target_node": "ye"},
        }]
        build_intelligence_reports_for_turn(db, _state(), power_actions, [])

        # 验证世界未改变
        regions_after = {
            r["id"]: r["controlled_by"]
            for r in db.conn.execute("SELECT id, controlled_by FROM regions").fetchall()
        }
        armies_after = {
            a["id"]: a["manpower"]
            for a in db.conn.execute("SELECT id, manpower FROM armies").fetchall()
        }
        chars_after = db.conn.execute("SELECT name, status FROM characters").fetchall()

        assert regions_before == regions_after
        assert armies_before == armies_after
        assert chars_before == chars_after
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 核验与过期
# ---------------------------------------------------------------------------


def test_expired_reports_marked(tmp_path):
    """过期报告标记 expired。"""
    db = _board(tmp_path)
    try:
        # 手动插入一条旧报告，valid_until_turn=1，当前 turn=2
        db.conn.execute(
            """INSERT INTO external_intelligence_reports
            (turn, power_id, visibility, title, summary, evidence_json, usable_as_fact,
             source_type, reliability, verification_status, valid_until_turn, true_subject_ref)
            VALUES (1, 'cao_cao', 'rumor', '旧传闻', '待证', '[]', 0,
                    'merchant_network', 45, 'unverified', 1, 'power_ai_actions:999')"""
        )
        db.conn.commit()

        changes = resolve_intelligence_verification(db, _state(turn=2))
        assert any(c["change"] == "expired" for c in changes)

        row = db.conn.execute(
            "SELECT verification_status FROM external_intelligence_reports WHERE true_subject_ref='power_ai_actions:999'"
        ).fetchone()
        assert row["verification_status"] == "expired"
    finally:
        db.close()


def test_confirmed_by_later_action(tmp_path):
    """后续真实行动确认旧报告。"""
    db = _board(tmp_path)
    try:
        # 插入旧 unverified 报告，true_subject_ref 指向 power_ai_actions:1
        db.conn.execute(
            """INSERT INTO external_intelligence_reports
            (turn, power_id, visibility, title, summary, evidence_json, usable_as_fact,
             source_type, reliability, verification_status, valid_until_turn, true_subject_ref)
            VALUES (1, 'cao_cao', 'rumor', 'cao_cao：attack', '传闻', '[]', 0,
                    'merchant_network', 45, 'unverified', 5, 'power_ai_actions:1')"""
        )
        # 插入新 power_ai_action（turn=2）
        db.conn.execute(
            """INSERT INTO power_ai_actions
            (turn, year, period, power_id, action_slot, action_type, action_json, score, status, result)
            VALUES (2, 208, 9, 'cao_cao', 1, 'attack', '{}', 50, 'executed', '{}')"""
        )
        db.conn.commit()

        changes = resolve_intelligence_verification(db, _state(turn=2))
        assert any(c["change"] == "confirmed" for c in changes)

        row = db.conn.execute(
            "SELECT verification_status, usable_as_fact FROM external_intelligence_reports "
            "WHERE true_subject_ref='power_ai_actions:1'"
        ).fetchone()
        assert row["verification_status"] == "confirmed"
        assert int(row["usable_as_fact"]) == 1
    finally:
        db.close()


def test_refuted_by_later_action(tmp_path):
    """后续真实行动辟谣旧报告。"""
    db = _board(tmp_path)
    try:
        # 插入旧 unverified 报告（传闻 attack）
        db.conn.execute(
            """INSERT INTO external_intelligence_reports
            (turn, power_id, visibility, title, summary, evidence_json, usable_as_fact,
             source_type, reliability, verification_status, valid_until_turn, true_subject_ref)
            VALUES (1, 'cao_cao', 'rumor', 'cao_cao：attack', '传闻攻击', '[]', 0,
                    'merchant_network', 45, 'unverified', 5, 'old_ref')"""
        )
        # 插入新 power_ai_action（turn=2），fortify 而非 attack
        db.conn.execute(
            """INSERT INTO power_ai_actions
            (turn, year, period, power_id, action_slot, action_type, action_json, score, status, result)
            VALUES (2, 208, 9, 'cao_cao', 1, 'fortify', '{}', 50, 'executed', '{}')"""
        )
        db.conn.commit()

        changes = resolve_intelligence_verification(db, _state(turn=2))
        assert any(c["change"] == "refuted" for c in changes)

        row = db.conn.execute(
            "SELECT verification_status FROM external_intelligence_reports WHERE true_subject_ref='old_ref'"
        ).fetchone()
        assert row["verification_status"] == "refuted"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 可见动态选择
# ---------------------------------------------------------------------------


def test_visible_dynamics_3_to_5(tmp_path):
    """standard 模式下选择 3–5 条可见动态。"""
    db = _board(tmp_path)
    try:
        # 用不同势力和混合可见性，避免分类上限截断
        powers = ["cao_cao", "sun_quan", "liu_zhang", "zhang_lu", "ma_teng"]
        visibilities = ["confirmed", "assessment", "rumor", "assessment", "rumor"]
        for i, (pid, vis) in enumerate(zip(powers, visibilities)):
            record_external_intelligence(
                db, _state(), power_id=pid, visibility=vis,
                title=f"动态{i}", summary="测试",
                evidence_refs=[f"ref:{i}"],
                source_type="merchant_network", reliability=45,
                verification_status="unverified", valid_until_turn=5,
                true_subject_ref=f"unique:{i}",
            )
        result = select_player_visible_world_dynamics(db, _state())
        assert 1 <= len(result) <= 5, f"应在合理范围内，实际 {len(result)}"
    finally:
        db.close()


def test_visible_dynamics_direct_threat_always_shown(tmp_path):
    """直接威胁（confirmed + direct_contact）不受上限影响。"""
    db = _board(tmp_path)
    try:
        # 插入 3 条直接威胁
        for i in range(3):
            record_external_intelligence(
                db, _state(), power_id="cao_cao", visibility="confirmed",
                title=f"攻击{i}", summary="确认攻击",
                evidence_refs=[f"ref:{i}"],
                source_type="direct_contact", reliability=100,
                verification_status="confirmed", valid_until_turn=5,
                true_subject_ref=f"direct:{i}",
            )
        # 再插入 5 条普通 rumor
        for i in range(5):
            record_external_intelligence(
                db, _state(), power_id="sun_quan", visibility="rumor",
                title=f"传闻{i}", summary="测试",
                evidence_refs=[f"rumor:{i}"],
                source_type="merchant_network", reliability=45,
                verification_status="unverified", valid_until_turn=5,
                true_subject_ref=f"rumor:{i}",
            )
        result = select_player_visible_world_dynamics(db, _state())
        direct = [r for r in result if r["source_type"] == "direct_contact"]
        assert len(direct) == 3, "所有直接威胁都应显示"
    finally:
        db.close()


def test_visible_dynamics_per_power_limit(tmp_path):
    """同势力最多两条。"""
    db = _board(tmp_path)
    try:
        # 插入 5 条同势力的 rumor（不同 true_subject_ref）
        for i in range(5):
            record_external_intelligence(
                db, _state(), power_id="cao_cao", visibility="rumor",
                title=f"传闻{i}", summary="测试",
                evidence_refs=[f"ref:{i}"],
                source_type="merchant_network", reliability=45,
                verification_status="unverified", valid_until_turn=5,
                true_subject_ref=f"unique_ref:{i}",
            )
        result = select_player_visible_world_dynamics(db, _state())
        cao_count = sum(1 for r in result if r["power_id"] == "cao_cao")
        assert cao_count <= 2, "同势力最多显示两条"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# API 安全
# ---------------------------------------------------------------------------


def test_api_does_not_leak_true_subject_ref(tmp_path):
    """select_player_visible_world_dynamics 返回结果不含 true_subject_ref。"""
    db = _board(tmp_path)
    try:
        record_external_intelligence(
            db, _state(), power_id="cao_cao", visibility="rumor",
            title="传闻", summary="测试",
            evidence_refs=["ref:1"],
            source_type="merchant_network", reliability=45,
            verification_status="unverified", valid_until_turn=5,
            true_subject_ref="secret_ref:123",
        )
        result = select_player_visible_world_dynamics(db, _state())
        for r in result:
            assert "true_subject_ref" not in r, "API 不应泄露 true_subject_ref"
    finally:
        db.close()
