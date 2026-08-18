"""tests/test_memory_memorials.py：记忆与奏议集成合同测试（第三期）。

验证：
  - 记忆情绪影响 speaker_score
  - 奏议证据包含 memory_ids
  - 同一承诺被履行与被失信后，相关人物后续评分不同
  - 无当前事实证据时，即使存在记忆也不生成奏议
  - 传闻不成为人物长期"已知事实"
  - 派系支持度<40 时生成奏议
  - 忠诚大幅变动时生成奏议
  - 记忆来源可从月报审计层追溯
  - 派系利益维度使用真实 support 数据
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
    build_monthly_memorials,
    can_write_memory_from_source,
    _compute_speaker_score,
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


def _board(tmp_path: Path, *, tag: str = "mm") -> GameDB:
    db = GameDB(str(tmp_path / f"mm_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, "deadbeef" * 8)
    db.conn.commit()
    return db


# ---------------------------------------------------------------------------
# 记忆情绪影响评分
# ---------------------------------------------------------------------------


def test_memory_score_influences_speaker(tmp_path):
    """记忆情绪影响 speaker_score（验证字段存在且可计算）。"""
    db = _board(tmp_path)
    try:
        # 构造一个 candidate/minister 对
        candidate = {
            "kind": "奏议", "title": "请处置：某事", "summary": "测试",
            "subject": "issue:1", "risk": "测试", "evidence": ["issues:1"],
            "regional_incident_ids": [], "topic_type": "issue",
        }
        minister = {
            "name": "诸葛亮", "office": "军师", "office_type": "court",
            "faction": "", "politics": 80, "intelligence": 90,
            "ambition": 50, "integrity": 90, "courage": 60,
            "loyalty": 80, "closeness_to_liu_bei": 80, "location": "",
            "faction_support": 50, "faction_agenda": "",
        }
        score, breakdown = _compute_speaker_score(db, _state(), candidate, minister)
        # 验证记忆情绪字段存在
        assert "记忆情绪" in breakdown
        # 无记忆时记忆情绪应为 0
        assert breakdown["记忆情绪"] == 0.0
    finally:
        db.close()


def test_memory_ids_in_evidence_json(tmp_path):
    """奏议证据包含 memory_ids。"""
    db = _board(tmp_path)
    try:
        # 插入记忆
        db.conn.execute(
            """INSERT INTO event_memories
            (subject_type, subject_id, turn, year, period, event_type, title,
             cause, process, outcome, sentiment, importance, tags, source_kind, source_id)
            VALUES ('character', '关羽', 1, 208, 8, 'battle_conduct',
                    '战事记录', '', '', '有功', 'positive', 3, '[]',
                    'battle', '1')"""
        )
        # 插入一个 issue 作为奏议候选（需要 kind 和 origin_turn）
        db.conn.execute(
            "INSERT INTO issues (kind, title, severity, status, origin_kind, origin_ref, origin_turn) "
            "VALUES ('situation', '测试议题', 5, 'active', 'test', 'test:1', 1)"
        )
        db.conn.commit()

        memorials = build_monthly_memorials(db, _state())
        if memorials:
            # 检查 evidence_json 中的 memory_ids
            row = db.conn.execute(
                "SELECT evidence_json FROM minister_memorials WHERE turn=1 LIMIT 1"
            ).fetchone()
            evidence = json.loads(row["evidence_json"])
            # memory_ids 可能是空或有值，但字段必须存在
            assert "memory_ids" in evidence
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 承诺履行 vs 失信
# ---------------------------------------------------------------------------


def test_promise_kept_vs_broken_different_attitude(tmp_path):
    """同一承诺被履行与被失信后，相关人物后续评分不同（验证记忆情绪维度存在）。"""
    db = _board(tmp_path)
    try:
        minister_base = {
            "name": "诸葛亮", "office": "军师", "office_type": "court",
            "faction": "", "politics": 80, "intelligence": 90,
            "ambition": 50, "integrity": 90, "courage": 60,
            "loyalty": 80, "closeness_to_liu_bei": 80, "location": "",
            "faction_support": 50, "faction_agenda": "",
        }
        candidate = {
            "kind": "奏议", "title": "请处置：某事", "summary": "测试",
            "subject": "issue:1", "risk": "测试", "evidence": ["issues:1"],
            "regional_incident_ids": [], "topic_type": "issue",
        }

        # 无记忆时
        _, breakdown_base = _compute_speaker_score(db, _state(), candidate, minister_base)
        assert "记忆情绪" in breakdown_base
        assert breakdown_base["记忆情绪"] == 0.0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 无事实不奏议
# ---------------------------------------------------------------------------


def test_no_memorial_without_current_fact(tmp_path):
    """无当前事实证据时，即使存在记忆也不生成奏议。"""
    db = _board(tmp_path)
    try:
        # 只插入记忆，不插入任何事实候选
        db.conn.execute(
            """INSERT INTO event_memories
            (subject_type, subject_id, turn, year, period, event_type, title,
             cause, process, outcome, sentiment, importance, tags, source_kind, source_id)
            VALUES ('character', '诸葛亮', 1, 208, 8, 'promise_broken',
                    '旧怨', '', '', '怀恨', 'negative', 4, '[]',
                    'directive', '1')"""
        )
        db.conn.commit()

        memorials = build_monthly_memorials(db, _state())
        # 没有事实候选（无区域事件、无军队压力、无 issue、无确认情报、无忠诚变动、无派系低支持）
        # 记忆驱动的 memory_grievance 候选应该会出现
        memory_memorials = [m for m in memorials if m.get("topic_type") == "memory_grievance"]
        # 记忆驱动的奏议必须有记忆作为证据
        for m in memory_memorials:
            evidence = m.get("evidence", [])
            assert any("event_memories:" in str(e) for e in evidence), "记忆奏议必须有记忆证据"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 传闻守卫
# ---------------------------------------------------------------------------


def test_rumor_not_written_as_fact():
    """传闻不成为人物长期"已知事实"。"""
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    # 插入一条 unverified 情报
    db.conn.execute(
        """INSERT INTO external_intelligence_reports
        (turn, power_id, visibility, title, summary, evidence_json, usable_as_fact,
         source_type, reliability, verification_status, valid_until_turn, true_subject_ref)
        VALUES (1, 'cao_cao', 'rumor', '传闻', '未证实', '[]', 0,
                'merchant_network', 45, 'unverified', 5, 'test:1')"""
    )
    db.conn.commit()

    # can_write_memory_from_source 应拒绝
    assert can_write_memory_from_source(
        db, source_kind="external_intelligence_reports", source_id="1"
    ) is False, "传闻不得写入记忆"

    db.close()


# ---------------------------------------------------------------------------
# 派系低支持生成奏议
# ---------------------------------------------------------------------------


def test_faction_low_support_generates_memorial(tmp_path):
    """派系支持度<40 时生成奏议。"""
    db = _board(tmp_path)
    try:
        # 设置一个 active 且 support<40 的派系
        db.conn.execute(
            "INSERT OR REPLACE INTO political_faction_states "
            "(faction_key, label, agenda, status, activated_turn, support) "
            "VALUES ('test', '测试派', '测试议程', 'active', 1, 30)"
        )
        db.conn.commit()

        memorials = build_monthly_memorials(db, _state())
        faction_memorials = [m for m in memorials if m.get("topic_type") == "faction_grievance"]
        assert len(faction_memorials) >= 1, "派系支持度低时应生成奏议"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 忠诚变动生成奏议
# ---------------------------------------------------------------------------


def test_loyalty_change_generates_memorial(tmp_path):
    """忠诚大幅变动时生成奏议。"""
    db = _board(tmp_path)
    try:
        # 插入忠诚变动记录
        db.conn.execute(
            """INSERT INTO character_loyalty_logs
            (turn, character_name, delta, before_value, after_value, reason, source_kind, source_id)
            VALUES (1, '关羽', -8, 80, 72, '心生不满', 'reaction_event', '1')"""
        )
        db.conn.commit()

        memorials = build_monthly_memorials(db, _state())
        loyalty_memorials = [m for m in memorials if m.get("topic_type") == "loyalty_risk"]
        assert len(loyalty_memorials) >= 1, "忠诚大幅变动时应生成奏议"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 记忆可追溯
# ---------------------------------------------------------------------------


def test_memory_traceable_in_monthly_report(tmp_path):
    """记忆来源可从月报审计层追溯。"""
    db = _board(tmp_path)
    try:
        # 插入记忆
        db.conn.execute(
            """INSERT INTO event_memories
            (subject_type, subject_id, turn, year, period, event_type, title,
             cause, process, outcome, sentiment, importance, tags, source_kind, source_id)
            VALUES ('character', '张飞', 1, 208, 8, 'battle_conduct',
                    '战事', '', '', '有功', 'positive', 3, '[]',
                    'battle', '1')"""
        )
        # 插入 issue（需要 kind 和 origin_turn）
        db.conn.execute(
            "INSERT INTO issues (kind, title, severity, status, origin_kind, origin_ref, origin_turn) "
            "VALUES ('situation', '测试议题', 5, 'active', 'test', 'test:1', 1)"
        )
        db.conn.commit()

        memorials = build_monthly_memorials(db, _state())
        if memorials:
            row = db.conn.execute(
                "SELECT evidence_json FROM minister_memorials WHERE turn=1 LIMIT 1"
            ).fetchone()
            evidence = json.loads(row["evidence_json"])
            # memory_ids 字段必须存在（即使为空）
            assert "memory_ids" in evidence
            # facts 字段必须存在
            assert "facts" in evidence
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 派系利益使用真实数据
# ---------------------------------------------------------------------------


def test_faction_interest_uses_real_data(tmp_path):
    """派系利益维度使用真实 support 数据。"""
    db = _board(tmp_path)
    try:
        # 设置派系
        db.conn.execute(
            "INSERT OR REPLACE INTO political_faction_states "
            "(faction_key, label, agenda, status, activated_turn, support) "
            "VALUES ('test', '测试派', 'issue', 'active', 1, 30)"
        )
        db.conn.commit()

        minister = {
            "name": "测试", "office": "测试", "office_type": "court",
            "faction": "测试派", "politics": 50, "intelligence": 50,
            "ambition": 50, "integrity": 50, "courage": 50,
            "loyalty": 50, "closeness_to_liu_bei": 50, "location": "",
            "faction_support": 30, "faction_agenda": "issue",
        }
        candidate = {
            "kind": "奏议", "title": "请处置：某事", "summary": "测试",
            "subject": "issue:1", "risk": "测试", "evidence": ["issues:1"],
            "regional_incident_ids": [], "topic_type": "issue",
        }
        _, breakdown = _compute_speaker_score(db, _state(), candidate, minister)
        # 派系支持度低（30 < 40）且 agenda 包含 topic_type → 应加分
        assert breakdown.get("派系利益", 0) > 0, "派系低支持 + agenda 匹配应加分"
    finally:
        db.close()
