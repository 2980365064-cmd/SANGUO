"""world_random：存档级确定性随机流。

所有世界模拟的随机抽取必须经由此模块，禁止其他世界模块直接调用 random。
同一 (turn, domain, subject_id, draw_kind) 重复调用返回已落库结果，保证读档/重放一致。

铁律：
  - 每个存档独立 campaign_seed_v2（kv_store）；新档 32 字节十六进制，旧档用稳定材料生成一次。
  - derive_seed 由 campaign_seed + turn + domain + subject_id + draw_kind 的 SHA-256 生成。
  - draw_int / draw_weighted 先查 world_random_draws；命中则直接返回，不重新抽取。
  - metadata_json 只保存审计材料，禁止作为规则输入反向覆盖已落库结果。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from typing import Any, Dict, List, Optional


CAMPAIGN_SEED_KEY = "campaign_seed_v2"


def ensure_campaign_seed(db) -> str:
    """确保 kv_store 里有 campaign_seed_v2；返回种子值。

    新档：生成 32 字节十六进制随机值。
    旧档：用 scenario_id + 开局 year/period + powers/regions 稳定排序摘要的 SHA-256 生成一次。
    """
    existing = db.kv_get(CAMPAIGN_SEED_KEY)
    if existing:
        return existing

    # 尝试用稳定材料生成旧档种子
    seed_value = _generate_stable_seed(db)
    db.kv_set(CAMPAIGN_SEED_KEY, seed_value)

    # 新档自动启用地缘反应随机性（v1）
    # 旧档升级时不设置，保持旧规则链行为
    db.kv_set("geopolitical_rng_v1", "1")

    return seed_value


def _generate_stable_seed(db) -> str:
    """用稳定材料生成旧档种子。

    区分新档和旧档：
      - game_state 已有数据 → 旧档迁移，用稳定材料派生。
      - game_state 无数据 → 新档，用 os.urandom。
    """
    has_game_state = db.conn.execute(
        "SELECT COUNT(*) FROM game_state"
    ).fetchone()[0] > 0

    if not has_game_state:
        # 新档：32 字节真随机
        return os.urandom(32).hex()

    materials: list[str] = []

    # scenario_id
    scenario_id = db.kv_get("scenario_id") or "unknown"
    materials.append(f"scenario:{scenario_id}")

    # 开局 year/period：从 game_state 读取
    row = db.conn.execute("SELECT year, period FROM game_state WHERE id=1").fetchone()
    if row:
        materials.append(f"year:{row['year']}:period:{row['period']}")

    # powers 稳定排序摘要
    powers = db.conn.execute(
        "SELECT id, status FROM powers ORDER BY id"
    ).fetchall()
    powers_summary = ";".join(f"{r['id']}={r['status']}" for r in powers)
    materials.append(f"powers:{powers_summary}")

    # regions 稳定排序摘要
    regions = db.conn.execute(
        "SELECT id, controlled_by FROM regions ORDER BY id"
    ).fetchall()
    regions_summary = ";".join(f"{r['id']}={r['controlled_by']}" for r in regions)
    materials.append(f"regions:{regions_summary}")

    raw = "|".join(materials)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def derive_seed(
    db,
    *,
    turn: int,
    domain: str,
    subject_id: str,
    draw_kind: str = "",
) -> str:
    """从 campaign_seed + turn + domain + subject_id + draw_kind 派生抽取种子。"""
    campaign_seed = ensure_campaign_seed(db)
    components = f"{campaign_seed}:{turn}:{domain}:{subject_id}:{draw_kind}"
    return hashlib.sha256(components.encode("utf-8")).hexdigest()


def draw_int(
    db,
    *,
    state,
    domain: str,
    subject_id: str,
    low: int,
    high: int,
    draw_kind: str = "int",
    metadata: dict[str, object] | None = None,
) -> int:
    """确定性整数抽取 [low, high]。同 key 重复调用返回已落库结果。

    若同 key 已有记录但 low/high 与当前不一致，抛 ValueError，
    防止规则版本漂移静默复用旧值。
    """
    turn = state.turn
    derived = derive_seed(db, turn=turn, domain=domain, subject_id=subject_id, draw_kind=draw_kind)

    # 先查库
    existing = db.conn.execute(
        "SELECT roll_value, low_value, high_value FROM world_random_draws "
        "WHERE turn=? AND domain=? AND subject_id=? AND draw_kind=?",
        (turn, domain, subject_id, draw_kind),
    ).fetchone()
    if existing is not None:
        stored_low = int(existing["low_value"]) if existing["low_value"] is not None else None
        stored_high = int(existing["high_value"]) if existing["high_value"] is not None else None
        if stored_low is not None and stored_high is not None:
            if stored_low != low or stored_high != high:
                raise ValueError(
                    f"draw_int 范围不兼容: key=(turn={turn}, domain={domain}, "
                    f"subject_id={subject_id}, draw_kind={draw_kind}), "
                    f"已存 low={stored_low}, high={stored_high}, "
                    f"当前 low={low}, high={high}"
                )
        return existing["roll_value"]

    # 用派生种子播种本地 RNG
    rng = random.Random(int(derived, 16))
    roll = rng.randint(low, high)

    # 落库
    db.conn.execute(
        """
        INSERT INTO world_random_draws
            (turn, domain, subject_id, derived_seed, draw_kind,
             low_value, high_value, roll_value, choice_key,
             candidates_snapshot_json, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '[]', ?)
        """,
        (
            turn, domain, subject_id, derived, draw_kind,
            low, high, roll,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    db.conn.commit()
    return roll


def _write_audit_warning(db, row_id: int, existing_metadata_json: str, reason: str) -> None:
    """向已存抽取记录的 metadata_json 追加 audit_warning 字段。

    不覆盖原有 metadata，仅新增 "audit_warning" 键。
    用于月报审计追踪为何某个随机步骤返回 None。
    """
    try:
        metadata = json.loads(str(existing_metadata_json or "{}"))
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    metadata["audit_warning"] = reason
    db.conn.execute(
        "UPDATE world_random_draws SET metadata_json=? WHERE id=?",
        (json.dumps(metadata, ensure_ascii=False), row_id),
    )
    db.conn.commit()


def draw_weighted(
    db,
    *,
    state,
    domain: str,
    subject_id: str,
    choices: list[dict[str, object]],
    weight_key: str = "weight",
    draw_kind: str = "weighted",
    metadata: dict[str, object] | None = None,
) -> dict[str, object] | None:
    """按权重确定性抽取一项。同 key 重复调用返回已落库结果。

    choices 为空时返回 None。每项必须有 weight_key 字段（正整数/浮点）。
    候选快照必须与落库时记录的完整 [{key, weight}] 规范化快照一致；
    若不一致（键变化、权重变化、或旧记录无快照），返回 None 并将
    结构化 audit_warning 写入 metadata_json，不能静默退化。
    """
    if not choices:
        return None

    turn = state.turn
    derived = derive_seed(db, turn=turn, domain=domain, subject_id=subject_id, draw_kind=draw_kind)

    # 当前候选规范化快照（用于比对）
    current_snapshot_items = sorted(
        [{"key": _choice_key(c), "weight": float(c.get(weight_key, 0))} for c in choices],
        key=lambda x: x["key"],
    )
    current_snapshot = json.dumps(current_snapshot_items, ensure_ascii=False, sort_keys=True)

    # 先查库
    existing = db.conn.execute(
        "SELECT id, choice_key, candidates_snapshot_json, metadata_json FROM world_random_draws "
        "WHERE turn=? AND domain=? AND subject_id=? AND draw_kind=?",
        (turn, domain, subject_id, draw_kind),
    ).fetchone()
    if existing is not None:
        chosen_key = str(existing["choice_key"] or "")

        # 解析已存快照
        try:
            stored_items = json.loads(str(existing["candidates_snapshot_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            stored_items = []

        # 规范化已存快照（按 key 排序）
        stored_normalized = sorted(
            [{"key": str(item.get("key", "")), "weight": float(item.get("weight", 0))}
             for item in stored_items if isinstance(item, dict) and "key" in item],
            key=lambda x: x["key"],
        )

        if not stored_normalized:
            # 旧档无快照记录 → 审计不兼容，明确返回 None
            _write_audit_warning(
                db, int(existing["id"]), existing["metadata_json"],
                f"候选快照缺失（旧档记录），无法验证兼容性: domain={domain}, "
                f"subject_id={subject_id}, draw_kind={draw_kind}",
            )
            return None

        if stored_normalized != current_snapshot_items:
            # 快照不兼容（键或权重变化）→ 返回 None，不静默复用
            stored_keys = {item["key"] for item in stored_normalized}
            current_keys = {item["key"] for item in current_snapshot_items}
            if stored_keys != current_keys:
                reason = (
                    f"候选键不兼容: 已存={sorted(stored_keys)}, "
                    f"当前={sorted(current_keys)}"
                )
            else:
                reason = (
                    f"候选权重不兼容（键相同但权重已变）: domain={domain}, "
                    f"subject_id={subject_id}, draw_kind={draw_kind}"
                )
            _write_audit_warning(db, int(existing["id"]), existing["metadata_json"], reason)
            return None

        # 从当前候选里找原选择
        for choice in choices:
            if _choice_key(choice) == chosen_key:
                return choice
        # 快照一致但具体项找不到（理论上不应发生）
        return None

    # 按权重抽取
    weights = [float(c.get(weight_key, 0)) for c in choices]
    total = sum(weights)
    if total <= 0:
        # 等权退化
        rng = random.Random(int(derived, 16))
        idx = rng.randint(0, len(choices) - 1)
    else:
        rng = random.Random(int(derived, 16))
        r = rng.random() * total
        cumulative = 0.0
        idx = len(choices) - 1
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                idx = i
                break

    chosen = choices[idx]
    chosen_key = _choice_key(chosen)

    # 落库（含候选快照）
    db.conn.execute(
        """
        INSERT INTO world_random_draws
            (turn, domain, subject_id, derived_seed, draw_kind,
             low_value, high_value, roll_value, choice_key,
             candidates_snapshot_json, metadata_json)
        VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
        """,
        (
            turn, domain, subject_id, derived, draw_kind,
            chosen_key,
            current_snapshot,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    db.conn.commit()
    return chosen


def _choice_key(choice: dict[str, object]) -> str:
    """从候选项提取稳定键：优先用 'key' 字段，否则用 'type'/'kind'/'id'，最后用 JSON 序列化。"""
    for field in ("key", "type", "kind", "id", "incident_type"):
        if field in choice:
            return str(choice[field])
    return json.dumps(choice, sort_keys=True, ensure_ascii=False)
