"""公共基础设施：种子、季节、关系操作、活跃势力遍历、审计日志。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from functools import cache
from typing import Any, Dict

from ming_sim.ws_utils import decode_json as _decode, get_turn, get_year, get_period


def seed_for(state: object) -> str:
    raw = f"sanguo-world-v1:{getattr(state, 'year', 0)}:{getattr(state, 'period', 0)}:{getattr(state, 'turn', 0)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


# 保留私有别名以兼容内部调用
_seed_for = seed_for


@cache
def season(period: int) -> str:
    return {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春", 6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}.get(period, "四时")


_season = season


def get_or_create_relation(db, power_a: str, power_b: str):
    """获取或创建双边外交关系。返回行 dict 或 None。"""
    first, second = db._relation_pair(power_a, power_b)
    row = db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE power_a=? AND power_b=?",
        (first, second),
    ).fetchone()
    if row is not None:
        return row
    # 不存在则不自动创建（只返回 None）
    return None


_get_or_create_relation = get_or_create_relation


def get_relation(db, power_a: str, power_b: str):
    """获取双边关系，不存在时返回 None。"""
    if not power_a or not power_b or power_a == power_b:
        return None
    first, second = db._relation_pair(power_a, power_b)
    row = db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE power_a=? AND power_b=?",
        (first, second),
    ).fetchone()
    return row


_get_relation = get_relation


# ---------------------------------------------------------------------------
# 第六期新增 — 活跃势力遍历 + 审计日志
# ---------------------------------------------------------------------------


def iter_active_powers(db, *, exclude_liu_bei: bool = True) -> list[sqlite3.Row]:
    """返回所有未灭亡势力。替代多处重复 SQL。"""
    sql = "SELECT id, cohesion, supply, status FROM powers"
    if exclude_liu_bei:
        sql += " WHERE id != 'liu_bei'"
    return db.conn.execute(sql).fetchall()


def log_power_change(db, state, power_id: str, field: str,
                     old_value: int, new_value: int, reason: str) -> None:
    """写入 power_logs 审计。替代 6 处近乎相同的 INSERT 模板。"""
    db.conn.execute(
        "INSERT INTO power_logs "
        "(turn, year, period, power_id, field, old_value, new_value, delta, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (get_turn(state), get_year(state), get_period(state),
         power_id, field, str(old_value), str(new_value),
         new_value - old_value, reason),
    )


def log_diplomacy_change(db, state, power_a: str, power_b: str, field: str,
                         old_value, new_value, reason: str, actor: str = "") -> None:
    """写入 diplomacy_logs 审计。"""
    db.conn.execute(
        """INSERT INTO diplomacy_logs
        (turn, power_a, power_b, field, old_value, new_value, reason, actor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (get_turn(state), power_a, power_b, field,
         str(old_value), str(new_value), reason, actor),
    )


def log_region_change(db, state, region_id: str, field: str,
                      old_value: int, new_value: int, reason: str, actor: str = "") -> None:
    """写入 region_logs 审计。"""
    db.conn.execute(
        """INSERT INTO region_logs
        (turn, year, period, region_id, field, old_value, new_value, delta, reason, actor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (get_turn(state), get_year(state), get_period(state),
         region_id, field, str(old_value), str(new_value),
         new_value - old_value, reason, actor),
    )
