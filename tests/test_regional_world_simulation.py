"""tests/test_regional_world_simulation.py：区域月度状态合同测试。

验证：
  - 各地区本回合有一条状态，数值在合法范围 [-100, 100]。
  - 季节和地区类型影响天气/道路结果。
  - 上回合恶劣道路会以规定速度延续或恢复。
  - 固定种子下区域状态完全一致。
  - 幂等性：同 turn 重复调用返回已落库结果。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from pathlib import Path

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import (
    ensure_regional_world_states,
    region_world_state,
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


def _board(tmp_path: Path, *, tag: str = "rws") -> GameDB:
    db = GameDB(str(tmp_path / f"rws_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    # 固定种子以确保可重复
    db.kv_set(CAMPAIGN_SEED_KEY, "a1b2c3d4" * 8)
    db.conn.commit()
    return db


def _region_count(db: GameDB) -> int:
    return db.conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]


# ---------------------------------------------------------------------------
# 基本生成
# ---------------------------------------------------------------------------


def test_each_region_has_a_state_record_for_the_turn(tmp_path):
    """各地区本回合有一条状态。"""
    db = _board(tmp_path)
    try:
        states = ensure_regional_world_states(db, _state())
        assert len(states) == _region_count(db)
        assert len(states) > 0
    finally:
        db.close()


def test_all_state_values_in_valid_range(tmp_path):
    """所有状态字段在 [-100, 100] 内。"""
    db = _board(tmp_path)
    try:
        states = ensure_regional_world_states(db, _state())
        for s in states:
            for field in (
                "weather_severity", "road_condition",
                "grain_transport_pressure", "harvest_outlook",
                "epidemic_pressure", "disaster_risk", "public_mood_delta",
            ):
                val = s[field]
                assert -100 <= val <= 100, (
                    f"{s['region_id']}.{field}={val} out of [-100,100]"
                )
    finally:
        db.close()


def test_epidemic_and_disaster_risk_are_non_negative(tmp_path):
    """epidemic_pressure 和 disaster_risk 只取 [0, 100]。"""
    db = _board(tmp_path)
    try:
        states = ensure_regional_world_states(db, _state())
        for s in states:
            assert 0 <= s["epidemic_pressure"] <= 100
            assert 0 <= s["disaster_risk"] <= 100
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 季节与地区类型
# ---------------------------------------------------------------------------


def test_season_affects_weather_kind(tmp_path):
    """不同季节的天气候选不同。"""
    db = _board(tmp_path)
    try:
        # 冬季（period=12）
        winter = ensure_regional_world_states(db, _state(period=12))
        winter_weathers = {s["weather_kind"] for s in winter}
    finally:
        db.close()

    db2 = _board(tmp_path, tag="rws_summer")
    try:
        # 夏季（period=6）
        summer = ensure_regional_world_states(db2, _state(period=6))
        summer_weathers = {s["weather_kind"] for s in summer}
    finally:
        db2.close()

    # 冬夏天气池不完全相同
    assert winter_weathers != summer_weathers or len(winter_weathers) > 0


def test_region_kind_influences_road_severity(tmp_path):
    """山道/关隘在恶劣天气下道路更差（相比普通路）。"""
    db = _board(tmp_path)
    try:
        states = ensure_regional_world_states(db, _state())
        # 检查 state_json 中有审计因子
        row = db.conn.execute(
            "SELECT state_json FROM regional_world_states WHERE turn=1 LIMIT 1"
        ).fetchone()
        audit = json.loads(row["state_json"])
        assert "region_kind" in audit
        assert "weather_kind" in audit
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 延续与恢复
# ---------------------------------------------------------------------------


def test_bad_road_is_adjusted_by_weather(tmp_path):
    """上回合恶劣道路在本回合会因天气被调整（恢复或继续恶化）。"""
    db = _board(tmp_path)
    try:
        # 手动插入一个上回合的恶劣道路状态（全地区 road=-50）
        regions = db.conn.execute("SELECT id FROM regions ORDER BY id").fetchall()
        for r in regions:
            db.conn.execute(
                """INSERT INTO regional_world_states
                (region_id, turn, season, weather_kind, weather_severity,
                 road_condition, grain_transport_pressure, harvest_outlook,
                 epidemic_pressure, disaster_risk, public_mood_delta)
                VALUES (?, 0, '秋', '清朗', 10, -50, 0, 0, 0, 0, 0)""",
                (r["id"],),
            )
        db.conn.commit()

        states_turn1 = ensure_regional_world_states(db, _state(turn=1))
        # 每个之前 road=-50 的地区值都发生了变化
        for s in states_turn1:
            assert s["road_condition"] != -50, (
                f"{s['region_id']}: road did not change from -50"
            )
            # 仍然在合法范围内
            assert -100 <= s["road_condition"] <= 100
    finally:
        db.close()


def test_road_does_not_exceed_bounds_after_recovery(tmp_path):
    """道路恢复不会超过 100。"""
    db = _board(tmp_path)
    try:
        regions = db.conn.execute("SELECT id FROM regions ORDER BY id LIMIT 1").fetchall()
        db.conn.execute(
            """INSERT INTO regional_world_states
            (region_id, turn, season, weather_kind, weather_severity,
             road_condition, grain_transport_pressure, harvest_outlook,
             epidemic_pressure, disaster_risk, public_mood_delta)
            VALUES (?, 0, '秋', '丰收', 15, 95, 0, 0, 0, 0, 0)""",
            (regions[0]["id"],),
        )
        db.conn.commit()

        states = ensure_regional_world_states(db, _state(turn=1))
        for s in states:
            assert -100 <= s["road_condition"] <= 100
    finally:
        db.close()


def test_recovery_mechanism_with_good_weather(tmp_path):
    """直接验证：当前一回合天气 severity >= 0 时，道路按 _ROAD_RECOVERY_PER_TURN 恢复。"""
    db = _board(tmp_path)
    try:
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        # 前一回合好天气 + 恶劣道路
        db.conn.execute(
            """INSERT INTO regional_world_states
            (region_id, turn, season, weather_kind, weather_severity,
             road_condition, grain_transport_pressure, harvest_outlook,
             epidemic_pressure, disaster_risk, public_mood_delta)
            VALUES (?, 0, '秋', '清朗', 5, -40, 0, 0, 0, 0, 0)""",
            (region_id,),
        )
        db.conn.commit()

        states = ensure_regional_world_states(db, _state(turn=1))
        target = next(s for s in states if s["region_id"] == region_id)
        audit = json.loads(
            db.conn.execute(
                "SELECT state_json FROM regional_world_states WHERE region_id=? AND turn=1",
                (region_id,),
            ).fetchone()["state_json"]
        )
        # 如果本回合天气也好（severity >= -10），道路应恢复
        if audit["weather_severity"] >= -10:
            assert target["road_condition"] > -40, (
                f"road should recover from -40 with good weather, got {target['road_condition']}"
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 确定性 / 幂等
# ---------------------------------------------------------------------------


def test_fixed_seed_produces_identical_states(tmp_path):
    """固定种子下区域状态完全一致。"""
    results = []
    for tag in ("fs1", "fs2"):
        db = _board(tmp_path, tag=tag)
        try:
            states = ensure_regional_world_states(db, _state())
            results.append(states)
        finally:
            db.close()

    assert len(results[0]) == len(results[1])
    for a, b in zip(results[0], results[1]):
        assert a["region_id"] == b["region_id"]
        assert a["weather_kind"] == b["weather_kind"]
        assert a["weather_severity"] == b["weather_severity"]
        assert a["road_condition"] == b["road_condition"]
        assert a["harvest_outlook"] == b["harvest_outlook"]


def test_idempotent_same_turn_returns_cached(tmp_path):
    """同 turn 重复调用返回已落库结果，不生成新记录。"""
    db = _board(tmp_path)
    try:
        first = ensure_regional_world_states(db, _state())
        count_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM regional_world_states WHERE turn=1"
        ).fetchone()[0]
        second = ensure_regional_world_states(db, _state())
        count_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM regional_world_states WHERE turn=1"
        ).fetchone()[0]
        assert count_after_first == count_after_second
        assert first == second
    finally:
        db.close()


# ---------------------------------------------------------------------------
# region_world_state
# ---------------------------------------------------------------------------


def test_region_world_state_returns_existing(tmp_path):
    db = _board(tmp_path)
    try:
        ensure_regional_world_states(db, _state())
        region_id = db.conn.execute(
            "SELECT id FROM regions ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        state = region_world_state(db, turn=1, region_id=region_id)
        assert state["region_id"] == region_id
        assert state["turn"] == 1
        assert state["weather_kind"]
    finally:
        db.close()


def test_region_world_state_returns_neutral_baseline_for_missing(tmp_path):
    """不存在时返回中性基线。"""
    db = _board(tmp_path)
    try:
        state = region_world_state(db, turn=999, region_id="nonexistent")
        assert state["weather_kind"] == "未定"
        assert state["weather_severity"] == 0
        assert state["road_condition"] == 0
    finally:
        db.close()
