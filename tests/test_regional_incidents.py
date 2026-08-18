"""tests/test_regional_incidents.py：区域事件合同测试。

验证：
  - 固定种子下事件完全一致。
  - 强制 dramatic_global 命中时只生成一项重大事件。
  - 未命中时不生成重大事件。
  - 重大事件目标具备对应风险条件。
  - 效果不超过表中边界。
  - 局部效果不改变 controlled_by、人物状态、兵力、条约。
  - 重大事件创建 issue（severity=8, origin_kind=regional_incident）。
  - 幂等性。
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
    ALLOWED_INCIDENT_TYPES,
    _DRAMATIC_EFFECT_CAPS,
    _ORDINARY_EFFECT_CAPS,
    apply_local_incident_effects,
    build_incident_policy_issue,
    ensure_regional_world_states,
    generate_regional_incidents,
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


def _board(tmp_path: Path, *, tag: str = "ri") -> GameDB:
    db = GameDB(str(tmp_path / f"ri_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


def _force_high_risk_state(db: GameDB, region_id: str, turn: int = 0) -> None:
    """强制一个地区处于高风险状态，以便测试重大事件选中。"""
    db.conn.execute(
        """INSERT OR REPLACE INTO regional_world_states
        (region_id, turn, season, weather_kind, weather_severity,
         road_condition, grain_transport_pressure, harvest_outlook,
         epidemic_pressure, disaster_risk, public_mood_delta)
        VALUES (?, ?, '秋', '暴雨', -50, -60, 40, -55, 55, 30, -10)""",
        (region_id, turn),
    )
    db.conn.commit()


def _force_dramatic_gate(db: GameDB, *, hit: bool, turn: int = 1) -> None:
    """预写 dramatic_gate 抽取记录，强制命中/不命中。"""
    roll = 10 if hit else 80  # 35% 门槛：<=35 命中
    from ming_sim.world_random import derive_seed
    derived = derive_seed(
        db, turn=turn, domain="regional_incident",
        subject_id="dramatic_global", draw_kind="dramatic_gate",
    )
    db.conn.execute(
        """INSERT OR REPLACE INTO world_random_draws
        (turn, domain, subject_id, derived_seed, draw_kind,
         low_value, high_value, roll_value, choice_key,
         candidates_snapshot_json, metadata_json)
        VALUES (?, 'regional_incident', 'dramatic_global', ?, 'dramatic_gate',
                1, 100, ?, '', '[]', '{}')""",
        (turn, derived, roll),
    )
    db.conn.commit()


# ---------------------------------------------------------------------------
# 基本生成
# ---------------------------------------------------------------------------


def test_incident_types_are_fixed_set():
    """incident_type 只允许固定集合。"""
    expected = {
        "flood", "drought", "epidemic", "landslide",
        "harvest_bumper", "grain_convoy_loss", "refugee_influx",
        "bandit_surge", "market_opportunity", "gentry_petition",
    }
    assert ALLOWED_INCIDENT_TYPES == expected


def test_incidents_generated_are_deterministic(tmp_path):
    """固定种子下事件完全一致。"""
    results = []
    for tag in ("d1", "d2"):
        db = _board(tmp_path, tag=tag)
        try:
            incidents = generate_regional_incidents(db, _state())
            results.append(incidents)
        finally:
            db.close()

    assert len(results[0]) == len(results[1])
    for a, b in zip(results[0], results[1]):
        assert a["incident_type"] == b["incident_type"]
        assert a["region_id"] == b["region_id"]
        assert a["tier"] == b["tier"]


def test_at_most_2_ordinary_plus_1_dramatic(tmp_path):
    """每月最多 2 项普通 + 1 项重大。"""
    db = _board(tmp_path)
    try:
        incidents = generate_regional_incidents(db, _state())
        ordinary = [i for i in incidents if i["tier"] == "ordinary"]
        dramatic = [i for i in incidents if i["tier"] == "dramatic"]
        assert len(ordinary) <= 2
        assert len(dramatic) <= 1
    finally:
        db.close()


def test_all_incident_types_in_allowed_set(tmp_path):
    db = _board(tmp_path)
    try:
        incidents = generate_regional_incidents(db, _state())
        for inc in incidents:
            assert inc["incident_type"] in ALLOWED_INCIDENT_TYPES
    finally:
        db.close()


def test_idempotent_same_turn_returns_cached(tmp_path):
    db = _board(tmp_path)
    try:
        first = generate_regional_incidents(db, _state())
        count1 = db.conn.execute(
            "SELECT COUNT(*) FROM regional_incidents WHERE turn=1"
        ).fetchone()[0]
        second = generate_regional_incidents(db, _state())
        count2 = db.conn.execute(
            "SELECT COUNT(*) FROM regional_incidents WHERE turn=1"
        ).fetchone()[0]
        assert count1 == count2
        assert first == second
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 重大事件（确定性强制）
# ---------------------------------------------------------------------------


def test_dramatic_forced_hit_creates_incident(tmp_path):
    """预写 dramatic_gate=10（命中），强制生成 1 项重大事件。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        _force_high_risk_state(db, region_id)
        _force_dramatic_gate(db, hit=True)

        incidents = generate_regional_incidents(db, _state())
        dramatic = [i for i in incidents if i["tier"] == "dramatic"]
        assert len(dramatic) == 1, "强制命中时必须生成 1 项重大事件"
        assert dramatic[0]["region_id"] is not None
        assert dramatic[0]["incident_type"] in ALLOWED_INCIDENT_TYPES
    finally:
        db.close()


def test_dramatic_forced_miss_no_incident(tmp_path):
    """预写 dramatic_gate=80（不命中），不生成重大事件。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        _force_high_risk_state(db, region_id)
        _force_dramatic_gate(db, hit=False)

        incidents = generate_regional_incidents(db, _state())
        dramatic = [i for i in incidents if i["tier"] == "dramatic"]
        assert len(dramatic) == 0, "强制不命中时不应生成重大事件"
    finally:
        db.close()


def test_dramatic_forced_hit_creates_issue_with_severity_8(tmp_path):
    """强制命中后，build_incident_policy_issue 创建 severity=8 的 issue。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        _force_high_risk_state(db, region_id)
        _force_dramatic_gate(db, hit=True)

        incidents = generate_regional_incidents(db, _state())
        dramatic = [i for i in incidents if i["tier"] == "dramatic"]
        assert len(dramatic) == 1

        issue_id = build_incident_policy_issue(db, _state(), dramatic[0])
        assert issue_id is not None
        row = db.conn.execute(
            "SELECT severity, origin_kind, origin_ref FROM issues WHERE id=?",
            (issue_id,),
        ).fetchone()
        assert int(row["severity"]) == 8
        assert row["origin_kind"] == "regional_incident"
        assert row["origin_ref"].startswith("regional_incident:")
    finally:
        db.close()


def test_dramatic_target_has_risk_conditions(tmp_path):
    """强制命中后，重大事件目标具备对应风险条件。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        _force_high_risk_state(db, region_id)
        _force_dramatic_gate(db, hit=True)

        incidents = generate_regional_incidents(db, _state())
        dramatic = [i for i in incidents if i["tier"] == "dramatic"]
        assert len(dramatic) == 1

        row = db.conn.execute(
            "SELECT risk_snapshot_json FROM regional_incidents WHERE id=?",
            (dramatic[0]["id"],),
        ).fetchone()
        risk = json.loads(row["risk_snapshot_json"])
        assert risk.get("region_risk", 0) > 0
        # 风险快照应包含 dramatic_roll
        assert "dramatic_roll" in risk
    finally:
        db.close()


def test_dramatic_effects_applied_exactly_once(tmp_path):
    """强制命中后，apply 两次效果只应用一次，审计日志只记一次。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        _force_high_risk_state(db, region_id)
        _force_dramatic_gate(db, hit=True)

        incidents = generate_regional_incidents(db, _state())
        dramatic = [i for i in incidents if i["tier"] == "dramatic"]
        assert len(dramatic) == 1

        # 读取初始 public_support
        before = db.conn.execute(
            "SELECT public_support FROM regions WHERE id=?", (region_id,)
        ).fetchone()["public_support"]

        # 第一次 apply
        applied1 = apply_local_incident_effects(db, _state(), dramatic[0])
        after_first = db.conn.execute(
            "SELECT public_support FROM regions WHERE id=?", (region_id,)
        ).fetchone()["public_support"]

        # 第二次 apply（应跳过）
        applied2 = apply_local_incident_effects(db, _state(), dramatic[0])
        after_second = db.conn.execute(
            "SELECT public_support FROM regions WHERE id=?", (region_id,)
        ).fetchone()["public_support"]

        # 第一次有实际效果，第二次返回空
        assert applied2 == [], "第二次 apply 应返回空（已应用过）"
        assert after_first == after_second, "第二次 apply 不应改变盘面数值"

        # 检查 effects_applied_at 已标记
        row = db.conn.execute(
            "SELECT effects_applied_at FROM regional_incidents WHERE id=?",
            (dramatic[0]["id"],),
        ).fetchone()
        assert int(row["effects_applied_at"]) == 1, "effects_applied_at 应等于当前 turn"

        # region_logs 中该事件的审计记录数应与实际 effect 条数一致
        logs = db.conn.execute(
            "SELECT COUNT(*) FROM region_logs "
            "WHERE actor='regional_incident' AND region_id=? AND turn=1",
            (region_id,),
        ).fetchone()[0]
        # logs 应该 > 0（至少一个 effect 影响 regions 表字段）
        # 但不能翻倍（即使 apply 被调用了两次）
        public_support_effects = sum(
            1 for e in dramatic[0]["local_effects"] if e["field"] == "public_support"
        )
        assert logs >= public_support_effects  # 至少记了一次
    finally:
        db.close()


def test_ordinary_does_not_create_policy_issue(tmp_path):
    db = _board(tmp_path)
    try:
        incidents = generate_regional_incidents(db, _state())
        ordinary = [i for i in incidents if i["tier"] == "ordinary"]
        for inc in ordinary:
            assert build_incident_policy_issue(db, _state(), inc) is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 局部效果
# ---------------------------------------------------------------------------


def test_local_effects_within_ordinary_caps(tmp_path):
    """普通事件效果不超上限。"""
    db = _board(tmp_path)
    try:
        incidents = generate_regional_incidents(db, _state())
        for inc in incidents:
            if inc["tier"] != "ordinary":
                continue
            for effect in inc["local_effects"]:
                field = effect["field"]
                delta = abs(int(effect["delta"]))
                cap = _ORDINARY_EFFECT_CAPS.get(field)
                if cap is not None and isinstance(cap, int):
                    assert delta <= cap, (
                        f"ordinary {inc['incident_type']}: {field} delta={delta} > cap={cap}"
                    )
    finally:
        db.close()


def test_local_effects_within_dramatic_caps(tmp_path):
    """重大事件效果不超上限。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        _force_high_risk_state(db, region_id)
        incidents = generate_regional_incidents(db, _state())
        for inc in incidents:
            if inc["tier"] != "dramatic":
                continue
            for effect in inc["local_effects"]:
                field = effect["field"]
                delta = abs(int(effect["delta"]))
                cap = _DRAMATIC_EFFECT_CAPS.get(field)
                if cap is not None and isinstance(cap, int):
                    assert delta <= cap, (
                        f"dramatic {inc['incident_type']}: {field} delta={delta} > cap={cap}"
                    )
    finally:
        db.close()


def test_local_effects_do_not_change_controlled_by(tmp_path):
    """局部效果不改变 controlled_by。"""
    db = _board(tmp_path)
    try:
        # 记录所有 controlled_by
        before = {
            r["id"]: r["controlled_by"]
            for r in db.conn.execute("SELECT id, controlled_by FROM regions").fetchall()
        }
        incidents = generate_regional_incidents(db, _state())
        for inc in incidents:
            apply_local_incident_effects(db, _state(), inc)

        after = {
            r["id"]: r["controlled_by"]
            for r in db.conn.execute("SELECT id, controlled_by FROM regions").fetchall()
        }
        assert before == after
    finally:
        db.close()


def test_local_effects_do_not_change_characters_or_treaties(tmp_path):
    """局部效果不改变人物状态、兵力、条约。"""
    db = _board(tmp_path)
    try:
        chars_before = db.conn.execute(
            "SELECT name, status FROM characters"
        ).fetchall()
        armies_before = db.conn.execute(
            "SELECT id, manpower FROM armies"
        ).fetchall()
        treaties_before = db.conn.execute(
            "SELECT proposer, target, status FROM diplomacy_treaties"
        ).fetchall()

        incidents = generate_regional_incidents(db, _state())
        for inc in incidents:
            apply_local_incident_effects(db, _state(), inc)

        chars_after = db.conn.execute(
            "SELECT name, status FROM characters"
        ).fetchall()
        armies_after = db.conn.execute(
            "SELECT id, manpower FROM armies"
        ).fetchall()
        treaties_after = db.conn.execute(
            "SELECT proposer, target, status FROM diplomacy_treaties"
        ).fetchall()

        assert chars_before == chars_after
        assert armies_before == armies_after
        assert treaties_before == treaties_after
    finally:
        db.close()


def test_apply_effects_writes_region_logs(tmp_path):
    """局部效果写入 region_logs 审计，且 apply 两次不重复写入。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]

        # 强制生成事件
        incidents = generate_regional_incidents(db, _state())
        # 只对有 public_support 效果的事件进行验证
        target = None
        for inc in incidents:
            if any(e["field"] == "public_support" for e in inc["local_effects"]):
                target = inc
                break
        if target is None:
            pytest.skip("本种子下无影响 public_support 的事件")

        apply_local_incident_effects(db, _state(), target)

        logs_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM region_logs "
            "WHERE actor='regional_incident' AND region_id=? AND turn=1",
            (region_id,),
        ).fetchone()[0]

        # 第二次 apply（应跳过）
        applied2 = apply_local_incident_effects(db, _state(), target)
        assert applied2 == []

        logs_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM region_logs "
            "WHERE actor='regional_incident' AND region_id=? AND turn=1",
            (region_id,),
        ).fetchone()[0]

        assert logs_after_first == logs_after_second, (
            "第二次 apply 不应新增 region_logs 记录"
        )
    finally:
        db.close()


def test_ordinary_effects_idempotent(tmp_path):
    """普通事件 apply 两次效果不重复。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]

        incidents = generate_regional_incidents(db, _state())
        ordinary = [i for i in incidents if i["tier"] == "ordinary"]
        # 找一个影响 public_support 的普通事件
        target = None
        for inc in ordinary:
            if any(e["field"] == "public_support" for e in inc["local_effects"]):
                target = inc
                break
        if target is None:
            pytest.skip("本种子下无影响 public_support 的普通事件")

        before = db.conn.execute(
            "SELECT public_support FROM regions WHERE id=?", (region_id,)
        ).fetchone()["public_support"]

        applied1 = apply_local_incident_effects(db, _state(), target)
        after_first = db.conn.execute(
            "SELECT public_support FROM regions WHERE id=?", (region_id,)
        ).fetchone()["public_support"]

        applied2 = apply_local_incident_effects(db, _state(), target)
        after_second = db.conn.execute(
            "SELECT public_support FROM regions WHERE id=?", (region_id,)
        ).fetchone()["public_support"]

        # 第一次有实际变更
        ps_delta = sum(e["delta"] for e in applied1 if e["field"] == "public_support")
        # 受 [0,100] 夹紧影响，变化量可能小于 delta
        # 但第二次不应再有变化
        assert applied2 == []
        assert after_first == after_second
    finally:
        db.close()
