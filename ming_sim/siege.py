"""多回合围城与救援状态机。行动范围按城池直连路线判断。"""

from __future__ import annotations

import json
import math
from typing import Dict, List, Tuple

from ming_sim.adjudication import (
    COMMON_FORBIDDEN_TEXT,
    adjudication_runtime_from_state,
    build_adjudication_pack,
    check_forbidden_fields,
    record_pending_adjudication,
    run_adjudication,
    validate_ai_proposal,
)


# ---------------------------------------------------------------------------
# 自由围城路径边界常量
# ---------------------------------------------------------------------------

FREE_SIEGE_BOUNDS = {
    "progress_delta": (-10, 20),
    "casualty_pct": (0, 30),
}

SIEGE_FORBIDDEN_TEXT = {
    **COMMON_FORBIDDEN_TEXT,
    "破城屠城": "不得写屠城",
    "屠城": "不得写屠城",
}
from ming_sim.sanguo_rules import ArmyOrderError, calculate_siege_progress, find_strategic_route, require_city_node


def _json_dict(raw: object) -> Dict[str, object]:
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: object) -> List[str]:
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value = []
    return [str(item) for item in value] if isinstance(value, list) else []


def _route_between(db, source: str, target: str):
    """查询两城池节点之间的直连路线；不存在返回 None。"""
    try:
        return find_strategic_route(db, source, target)
    except ArmyOrderError:
        return None


def _city_target(db, raw_target: str):
    """接受新 city_id，并将旧军令中的郡节点确定性映射至郡治城。"""
    city = db.conn.execute(
        "SELECT id, commandery_id, controlled_by, name, fortification, grain_stock FROM administrative_cities WHERE id=?",
        (raw_target,),
    ).fetchone()
    if city is not None:
        return city
    return db.conn.execute(
        "SELECT id, commandery_id, controlled_by, name, fortification, grain_stock FROM administrative_cities WHERE commandery_id=? AND is_commandery_capital=1",
        (raw_target,),
    ).fetchone()


def validate_siege_target(db, army_id: str, target_node: str) -> Dict[str, str]:
    army = db.conn.execute(
        "SELECT id, station_node, owner_power, supply, manpower FROM armies WHERE id=? AND active=1",
        (army_id,),
    ).fetchone()
    if army is None:
        raise ArmyOrderError(f"军队不存在或已失效：{army_id}")
    source = str(army["station_node"])
    require_city_node(source, label="出发节点")
    target = _city_target(db, target_node)
    if target is None:
        raise ArmyOrderError(f"目标城池不存在：{target_node}")
    target_city_id = str(target["id"])
    require_city_node(target_city_id, label="目标城池")
    if source == target_city_id:
        raise ArmyOrderError("不可围攻己方所在城池。")
    route = _route_between(db, source, target_city_id)
    if route is None:
        raise ArmyOrderError(f"{source} 与 {target_city_id} 之间无直连路线，无法围城。")
    defender = str(target["controlled_by"])
    attacker = str(army["owner_power"])
    if defender == attacker:
        raise ArmyOrderError("不可围攻己方城池。")
    if int(army["manpower"] or 0) <= 0:
        raise ArmyOrderError("该军已无可战兵力。")
    if db.conn.execute(
        "SELECT 1 FROM sieges WHERE target_node=? AND status='active' LIMIT 1", (target_city_id,)
    ).fetchone():
        raise ArmyOrderError("该城池已有进行中的围城。")
    return {
        "source_node": source,
        "target_node": target_city_id,
        "target_commandery_id": str(target["commandery_id"]),
        "attacker_power": attacker,
        "defender_power": defender,
        "route_kind": route.kind,
        "route_note": route.note,
    }


def start_siege(db, state: object, army_id: str, target_node: str) -> int:
    validated = validate_siege_target(db, army_id, target_node)
    turn = int(getattr(state, "turn", 0))
    details: Dict[str, object] = {
        **validated,
        "history": [
            {
                "turn": turn,
                "event": "started",
                "summary": f"{army_id}自{validated['source_node']}围攻{target_node}",
            }
        ],
        "relief_army_ids": [],
    }
    cursor = db.conn.execute(
        """
        INSERT INTO sieges
        (target_node, attacker_army_id, defender_power, progress, status,
         started_turn, last_turn, details)
        VALUES (?, ?, ?, 0, 'active', ?, ?, ?)
        """,
        (
            validated["target_node"],
            army_id,
            validated["defender_power"],
            turn,
            turn - 1,
            json.dumps(details, ensure_ascii=False),
        ),
    )
    db.conn.execute("UPDATE armies SET status='围城' WHERE id=?", (army_id,))
    db.conn.commit()
    return int(cursor.lastrowid)


def _commander_profile(db, commander: str) -> Tuple[int, List[str]]:
    row = db.conn.execute(
        "SELECT leadership, personal_skills FROM characters WHERE name=?", (commander,)
    ).fetchone()
    if row is None:
        return 50, []
    return int(row["leadership"] or 50), _json_list(row["personal_skills"])


def _siege_scores(db, siege_id: int) -> Tuple[int, int, Dict[str, List[str]]]:
    siege = db.conn.execute("SELECT * FROM sieges WHERE id=?", (int(siege_id),)).fetchone()
    if siege is None:
        raise ValueError(f"围城不存在：{siege_id}")
    attacker = db.conn.execute(
        "SELECT * FROM armies WHERE id=? AND active=1", (siege["attacker_army_id"],)
    ).fetchone()
    if attacker is None:
        return 1, 100, {"attacker": ["攻方军队失效"], "defender": []}
    details = _json_dict(siege["details"])
    target_node = str(siege["target_node"])
    defender_power = str(siege["defender_power"])
    factors: Dict[str, List[str]] = {"attacker": [], "defender": []}

    attacker_leadership, attacker_traits = _commander_profile(db, str(attacker["commander"]))
    attacker_quality = (
        int(attacker["morale"] or 0)
        + int(attacker["training"] or 0)
        + int(attacker["equipment"] or 0)
        + int(attacker["discipline"] or 0)
    ) / 4
    attacker_score = max(5.0, int(attacker["manpower"] or 0) / 1000)
    attacker_score *= 0.5 + attacker_quality / 100
    attacker_score *= 0.5 + attacker_leadership / 100
    attacker_score *= float(attacker["hazard_combat_multiplier"] or 1.0)
    attacker_score *= float(attacker["supply_combat_multiplier"] or 1.0)
    factors["attacker"].append(f"兵力{int(attacker['manpower'])}、统率{attacker_leadership}")
    if "攻城" in attacker_traits:
        attacker_score *= 1.15
        factors["attacker"].append("攻城特性 +15%")
    if int(attacker["starvation_turns"] or 0) > 0:
        factors["attacker"].append(f"断粮{int(attacker['starvation_turns'])}月")

    target_commandery_id = str(details.get("target_commandery_id") or "")
    defenders = db.conn.execute(
        "SELECT * FROM armies WHERE station_node=? AND owner_power=? AND active=1",
        (target_node, defender_power),
    ).fetchall()
    defender_manpower = sum(int(row["manpower"] or 0) for row in defenders)
    if defender_manpower <= 0:
        defender_manpower = 10000
        factors["defender"].append("城内基础守军10000")
    defender_quality = 55.0
    defender_leadership = 50
    defender_traits: List[str] = []
    if defenders:
        defender_quality = sum(
            (
                int(row["morale"] or 0)
                + int(row["training"] or 0)
                + int(row["equipment"] or 0)
                + int(row["discipline"] or 0)
            ) / 4
            for row in defenders
        ) / len(defenders)
        for row in defenders:
            leadership, traits = _commander_profile(db, str(row["commander"]))
            if leadership >= defender_leadership:
                defender_leadership, defender_traits = leadership, traits

    defender_score = max(5.0, defender_manpower / 1000)
    defender_score *= 0.5 + defender_quality / 100
    defender_score *= 0.5 + defender_leadership / 100
    city = _city_target(db, target_node)
    region = db.conn.execute("SELECT fiscal FROM regions WHERE id=?", (city["commandery_id"],)).fetchone() if city else None
    fiscal = _json_dict(region["fiscal"] if region else "{}")
    fortification = max(0, min(100, int(city["fortification"] if city is not None else fiscal.get("fortification") or 0)))
    defender_score *= 0.75 + fortification / 100
    factors["defender"].append(f"城防{fortification}")
    if "守城" in defender_traits:
        defender_score *= 1.15
        factors["defender"].append("守城特性 +15%")
    grain_stock = max(0, int(city["grain_stock"] if city is not None else fiscal.get("grain_stock") or fiscal.get("granary") or 0))
    if grain_stock <= 0:
        defender_score *= 0.75
        factors["defender"].append("城内断粮 -25%")
    elif grain_stock >= math.ceil(defender_manpower / 1000):
        defender_score *= 1.10
        factors["defender"].append("城内粮足 +10%")
    relief_ids = [str(item) for item in details.get("relief_army_ids", [])]
    if relief_ids:
        defender_score *= 1 + min(0.45, 0.15 * len(relief_ids))
        factors["defender"].append(f"{len(relief_ids)}支援军牵制")
    return max(1, round(attacker_score)), max(1, round(defender_score)), factors


def _siege_payload(row) -> Dict[str, object]:
    details = _json_dict(row["details"])
    return {
        "siege_id": int(row["id"]),
        "target_node": str(row["target_node"]),
        "attacker_army_id": str(row["attacker_army_id"]),
        "defender_power": str(row["defender_power"]),
        "progress": int(row["progress"]),
        "status": str(row["status"]),
        "started_turn": int(row["started_turn"]),
        "last_turn": int(row["last_turn"]),
        "history": list(details.get("history", [])),
        "details": details,
    }


def build_siege_adjudication_pack(db, state: object, siege_id: int) -> Dict[str, object]:
    row = db.conn.execute("SELECT * FROM sieges WHERE id=?", (int(siege_id),)).fetchone()
    if row is None:
        raise ValueError(f"围城不存在：{siege_id}")
    details = _json_dict(row["details"])
    target_node = str(row["target_node"])
    city = _city_target(db, target_node)
    region = db.conn.execute(
        "SELECT name, controlled_by, public_support, unrest, fiscal FROM regions WHERE id=?",
        (city["commandery_id"],),
    ).fetchone() if city is not None else None
    fiscal = _json_dict(region["fiscal"] if region else "{}")
    attacker = db.conn.execute(
        "SELECT id, name, commander, owner_power, manpower, morale, training, equipment, discipline, supply, starvation_turns, station_node FROM armies WHERE id=?",
        (str(row["attacker_army_id"]),),
    ).fetchone()
    target_commandery_id = str(details.get("target_commandery_id") or "")
    defenders = db.conn.execute(
        "SELECT id, name, commander, owner_power, manpower, morale, training, equipment, discipline, supply FROM armies WHERE station_node=? AND owner_power=? AND active=1 ORDER BY id",
        (target_node, str(row["defender_power"])),
    ).fetchall()
    attacker_score = defender_score = 0
    factors: Dict[str, List[str]] = {"attacker": [], "defender": []}
    if str(row["status"]) == "active":
        attacker_score, defender_score, factors = _siege_scores(db, int(siege_id))
    old_progress = int(row["progress"] or 0)
    projected = (
        calculate_siege_progress(old_progress, attacker_score=max(1, attacker_score), defender_score=max(1, defender_score))
        if attacker_score and defender_score
        else old_progress
    )
    allowed = ["continue_siege", "withdraw_siege"]
    if projected >= 100:
        allowed.append("conquer_city")
    return build_adjudication_pack(
        kind="siege",
        turn=int(getattr(state, "turn", 0)),
        subject_id=str(siege_id),
        facts={
            "siege": _siege_payload(row),
            "target_region": {
                "id": target_node,
                "name": str(city["name"] if city is not None else (region["name"] if region else target_node)),
                "controlled_by": str(region["controlled_by"] if region else ""),
                "public_support": int(region["public_support"] or 0) if region else 0,
                "unrest": int(region["unrest"] or 0) if region else 0,
                "fortification": int(fiscal.get("fortification") or 0),
                "grain_stock": int(fiscal.get("grain_stock") or fiscal.get("granary") or 0),
            },
            "attacker": dict(attacker) if attacker else {},
            "defenders": [dict(item) for item in defenders],
            "relief_army_ids": [str(item) for item in details.get("relief_army_ids", [])],
        },
        rules={
            "progress_rule": "calculate_siege_progress(old_progress, attacker_score, defender_score)",
            "territory_rule": "仅 progress>=100 且 status=conquered 后才允许改变城权；郡权、州权由城权逐层推导。",
            "relief_rule": "救援军必须属于守方且在目标城或相邻节点。",
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["territory_change_before_progress_100", "unlisted_death", "free_reinforcements"],
        ai_options=[
            {"outcome": "continue_siege", "label": "继续围城"},
            {"outcome": "withdraw_siege", "label": "撤围整备"},
        ],
        audit={
            "attacker_score": attacker_score,
            "defender_score": defender_score,
            "projected_progress": projected,
            "factors": factors,
        },
        source_tables=["sieges", "armies", "regions", "administrative_cities", "administrative_provinces", "strategic_routes", "characters"],
    )


def _validate_free_siege(pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """校验 AI 的自由围城提案是否在边界内。

    AI 通过查询工具获取围城数据后，输出自由评估。
    校验器确保 delta 在安全范围内，且 AI 的声称与盘面事实一致。
    """
    # 1. feasibility=impossible → 安全默认（继续围城）
    feasibility = str(proposal.get("feasibility", "medium"))
    if feasibility == "impossible":
        return {
            "siege_action": "继续围城",
            "progress_delta": 0,
            "casualty_pct": 0,
            "feasibility": "impossible",
            "reasoning": proposal.get("reasoning", []),
            "narrative": str(proposal.get("narrative", "围城方案不可行，继续围困。")),
            "risk_note": str(proposal.get("risk_note", "")),
        }

    # 1b. 禁止字段检查
    check_forbidden_fields(proposal)

    # 2. 提取并裁剪 deltas
    progress_delta = int(proposal.get("progress_delta", 0))
    casualty_pct = int(proposal.get("casualty_pct", 0))

    progress_delta = max(FREE_SIEGE_BOUNDS["progress_delta"][0], min(FREE_SIEGE_BOUNDS["progress_delta"][1], progress_delta))
    casualty_pct = max(FREE_SIEGE_BOUNDS["casualty_pct"][0], min(FREE_SIEGE_BOUNDS["casualty_pct"][1], casualty_pct))

    # 3. 禁止文本检查
    reasoning_text = " ".join(str(r) for r in proposal.get("reasoning", []))
    narrative = str(proposal.get("narrative", ""))
    combined = f"{reasoning_text}\n{narrative}"
    for marker, message in SIEGE_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)

    # 4. 事实一致性检查
    facts = pack.get("facts", {})
    audit = pack.get("audit", {})
    defenders = facts.get("defenders", [])
    target_region = facts.get("target_region", {})

    # 声称"守军士气低落" → 检查守军 morale
    if "士气低落" in reasoning_text or "军心涣散" in reasoning_text:
        any_low_morale = False
        for d in defenders:
            if int(d.get("morale", 50)) < 40:
                any_low_morale = True
                break
        if not any_low_morale:
            raise ValueError("AI 声称'守军士气低落'，但盘面事实不支持（守军士气均≥40）。")

    # 声称"城防薄弱" → 检查 fortification
    if "城防薄弱" in reasoning_text or "城墙残破" in reasoning_text:
        fortification = int(target_region.get("fortification", 100))
        if fortification >= 60:
            raise ValueError("AI 声称'城防薄弱'，但盘面事实不支持（城防≥60）。")

    # 声称"民心向背" → 检查 public_support
    if "民心向背" in reasoning_text or "百姓拥戴" in reasoning_text:
        public_support = int(target_region.get("public_support", 50))
        if public_support < 40:
            raise ValueError("AI 声称'民心向背'，但盘面事实不支持（民心<40）。")

    # 5.  projected_progress 校验：如果 projected < 100，不能声称即将破城
    projected = int(audit.get("projected_progress", 0))
    if projected < 100 and ("即将破城" in reasoning_text or "城破在即" in reasoning_text):
        raise ValueError("AI 声称'即将破城'，但 projected_progress < 100。")

    # 6. outcome 合法性校验（保留与白名单兼容的约束）
    outcome = str(proposal.get("outcome") or "")
    allowed_outcomes = pack.get("allowed_outcomes", [])
    if outcome and allowed_outcomes and outcome not in allowed_outcomes:
        raise ValueError(f"围城裁决结果不在允许范围：{outcome}")

    return {
        "siege_action": str(proposal.get("siege_action", "自由围城评估")),
        "outcome": outcome,
        "progress_delta": progress_delta,
        "casualty_pct": casualty_pct,
        "feasibility": feasibility,
        "reasoning": proposal.get("reasoning", []),
        "narrative": narrative,
        "risk_note": str(proposal.get("risk_note", "")),
    }


def run_siege_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """围城 AI 裁判：统一走自由路径。"""
    try:
        return _validate_free_siege(pack, proposal)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}


def _append_siege_ai_judge_history(
    db,
    state: object,
    siege_id: int,
    history: List[Dict[str, object]],
) -> Dict[str, object] | None:
    llm_config, agno_db = adjudication_runtime_from_state(state)
    if llm_config is None:
        return None
    result = run_adjudication(
        db,
        state,
        "siege",
        str(siege_id),
        llm_config=llm_config,
        agno_db=agno_db,
    )
    turn = int(getattr(state, "turn", 0))
    if result.get("status") == "validated":
        proposal = dict(result.get("proposal") or {})
        history.append(
            {
                "turn": turn,
                "event": "ai_judge",
                "outcome": str(proposal.get("outcome") or ""),
                "reason": str(proposal.get("reason") or ""),
                "risk_note": str(proposal.get("risk_note") or ""),
                "adjudication_kind": "siege",
            }
        )
    elif result.get("status") == "pending_review":
        pending = dict(result.get("pending_adjudication") or {})
        history.append(
            {
                "turn": turn,
                "event": "ai_judge_pending",
                "pending_adjudication_id": int(pending.get("id") or 0),
                "reason": str(pending.get("reason") or ""),
                "adjudication_kind": "siege",
            }
        )
    return result


def advance_siege(db, state: object, siege_id: int) -> Dict[str, object]:
    row = db.conn.execute("SELECT * FROM sieges WHERE id=?", (int(siege_id),)).fetchone()
    if row is None:
        raise ValueError(f"围城不存在：{siege_id}")
    if str(row["status"]) != "active":
        return _siege_payload(row)
    turn = int(getattr(state, "turn", 0))
    if int(row["last_turn"]) >= turn:
        return _siege_payload(row)
    details = _json_dict(row["details"])
    history = list(details.get("history", []))
    attacker = db.conn.execute(
        "SELECT * FROM armies WHERE id=? AND active=1", (row["attacker_army_id"],)
    ).fetchone()
    if attacker is None or int(attacker["manpower"] or 0) <= 0:
        history.append({"turn": turn, "event": "failed", "summary": "攻方军队已失去作战能力"})
        details["history"] = history
        db.conn.execute(
            "UPDATE sieges SET status='failed', last_turn=?, details=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (turn, json.dumps(details, ensure_ascii=False), int(siege_id)),
        )
        db.conn.commit()
        return _siege_payload(db.conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,)).fetchone())
    if str(attacker["station_node"]) != str(details.get("source_node") or ""):
        return withdraw_siege(db, state, siege_id, reason="攻方已离开围城阵地")

    attacker_score, defender_score, factors = _siege_scores(db, siege_id)
    old_progress = int(row["progress"])
    progress = calculate_siege_progress(
        old_progress, attacker_score=attacker_score, defender_score=defender_score
    )
    history.append(
        {
            "turn": turn,
            "event": "advanced",
            "progress_before": old_progress,
            "progress_after": progress,
            "attacker_score": attacker_score,
            "defender_score": defender_score,
            "factors": factors,
        }
    )
    details["history"] = history
    _append_siege_ai_judge_history(db, state, siege_id, history)
    details["history"] = history
    status = "active"
    opened_passes: List[str] = []
    if progress >= 100:
        status = "conquered"
        attacker_power = str(details.get("attacker_power") or attacker["owner_power"])
        target_node = str(row["target_node"])
        # 围城仅直接写城权；郡、州控制权从城权逐层推导，避免旁路领土写入。
        db.conn.execute(
            "UPDATE administrative_cities SET controlled_by=?, siege_status='失守', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (attacker_power, target_node),
        )
        db.recompute_administrative_control()
        target_name_row = db.conn.execute(
            "SELECT name FROM administrative_cities WHERE id=?", (target_node,)
        ).fetchone()
        db.conn.execute(
            "UPDATE armies SET station_node=?, station=?, status='驻守' WHERE id=?",
                (target_node, str(target_name_row["name"] if target_name_row else target_node), attacker["id"]),
        )
        db.conn.execute(
            "UPDATE armies SET status='失城溃退' WHERE station_node=? AND owner_power=? AND active=1",
                (target_node, str(row["defender_power"])),
        )
        opened_passes = [
            str(edge["note"] or "关隘")
            for edge in db.conn.execute(
                """
                SELECT note FROM strategic_routes
                WHERE kind='关隘' AND (source=? OR target=?) ORDER BY id
                """,
                (target_node, target_node),
            ).fetchall()
        ]
        details["opened_passes"] = opened_passes
        history.append(
            {"turn": turn, "event": "conquered", "summary": f"攻下{target_node}", "opened_passes": opened_passes}
        )
        details["history"] = history
    db.conn.execute(
        """
        UPDATE sieges SET progress=?, status=?, last_turn=?, details=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (progress, status, turn, json.dumps(details, ensure_ascii=False), int(siege_id)),
    )
    db.conn.commit()
    payload = _siege_payload(db.conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,)).fetchone())
    payload["opened_passes"] = opened_passes
    payload["attacker_score"] = attacker_score
    payload["defender_score"] = defender_score
    payload["factors"] = factors
    return payload


def withdraw_siege(db, state: object, siege_id: int, reason: str = "主动撤围") -> Dict[str, object]:
    row = db.conn.execute("SELECT * FROM sieges WHERE id=?", (int(siege_id),)).fetchone()
    if row is None:
        raise ValueError(f"围城不存在：{siege_id}")
    details = _json_dict(row["details"])
    history = list(details.get("history", []))
    history.append(
        {"turn": int(getattr(state, "turn", 0)), "event": "withdrawn", "summary": str(reason)}
    )
    details["history"] = history
    db.conn.execute(
        "UPDATE sieges SET status='withdrawn', last_turn=?, details=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(getattr(state, "turn", 0)), json.dumps(details, ensure_ascii=False), int(siege_id)),
    )
    db.conn.execute("UPDATE armies SET status='围城撤退' WHERE id=?", (row["attacker_army_id"],))
    db.conn.commit()
    return _siege_payload(db.conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,)).fetchone())


def register_siege_relief(db, siege_id: int, army_id: str) -> Dict[str, object]:
    row = db.conn.execute("SELECT * FROM sieges WHERE id=? AND status='active'", (int(siege_id),)).fetchone()
    if row is None:
        raise ValueError("围城不存在或已结束。")
    relief = db.conn.execute("SELECT * FROM armies WHERE id=? AND active=1", (army_id,)).fetchone()
    if relief is None or str(relief["owner_power"]) != str(row["defender_power"]):
        raise ValueError("救援军必须属于守方且仍可作战。")
    target = str(row["target_node"])
    if str(relief["station_node"]) != target and _route_between(db, str(relief["station_node"]), target) is None:
        raise ValueError("救援军不在目标城或相邻节点。")
    details = _json_dict(row["details"])
    relief_ids = [str(item) for item in details.get("relief_army_ids", [])]
    if army_id not in relief_ids:
        relief_ids.append(army_id)
    details["relief_army_ids"] = relief_ids
    history = list(details.get("history", []))
    history.append({"event": "relief_registered", "army_id": army_id})
    details["history"] = history
    db.conn.execute(
        "UPDATE sieges SET details=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(details, ensure_ascii=False), int(siege_id)),
    )
    db.conn.commit()
    return _siege_payload(db.conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,)).fetchone())


def resolve_siege_relief(
    db,
    state: object,
    siege_id: int,
    relief_army_id: str,
    attacker_defeated: bool,
) -> Dict[str, object]:
    register_siege_relief(db, siege_id, relief_army_id)
    row = db.conn.execute("SELECT * FROM sieges WHERE id=?", (int(siege_id),)).fetchone()
    if not attacker_defeated:
        return _siege_payload(row)
    details = _json_dict(row["details"])
    history = list(details.get("history", []))
    history.append(
        {
            "turn": int(getattr(state, "turn", 0)),
            "event": "relief_defeat",
            "summary": f"{relief_army_id}击破围城军",
        }
    )
    details["history"] = history
    db.conn.execute(
        "UPDATE sieges SET status='relief_defeat', last_turn=?, details=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(getattr(state, "turn", 0)), json.dumps(details, ensure_ascii=False), int(siege_id)),
    )
    db.conn.execute("UPDATE armies SET status='援军击退' WHERE id=?", (row["attacker_army_id"],))
    db.conn.commit()
    return _siege_payload(db.conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,)).fetchone())


def resolve_siege_turn(db, state: object) -> List[Dict[str, object]]:
    turn = int(getattr(state, "turn", 0))
    results: List[Dict[str, object]] = []
    orders = db.conn.execute(
        "SELECT id, army_id, payload FROM army_orders WHERE turn=? AND status='issued' AND order_type='围城' ORDER BY id",
        (turn,),
    ).fetchall()
    for order in orders:
        order_id = int(order["id"])
        try:
            payload = _json_dict(order["payload"])
            target = str(payload.get("target") or payload.get("to") or "")
            siege_id = start_siege(db, state, str(order["army_id"]), target)
            result = {"order_id": order_id, "siege_id": siege_id, "status": "resolved"}
            status = "resolved"
        except (ArmyOrderError, ValueError) as error:
            result = {"order_id": order_id, "status": "rejected", "reason": str(error)}
            status = "rejected"
        db.conn.execute(
            "UPDATE army_orders SET status=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), order_id),
        )
        results.append(result)
    db.conn.commit()
    active = db.conn.execute(
        "SELECT id FROM sieges WHERE status='active' AND last_turn < ? ORDER BY id", (turn,)
    ).fetchall()
    results.extend(advance_siege(db, state, int(row["id"])) for row in active)
    return results
