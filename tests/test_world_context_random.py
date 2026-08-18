"""tests/test_world_context_random.py：全局世界上下文随机流合同测试。

验证：
  - 全局天气/民情趋势/民情数值已统一到 world_random 抽取。
  - 固定 campaign_seed_v2 下，不同存档得到相同全局环境。
  - 不同 campaign_seed_v2 下，允许得到不同全局环境。
  - 重复调用不新增抽取记录、不改变世界上下文（幂等）。
  - weather_json 和 public_mood_json 含 draw_refs 字段。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from pathlib import Path

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_simulation import get_or_create_world_context
from ming_sim.world_random import CAMPAIGN_SEED_KEY


def _state(turn: int = 1, year: int = 208, period: int = 8) -> Any:
    return SimpleNamespace(
        turn=turn, year=year, period=period,
        metrics={
            "军资": 60, "粮秣": 60, "民望": 55,
            "名分": 70, "军心": 65, "士族支持": 40,
        },
    )


def _board(tmp_path: Path, *, tag: str, seed_hex: str) -> GameDB:
    db = GameDB(str(tmp_path / f"wctx_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
    )
    db.kv_set(CAMPAIGN_SEED_KEY, seed_hex)
    db.conn.commit()
    return db


# ---------------------------------------------------------------------------
# 同一种子 → 相同全局环境
# ---------------------------------------------------------------------------


def test_world_context_same_seed_same_result(tmp_path):
    """固定 campaign_seed_v2 的两个新存档，同回合同一全局天气、民情趋势和民情数值。"""
    results = []
    for tag in ("d1", "d2"):
        db = _board(tmp_path, tag=tag, seed_hex="deadbeef" * 8)
        try:
            ctx = get_or_create_world_context(db, _state())
            results.append(ctx)
        finally:
            db.close()

    a, b = results
    assert a["weather"]["kind"] == b["weather"]["kind"]
    assert a["weather"]["battle_probability_delta"] == b["weather"]["battle_probability_delta"]
    assert a["public_mood"]["trend"] == b["public_mood"]["trend"]
    assert a["public_mood"]["delta"] == b["public_mood"]["delta"]


# ---------------------------------------------------------------------------
# 不同种子 → 允许不同全局环境
# ---------------------------------------------------------------------------


def test_world_context_different_seed_allows_difference(tmp_path):
    """不同 campaign_seed_v2 的两个新存档，全局环境可以不同（不强制）。"""
    results = []
    for tag, seed in (("s1", "11111111" * 8), ("s2", "22222222" * 8)):
        db = _board(tmp_path, tag=tag, seed_hex=seed)
        try:
            ctx = get_or_create_world_context(db, _state())
            results.append(ctx)
        finally:
            db.close()

    # 我们只验证"允许不同"——至少 weather 或 mood 可以不同（也可能碰巧相同）。
    # 真正的合同是：种子不同 → 抽取路径独立 → 结果由种子决定。
    # 这里验证 draw_refs 存在，说明走了 world_random 路径。
    for ctx in results:
        assert "draw_refs" in ctx["weather"]
        assert "draw_refs" in ctx["public_mood"]


# ---------------------------------------------------------------------------
# 幂等性
# ---------------------------------------------------------------------------


def test_world_context_idempotent(tmp_path):
    """同存档重复调用不新增抽取记录、不改变世界上下文。"""
    db = _board(tmp_path, tag="idem", seed_hex="deadbeef" * 8)
    try:
        ctx1 = get_or_create_world_context(db, _state())
        draws_after_first = db.conn.execute(
            "SELECT COUNT(*) FROM world_random_draws "
            "WHERE domain='world_context' AND turn=1"
        ).fetchone()[0]

        ctx2 = get_or_create_world_context(db, _state())
        draws_after_second = db.conn.execute(
            "SELECT COUNT(*) FROM world_random_draws "
            "WHERE domain='world_context' AND turn=1"
        ).fetchone()[0]

        assert ctx1["weather"] == ctx2["weather"]
        assert ctx1["public_mood"] == ctx2["public_mood"]
        assert draws_after_first == draws_after_second
        # 每个新回合应产生 3 条抽取：weather, public_mood_trend, public_mood_delta
        assert draws_after_first == 3
    finally:
        db.close()


# ---------------------------------------------------------------------------
# draw_refs 字段
# ---------------------------------------------------------------------------


def test_world_context_draw_refs_in_json(tmp_path):
    """weather_json 和 public_mood_json 含 draw_refs 字段，指向 world_random_draws。"""
    db = _board(tmp_path, tag="refs", seed_hex="deadbeef" * 8)
    try:
        ctx = get_or_create_world_context(db, _state())

        # weather.draw_refs
        w_refs = ctx["weather"].get("draw_refs")
        assert isinstance(w_refs, dict)
        assert w_refs.get("domain") == "world_context"
        assert w_refs.get("subject_id") == "global"
        assert w_refs.get("draw_kind") == "weather"

        # public_mood.draw_refs（含 trend 和 delta 两个子引用）
        m_refs = ctx["public_mood"].get("draw_refs")
        assert isinstance(m_refs, dict)
        assert m_refs.get("trend", {}).get("draw_kind") == "public_mood_trend"
        assert m_refs.get("delta", {}).get("draw_kind") == "public_mood_delta"

        # 验证数据库行也正确写入了 draw_refs
        row = db.conn.execute(
            "SELECT weather_json, public_mood_json FROM world_simulation_contexts WHERE turn=1"
        ).fetchone()
        weather_from_db = json.loads(row["weather_json"])
        mood_from_db = json.loads(row["public_mood_json"])
        assert "draw_refs" in weather_from_db
        assert "draw_refs" in mood_from_db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 世界上下文记录到 world_random_draws
# ---------------------------------------------------------------------------


def test_world_context_records_draws_in_world_random_draws(tmp_path):
    """全局天气和民情抽取记录到 world_random_draws 表，domain='world_context'。"""
    db = _board(tmp_path, tag="draws", seed_hex="deadbeef" * 8)
    try:
        ctx = get_or_create_world_context(db, _state())

        draws = db.conn.execute(
            "SELECT domain, subject_id, draw_kind FROM world_random_draws "
            "WHERE domain='world_context' AND turn=1 ORDER BY draw_kind"
        ).fetchall()

        kinds = {row["draw_kind"] for row in draws}
        assert "weather" in kinds
        assert "public_mood_trend" in kinds
        assert "public_mood_delta" in kinds

        # 验证 subject_id 均为 "global"
        for row in draws:
            assert row["subject_id"] == "global"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 旧档兼容：已有 world_simulation_contexts 行不重算
# ---------------------------------------------------------------------------


def test_world_context_old_row_not_recomputed(tmp_path):
    """旧档中已有 world_simulation_contexts 行，调用不重算、不新增抽取记录。"""
    db = _board(tmp_path, tag="old", seed_hex="deadbeef" * 8)
    try:
        # 预先插入一行旧格式（无 draw_refs）
        old_weather = json.dumps({"kind": "阴晴", "battle_probability_delta": 0, "source": "legacy"})
        old_mood = json.dumps({"trend": "安", "delta": 1, "source": "legacy"})
        db.conn.execute(
            """INSERT INTO world_simulation_contexts
            (turn, year, period, seed, season, weather_json, regional_conditions_json, public_mood_json, power_budgets_json)
            VALUES (1, 208, 8, 'legacy_seed', '秋', ?, '{}', ?, '{}')""",
            (old_weather, old_mood),
        )
        db.conn.commit()

        draws_before = db.conn.execute(
            "SELECT COUNT(*) FROM world_random_draws WHERE domain='world_context'"
        ).fetchone()[0]

        ctx = get_or_create_world_context(db, _state())

        draws_after = db.conn.execute(
            "SELECT COUNT(*) FROM world_random_draws WHERE domain='world_context'"
        ).fetchone()[0]

        # 应返回旧行数据，不新增抽取
        assert ctx["weather"]["kind"] == "阴晴"
        assert ctx["weather"]["source"] == "legacy"
        assert draws_before == draws_after == 0
    finally:
        db.close()
