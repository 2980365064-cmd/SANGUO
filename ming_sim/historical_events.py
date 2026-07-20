"""可改写历史事件卡。

事件卡只提供压力窗口和合法变体；人物、势力与世界结果仍由规则层核定。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from ming_sim.adjudication import (
    adjudication_runtime_from_state,
    build_adjudication_pack,
    record_pending_adjudication,
    run_adjudication,
    validate_ai_proposal,
)
from ming_sim.context import victory_status
from ming_sim.models import Event


LIFECYCLE = {"scheduled", "eligible", "adapted", "resolved", "superseded", "expired"}
TERMINAL_STATUSES = {"resolved", "superseded", "expired"}


def _date_index(year: int, month: int) -> int:
    return int(year) * 12 + max(1, int(month)) - 1


def _event_window(event: Event) -> tuple[int, int]:
    start = _date_index(event.trigger_year, event.trigger_month or 1)
    end_year = event.trigger_end_year or event.trigger_year
    end_month = event.trigger_end_month or 12
    return start, _date_index(end_year, end_month)


def _state_row(db, event_id: str):
    db.conn.execute(
        "INSERT OR IGNORE INTO historical_event_states (event_id, status) VALUES (?, 'scheduled')",
        (event_id,),
    )
    return db.conn.execute(
        "SELECT * FROM historical_event_states WHERE event_id=?", (event_id,)
    ).fetchone()


def _event(db, event_id: str) -> Event:
    event = db.content.event_by_id.get(event_id)
    if event is None or not event.is_historical:
        raise ValueError(f"历史事件卡不存在：{event_id}")
    return event


def _available_character(db, names: Iterable[str]) -> str:
    for name in names:
        row = db.conn.execute(
            "SELECT status FROM characters WHERE name=?", (str(name),)
        ).fetchone()
        if row is not None and str(row["status"]) == "active":
            return str(name)
    return ""


def _hard_condition_failure(db, event: Event) -> str:
    conditions = event.hard_conditions or {}
    for power_id in conditions.get("required_powers_active") or []:
        row = db.conn.execute("SELECT status FROM powers WHERE id=?", (str(power_id),)).fetchone()
        status = str(row["status"] if row is not None else "")
        terminal = status.lower() in {"defeated", "destroyed", "collapsed", "inactive"}
        terminal = terminal or any(token in status for token in ("灭亡", "瓦解", "覆灭", "已亡"))
        if row is None or terminal:
            return f"硬前提失效：势力 {power_id} 已不存续"
    return ""


def _decode_json(raw: object, fallback):
    try:
        return json.loads(str(raw or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _payload(row) -> Dict[str, object]:
    return {
        "event_id": str(row["event_id"]),
        "status": str(row["status"]),
        "participants": _decode_json(row["participants"], {}),
        "variant_id": str(row["variant_id"] or ""),
        "reason": str(row["reason"] or ""),
        "changed_turn": int(row["changed_turn"] or 0),
    }


def _record_chronicle(
    db,
    state: object,
    event: Event,
    status: str,
    reason: str,
    participants: Dict[str, str],
    *,
    variant_id: str = "",
    effects: Dict[str, object] | None = None,
) -> None:
    db.conn.execute(
        """
        INSERT OR IGNORE INTO historical_chronicle
        (event_id, turn, year, period, title, status, variant_id, summary, participants, effects)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.id,
            int(getattr(state, "turn", 0)),
            int(getattr(state, "year", 0)),
            int(getattr(state, "period", 0)),
            event.title,
            status,
            variant_id,
            reason,
            json.dumps(participants, ensure_ascii=False),
            json.dumps(effects or {}, ensure_ascii=False),
        ),
    )


def _transition(
    db,
    state: object,
    event: Event,
    status: str,
    reason: str,
    participants: Dict[str, str] | None = None,
) -> Dict[str, object]:
    if status not in LIFECYCLE:
        raise ValueError(f"非法历史事件状态：{status}")
    participants = participants or {}
    row = _state_row(db, event.id)
    old_status = str(row["status"])
    if old_status in TERMINAL_STATUSES:
        return _payload(row)
    db.conn.execute(
        """
        UPDATE historical_event_states
        SET status=?, participants=?, reason=?, changed_turn=?, updated_at=CURRENT_TIMESTAMP
        WHERE event_id=?
        """,
        (
            status,
            json.dumps(participants, ensure_ascii=False),
            reason,
            int(getattr(state, "turn", 0)),
            event.id,
        ),
    )
    if old_status != status:
        db.conn.execute(
            """
            INSERT INTO historical_event_logs
            (event_id, turn, year, period, old_status, new_status, reason, participants)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                int(getattr(state, "turn", 0)),
                int(getattr(state, "year", 0)),
                int(getattr(state, "period", 0)),
                old_status,
                status,
                reason,
                json.dumps(participants, ensure_ascii=False),
            ),
        )
    if status in {"superseded", "expired"}:
        _record_chronicle(db, state, event, status, reason, participants)
    db.conn.commit()
    return _payload(_state_row(db, event.id))


def evaluate_historical_event(db, state: object, event_id: str) -> Dict[str, object]:
    """根据当前日期、势力与人物状态推进一张卡，不自动选择结果。"""
    event = _event(db, event_id)
    row = _state_row(db, event_id)
    if str(row["status"]) in TERMINAL_STATUSES:
        return _payload(row)

    current = _date_index(int(getattr(state, "year", 0)), int(getattr(state, "period", 1)))
    start, end = _event_window(event)
    if current < start:
        return _transition(db, state, event, "scheduled", "尚未进入历史窗口")
    if current > end:
        return _transition(db, state, event, "expired", "事件窗口已过，未在本局势中成立")

    failure = _hard_condition_failure(db, event)
    if failure:
        return _transition(db, state, event, "superseded", failure)

    participants: Dict[str, str] = {}
    adaptations: list[str] = []
    for role_name, raw in (event.roles or {}).items():
        role = raw if isinstance(raw, dict) else {}
        primary = str(role.get("primary") or "")
        alternates = [str(item) for item in (role.get("alternates") or [])]
        chosen = _available_character(db, [primary, *alternates])
        if not chosen and bool(role.get("required", True)):
            reason = f"角色「{role_name}」的首选 {primary or '未设定'} 与合理候补均不可用，无合理候补"
            return _transition(db, state, event, "superseded", reason, participants)
        if chosen:
            participants[str(role_name)] = chosen
            if primary and chosen != primary:
                adaptations.append(f"{primary}不可用，改由{chosen}承担{role_name}")

    if adaptations:
        return _transition(db, state, event, "adapted", "；".join(adaptations), participants)
    return _transition(db, state, event, "eligible", "窗口与硬前提均成立", participants)


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _apply_world_effects(db, state: object, effects: Dict[str, object], event: Event) -> None:
    metrics = getattr(state, "metrics", {})
    for key, delta in (effects.get("metric_delta") or {}).items():
        metrics[str(key)] = _clamp(int(metrics.get(str(key), 50)) + int(delta))

    for region_id, owner in (effects.get("region_control") or {}).items():
        db.conn.execute(
            "UPDATE regions SET controlled_by=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (str(owner), str(region_id)),
        )

    relation = effects.get("relation_delta") or {}
    if isinstance(relation, dict) and relation.get("power"):
        target = str(relation["power"])
        first, second = db._relation_pair("liu_bei", target)
        row = db.conn.execute(
            "SELECT * FROM diplomatic_relations WHERE power_a=? AND power_b=?", (first, second)
        ).fetchone()
        if row is not None:
            updates: Dict[str, int] = {}
            for field, low, high in (("public_relation", -100, 100), ("trust", 0, 100), ("military_coordination", 0, 100)):
                if field in relation:
                    updates[field] = _clamp(int(row[field]) + int(relation[field]), low, high)
            if updates:
                clauses = ", ".join(f"{field}=?" for field in updates)
                db.conn.execute(
                    f"UPDATE diplomatic_relations SET {clauses}, updated_at=CURRENT_TIMESTAMP WHERE power_a=? AND power_b=?",
                    (*updates.values(), first, second),
                )
                for field, value in updates.items():
                    db.conn.execute(
                        """
                        INSERT INTO diplomacy_logs
                        (turn, power_a, power_b, field, old_value, new_value, reason, actor)
                        VALUES (?, ?, ?, ?, ?, ?, ?, '历史事件系统')
                        """,
                        (int(getattr(state, "turn", 0)), first, second, field, str(row[field]), str(value), event.title),
                    )


def resolve_historical_event(
    db,
    state: object,
    event_id: str,
    variant_id: str,
    *,
    adjudication_reason: str = "",
) -> Dict[str, object]:
    """以已经规则层核定的变体结案；同一张卡只会施加一次效果。"""
    event = _event(db, event_id)
    row = _state_row(db, event_id)
    if str(row["status"]) == "resolved":
        result = _payload(row)
        result["metrics_after"] = dict(getattr(state, "metrics", {}))
        result["effects"] = _decode_json(row["outcome_effects"], {})
        return result

    evaluated = evaluate_historical_event(db, state, event_id)
    if evaluated["status"] not in {"eligible", "adapted"}:
        if evaluated["status"] in {"superseded", "expired"}:
            return evaluated
        raise ValueError(f"事件当前不可结案：{evaluated['status']}")

    variants = {str(item.get("id") or ""): item for item in event.variants}
    variant = variants.get(variant_id)
    if variant is None:
        raise ValueError(f"事件变体不存在：{variant_id}")
    effects = dict(variant.get("effects") or {})
    _apply_world_effects(db, state, effects, event)
    participants = dict(evaluated.get("participants") or {})
    reason = f"采用变体「{variant.get('title') or variant_id}」"
    if adjudication_reason:
        reason = f"{reason}；AI裁判依据：{adjudication_reason}"
    db.conn.execute(
        """
        UPDATE historical_event_states
        SET status='resolved', variant_id=?, reason=?, resolved_turn=?, changed_turn=?,
            outcome_effects=?, updated_at=CURRENT_TIMESTAMP
        WHERE event_id=?
        """,
        (
            variant_id,
            reason,
            int(getattr(state, "turn", 0)),
            int(getattr(state, "turn", 0)),
            json.dumps(effects, ensure_ascii=False),
            event_id,
        ),
    )
    db.conn.execute(
        """
        INSERT INTO historical_event_logs
        (event_id, turn, year, period, old_status, new_status, reason, participants)
        VALUES (?, ?, ?, ?, ?, 'resolved', ?, ?)
        """,
        (
            event_id,
            int(getattr(state, "turn", 0)),
            int(getattr(state, "year", 0)),
            int(getattr(state, "period", 0)),
            str(evaluated["status"]),
            reason,
            json.dumps(participants, ensure_ascii=False),
        ),
    )
    _record_chronicle(
        db, state, event, "resolved", reason, participants, variant_id=variant_id, effects=effects
    )
    db.conn.commit()
    result = _payload(_state_row(db, event_id))
    result["effects"] = effects
    result["metrics_after"] = dict(getattr(state, "metrics", {}))
    return result


def historical_timeline_preview(db, state: object, months: int = 12) -> list[Dict[str, object]]:
    """只返回标题与窗口，不暴露人物、变体、死生、胜负或计策。"""
    current = _date_index(int(getattr(state, "year", 0)), int(getattr(state, "period", 1)))
    horizon = current + max(0, int(months))
    result: list[Dict[str, object]] = []
    for event in db.content.events:
        if not event.is_historical:
            continue
        start, end = _event_window(event)
        if end < current or start > horizon:
            continue
        row = _state_row(db, event.id)
        result.append(
            {
                "id": event.id,
                "title": event.title,
                "window": f"{event.trigger_year}.{event.trigger_month or 1}–{event.trigger_end_year or event.trigger_year}.{event.trigger_end_month or 12}",
                "status": str(row["status"]),
            }
        )
    db.conn.commit()
    return result


def build_world_event_adjudication_pack(
    db,
    state: object,
    event_id: str = "",
) -> Dict[str, object]:
    timeline = historical_timeline_preview(db, state, months=12)
    selected = {}
    if event_id:
        event = _event(db, event_id)
        row = _state_row(db, event_id)
        current = _date_index(int(getattr(state, "year", 0)), int(getattr(state, "period", 1)))
        start, end = _event_window(event)
        selected = {
            "event": {
                "id": event.id,
                "title": event.title,
                "event_type": event.event_type,
                "trigger_year": event.trigger_year,
                "trigger_month": event.trigger_month,
                "trigger_end_year": event.trigger_end_year,
                "trigger_end_month": event.trigger_end_month,
                "hard_conditions": event.hard_conditions,
                "variants": [
                    {
                        "id": str(item.get("id") or ""),
                        "title": str(item.get("title") or item.get("id") or ""),
                        "summary": str(item.get("summary") or item.get("description") or ""),
                    }
                    for item in event.variants
                ],
            },
            "state": _payload(row),
            "window": {
                "current": current,
                "start": start,
                "end": end,
                "is_open": start <= current <= end,
                "hard_condition_failure": _hard_condition_failure(db, event),
            },
        }
    try:
        victory = victory_status(db, state)
    except Exception:
        victory = {"status": "unknown"}
    chronicles = db.conn.execute(
        """
        SELECT event_id, turn, year, period, title, status, variant_id, summary
        FROM historical_chronicle
        ORDER BY turn DESC, id DESC LIMIT 8
        """
    ).fetchall()
    allowed = ["review_world_state", "keep_scheduled"]
    if selected:
        status = str((selected.get("state") or {}).get("status") or "")
        window = selected.get("window") or {}
        if status in {"eligible", "adapted"}:
            allowed.extend(["resolve_event_variant", "supersede_event"])
        elif status == "scheduled":
            allowed.append("wait_for_window")
            if isinstance(window, dict) and bool(window.get("is_open")) and not window.get("hard_condition_failure"):
                allowed.append("mark_eligible")
        elif status in {"resolved", "superseded", "expired"}:
            allowed.append("record_chronicle")
    return build_adjudication_pack(
        kind="world_event",
        turn=int(getattr(state, "turn", 0)),
        subject_id=str(event_id or "timeline"),
        facts={
            "timeline_preview": timeline,
            "selected_event": selected,
            "victory_status": victory,
            "recent_chronicle": [dict(item) for item in chronicles],
        },
        rules={
            "event_source_rule": "天下事件只来自 content.events、historical_event_states、historical_chronicle 与结局硬规则。",
            "lifecycle_rule": sorted(LIFECYCLE),
            "ending_rule": "结局由 victory_status 根据真实势力、地区、人物状态判断。",
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["unlisted_death", "free_power_collapse", "unvalidated_territory_change", "invent_historical_event"],
        ai_options=[{"outcome": item, "label": item} for item in allowed],
        audit={"event_id": event_id, "timeline_count": len(timeline)},
        source_tables=["historical_event_states", "historical_event_logs", "historical_chronicle", "powers", "regions", "characters"],
    )


def run_world_event_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    try:
        forbidden_fields = {"ending_status", "effects", "outcome_effects", "power_status", "character_status"}
        present_forbidden = sorted(field for field in forbidden_fields if field in proposal)
        if present_forbidden:
            raise ValueError(f"天下事件模型不得直接携带世界变更字段：{','.join(present_forbidden)}")
        text = "\n".join(str(proposal.get(key) or "") for key in ("narrative", "reason", "risk_note", "recommended_followup"))
        for marker in ("灭国", "覆灭", "天下归一", "统一天下", "病逝", "身死"):
            if marker in text:
                raise ValueError("天下事件模型不得用叙事创造灭国、终局或人物死亡。")
        selected = ((pack.get("facts") or {}).get("selected_event") or {})
        event_info = selected.get("event") if isinstance(selected, dict) else {}
        event_id = str((event_info or {}).get("id") or "")
        state_info = selected.get("state") if isinstance(selected, dict) else {}
        event_status = str((state_info or {}).get("status") or "")
        variants = {
            str(item.get("id") or "")
            for item in ((event_info or {}).get("variants") or [])
            if str(item.get("id") or "")
        }
        outcome = str(proposal.get("outcome") or "")
        variant_id = str(proposal.get("variant_id") or "")
        if outcome == "resolve_event_variant":
            if event_status not in {"eligible", "adapted"}:
                raise ValueError(f"事件当前状态不可由模型结案：{event_status}")
            if not variant_id:
                raise ValueError("天下事件结案必须提供 variant_id。")
            if variant_id not in variants:
                raise ValueError(f"事件变体不在允许范围：{variant_id}")
        if outcome == "record_chronicle" and proposal.get("changes"):
            raise ValueError("天下事件补史册只允许摘要，不允许结构化世界变更。")
        validated = validate_ai_proposal(
            pack,
            proposal,
            allowed_change_kinds=["historical_event_status", "chronicle_record"],
        )
        if variant_id:
            validated["variant_id"] = variant_id
        validated["event_id"] = event_id
        return validated
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}


def _world_event_ai_reason(result: Dict[str, object]) -> str:
    proposal = result.get("proposal") if isinstance(result.get("proposal"), dict) else {}
    validated = result.get("validated") if isinstance(result.get("validated"), dict) else {}
    parts = [
        str(proposal.get("reason") or ""),
        str(proposal.get("risk_note") or ""),
        str(proposal.get("recommended_followup") or ""),
    ]
    text = "；".join(item for item in parts if item)
    return text or str(validated.get("outcome") or "模型选择事件变体")


def _has_pending_world_event(db, state: object, event_id: str) -> bool:
    row = db.conn.execute(
        """
        SELECT 1 FROM pending_adjudications
        WHERE turn=? AND kind='world_event' AND subject_id=? AND status='pending_review'
        LIMIT 1
        """,
        (int(getattr(state, "turn", 0)), str(event_id)),
    ).fetchone()
    return row is not None


def apply_world_event_validated_adjudication(
    db,
    state: object,
    event_id: str,
    result: Dict[str, object],
) -> Dict[str, object]:
    """把已验证的天下事件模型候选映射到既有历史事件硬规则落库。"""
    if result.get("status") != "validated":
        return {"event_id": event_id, "status": str(result.get("status") or "skipped"), "adjudication": result}
    validated = result.get("validated") if isinstance(result.get("validated"), dict) else {}
    outcome = str(validated.get("outcome") or "")
    if outcome == "resolve_event_variant":
        variant_id = str(validated.get("variant_id") or "")
        resolved = resolve_historical_event(
            db,
            state,
            event_id,
            variant_id,
            adjudication_reason=_world_event_ai_reason(result),
        )
        resolved["adjudication_status"] = "validated"
        resolved["adjudication_kind"] = "world_event"
        return resolved
    return {
        "event_id": event_id,
        "status": str(outcome or "reviewed"),
        "adjudication_status": "validated",
        "adjudication_kind": "world_event",
    }


def resolve_world_events_for_turn(db, state: object) -> list[Dict[str, Any]]:
    """月末天下事件裁决：硬规则推进生命周期，模型只选择合法事件变体。"""
    llm_config, agno_db = adjudication_runtime_from_state(state)
    results: list[Dict[str, Any]] = []
    current = _date_index(int(getattr(state, "year", 0)), int(getattr(state, "period", 1)))
    for event in db.content.events:
        if not event.is_historical:
            continue
        start, end = _event_window(event)
        row = _state_row(db, event.id)
        if str(row["status"]) in TERMINAL_STATUSES:
            continue
        if current < start or current > end:
            lifecycle = evaluate_historical_event(db, state, event.id)
            if lifecycle["status"] != "scheduled":
                results.append(lifecycle)
            continue
        lifecycle = evaluate_historical_event(db, state, event.id)
        results.append(lifecycle)
        if lifecycle["status"] not in {"eligible", "adapted"}:
            continue
        if llm_config is None:
            continue
        if _has_pending_world_event(db, state, event.id):
            continue
        adjudication = run_adjudication(
            db,
            state,
            "world_event",
            event.id,
            llm_config=llm_config,
            agno_db=agno_db,
        )
        if adjudication.get("status") == "pending_review":
            pending = dict(adjudication.get("pending_adjudication") or {})
            results.append({
                "event_id": event.id,
                "status": "pending_review",
                "pending_adjudication": pending,
                "reason": str(pending.get("reason") or ""),
            })
            continue
        applied = apply_world_event_validated_adjudication(db, state, event.id, adjudication)
        results.append(applied)
    return results
