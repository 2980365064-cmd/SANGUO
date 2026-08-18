"""world_simulation 子系统共享的纯函数工具。

提取自 world_simulation.py / power_ai.py / reactions.py 中的重复定义。
所有函数纯计算、无副作用、不访问 db。
"""
from __future__ import annotations

import json
from functools import cache
from typing import Any


def decode_json(value: object, fallback: object) -> object:
    """将可能是 JSON 字符串或已有结构的值解码。

    统一了 7 处散布在 world_simulation / power_ai / monthly_report /
    historical_events / web_app / db/action_plans / sanguo_rules 中的
    等价实现。
    """
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def safe_list(value: object) -> list:
    """将可能是 JSON 字符串或已有列表的值转为 list。"""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        decoded = decode_json(value, [])
        if isinstance(decoded, list):
            return decoded
    return []


@cache
def status_terminal(status: str) -> bool:
    """判断势力状态是否为终态（灭亡/停用）。

    统一了 world_simulation.py:2333 和 power_ai.py:28 两处字节级等价的实现。
    """
    lowered = str(status).lower()
    return lowered in {"defeated", "destroyed", "collapsed", "inactive"} or any(
        token in str(status) for token in ("灭亡", "瓦解", "覆灭", "已亡")
    )


def clamp(value: int, lo: int = -100, hi: int = 100) -> int:
    """数值截断。默认边界 (-100, 100) 对应 _STATE_CLAMP。

    world_simulation.py 默认 (-100, 100)，diplomacy/reactions/historical_events/
    db/action_plans 默认 (0, 100)。调用方需显式传参。
    """
    return max(lo, min(hi, int(value)))


# ---------------------------------------------------------------------------
# 第六期新增 — 高频工具函数
# ---------------------------------------------------------------------------


def get_turn(state: object) -> int:
    """提取 state.turn。替代 25 处 int(getattr(state, "turn", 0))。"""
    return int(getattr(state, "turn", 0))


def get_year(state: object) -> int:
    """提取 state.year。"""
    return int(getattr(state, "year", 0))


def get_period(state: object) -> int:
    """提取 state.period。"""
    return int(getattr(state, "period", 0))


def to_json(value: object) -> str:
    """json.dumps(value, ensure_ascii=False) — 替代 26 处重复。"""
    return json.dumps(value, ensure_ascii=False)


def is_already_processed(
    db, table: str, key_columns: tuple, key_values: tuple,
) -> bool:
    """通用幂等守卫：SELECT 1 FROM table WHERE k1=? AND k2=? ... LIMIT 1。"""
    where = " AND ".join(f"{col}=?" for col in key_columns)
    row = db.conn.execute(
        f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", key_values,
    ).fetchone()
    return row is not None
