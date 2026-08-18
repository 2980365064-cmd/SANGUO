"""郡仓、携粮与断粮结算。"""

from __future__ import annotations

import json
import math
from collections import deque
from typing import Dict, List, Optional, Set

from ming_sim.adjudication import (
    COMMON_FORBIDDEN_TEXT,
    adjudication_runtime_from_state,
    build_adjudication_pack,
    check_forbidden_fields,
    record_pending_adjudication,
    run_adjudication,
    validate_ai_proposal,
)
from ming_sim.national_focus import national_focus_modifier
from ming_sim.military import morale_delta


# ---------------------------------------------------------------------------
# 自由补给路径边界常量
# ---------------------------------------------------------------------------

FREE_SUPPLY_BOUNDS = {
    "supply_delta": (-30, 30),
    "morale_delta": (-15, 10),
    "fatigue_delta": (-10, 15),
}

SUPPLY_FORBIDDEN_TEXT = {
    **COMMON_FORBIDDEN_TEXT,
    "凭空补给": "不得凭空生成补给",
    "天降粮草": "不得凭空生成补给",
}


def _monthly_grain_cost(manpower: int) -> int:
    return max(1, math.ceil(max(0, int(manpower)) / 1000))


def _army_grain_cost(db, army) -> int:
    cost = _monthly_grain_cost(int(army["manpower"] or 0))
    if str(army["owner_power"]) == "liu_bei":
        pct = national_focus_modifier(db, "supply_cost_pct")
        cost = max(1, math.ceil(cost * (1 + pct / 100)))
    return cost


def _garrison_supply_nodes(db, owner_power: str) -> Set[str]:
    nodes: Set[str] = set()
    rows = db.conn.execute(
        """
        SELECT terms FROM diplomacy_treaties
        WHERE target=? AND treaty_type='驻军权' AND status='active'
        """,
        (owner_power,),
    ).fetchall()
    for row in rows:
        try:
            terms = json.loads(str(row["terms"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        node_id = str(terms.get("node_id") or "")
        scope = str(terms.get("scope") or "")
        if node_id and "补给" in scope:
            nodes.add(node_id)
    return nodes


def _friendly_nodes(db, owner_power: str) -> Set[str]:
    return {
        str(row["id"])
        for row in db.conn.execute(
            "SELECT id FROM administrative_cities WHERE controlled_by=?", (owner_power,)
        ).fetchall()
    }


def _city_grain_stock(db, city_id: str) -> int:
    """查询城池的粮秣库存。"""
    row = db.conn.execute(
        "SELECT grain_stock FROM administrative_cities WHERE id=?", (city_id,)
    ).fetchone()
    return max(0, int(row["grain_stock"] or 0)) if row else 0


def reachable_friendly_granary(db, army_id: str) -> Optional[str]:
    """返回路线可达且足够供应本军一个月的最近友方城池粮仓。"""
    army = db.conn.execute(
        "SELECT station_node, owner_power, manpower FROM armies WHERE id=? AND active=1",
        (army_id,),
    ).fetchone()
    if army is None:
        raise ValueError(f"军队不存在或已失效：{army_id}")
    start = str(army["station_node"])
    owner = str(army["owner_power"])
    needed = _army_grain_cost(db, army)
    friendly = _friendly_nodes(db, owner)
    guest_nodes = _garrison_supply_nodes(db, owner)
    allowed_start = start in friendly or start in guest_nodes
    if not allowed_start:
        return None

    adjacency: Dict[str, List[tuple[str, str]]] = {}
    for edge in db.conn.execute(
        "SELECT source, target, kind FROM strategic_routes"
    ).fetchall():
        source, target, kind = str(edge["source"]), str(edge["target"]), str(edge["kind"])
        adjacency.setdefault(source, []).append((target, kind))
        adjacency.setdefault(target, []).append((source, kind))

    queue = deque([start])
    visited = {start}
    while queue:
        node = queue.popleft()
        if (node in friendly or node in guest_nodes) and _city_grain_stock(db, node) >= needed:
            active_siege = db.conn.execute(
                "SELECT 1 FROM sieges WHERE target_node=? AND status='active' LIMIT 1", (node,)
            ).fetchone()
            if active_siege is None:
                return node
        for neighbor, kind in adjacency.get(node, []):
            if neighbor in visited or neighbor not in friendly:
                continue
            if kind == "关隘":
                controller = db.conn.execute(
                    "SELECT controlled_by FROM administrative_cities WHERE id=?", (neighbor,)
                ).fetchone()
                if controller is None or str(controller["controlled_by"]) != owner:
                    continue
            if db.conn.execute(
                "SELECT 1 FROM sieges WHERE target_node=? AND status='active' LIMIT 1", (neighbor,)
            ).fetchone():
                continue
            visited.add(neighbor)
            queue.append(neighbor)
    return None


def build_supply_adjudication_pack(
    db,
    state: object,
    army_id: str,
    *,
    requested_amount: int = 0,
) -> Dict[str, object]:
    army = db.conn.execute("SELECT * FROM armies WHERE id=? AND active=1", (army_id,)).fetchone()
    if army is None:
        raise ValueError(f"军队不存在或已失效：{army_id}")
    source_node = reachable_friendly_granary(db, army_id)
    grain_cost = _army_grain_cost(db, army)
    carried_cost = 20
    if str(army["owner_power"]) == "liu_bei":
        carried_cost = max(5, math.ceil(20 * (1 + national_focus_modifier(db, "supply_cost_pct") / 100)))
    source_region = None
    if source_node:
        row = db.conn.execute(
            "SELECT id, name, controlled_by, grain_stock FROM administrative_cities WHERE id=?", (source_node,)
        ).fetchone()
        source_region = {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "controlled_by": str(row["controlled_by"]),
            "grain_stock": max(0, int(row["grain_stock"] or 0)),
        } if row else None
    supply = int(army["supply"] or 0)
    starvation = int(army["starvation_turns"] or 0)
    allowed = ["granary_supply"] if source_node else []
    if supply >= carried_cost:
        allowed.append("consume_carried_supply")
    if not allowed:
        allowed.append("starvation")
    if requested_amount:
        allowed.append("execute_supply_order")
    return build_adjudication_pack(
        kind="supply",
        turn=int(getattr(state, "turn", 0)),
        subject_id=str(army_id),
        facts={
            "army": dict(army),
            "reachable_granary": source_region,
            "requested_amount": int(requested_amount or 0),
        },
        rules={
            "monthly_grain_cost": grain_cost,
            "carried_supply_cost": carried_cost,
            "starvation_rule": "断粮1月降士气；2月增疲劳；3月逃散并降低战力倍率。",
            "authority_rule": "补给只可消耗可达友方城池粮仓或本军携粮。",
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["ignore_supply", "free_supply", "free_reinforcements"],
        ai_options=[{"outcome": item, "label": item} for item in allowed],
        audit={
            "grain_cost": grain_cost,
            "supply_before": supply,
            "starvation_before": starvation,
            "granary_node": source_node or "",
        },
        source_tables=["armies", "administrative_cities", "strategic_routes", "diplomacy_treaties", "national_focus_effects"],
    )


def _validate_free_supply(pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """校验 AI 的自由补给提案是否在边界内。

    AI 通过查询工具获取补给相关数据后，输出自由评估。
    校验器确保 delta 在安全范围内，且 AI 的声称与盘面事实一致。
    """
    # 1. feasibility=impossible → 安全默认（维持现状）
    feasibility = str(proposal.get("feasibility", "medium"))
    if feasibility == "impossible":
        return {
            "supply_action": "维持现状",
            "supply_delta": 0,
            "morale_delta": 0,
            "fatigue_delta": 0,
            "feasibility": "impossible",
            "reasoning": proposal.get("reasoning", []),
            "narrative": str(proposal.get("narrative", "补给方案不可行，维持现状。")),
            "risk_note": str(proposal.get("risk_note", "")),
        }

    # 1b. 禁止字段检查
    check_forbidden_fields(proposal)

    # 2. 提取并裁剪 deltas
    supply_delta = int(proposal.get("supply_delta", 0))
    morale_delta = int(proposal.get("morale_delta", 0))
    fatigue_delta = int(proposal.get("fatigue_delta", 0))

    supply_delta = max(FREE_SUPPLY_BOUNDS["supply_delta"][0], min(FREE_SUPPLY_BOUNDS["supply_delta"][1], supply_delta))
    morale_delta = max(FREE_SUPPLY_BOUNDS["morale_delta"][0], min(FREE_SUPPLY_BOUNDS["morale_delta"][1], morale_delta))
    fatigue_delta = max(FREE_SUPPLY_BOUNDS["fatigue_delta"][0], min(FREE_SUPPLY_BOUNDS["fatigue_delta"][1], fatigue_delta))

    # 3. 禁止文本检查
    reasoning_text = " ".join(str(r) for r in proposal.get("reasoning", []))
    narrative = str(proposal.get("narrative", ""))
    combined = f"{reasoning_text}\n{narrative}"
    for marker, message in SUPPLY_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)

    # 4. 事实一致性检查
    facts = pack.get("facts", {})
    army = facts.get("army", {})
    reachable_granary = facts.get("reachable_granary")

    # 声称"粮仓可达"但实际无粮仓 → 拒绝
    if "粮仓" in reasoning_text and "可达" in reasoning_text and not reachable_granary:
        raise ValueError("AI 声称'粮仓可达'，但盘面事实不支持（无可达粮仓）。")

    # 声称"携粮充足"但实际 supply < carried_cost → 拒绝
    if "携粮充足" in reasoning_text or "粮草充裕" in reasoning_text:
        supply_before = int(army.get("supply", 0))
        carried_cost = int(facts.get("carried_supply_cost", 20))
        if supply_before < carried_cost:
            raise ValueError("AI 声称'携粮充足'，但盘面事实不支持（携粮不足月度消耗）。")

    # 声称"断粮"但实际 supply > 0 且有粮仓 → 拒绝
    if "断粮" in reasoning_text or "饥饿" in reasoning_text:
        supply_before = int(army.get("supply", 0))
        starvation_before = int(army.get("starvation_turns", 0))
        if supply_before > 0 and reachable_granary:
            raise ValueError("AI 声称'断粮'，但盘面事实不支持（有携粮且粮仓可达）。")

    # 5. supply_delta 上限受实际条件约束
    # 无粮仓且无携粮时，supply_delta 不得为正
    if not reachable_granary and int(army.get("supply", 0)) <= 0 and supply_delta > 0:
        supply_delta = 0

    return {
        "supply_action": str(proposal.get("supply_action", "自由补给评估")),
        "outcome": str(proposal.get("outcome") or proposal.get("supply_action", "")),
        "supply_delta": supply_delta,
        "morale_delta": morale_delta,
        "fatigue_delta": fatigue_delta,
        "feasibility": feasibility,
        "reasoning": proposal.get("reasoning", []),
        "narrative": narrative,
        "risk_note": str(proposal.get("risk_note", "")),
    }


def run_supply_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """补给 AI 裁判：统一走自由路径。"""
    try:
        return _validate_free_supply(pack, proposal)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}


def _log_if_changed(db, state, army_id: str, field: str, old: object, new: object, reason: str) -> None:
    if old != new:
        db.log_army_rule_change(state, army_id, field, old, new, reason, actor="补给系统")


def _supply_ai_judge_note(db, state: object, army_id: str) -> Dict[str, object]:
    llm_config, agno_db = adjudication_runtime_from_state(state)
    if llm_config is None:
        return {"status": "skipped", "reason": "未启用模型裁判。"}
    result = run_adjudication(
        db,
        state,
        "supply",
        army_id,
        llm_config=llm_config,
        agno_db=agno_db,
    )
    summary = str(result.get("proposal_summary") or result.get("audit_reason") or "")
    if result.get("status") == "pending_review":
        pending = dict(result.get("pending_adjudication") or {})
        summary = f"AI裁判暂停待核议#{int(pending.get('id') or 0)}：{pending.get('reason', '')}"
    elif result.get("status") == "validated":
        summary = f"AI裁判依据：{summary or '补给风险已验证'}"
    if summary:
        db.log_army_rule_change(state, army_id, "ai_judge", "", summary, "补给模型裁判", actor="补给系统")
        db.conn.commit()
    return result


def settle_army_supply(db, state: object, army_id: str) -> Dict[str, object]:
    """结算一军一个月口粮；函数按军队的 last_settled_turn 幂等。"""
    army = db.conn.execute("SELECT * FROM armies WHERE id=? AND active=1", (army_id,)).fetchone()
    if army is None:
        raise ValueError(f"军队不存在或已失效：{army_id}")
    turn = int(getattr(state, "turn", 0))
    if int(army["supply_last_settled_turn"] or 0) >= turn:
        return {"army_id": army_id, "source": "already_settled", "turn": turn}

    source_node = reachable_friendly_granary(db, army_id)
    grain_cost = _army_grain_cost(db, army)
    old_supply = int(army["supply"] or 0)
    old_morale = int(army["morale"] or 0)
    old_fatigue = int(army["fatigue"] or 0)
    old_manpower = int(army["manpower"] or 0)
    old_starvation = int(army["starvation_turns"] or 0)
    old_multiplier = float(army["supply_combat_multiplier"] or 1.0)

    carried_cost = 20
    if str(army["owner_power"]) == "liu_bei":
        carried_cost = max(
            5,
            math.ceil(20 * (1 + national_focus_modifier(db, "supply_cost_pct") / 100)),
        )
    if source_node:
        # 从城池 ID 获取所属郡 ID，用于调整郡级粮秣
        city_row = db.conn.execute(
            "SELECT commandery_id FROM administrative_cities WHERE id=?", (source_node,)
        ).fetchone()
        commandery_id = str(city_row["commandery_id"]) if city_row else source_node
        db.adjust_region_grain_stock(
            state, commandery_id, -grain_cost, f"供应{army['name']}本月军粮"
        )
        source = "granary"
        new_supply = old_supply
        starvation = 0
    elif old_supply >= carried_cost:
        source = "carried"
        new_supply = old_supply - carried_cost
        starvation = 0
    else:
        source = "starvation"
        new_supply = 0
        starvation = old_starvation + 1

    morale = old_morale
    fatigue = old_fatigue
    manpower = old_manpower
    combat_multiplier = 1.0 if starvation == 0 else old_multiplier
    fatigue_delta = 0
    deserted = 0
    if starvation >= 2:
        fatigue_delta = 12
        fatigue = min(100, fatigue + fatigue_delta)
    if starvation >= 3:
        deserted = max(1, round(manpower * 0.02))
        manpower = max(0, manpower - deserted)
        combat_multiplier = 0.65

    morale_change, morale_reasons = morale_delta(
        supply_source=source, starvation_turns=starvation, arrears=int(army["arrears"] or 0),
        maintenance=int(army["maintenance_per_turn"] or 0), fatigue=old_fatigue,
        discipline=int(army["discipline"] or 50), has_deputy=bool(army["deputy_commander"]),
        has_adjutant=bool(army["military_adjutant"]),
    )
    morale = max(0, min(100, old_morale + morale_change))
    reason = "、".join(morale_reasons) or ("郡仓供粮" if source_node else "消耗携粮")

    db.conn.execute(
        """
        UPDATE armies
        SET supply=?, supply_turns=?, morale=?, fatigue=?, manpower=?, starvation_turns=?,
            supply_combat_multiplier=?, supply_last_settled_turn=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (
            new_supply,
            new_supply // 20,
            morale,
            fatigue,
            manpower,
            starvation,
            combat_multiplier,
            turn,
            army_id,
        ),
    )
    _log_if_changed(db, state, army_id, "supply", old_supply, new_supply, reason)
    _log_if_changed(db, state, army_id, "morale", old_morale, morale, reason)
    _log_if_changed(db, state, army_id, "fatigue", old_fatigue, fatigue, reason)
    _log_if_changed(db, state, army_id, "manpower", old_manpower, manpower, reason)
    _log_if_changed(
        db, state, army_id, "supply_combat_multiplier", old_multiplier, combat_multiplier, reason
    )
    adjudication = _supply_ai_judge_note(db, state, army_id)
    db.conn.commit()
    result = {
        "army_id": army_id,
        "source": source,
        "granary_node": source_node or "",
        "grain_cost": grain_cost if source_node else 0,
        "supply_after": new_supply,
        "starvation_turns": starvation,
        "morale_delta": morale - old_morale,
        "fatigue_delta": fatigue - old_fatigue,
        "deserted": deserted,
        "combat_multiplier": combat_multiplier,
    }
    if adjudication.get("status") != "skipped":
        result["adjudication"] = adjudication
    return result


def _execute_supply_order(db, state: object, army_id: str, amount: int) -> Dict[str, object]:
    army = db.conn.execute("SELECT * FROM armies WHERE id=? AND active=1", (army_id,)).fetchone()
    if army is None:
        raise ValueError(f"军队不存在或已失效：{army_id}")
    source_node = reachable_friendly_granary(db, army_id)
    if not source_node:
        raise ValueError("无路线可达的友方郡仓，无法补给。")
    requested = max(1, int(amount or 20))
    capacity = max(0, 120 - int(army["supply"] or 0))
    requested = min(requested, capacity)
    if requested <= 0:
        raise ValueError("该军携粮已满。")
    units = _army_grain_cost(db, army)
    # 从城池 ID 获取所属郡 ID，用于调整郡级粮秣
    city_row = db.conn.execute(
        "SELECT commandery_id FROM administrative_cities WHERE id=?", (source_node,)
    ).fetchone()
    commandery_id = str(city_row["commandery_id"]) if city_row else source_node
    available = db.region_grain_stock(commandery_id)
    max_points = (available * 20) // units
    added = min(requested, max_points)
    if added <= 0:
        raise ValueError("郡仓余粮不足，无法装运。")
    grain_cost = math.ceil(units * added / 20)
    old_supply = int(army["supply"] or 0)
    new_supply = old_supply + added
    db.adjust_region_grain_stock(state, commandery_id, -grain_cost, f"向{army['name']}装运军粮")
    db.conn.execute(
        "UPDATE armies SET supply=?, supply_turns=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_supply, new_supply // 20, army_id),
    )
    db.log_army_rule_change(state, army_id, "supply", old_supply, new_supply, "补给军令", actor="补给系统")
    db.conn.commit()
    return {
        "army_id": army_id,
        "source_node": source_node,
        "supply_added": added,
        "grain_cost": grain_cost,
        "supply_after": new_supply,
    }


def resolve_supply_orders_for_turn(db, state: object) -> List[Dict[str, object]]:
    turn = int(getattr(state, "turn", 0))
    rows = db.conn.execute(
        "SELECT id, army_id, payload FROM army_orders WHERE turn=? AND status='issued' AND order_type='补给' ORDER BY id",
        (turn,),
    ).fetchall()
    results: List[Dict[str, object]] = []
    for row in rows:
        order_id = int(row["id"])
        try:
            payload = json.loads(str(row["payload"] or "{}"))
            result = _execute_supply_order(
                db, state, str(row["army_id"]), int(payload.get("amount") or 20)
            )
            result.update({"order_id": order_id, "status": "resolved"})
            status = "resolved"
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            result = {"order_id": order_id, "status": "rejected", "reason": str(error)}
            status = "rejected"
        db.conn.execute(
            "UPDATE army_orders SET status=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), order_id),
        )
        results.append(result)
    db.conn.commit()
    return results


def settle_all_army_supply(db, state: object) -> List[Dict[str, object]]:
    army_ids = [
        str(row["id"])
        for row in db.conn.execute("SELECT id FROM armies WHERE active=1 ORDER BY id").fetchall()
    ]
    return [settle_army_supply(db, state, army_id) for army_id in army_ids]
