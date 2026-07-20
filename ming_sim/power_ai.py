"""外部势力的月末战略行动生成与硬校验。"""

from __future__ import annotations

import json
from typing import Dict, Iterable

from ming_sim.adjudication import (
    adjudication_runtime_from_state,
    build_adjudication_pack,
    record_pending_adjudication,
    run_adjudication,
    validate_ai_proposal,
)
from ming_sim.supply import reachable_friendly_granary


MILITARY_TYPES = {"move", "attack", "siege", "fortify", "resupply"}
DIPLOMACY_TYPES = {"declare_war", "seek_peace", "intrigue", "propose_alliance"}
ACTION_TYPES = MILITARY_TYPES | DIPLOMACY_TYPES
FORBIDDEN_FIELDS = {
    "region_control", "controlled_by", "kill_character", "character_status",
    "manpower_delta", "territory_delta", "spawn_army", "reinforcements",
}


def _status_terminal(status: str) -> bool:
    lowered = str(status).lower()
    return lowered in {"defeated", "destroyed", "collapsed", "inactive"} or any(
        token in str(status) for token in ("灭亡", "瓦解", "覆灭", "已亡")
    )


def _relation(db, power_a: str, power_b: str):
    first, second = db._relation_pair(power_a, power_b)
    return db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE power_a=? AND power_b=?", (first, second)
    ).fetchone()


def _at_war(db, power_a: str, power_b: str) -> bool:
    row = _relation(db, power_a, power_b)
    return row is not None and str(row["status"]) == "war"


def _adjacent_nodes(db, node_id: str) -> list[tuple[str, str]]:
    rows = db.conn.execute(
        """
        SELECT CASE WHEN source=? THEN target ELSE source END AS target, kind
        FROM strategic_routes WHERE source=? OR target=? ORDER BY id
        """,
        (node_id, node_id, node_id),
    ).fetchall()
    return [(str(row["target"]), str(row["kind"])) for row in rows]


def _intelligence_confidence(db, power_id: str) -> int:
    row = db.conn.execute(
        """
        SELECT MAX(intrigue) AS best FROM characters
        WHERE power_id=? AND status='active'
        """,
        (power_id,),
    ).fetchone()
    return max(20, min(95, int(row["best"] or 40)))


def _base_action(
    *, power_id: str, action_type: str, score: float, reasons: Iterable[str],
    intelligence: int, army_id: str = "", target_node: str = "", target_power: str = "",
    defender_ids: list[str] | None = None,
) -> Dict[str, object]:
    return {
        "power_id": power_id,
        "action_type": action_type,
        "army_id": army_id,
        "target_node": target_node,
        "target_power": target_power,
        "defender_ids": defender_ids or [],
        "score": round(max(0.0, float(score)), 2),
        "reasons": [str(reason) for reason in reasons if str(reason)],
        "factors": {"intelligence_confidence": intelligence},
    }


def available_power_actions(db, state: object, power_id: str) -> list[Dict[str, object]]:
    """只从当前军队、路线、补给、外交与情报生成合法候选。"""
    power = db.conn.execute("SELECT * FROM powers WHERE id=?", (power_id,)).fetchone()
    if power is None:
        raise ValueError(f"势力不存在：{power_id}")
    if power_id == "liu_bei" or _status_terminal(str(power["status"])):
        return []
    turn = int(getattr(state, "turn", 0))
    intelligence = _intelligence_confidence(db, power_id)
    agenda = str(power["agenda"] or "")
    power_supply = int(power["supply"] or 0)
    cohesion = int(power["cohesion"] or 0)
    military_strength = int(power["military_strength"] or 0)
    actions: list[Dict[str, object]] = []
    border_targets: Dict[str, set[str]] = {}

    armies = db.conn.execute(
        """
        SELECT * FROM armies WHERE owner_power=? AND active=1
          AND id NOT IN (SELECT army_id FROM army_orders WHERE turn=?)
        ORDER BY id
        """,
        (power_id, turn),
    ).fetchall()
    for army in armies:
        army_id = str(army["id"])
        node = str(army["station_node"])
        morale = int(army["morale"] or 0)
        supply = int(army["supply"] or 0)
        manpower = int(army["manpower"] or 0)
        defensive_score = 24 + max(0, 55 - morale) * 0.6 + max(0, 35 - supply) * 0.4
        actions.append(_base_action(
            power_id=power_id, action_type="fortify", army_id=army_id,
            score=defensive_score, reasons=[f"军心{morale}", f"携粮{supply}", "固守当前战略节点"],
            intelligence=intelligence,
        ))

        if supply < 70 and reachable_friendly_granary(db, army_id):
            actions.append(_base_action(
                power_id=power_id, action_type="resupply", army_id=army_id,
                score=45 + (70 - supply) * 1.2, reasons=[f"携粮仅{supply}", "友方郡仓可达", "补给优先"],
                intelligence=intelligence,
            ))

        for target, route_kind in _adjacent_nodes(db, node):
            region = db.conn.execute(
                "SELECT controlled_by FROM regions WHERE id=?", (target,)
            ).fetchone()
            controller = str(region["controlled_by"] if region else "")
            if controller and controller != power_id:
                border_targets.setdefault(controller, set()).add(target)
            defenders = db.conn.execute(
                "SELECT id, owner_power, manpower FROM armies WHERE station_node=? AND active=1 ORDER BY id",
                (target,),
            ).fetchall()
            if controller == power_id and not any(str(item["owner_power"]) != power_id for item in defenders):
                move_score = 30 + max(0, supply - 40) * 0.15
                if target in agenda:
                    move_score += 18
                actions.append(_base_action(
                    power_id=power_id, action_type="move", army_id=army_id, target_node=target,
                    score=move_score, reasons=[f"沿{route_kind}调动", "目标为己方节点", "调整战区部署"],
                    intelligence=intelligence,
                ))
                continue

            enemy_groups: Dict[str, list[object]] = {}
            for defender in defenders:
                owner = str(defender["owner_power"])
                if owner != power_id and _at_war(db, power_id, owner):
                    enemy_groups.setdefault(owner, []).append(defender)
            for enemy_power, group in enemy_groups.items():
                defender_ids = [str(item["id"]) for item in group]
                defender_manpower = sum(int(item["manpower"] or 0) for item in group)
                ratio = manpower / max(1, defender_manpower)
                attack_score = 35 + min(30, ratio * 12) + (supply - 40) * 0.15 + (morale - 50) * 0.15
                if route_kind in {"江河", "山道", "关隘"}:
                    attack_score -= 12
                actions.append(_base_action(
                    power_id=power_id, action_type="attack", army_id=army_id,
                    target_node=target, target_power=enemy_power, defender_ids=defender_ids,
                    score=attack_score,
                    reasons=[f"与{enemy_power}处于战争", f"兵力比{ratio:.2f}", f"经{route_kind}作战", f"军心{morale}/携粮{supply}"],
                    intelligence=intelligence,
                ))

            if controller and controller != power_id and _at_war(db, power_id, controller) and not defenders:
                actions.append(_base_action(
                    power_id=power_id, action_type="siege", army_id=army_id,
                    target_node=target, target_power=controller,
                    score=42 + min(25, manpower / 1000) + (supply - 50) * 0.1,
                    reasons=[f"与{controller}处于战争", "目标节点无野战守军", f"经{route_kind}接近"],
                    intelligence=intelligence,
                ))

    # 外交与谍报也必须基于已建档的双边关系。
    relations = db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE power_a=? OR power_b=?",
        (power_id, power_id),
    ).fetchall()
    for relation in relations:
        target = str(relation["power_b"] if str(relation["power_a"]) == power_id else relation["power_a"])
        if target == "liu_bei" or target != power_id:
            status = str(relation["status"])
            public = int(relation["public_relation"] or 0)
            trust = int(relation["trust"] or 0)
            if status == "war" and (military_strength < 45 or power_supply < 35 or cohesion < 40):
                actions.append(_base_action(
                    power_id=power_id, action_type="seek_peace", target_power=target,
                    score=58 + max(0, 45 - military_strength) + max(0, 35 - power_supply),
                    reasons=["当前处于战争", f"军力{military_strength}/总补给{power_supply}/凝聚{cohesion}", "战略收缩"],
                    intelligence=intelligence,
                ))
            elif status != "war" and public <= -40:
                actions.append(_base_action(
                    power_id=power_id, action_type="declare_war", target_power=target,
                    score=35 + abs(public) * 0.35 + military_strength * 0.12,
                    reasons=[f"公开关系{public}", f"军力{military_strength}", "战略意图与外交冲突"],
                    intelligence=intelligence,
                ))
            elif status in {"neutral", "friendly"} and public >= 45 and trust >= 40:
                actions.append(_base_action(
                    power_id=power_id, action_type="propose_alliance", target_power=target,
                    score=25 + public * 0.2 + trust * 0.2,
                    reasons=[f"公开关系{public}", f"互信{trust}", "寻求军事与外交协作"],
                    intelligence=intelligence,
                ))
            if status != "allied" and trust < 35 and intelligence >= 65:
                actions.append(_base_action(
                    power_id=power_id, action_type="intrigue", target_power=target,
                    score=24 + (35 - trust) * 0.5 + (intelligence - 65) * 0.4,
                    reasons=[f"互信仅{trust}", f"情报能力{intelligence}", "尝试策反与离间"],
                    intelligence=intelligence,
                ))
    related_targets = {
        str(row["power_b"] if str(row["power_a"]) == power_id else row["power_a"])
        for row in relations
    }
    # 没有预置双边关系的邻接势力也可因地缘与战略意图产生宣战候选。
    # 只在执行时建档，读取候选本身不改变世界。
    for target_power, target_nodes in border_targets.items():
        if target_power in related_targets:
            continue
        target_row = db.conn.execute("SELECT name FROM powers WHERE id=?", (target_power,)).fetchone()
        target_name = str(target_row["name"] if target_row else target_power)
        node_names = [
            str(row["name"])
            for row in db.conn.execute(
                f"SELECT name FROM regions WHERE id IN ({','.join('?' for _ in target_nodes)})",
                tuple(sorted(target_nodes)),
            ).fetchall()
        ]
        intent_conflict = target_name in agenda or any(name in agenda for name in node_names)
        intent_conflict = intent_conflict or any(word in agenda for word in ("统一天下", "争夺", "压服", "控制长江"))
        if intent_conflict and military_strength >= 40 and power_supply >= 40:
            actions.append(_base_action(
                power_id=power_id, action_type="declare_war", target_power=target_power,
                score=32 + military_strength * 0.18 + power_supply * 0.08,
                reasons=[f"与{target_name}控区相邻", f"战略意图：{agenda}", f"军力{military_strength}/总补给{power_supply}"],
                intelligence=intelligence,
            ))
    return sorted(actions, key=lambda item: (-float(item["score"]), str(item["action_type"]), str(item["army_id"])))


def validate_power_action(db, state: object, action: Dict[str, object]) -> Dict[str, object]:
    forbidden = sorted(FORBIDDEN_FIELDS & set(action))
    action_type = str(action.get("action_type") or "")
    if forbidden or action_type not in ACTION_TYPES:
        detail = ",".join(forbidden or [action_type or "<empty>"])
        raise ValueError(f"外部 AI 行动包含非法字段或类型：{detail}")
    power_id = str(action.get("power_id") or "")
    if power_id == "liu_bei":
        raise ValueError("外部势力 AI 不得替玩家控制刘备。")
    army_id = str(action.get("army_id") or "")
    if action_type in MILITARY_TYPES:
        army = db.conn.execute(
            "SELECT owner_power FROM armies WHERE id=? AND active=1", (army_id,)
        ).fetchone()
        if army is None or str(army["owner_power"]) != power_id:
            raise ValueError(f"军队 {army_id} 不属于势力 {power_id}")

    generated = available_power_actions(db, state, power_id)
    keys = ("action_type", "army_id", "target_node", "target_power")
    match = next(
        (
            candidate for candidate in generated
            if all(str(candidate.get(key) or "") == str(action.get(key) or "") for key in keys)
            and list(candidate.get("defender_ids") or []) == list(action.get("defender_ids") or [])
        ),
        None,
    )
    if match is None:
        raise ValueError("行动不在当前规则层提供的合法候选中。")
    return {"valid": True, "action": match}


def build_power_action_adjudication_pack(db, state: object, power_id: str) -> Dict[str, object]:
    power = db.conn.execute("SELECT * FROM powers WHERE id=?", (power_id,)).fetchone()
    if power is None:
        raise ValueError(f"势力不存在：{power_id}")
    candidates = available_power_actions(db, state, power_id)
    armies = db.conn.execute(
        """
        SELECT id, name, commander, station_node, manpower, morale, supply, fatigue, status
        FROM armies WHERE owner_power=? AND active=1 ORDER BY id
        """,
        (power_id,),
    ).fetchall()
    relations = db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE power_a=? OR power_b=? ORDER BY power_a, power_b",
        (power_id, power_id),
    ).fetchall()
    allowed = sorted({str(item["action_type"]) for item in candidates}) or ["no_action"]
    return build_adjudication_pack(
        kind="power_action",
        turn=int(getattr(state, "turn", 0)),
        subject_id=power_id,
        facts={
            "power": dict(power),
            "armies": [dict(item) for item in armies],
            "relations": [dict(item) for item in relations],
            "legal_candidates": candidates,
        },
        rules={
            "candidate_rule": "外部势力行动必须来自 available_power_actions 或通过同等硬校验。",
            "one_action_rule": "每月每个外部势力最多执行一项高优先级行动。",
            "execution_rule": "军事行动只排入 army_orders；外交行动只改双边关系状态或微量互信。",
            "forbidden_fields": sorted(FORBIDDEN_FIELDS),
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["direct_region_control", "kill_character", "spawn_army", "direct_manpower_delta"],
        ai_options=candidates,
        audit={"candidate_count": len(candidates), "best_candidate": candidates[0] if candidates else {}},
        source_tables=["powers", "armies", "strategic_routes", "regions", "diplomatic_relations", "characters"],
    )


def run_power_action_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    try:
        validated = validate_ai_proposal(
            pack,
            proposal,
            allowed_change_kinds=["queue_army_order", "relation_status", "trust", "public_relation"],
        )
        action = proposal.get("action") if isinstance(proposal.get("action"), dict) else proposal
        power_id = str(pack.get("subject_id") or action.get("power_id") or "")
        action = {**dict(action), "power_id": power_id}
        validated["action"] = validate_power_action(db, state, action)["action"]
        return validated
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}


def _execute_validated_action(db, state: object, action: Dict[str, object]) -> Dict[str, object]:
    action_type = str(action["action_type"])
    army_id = str(action.get("army_id") or "")
    target = str(action.get("target_node") or "")
    if action_type in MILITARY_TYPES:
        mapping = {
            "move": ("移动", {"to": target}),
            "fortify": ("驻守", {}),
            "resupply": ("补给", {"amount": 40}),
            "siege": ("围城", {"target": target}),
            "attack": (
                "突袭",
                {
                    "target": target,
                    "defender_ids": list(action.get("defender_ids") or []),
                    "ai_choice": {
                        "tactic": "正面交锋",
                        "actor": str(db.conn.execute("SELECT commander FROM armies WHERE id=?", (army_id,)).fetchone()[0]),
                    },
                },
            ),
        }
        order_type, payload = mapping[action_type]
        order_id = db.issue_army_order(state, army_id, order_type, payload)
        return {"queued_order_id": order_id, "order_type": order_type}

    power_id = str(action["power_id"])
    target_power = str(action.get("target_power") or "")
    first, second = db._relation_pair(power_id, target_power)
    relation = db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE power_a=? AND power_b=?", (first, second)
    ).fetchone()
    if action_type == "declare_war":
        if relation is None:
            db.conn.execute(
                """
                INSERT INTO diplomatic_relations
                (power_a, power_b, public_relation, trust, obligations, territorial_claims,
                 marriage_hostages, military_coordination, status)
                VALUES (?, ?, -20, 10, '[]', '{}', '{}', 0, 'neutral')
                """,
                (first, second),
            )
        db.conn.execute(
            "UPDATE diplomatic_relations SET status='war', trust=MAX(0, trust-20), public_relation=MAX(-100, public_relation-20), updated_at=CURRENT_TIMESTAMP WHERE power_a=? AND power_b=?",
            (first, second),
        )
        result = {"relation_status": "war"}
    elif action_type == "seek_peace":
        db.conn.execute(
            "UPDATE diplomatic_relations SET status='negotiating', updated_at=CURRENT_TIMESTAMP WHERE power_a=? AND power_b=?",
            (first, second),
        )
        result = {"relation_status": "negotiating"}
    elif action_type == "propose_alliance":
        db.conn.execute(
            "UPDATE diplomatic_relations SET status='negotiating', updated_at=CURRENT_TIMESTAMP WHERE power_a=? AND power_b=?",
            (first, second),
        )
        result = {"relation_status": "negotiating"}
    else:  # intrigue：只产生受控外交修正，不凭空策反成功、杀人或换地。
        old_trust = int(relation["trust"] or 0)
        new_trust = max(0, old_trust - 2)
        db.conn.execute(
            "UPDATE diplomatic_relations SET trust=?, updated_at=CURRENT_TIMESTAMP WHERE power_a=? AND power_b=?",
            (new_trust, first, second),
        )
        result = {"trust_before": old_trust, "trust_after": new_trust, "outcome": "情报扰动"}
    db.conn.commit()
    return result


def _record_power_ai_action(
    db,
    state: object,
    power_id: str,
    *,
    action_type: str,
    action_json: Dict[str, object],
    score: float,
    status: str,
    result: Dict[str, object],
) -> int:
    cursor = db.conn.execute(
        """
        INSERT INTO power_ai_actions
        (turn, year, period, power_id, action_type, action_json, score, status, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(getattr(state, "turn", 0)),
            int(getattr(state, "year", 0)),
            int(getattr(state, "period", 0)),
            power_id,
            action_type,
            json.dumps(action_json, ensure_ascii=False),
            float(score),
            status,
            json.dumps(result, ensure_ascii=False),
        ),
    )
    db.conn.commit()
    return int(cursor.lastrowid)


def _choose_power_action_with_judge(
    db,
    state: object,
    power_id: str,
    candidates: list[Dict[str, object]],
    llm_config: object | None,
    agno_db: object | None,
) -> Dict[str, object]:
    if llm_config is None:
        return {"status": "validated", "action": validate_power_action(db, state, candidates[0])["action"], "ai_proposal": {}}
    result = run_adjudication(
        db,
        state,
        "power_action",
        power_id,
        llm_config=llm_config,
        agno_db=agno_db,
    )
    if result["status"] == "validated":
        validated = dict(result.get("validated") or {})
        return {
            "status": "validated",
            "action": dict(validated.get("action") or {}),
            "ai_proposal": dict(validated.get("ai_proposal") or result.get("proposal") or {}),
        }
    if result["status"] == "pending_review":
        return {"status": "pending_review", "pending_adjudication": dict(result.get("pending_adjudication") or {})}
    return {"status": "validated", "action": validate_power_action(db, state, candidates[0])["action"], "ai_proposal": {}}


def resolve_power_ai_turn(
    db,
    state: object,
    llm_config: object | None = None,
    agno_db: object | None = None,
) -> list[Dict[str, object]]:
    """每月每个外部势力最多执行一项高优先级合法行动。"""
    turn = int(getattr(state, "turn", 0))
    runtime_llm, runtime_agno = adjudication_runtime_from_state(state)
    llm_config = llm_config if llm_config is not None else runtime_llm
    agno_db = agno_db if agno_db is not None else runtime_agno
    results: list[Dict[str, object]] = []
    powers = db.conn.execute("SELECT id FROM powers WHERE id!='liu_bei' ORDER BY id").fetchall()
    for row in powers:
        power_id = str(row["id"])
        if db.conn.execute(
            "SELECT 1 FROM power_ai_actions WHERE turn=? AND power_id=?", (turn, power_id)
        ).fetchone():
            continue
        candidates = available_power_actions(db, state, power_id)
        if not candidates:
            continue
        choice = _choose_power_action_with_judge(db, state, power_id, candidates, llm_config, agno_db)
        if choice.get("status") == "pending_review":
            pending = dict(choice.get("pending_adjudication") or {})
            action_id = _record_power_ai_action(
                db,
                state,
                power_id,
                action_type="pending_review",
                action_json={"pending_adjudication_id": pending.get("id", 0)},
                score=0,
                status="pending_review",
                result={"reason": pending.get("reason", "裁判模型输出待核议")},
            )
            results.append({
                "id": action_id,
                "power_id": power_id,
                "status": "pending_review",
                "pending_adjudication": pending,
            })
            continue
        validated = dict(choice["action"])
        status = "executed"
        try:
            execution = _execute_validated_action(db, state, validated)
        except Exception as error:  # 单一势力行动失败不得中断全世界月末结算。
            status = "rejected"
            execution = {"reason": str(error)}
        action_record = dict(validated)
        if choice.get("ai_proposal"):
            action_record["ai_proposal"] = {
                key: choice["ai_proposal"].get(key)
                for key in ("outcome", "reason", "narrative", "risk_note", "recommended_followup")
                if isinstance(choice.get("ai_proposal"), dict) and choice["ai_proposal"].get(key)
            }
        action_id = _record_power_ai_action(
            db,
            state,
            power_id,
            action_type=str(validated["action_type"]),
            action_json=action_record,
            score=float(validated["score"]),
            status=status,
            result=execution,
        )
        results.append({
            "id": action_id, "power_id": power_id, "status": status,
            "action": validated, "ai_proposal": choice.get("ai_proposal") or {}, "result": execution,
        })
    return results
