"""国策书、国策点与郡级单项投资。"""

from __future__ import annotations

import json
from typing import Dict

from ming_sim.adjudication import (
    COMMON_FORBIDDEN_TEXT,
    adjudication_runtime_from_state,
    build_adjudication_pack,
    check_forbidden_fields,
    record_pending_adjudication,
    run_adjudication,
    validate_ai_proposal,
)
from ming_sim.government import office_effect


FOCUS_CATEGORIES = {"政治", "军事", "经济"}
INVESTMENT_CATEGORIES = {
    "屯田粮仓", "城防守备", "军备练兵", "水军船政", "道路粮道", "民政市易",
}
KEY_OFFICES = {
    "政治": "civil_chief",
    "军事": "main_commander",
    "经济": "finance_chief",
}

# ---------------------------------------------------------------------------
# 自由投资路径边界常量
# ---------------------------------------------------------------------------

FREE_INVESTMENT_BOUNDS = {
    "progress_delta": (-5, 15),
    "resource_cost_modifier": (0.5, 1.5),
}

INVESTMENT_FORBIDDEN_TEXT = {
    **COMMON_FORBIDDEN_TEXT,
}


def focus_points(db, state: object, category: str) -> int:
    if category not in FOCUS_CATEGORIES:
        raise ValueError(f"未知国策类别：{category}")
    points = 1
    metrics = getattr(state, "metrics", {})
    if category == "政治" and int(metrics.get("士族支持", 0)) >= 65:
        points += 1
    elif category == "军事":
        manpower = db.conn.execute(
            "SELECT COALESCE(SUM(manpower), 0) FROM armies WHERE owner_power='liu_bei' AND active=1"
        ).fetchone()[0]
        if int(manpower or 0) >= 40000:
            points += 1
    elif category == "经济" and int(metrics.get("民望", 0)) >= 65:
        points += 1

    office = office_effect(db, KEY_OFFICES[category])
    key_person = not bool(office["vacant"]) and int(office.get("ability_value") or 0) >= 85
    active = db.conn.execute(
        "SELECT focus_id FROM national_focus_progress WHERE category=? AND status='active'",
        (category,),
    ).fetchone()
    special_focus = bool(
        active
        and db.content.national_focuses.get(str(active["focus_id"]), {}).get("point_bonus")
    )
    if key_person or special_focus:
        points += 1
    return max(0, min(3, points))


def start_focus(db, state: object, focus_id: str) -> Dict[str, object]:
    definition = db.content.national_focuses.get(focus_id)
    if definition is None:
        raise ValueError(f"未知国策：{focus_id}")
    category = str(definition["category"])
    active = db.conn.execute(
        "SELECT focus_id FROM national_focus_progress WHERE category=? AND status='active'",
        (category,),
    ).fetchone()
    if active and str(active["focus_id"]) != focus_id:
        raise ValueError(f"同类国策已有进行项：{active['focus_id']}")
    completed = {
        str(row["focus_id"])
        for row in db.conn.execute(
            "SELECT focus_id FROM national_focus_progress WHERE status='completed'"
        ).fetchall()
    }
    unmet = [str(item) for item in (definition.get("prerequisites") or []) if str(item) not in completed]
    if unmet:
        raise ValueError(f"国策前置未完成：{','.join(unmet)}")
    existing = db.conn.execute(
        "SELECT * FROM national_focus_progress WHERE focus_id=?", (focus_id,)
    ).fetchone()
    if existing and str(existing["status"]) == "completed":
        return dict(existing)
    turn = int(getattr(state, "turn", 0))
    db.conn.execute(
        """
        INSERT INTO national_focus_progress
        (focus_id, category, progress, status, started_turn, last_turn)
        VALUES (?, ?, 0, 'active', ?, 0)
        ON CONFLICT(focus_id) DO UPDATE SET status='active', updated_at=CURRENT_TIMESTAMP
        """,
        (focus_id, category, turn),
    )
    db.conn.commit()
    return {
        "focus_id": focus_id,
        "category": category,
        "progress": 0,
        "cost": int(definition["cost"]),
        "status": "active",
    }


def _apply_focus_effects(db, state: object, focus_id: str, definition: Dict[str, object]) -> None:
    effects = definition.get("effects") or {}
    if not isinstance(effects, dict):
        return
    turn = int(getattr(state, "turn", 0))
    for key, delta in (effects.get("metric_delta") or {}).items():
        exists = db.conn.execute(
            "SELECT 1 FROM national_focus_effects WHERE focus_id=? AND effect_key=? AND effect_kind='metric'",
            (focus_id, str(key)),
        ).fetchone()
        if exists:
            continue
        old = int(state.metrics.get(str(key), 50))
        state.metrics[str(key)] = max(0, min(100, old + int(delta)))
        db.conn.execute(
            "INSERT INTO national_focus_effects VALUES (?, ?, ?, 'metric', ?)",
            (focus_id, str(key), float(delta), turn),
        )
    for key, value in (effects.get("modifiers") or {}).items():
        db.conn.execute(
            """
            INSERT OR IGNORE INTO national_focus_effects
            (focus_id, effect_key, effect_value, effect_kind, applied_turn)
            VALUES (?, ?, ?, 'modifier', ?)
            """,
            (focus_id, str(key), float(value), turn),
        )


def advance_focus(db, state: object, focus_id: str) -> Dict[str, object]:
    definition = db.content.national_focuses.get(focus_id)
    if definition is None:
        raise ValueError(f"未知国策：{focus_id}")
    row = db.conn.execute(
        "SELECT * FROM national_focus_progress WHERE focus_id=?", (focus_id,)
    ).fetchone()
    if row is None:
        raise ValueError("国策尚未开始。")
    if str(row["status"]) == "completed":
        return {**dict(row), "cost": int(definition["cost"])}
    turn = int(getattr(state, "turn", 0))
    if int(row["last_turn"] or 0) >= turn:
        return {**dict(row), "cost": int(definition["cost"])}
    points = focus_points(db, state, str(definition["category"]))
    before = int(row["progress"] or 0)
    after = min(int(definition["cost"]), before + points)
    status = "completed" if after >= int(definition["cost"]) else "active"
    db.conn.execute(
        """
        UPDATE national_focus_progress
        SET progress=?, status=?, last_turn=?,
            completed_turn=CASE WHEN ?='completed' THEN ? ELSE completed_turn END,
            updated_at=CURRENT_TIMESTAMP
        WHERE focus_id=?
        """,
        (after, status, turn, status, turn, focus_id),
    )
    db.conn.execute(
        """
        INSERT INTO national_focus_logs
        (turn, focus_id, points, progress_before, progress_after, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, '按本回合国策点推进')
        """,
        (turn, focus_id, points, before, after, status),
    )
    if status == "completed":
        _apply_focus_effects(db, state, focus_id, definition)
    db.conn.commit()
    return {
        "focus_id": focus_id,
        "category": str(definition["category"]),
        "points": points,
        "progress": after,
        "cost": int(definition["cost"]),
        "status": status,
    }


def national_focus_modifier(db, effect_key: str) -> float:
    row = db.conn.execute(
        """
        SELECT COALESCE(SUM(effect_value), 0) AS total FROM national_focus_effects
        WHERE effect_kind='modifier' AND effect_key=?
        """,
        (effect_key,),
    ).fetchone()
    return float(row["total"] or 0)


def advance_all_focuses(db, state: object) -> list[Dict[str, object]]:
    focus_ids = [
        str(row["focus_id"])
        for row in db.conn.execute(
            "SELECT focus_id FROM national_focus_progress WHERE status='active' ORDER BY category"
        ).fetchall()
    ]
    return [advance_focus(db, state, focus_id) for focus_id in focus_ids]


def start_region_investment(db, state: object, region_id: str, category: str) -> Dict[str, object]:
    if category not in INVESTMENT_CATEGORIES:
        raise ValueError(f"未知地区投资方向：{category}")
    region = db.conn.execute(
        "SELECT controlled_by FROM regions WHERE id=?", (region_id,)
    ).fetchone()
    if region is None:
        raise ValueError(f"地区不存在：{region_id}")
    if str(region["controlled_by"]) != "liu_bei":
        raise ValueError("只能投资刘备政权实际控制的地区。")
    active = db.conn.execute(
        "SELECT category FROM region_investments WHERE region_id=? AND status='active'",
        (region_id,),
    ).fetchone()
    if active:
        raise ValueError(f"每郡同一时间只能推进一项投资：{active['category']}")
    turn = int(getattr(state, "turn", 0))
    db.conn.execute(
        """
        INSERT INTO region_investments
        (region_id, category, progress, status, started_turn, last_turn, completed_turn)
        VALUES (?, ?, 0, 'active', ?, 0, NULL)
        ON CONFLICT(region_id) DO UPDATE SET
            category=excluded.category, progress=0, status='active',
            started_turn=excluded.started_turn, last_turn=0, completed_turn=NULL,
            updated_at=CURRENT_TIMESTAMP
        """,
        (region_id, category, turn),
    )
    db.conn.commit()
    return {"region_id": region_id, "category": category, "progress": 0, "status": "active"}


def build_region_investment_adjudication_pack(
    db,
    state: object,
    region_id: str,
    category: str = "",
) -> Dict[str, object]:
    row = db.conn.execute(
        "SELECT id, name, controlled_by, public_support, unrest, fiscal, status FROM regions WHERE id=?",
        (region_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"地区不存在：{region_id}")
    fiscal = json.loads(str(row["fiscal"] or "{}"))
    active = db.conn.execute(
        "SELECT * FROM region_investments WHERE region_id=?",
        (region_id,),
    ).fetchone()
    requested = str(category or (active["category"] if active else ""))
    resource_cost = 2
    current_resource = int(getattr(state, "metrics", {}).get("军资", 0))
    speed_bonus = national_focus_modifier(db, "investment_speed_pct")
    step = max(1, round(25 * (1 + speed_bonus / 100)))
    allowed = ["view_region"]
    if str(row["controlled_by"]) == "liu_bei" and not active and requested in INVESTMENT_CATEGORIES:
        allowed.append("start_investment")
    if active and str(active["status"]) == "active":
        allowed.append("advance_investment" if current_resource >= resource_cost else "stall_investment")
    return build_adjudication_pack(
        kind="region_investment",
        turn=int(getattr(state, "turn", 0)),
        subject_id=str(region_id),
        facts={
            "region": {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "controlled_by": str(row["controlled_by"]),
                "public_support": int(row["public_support"] or 0),
                "unrest": int(row["unrest"] or 0),
                "status": str(row["status"]),
                "granary": int(fiscal.get("granary") or fiscal.get("grain_stock") or 0),
                "grain_output": int(fiscal.get("grain_output") or 0),
                "fortification": int(fiscal.get("fortification") or 0),
                "commerce_tax": int(fiscal.get("commerce_tax") or 0),
                "transport": int(fiscal.get("transport") or 0),
                "shipbuilding": int(fiscal.get("shipbuilding") or 0),
            },
            "active_investment": dict(active) if active else {},
            "requested_category": requested,
            "metrics": {"军资": current_resource},
        },
        rules={
            "investment_categories": sorted(INVESTMENT_CATEGORIES),
            "resource_cost_per_month": resource_cost,
            "monthly_progress_step": step,
            "control_rule": "只能投资刘备政权实际控制的地区。",
            "single_active_rule": "每郡同一时间只能推进一项投资。",
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["free_region_effect", "unvalidated_territory_change", "ignore_resource_cost"],
        ai_options=[{"outcome": item, "label": item} for item in allowed],
        audit={
            "speed_bonus_pct": speed_bonus,
            "projected_progress_step": step,
            "resource_cost": resource_cost,
        },
        source_tables=["regions", "region_investments", "region_investment_logs", "national_focus_effects", "metrics"],
    )


def _validate_free_region_investment(pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """校验 AI 的自由投资提案是否在边界内。

    AI 通过查询工具获取区域数据后，输出自由评估。
    校验器确保 delta 在安全范围内，且 AI 的声称与盘面事实一致。
    """
    # 1. feasibility=impossible → 安全默认（观望）
    feasibility = str(proposal.get("feasibility", "medium"))
    if feasibility == "impossible":
        return {
            "investment_action": "观望",
            "investment_category": str(proposal.get("investment_category", "")),
            "progress_delta": 0,
            "resource_cost_modifier": 1.0,
            "feasibility": "impossible",
            "reasoning": proposal.get("reasoning", []),
            "narrative": str(proposal.get("narrative", "投资方案不可行，暂且观望。")),
            "risk_note": str(proposal.get("risk_note", "")),
        }

    # 1b. 禁止字段检查
    check_forbidden_fields(proposal)

    # 2. 提取并裁剪 deltas
    progress_delta = int(proposal.get("progress_delta", 0))
    resource_cost_modifier = float(proposal.get("resource_cost_modifier", 1.0))

    progress_delta = max(FREE_INVESTMENT_BOUNDS["progress_delta"][0], min(FREE_INVESTMENT_BOUNDS["progress_delta"][1], progress_delta))
    resource_cost_modifier = max(FREE_INVESTMENT_BOUNDS["resource_cost_modifier"][0], min(FREE_INVESTMENT_BOUNDS["resource_cost_modifier"][1], resource_cost_modifier))

    # 3. 投资类别合法性
    category = str(proposal.get("investment_category", ""))
    if category and category not in INVESTMENT_CATEGORIES:
        raise ValueError(f"投资类别不在允许范围：{category}")

    # 4. 禁止文本检查
    reasoning_text = " ".join(str(r) for r in proposal.get("reasoning", []))
    narrative = str(proposal.get("narrative", ""))
    combined = f"{reasoning_text}\n{narrative}"
    for marker, message in INVESTMENT_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)

    # 5. 事实一致性检查
    facts = pack.get("facts", {})
    region = facts.get("region", {})
    metrics = facts.get("metrics", {})

    # 声称"民心高涨" → 检查 public_support
    if "民心高涨" in reasoning_text or "百姓安居" in reasoning_text:
        public_support = int(region.get("public_support", 50))
        if public_support < 60:
            raise ValueError("AI 声称'民心高涨'，但盘面事实不支持（民心<60）。")

    # 声称"资源充裕" → 检查军资
    if "资源充裕" in reasoning_text or "军资充足" in reasoning_text:
        junzi = int(metrics.get("军资", 0))
        if junzi < 30:
            raise ValueError("AI 声称'资源充裕'，但盘面事实不支持（军资<30）。")

    # 声称"动乱平息" → 检查 unrest
    if "动乱平息" in reasoning_text or "治安良好" in reasoning_text:
        unrest = int(region.get("unrest", 0))
        if unrest > 30:
            raise ValueError("AI 声称'动乱平息'，但盘面事实不支持（unrest>30）。")

    # 6. 区域不被控制时，progress_delta 不得为正
    controlled_by = str(region.get("controlled_by", ""))
    if controlled_by != "liu_bei" and progress_delta > 0:
        progress_delta = 0

    return {
        "investment_action": str(proposal.get("investment_action", "自由投资评估")),
        "outcome": str(proposal.get("outcome") or proposal.get("investment_action", "")),
        "investment_category": category,
        "progress_delta": progress_delta,
        "resource_cost_modifier": round(resource_cost_modifier, 2),
        "feasibility": feasibility,
        "reasoning": proposal.get("reasoning", []),
        "narrative": narrative,
        "risk_note": str(proposal.get("risk_note", "")),
    }


def run_region_investment_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """区域投资 AI 裁判：统一走自由路径。"""
    try:
        return _validate_free_region_investment(pack, proposal)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}


def _region_investment_ai_note(db, state: object, region_id: str, category: str) -> Dict[str, object]:
    llm_config, agno_db = adjudication_runtime_from_state(state)
    if llm_config is None:
        return {"status": "skipped", "reason": "未启用模型裁判。"}
    result = run_adjudication(
        db,
        state,
        "region_investment",
        region_id,
        llm_config=llm_config,
        agno_db=agno_db,
        category=category,
    )
    if result.get("status") == "validated":
        proposal = dict(result.get("proposal") or {})
        return {
            "status": "validated",
            "outcome": str(proposal.get("outcome") or ""),
            "reason": str(proposal.get("reason") or ""),
            "risk_note": str(proposal.get("risk_note") or ""),
        }
    if result.get("status") == "pending_review":
        pending = dict(result.get("pending_adjudication") or {})
        return {
            "status": "pending_review",
            "pending_adjudication_id": int(pending.get("id") or 0),
            "reason": str(pending.get("reason") or ""),
        }
    return {"status": str(result.get("status") or "skipped"), "reason": str(result.get("reason") or "")}


def _investment_log_reason(ai_note: Dict[str, object]) -> str:
    if ai_note.get("status") == "validated":
        detail = str(ai_note.get("reason") or ai_note.get("outcome") or "已验证")
        return f"地区预算推进；AI裁判依据：{detail}"
    if ai_note.get("status") == "pending_review":
        return f"地区预算推进；AI裁判暂停待核议#{ai_note.get('pending_adjudication_id', 0)}：{ai_note.get('reason', '')}"
    return "地区预算推进"


def _apply_investment_effect(db, state: object, region_id: str, category: str) -> None:
    row = db.conn.execute("SELECT fiscal, public_support FROM regions WHERE id=?", (region_id,)).fetchone()
    fiscal = json.loads(str(row["fiscal"] or "{}"))
    if category == "屯田粮仓":
        focus_bonus = national_focus_modifier(db, "grain_output_pct")
        fiscal["grain_output"] = round(
            int(fiscal.get("grain_output") or 0) * (1.10 + focus_bonus / 100)
        )
        fiscal["grain_stock"] = int(fiscal.get("grain_stock") or 0) + 50
        fiscal["granary"] = fiscal["grain_stock"]
    elif category == "城防守备":
        fiscal["fortification"] = min(100, int(fiscal.get("fortification") or 0) + 10)
    elif category == "军备练兵":
        db.conn.execute(
            "UPDATE armies SET training=MIN(100, training+5) WHERE station_node=? AND owner_power='liu_bei' AND active=1",
            (region_id,),
        )
    elif category == "水军船政":
        fiscal["shipbuilding"] = min(100, int(fiscal.get("shipbuilding") or 0) + 15)
    elif category == "道路粮道":
        fiscal["transport"] = min(100, int(fiscal.get("transport") or 0) + 10)
    elif category == "民政市易":
        fiscal["commerce_tax"] = int(fiscal.get("commerce_tax") or 0) + 2
        db.conn.execute(
            "UPDATE regions SET public_support=MIN(100, public_support+5) WHERE id=?", (region_id,)
        )
    db.conn.execute(
        "UPDATE regions SET fiscal=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(fiscal, ensure_ascii=False), region_id),
    )


def advance_region_investment(db, state: object, region_id: str) -> Dict[str, object]:
    row = db.conn.execute(
        "SELECT * FROM region_investments WHERE region_id=?", (region_id,)
    ).fetchone()
    if row is None or str(row["status"]) != "active":
        if row is not None:
            return dict(row)
        raise ValueError("该郡没有进行中的投资。")
    turn = int(getattr(state, "turn", 0))
    if int(row["last_turn"] or 0) >= turn:
        return dict(row)
    resource_cost = 2
    current_resource = int(state.metrics.get("军资", 0))
    if current_resource < resource_cost:
        raise ValueError("军资不足，地区投资无法推进。")
    state.metrics["军资"] = current_resource - resource_cost
    before = int(row["progress"] or 0)
    speed_bonus = national_focus_modifier(db, "investment_speed_pct")
    step = max(1, round(25 * (1 + speed_bonus / 100)))
    after = min(100, before + step)
    status = "completed" if after >= 100 else "active"
    ai_note = _region_investment_ai_note(db, state, region_id, str(row["category"]))
    db.conn.execute(
        """
        UPDATE region_investments
        SET progress=?, status=?, last_turn=?,
            completed_turn=CASE WHEN ?='completed' THEN ? ELSE completed_turn END,
            updated_at=CURRENT_TIMESTAMP
        WHERE region_id=?
        """,
        (after, status, turn, status, turn, region_id),
    )
    db.conn.execute(
        """
        INSERT INTO region_investment_logs
        (turn, region_id, category, progress_before, progress_after, resource_cost, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (turn, region_id, str(row["category"]), before, after, resource_cost, status, _investment_log_reason(ai_note)),
    )
    if status == "completed":
        _apply_investment_effect(db, state, region_id, str(row["category"]))
    db.conn.commit()
    result = {
        "region_id": region_id,
        "category": str(row["category"]),
        "progress": after,
        "status": status,
        "resource_cost": resource_cost,
    }
    if ai_note.get("status") != "skipped":
        result["adjudication"] = ai_note
    return result


def advance_all_region_investments(db, state: object) -> list[Dict[str, object]]:
    region_ids = [
        str(row["region_id"])
        for row in db.conn.execute(
            "SELECT region_id FROM region_investments WHERE status='active' ORDER BY region_id"
        ).fetchall()
    ]
    results: list[Dict[str, object]] = []
    for region_id in region_ids:
        try:
            results.append(advance_region_investment(db, state, region_id))
        except ValueError as error:
            results.append({"region_id": region_id, "status": "stalled", "reason": str(error)})
    return results
