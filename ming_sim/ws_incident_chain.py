"""事件链：加载、应用效果、创建政策议题。

从 world_simulation.py 提取。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list
from ming_sim.ws_utils import get_turn
from ming_sim.ws_regional import _apply_effects_to_region


def _load_incidents(db, turn: int) -> list[dict]:
    rows = db.conn.execute(
        "SELECT * FROM regional_incidents WHERE turn=? ORDER BY id", (turn,)
    ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "turn": int(r["turn"]),
            "region_id": str(r["region_id"]),
            "incident_type": str(r["incident_type"]),
            "tier": str(r["tier"]),
            "title": str(r["title"]),
            "summary": str(r["summary"]),
            "visibility": str(r["visibility"]),
            "status": str(r["status"]),
            "effects_applied_at": int(r["effects_applied_at"] or 0),
            "local_effects": json.loads(str(r["local_effects_json"] or "[]")),
        }
        for r in rows
    ]


def apply_local_incident_effects(db, state, incident: dict) -> list[dict]:
    """应用区域事件的局部效果到盘面。返回实际应用的变更列表。

    幂等保护：同一 (incident_id, turn) 只应用一次。中途重试/读档重放
    不会重复增减民心、动乱、道路等数值。
    """
    effects = incident.get("local_effects", [])
    if not effects:
        return []
    region_id = str(incident["region_id"])
    turn = get_turn(state)
    incident_id = incident.get("id")

    # 检查是否已经在本回合应用过效果
    if incident_id is not None:
        row = db.conn.execute(
            "SELECT effects_applied_at FROM regional_incidents WHERE id=?",
            (incident_id,),
        ).fetchone()
        if row is not None:
            applied_at = int(row["effects_applied_at"] or 0)
            if applied_at >= turn:
                return []

    _apply_effects_to_region(db, state, region_id, effects)

    # 标记已应用（与写入同事务）
    if incident_id is not None:
        db.conn.execute(
            "UPDATE regional_incidents SET effects_applied_at=? WHERE id=?",
            (turn, incident_id),
        )
    db.conn.commit()
    return effects


def build_incident_policy_issue(db, state, incident: dict) -> int | None:
    """重大事件创建一条 issues 记录，severity=8，origin_kind=regional_incident。"""
    if incident.get("tier") != "dramatic":
        return None

    turn = get_turn(state)
    incident_id = incident.get("id")
    if incident_id is None:
        return None

    # 检查是否已经创建过
    existing = db.conn.execute(
        "SELECT id FROM issues WHERE origin_kind='regional_incident' AND origin_ref=? LIMIT 1",
        (f"regional_incident:{incident_id}",),
    ).fetchone()
    if existing:
        return int(existing["id"])

    title = str(incident["title"])
    summary = str(incident["summary"])
    region_id = str(incident["region_id"])

    issue_id = db.insert_issue(
        state,
        kind="situation",
        title=f"请处置：{title}",
        origin_kind="regional_incident",
        origin_ref=f"regional_incident:{incident_id}",
        bar_value=35,
        bar_good_meaning="已平",
        bar_bad_meaning="失控",
        severity=8,
        region_hint=region_id,
        tags=["regional_incident", "dramatic"],
    )
    return issue_id
