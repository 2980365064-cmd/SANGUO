"""tests/test_world_random.py：存档级确定性随机流合同测试。

验证：
  - 同 campaign_seed + 同状态重复 draw 返回同一结果，数据库只有一条抽取记录。
  - 两个新数据库种子不同；相同历史月份的抽取结果允许不同。
  - 旧档无种子时迁移后生成一次，第二次读取不变。
  - 不存在未审计的世界随机调用：对生产模块做源代码合同断言。
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.world_random import (
    CAMPAIGN_SEED_KEY,
    draw_int,
    draw_weighted,
    ensure_campaign_seed,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MING_SIM_DIR = _REPO_ROOT / "ming_sim"


def _state(turn: int = 1) -> Any:
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={
            "军资": 60, "粮秣": 60, "民望": 55,
            "名分": 70, "军心": 65, "士族支持": 40,
        },
    )


def _fresh_db(tmp_path: Path, *, tag: str = "test") -> GameDB:
    """创建新 DB 并 seed 静态数据。不自动插 game_state（模拟新档）。"""
    db = GameDB(str(tmp_path / f"wr_{tag}.db"), content=GameContent.load())
    db.seed_static_data()
    return db


def _fresh_db_with_game_state(tmp_path: Path, *, tag: str = "test") -> GameDB:
    """创建 DB 并插入 game_state 行（模拟旧档已有存档数据）。"""
    db = _fresh_db(tmp_path, tag=tag)
    db.conn.execute(
        "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)",
    )
    db.conn.commit()
    return db


def _draw_count(db: GameDB) -> int:
    return db.conn.execute("SELECT COUNT(*) FROM world_random_draws").fetchone()[0]


# ---------------------------------------------------------------------------
# ensure_campaign_seed
# ---------------------------------------------------------------------------


def test_new_campaign_gets_32_byte_hex_seed(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        seed = ensure_campaign_seed(db)
        assert isinstance(seed, str)
        assert len(seed) == 64  # 32 bytes = 64 hex chars
        assert all(c in "0123456789abcdef" for c in seed)
        # 永久写入 kv_store
        assert db.kv_get(CAMPAIGN_SEED_KEY) == seed
    finally:
        db.close()


def test_old_campaign_without_seed_gets_stable_migrated_seed(tmp_path):
    """旧档（game_state 已有数据、无种子）首次调用时用稳定材料生成一次。"""
    db = _fresh_db_with_game_state(tmp_path)
    try:
        # 模拟旧档：game_state 有数据，但无 campaign_seed_v2
        db.conn.execute(
            "UPDATE game_state SET year=208, period=8, turn=5 WHERE id=1"
        )
        db.conn.commit()
        first = ensure_campaign_seed(db)
        assert first
        assert len(first) == 64
        # 第二次读取不变
        second = ensure_campaign_seed(db)
        assert second == first
        assert db.kv_get(CAMPAIGN_SEED_KEY) == first
    finally:
        db.close()


def test_old_campaign_stable_seed_is_deterministic(tmp_path):
    """同一旧档状态材料，两次生成的稳定种子一致。"""
    seeds = []
    for tag in ("old1", "old2"):
        db = _fresh_db_with_game_state(tmp_path, tag=tag)
        try:
            db.conn.execute(
                "UPDATE game_state SET year=208, period=8, turn=5 WHERE id=1"
            )
            db.conn.commit()
            seeds.append(ensure_campaign_seed(db))
        finally:
            db.close()
    # 同样的数据 → 同样的稳定种子
    assert seeds[0] == seeds[1]


def test_different_dbs_get_different_seeds(tmp_path):
    """两个独立新档的种子不同。"""
    db1 = _fresh_db(tmp_path, tag="a")
    db2 = _fresh_db(tmp_path, tag="b")
    try:
        s1 = ensure_campaign_seed(db1)
        s2 = ensure_campaign_seed(db2)
        assert s1 != s2
    finally:
        db1.close()
        db2.close()


def test_test_can_fix_seed_via_kv_set(tmp_path):
    """测试可通过 db.kv_set("campaign_seed_v2", "...") 固定种子。"""
    db = _fresh_db(tmp_path)
    try:
        fixed = "a" * 64
        db.kv_set(CAMPAIGN_SEED_KEY, fixed)
        assert ensure_campaign_seed(db) == fixed
    finally:
        db.close()


# ---------------------------------------------------------------------------
# draw_int
# ---------------------------------------------------------------------------


def test_draw_int_returns_same_result_on_repeated_call(tmp_path):
    """同 turn/domain/subject_id/draw_kind 重复调用返回同一结果，数据库只有一条记录。"""
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=3)
        first = draw_int(
            db, state=state, domain="test", subject_id="region:jiangxia",
            low=1, high=100,
        )
        second = draw_int(
            db, state=state, domain="test", subject_id="region:jiangxia",
            low=1, high=100,
        )
        assert first == second
        assert 1 <= first <= 100
        assert _draw_count(db) == 1
    finally:
        db.close()


def test_draw_int_different_domains_diverge(tmp_path):
    """不同 domain 的抽取互不影响。"""
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=1)
        a = draw_int(
            db, state=state, domain="weather", subject_id="region:jiangxia",
            low=1, high=100,
        )
        b = draw_int(
            db, state=state, domain="harvest", subject_id="region:jiangxia",
            low=1, high=100,
        )
        # 允许相等但极小概率；主要验证不互相覆盖
        assert 1 <= a <= 100
        assert 1 <= b <= 100
        assert _draw_count(db) == 2
    finally:
        db.close()


def test_draw_int_different_turns_diverge(tmp_path):
    """同一 domain+subject，不同 turn 允许不同结果。"""
    db = _fresh_db(tmp_path)
    try:
        a = draw_int(
            db, state=_state(turn=1), domain="test", subject_id="x",
            low=1, high=1000,
        )
        b = draw_int(
            db, state=_state(turn=2), domain="test", subject_id="x",
            low=1, high=1000,
        )
        # 大范围下几乎必然不同
        assert _draw_count(db) == 2
    finally:
        db.close()


def test_draw_int_different_seeds_diverge(tmp_path):
    """两个独立数据库种子不同，相同历史月份的抽取结果允许不同。"""
    results = []
    for tag in ("s1", "s2"):
        db = _fresh_db(tmp_path, tag=tag)
        try:
            val = draw_int(
                db, state=_state(turn=5), domain="weather", subject_id="region:a",
                low=1, high=10000,
            )
            results.append(val)
        finally:
            db.close()
    # 不同种子 → 大概率不同
    assert results[0] != results[1]


def test_draw_int_fixed_seed_is_reproducible(tmp_path):
    """固定 campaign_seed_v2 后，多次创建 DB 的抽取完全一致。"""
    fixed_seed = "b" * 64
    results = []
    for tag in ("r1", "r2"):
        db = _fresh_db(tmp_path, tag=tag)
        try:
            db.kv_set(CAMPAIGN_SEED_KEY, fixed_seed)
            val = draw_int(
                db, state=_state(turn=4), domain="incident", subject_id="region:jiangxia",
                low=1, high=100,
            )
            results.append(val)
        finally:
            db.close()
    assert results[0] == results[1]


def test_draw_int_respects_range(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        for i in range(20):
            val = draw_int(
                db, state=_state(turn=i + 100), domain="range", subject_id=f"s{i}",
                low=10, high=20,
            )
            assert 10 <= val <= 20, f"turn={i}: val={val} out of [10,20]"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# draw_weighted
# ---------------------------------------------------------------------------


def test_draw_weighted_returns_same_choice_on_repeated_call(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=2)
        choices = [
            {"key": "flood", "weight": 30, "label": "洪水"},
            {"key": "drought", "weight": 50, "label": "旱灾"},
            {"key": "epidemic", "weight": 20, "label": "瘟疫"},
        ]
        first = draw_weighted(
            db, state=state, domain="incident", subject_id="region:jiangxia",
            choices=choices,
        )
        second = draw_weighted(
            db, state=state, domain="incident", subject_id="region:jiangxia",
            choices=choices,
        )
        assert first is not None
        assert first["key"] == second["key"]
        assert _draw_count(db) == 1
    finally:
        db.close()


def test_draw_weighted_empty_choices_returns_none(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        result = draw_weighted(
            db, state=_state(), domain="test", subject_id="x",
            choices=[],
        )
        assert result is None
        assert _draw_count(db) == 0
    finally:
        db.close()


def test_draw_weighted_equal_weights_fallback(tmp_path):
    """所有权重为 0 时退化为等权。"""
    db = _fresh_db(tmp_path)
    try:
        choices = [{"key": "a", "weight": 0}, {"key": "b", "weight": 0}]
        result = draw_weighted(
            db, state=_state(), domain="test", subject_id="eq",
            choices=choices,
        )
        assert result is not None
        assert result["key"] in ("a", "b")
    finally:
        db.close()


def test_draw_weighted_custom_weight_key(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        choices = [
            {"type": "bandit", "score": 80},
            {"type": "harvest", "score": 20},
        ]
        result = draw_weighted(
            db, state=_state(), domain="test", subject_id="ck",
            choices=choices, weight_key="score",
        )
        assert result is not None
        assert result["type"] in ("bandit", "harvest")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 源代码合同：禁止裸 random 调用
# ---------------------------------------------------------------------------

# 允许 import random 的模块（world_random.py 本身是随机入口）
_RANDOM_ALLOWED_MODULES = {
    "world_random.py",
    # 以下模块在 Step 4/6 迁移后也应不再使用裸 random
    # 目前只断言核心世界模块
}

# 需要检查的生产模块
_MODULES_TO_AUDIT = [
    "random_events.py",
    "world_simulation.py",
    "battle.py",
    "power_ai.py",
]

# 禁止的直接调用模式
_FORBIDDEN_PATTERNS = [
    re.compile(r"\brandom\.random\s*\("),
    re.compile(r"\brandom\.choice\s*\("),
    re.compile(r"\brandom\.randint\s*\("),
    re.compile(r"\brandom\.randrange\s*\("),
    re.compile(r"\brandom\.sample\s*\("),
    re.compile(r"\b_random\.random\s*\("),
    re.compile(r"\b_random\.choice\s*\("),
    re.compile(r"\b_random\.randint\s*\("),
]


def _scan_module_for_bare_random(module_path: Path) -> list[str]:
    """扫描一个模块的源代码，返回违规行描述列表。

    跳过注释行和字符串内的匹配。使用 ast 精确查找 Call 节点。
    """
    source = module_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [f"{module_path.name}: 无法解析为 Python"]

    violations: list[str] = []
    forbidden_names = {"random", "_random"}
    forbidden_methods = {"random", "choice", "randint", "randrange", "sample"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # random.xxx(...) 或 _random.xxx(...)
            if isinstance(func, ast.Attribute) and func.attr in forbidden_methods:
                if isinstance(func.value, ast.Name) and func.value.id in forbidden_names:
                    violations.append(
                        f"{module_path.name}:{node.lineno}: "
                        f"{func.value.id}.{func.attr}()"
                    )
    return violations


def test_no_bare_random_in_production_world_modules():
    """核心世界模块禁止裸 random.random/choice/randint。"""
    all_violations: list[str] = []
    for module_name in _MODULES_TO_AUDIT:
        module_path = _MING_SIM_DIR / module_name
        if not module_path.exists():
            continue
        violations = _scan_module_for_bare_random(module_path)
        all_violations.extend(violations)

    assert not all_violations, (
        "以下生产模块仍有裸 random 调用，"
        "必须通过 ming_sim.world_random 抽取：\n"
        + "\n".join(all_violations)
    )


# ---------------------------------------------------------------------------
# 数据库表存在性
# ---------------------------------------------------------------------------


def test_world_random_draws_table_exists(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        row = db.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_random_draws'"
        ).fetchone()
        assert row is not None
    finally:
        db.close()


def test_regional_world_states_table_exists(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        row = db.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='regional_world_states'"
        ).fetchone()
        assert row is not None
    finally:
        db.close()


def test_regional_incidents_table_exists(tmp_path):
    db = _fresh_db(tmp_path)
    try:
        row = db.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='regional_incidents'"
        ).fetchone()
        assert row is not None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 候选变更合同：P1 修复
# ---------------------------------------------------------------------------


def test_draw_int_raises_on_range_mismatch(tmp_path):
    """draw_int 同 key 再次调用时 low/high 必须一致，否则抛 ValueError。"""
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=5)
        first = draw_int(
            db, state=state, domain="test", subject_id="range_check",
            low=1, high=100,
        )
        # 同 key 同样范围 → 正常返回
        second = draw_int(
            db, state=state, domain="test", subject_id="range_check",
            low=1, high=100,
        )
        assert first == second

        # 同 key 不同范围 → 抛 ValueError
        with pytest.raises(ValueError, match="low.*high"):
            draw_int(
                db, state=state, domain="test", subject_id="range_check",
                low=1, high=200,  # high 变了
            )
        with pytest.raises(ValueError, match="low.*high"):
            draw_int(
                db, state=state, domain="test", subject_id="range_check",
                low=10, high=100,  # low 变了
            )
    finally:
        db.close()


def test_draw_weighted_returns_none_when_candidates_change(tmp_path):
    """draw_weighted 候选键集合变化时返回 None，不静默取第一项，并写入 audit_warning。"""
    import json
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=3)
        original_choices = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 50},
            {"key": "epidemic", "weight": 20},
        ]
        first = draw_weighted(
            db, state=state, domain="incident", subject_id="candidate_change",
            choices=original_choices,
        )
        assert first is not None
        assert first["key"] in ("flood", "drought", "epidemic")

        # 候选键集合变了（去掉 epidemic，加 bandit）→ 返回 None
        changed_choices = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 50},
            {"key": "bandit", "weight": 20},
        ]
        result = draw_weighted(
            db, state=state, domain="incident", subject_id="candidate_change",
            choices=changed_choices,
        )
        assert result is None, "候选键不匹配时应返回 None，不能静默取第一项"

        # 检查 audit_warning 已写入 metadata_json
        row = db.conn.execute(
            "SELECT metadata_json FROM world_random_draws "
            "WHERE domain='incident' AND subject_id='candidate_change'"
        ).fetchone()
        meta = json.loads(row["metadata_json"])
        assert "audit_warning" in meta, "应写入 audit_warning"
        assert "候选键不兼容" in meta["audit_warning"]
    finally:
        db.close()


def test_draw_weighted_same_candidates_same_result(tmp_path):
    """draw_weighted 候选键集合一致（即使顺序不同），返回原选择。"""
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=4)
        choices_v1 = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 50},
            {"key": "epidemic", "weight": 20},
        ]
        first = draw_weighted(
            db, state=state, domain="incident", subject_id="same_candidates",
            choices=choices_v1,
        )
        assert first is not None

        # 同样的候选，不同顺序 → 仍返回原选择
        choices_v2 = [
            {"key": "epidemic", "weight": 20},
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 50},
        ]
        second = draw_weighted(
            db, state=state, domain="incident", subject_id="same_candidates",
            choices=choices_v2,
        )
        assert second is not None
        assert first["key"] == second["key"]
    finally:
        db.close()


def test_draw_weighted_records_candidates_snapshot(tmp_path):
    """draw_weighted 落库时写入 candidates_snapshot_json。"""
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=6)
        choices = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 70},
        ]
        draw_weighted(
            db, state=state, domain="incident", subject_id="snap_test",
            choices=choices,
        )
        row = db.conn.execute(
            "SELECT candidates_snapshot_json FROM world_random_draws "
            "WHERE domain='incident' AND subject_id='snap_test'"
        ).fetchone()
        assert row is not None
        import json
        snapshot = json.loads(row["candidates_snapshot_json"])
        assert len(snapshot) == 2
        keys_in_snapshot = {item["key"] for item in snapshot}
        assert keys_in_snapshot == {"flood", "drought"}
    finally:
        db.close()


def test_draw_weighted_returns_none_on_weight_change(tmp_path):
    """候选键相同但权重变化 → 返回 None，并写入 audit_warning。"""
    import json
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=7)
        original = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 70},
        ]
        first = draw_weighted(
            db, state=state, domain="incident", subject_id="weight_change",
            choices=original,
        )
        assert first is not None

        # 候选键相同，但权重翻转
        changed = [
            {"key": "flood", "weight": 70},
            {"key": "drought", "weight": 30},
        ]
        result = draw_weighted(
            db, state=state, domain="incident", subject_id="weight_change",
            choices=changed,
        )
        assert result is None, "权重变化时应返回 None"

        # 检查 audit_warning 已写入 metadata_json
        row = db.conn.execute(
            "SELECT metadata_json FROM world_random_draws "
            "WHERE domain='incident' AND subject_id='weight_change'"
        ).fetchone()
        meta = json.loads(row["metadata_json"])
        assert "audit_warning" in meta, "应写入 audit_warning"
        assert "权重" in meta["audit_warning"]
    finally:
        db.close()


def test_draw_weighted_returns_none_on_empty_snapshot(tmp_path):
    """旧档记录快照为空 → 审计不兼容，返回 None，写入 audit_warning。"""
    import json
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=8)
        from ming_sim.world_random import derive_seed
        derived = derive_seed(
            db, turn=8, domain="incident", subject_id="old_record",
            draw_kind="weighted",
        )
        # 模拟旧档：直接插入记录，candidates_snapshot_json 为空
        db.conn.execute(
            """INSERT INTO world_random_draws
            (turn, domain, subject_id, derived_seed, draw_kind,
             low_value, high_value, roll_value, choice_key,
             candidates_snapshot_json, metadata_json)
            VALUES (?, 'incident', 'old_record', ?, 'weighted',
                    NULL, NULL, NULL, 'flood', '[]', '{}')""",
            (8, derived),
        )
        db.conn.commit()

        # 现在调用 draw_weighted，应返回 None
        choices = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 70},
        ]
        result = draw_weighted(
            db, state=state, domain="incident", subject_id="old_record",
            choices=choices,
        )
        assert result is None, "旧档无快照时应返回 None"

        # 检查 audit_warning
        row = db.conn.execute(
            "SELECT metadata_json FROM world_random_draws "
            "WHERE domain='incident' AND subject_id='old_record'"
        ).fetchone()
        meta = json.loads(row["metadata_json"])
        assert "audit_warning" in meta, "应写入 audit_warning"
        assert "快照缺失" in meta["audit_warning"] or "旧档" in meta["audit_warning"]
    finally:
        db.close()


def test_draw_weighted_same_candidates_returns_result(tmp_path):
    """完全相同的候选（键+权重均一致）→ 返回原选择，无 audit_warning。"""
    import json
    db = _fresh_db(tmp_path)
    try:
        state = _state(turn=9)
        choices = [
            {"key": "flood", "weight": 30},
            {"key": "drought", "weight": 70},
        ]
        first = draw_weighted(
            db, state=state, domain="incident", subject_id="exact_same",
            choices=choices,
        )
        assert first is not None

        # 完全相同候选再次调用
        second = draw_weighted(
            db, state=state, domain="incident", subject_id="exact_same",
            choices=choices,
        )
        assert second is not None
        assert first["key"] == second["key"]

        # 无 audit_warning
        row = db.conn.execute(
            "SELECT metadata_json FROM world_random_draws "
            "WHERE domain='incident' AND subject_id='exact_same'"
        ).fetchone()
        meta = json.loads(row["metadata_json"])
        assert "audit_warning" not in meta, "不应有 audit_warning"
    finally:
        db.close()
