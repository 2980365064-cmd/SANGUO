"""六维外交关系、盟约提案与规则化违约。"""

from __future__ import annotations

import json
from typing import Dict, List

from ming_sim.adjudication import (
    adjudication_runtime_from_state,
    build_adjudication_pack,
    record_pending_adjudication,
    run_adjudication,
    validate_ai_proposal,
)
from ming_sim.character_effects import evaluate_character_modifier


CLAUSE_KEYS = (
    "obligations",
    "territorial_claims",
    "marriage_hostages",
    "military_coordination",
)


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _character(db, name: str):
    return db.content.characters.get(name)


def _hard_blockers(db, proposer: str, target: str, terms: Dict[str, object]) -> List[str]:
    blockers: List[str] = []
    relation = db.get_diplomatic_relation(proposer, target)
    claims = relation.get("territorial_claims") or {}
    proposal_claims = terms.get("territorial_claims") or {}
    if isinstance(proposal_claims, dict):
        cede = [str(item) for item in (proposal_claims.get("cede") or [])]
        cede_from = str(proposal_claims.get("from") or "")
        target_claims = [str(item) for item in (claims.get(target) or [])] if isinstance(claims, dict) else []
        if cede_from == target and set(cede) & set(target_claims):
            blockers.append("要求对方无偿放弃既有荆州或其他核心领土主张。")

    proposed_obligations = terms.get("obligations") or []
    proposed_types = {
        str(item.get("type") or "") for item in proposed_obligations if isinstance(item, dict)
    }
    for treaty in db.list_diplomacy_treaties("active"):
        if {str(treaty["proposer"]), str(treaty["target"])} != {proposer, target}:
            continue
        active_types = {
            str(item.get("type") or "")
            for item in (treaty["terms"].get("obligations") or [])
            if isinstance(item, dict)
        }
        if "互不攻伐" in active_types and "进攻对方" in proposed_types:
            blockers.append("新条款与现行互不攻伐义务冲突。")
    return blockers


def _diplomacy_adjudication_summary(result: Dict[str, object]) -> str:
    if result.get("status") == "pending_review":
        pending = dict(result.get("pending_adjudication") or {})
        return json.dumps(
            {
                "status": "pending_review",
                "pending_adjudication_id": pending.get("id", 0),
                "reason": pending.get("reason", ""),
            },
            ensure_ascii=False,
        )
    proposal = dict(result.get("proposal") or {})
    return json.dumps(
        {
            "status": result.get("status"),
            "outcome": proposal.get("outcome", ""),
            "reason": proposal.get("reason", ""),
            "risk_note": proposal.get("risk_note", ""),
            "recommended_followup": proposal.get("recommended_followup", ""),
        },
        ensure_ascii=False,
    )


def propose_treaty(
    db,
    proposer: str,
    target: str,
    terms: Dict[str, object],
    *,
    state: object | None = None,
) -> Dict[str, object]:
    if proposer == target:
        raise ValueError("不能与自身缔约。")
    for power_id in (proposer, target):
        if db.conn.execute("SELECT 1 FROM powers WHERE id=?", (power_id,)).fetchone() is None:
            raise ValueError(f"势力不存在：{power_id}")
    missing = [key for key in CLAUSE_KEYS if key not in terms]
    if missing:
        raise ValueError(f"盟约缺少独立条款：{','.join(missing)}")
    relation = db.get_diplomatic_relation(proposer, target)
    envoy_name = str(terms.get("envoy") or "")
    envoy = _character(db, envoy_name)
    modifier = 0.0
    if envoy is not None:
        modifiers = evaluate_character_modifier(
            envoy,
            "negotiation",
            db=db,
            turn=int(terms.get("turn") or 0),
        )
        modifier = sum(float(item.delta) for item in modifiers)
    blockers = _hard_blockers(db, proposer, target, terms)
    chance = _clamp(
        round(
            40
            + int(relation["public_relation"]) * 0.20
            + int(relation["trust"]) * 0.20
            + modifier
        ),
        5,
        95,
    )
    if blockers:
        return {
            "status": "blocked",
            "acceptance_chance": chance,
            "hard_blockers": blockers,
            "diplomacy_modifier": round(modifier, 2),
        }
    treaty_key = str(terms.get("treaty_key") or "").strip()
    treaty_type = str(terms.get("treaty_type") or "盟约").strip()
    stored_terms = {key: terms[key] for key in CLAUSE_KEYS}
    if envoy_name:
        stored_terms["envoy"] = envoy_name
    try:
        cursor = db.conn.execute(
            """
            INSERT INTO diplomacy_treaties
            (treaty_key, proposer, target, treaty_type, terms, start_turn, end_turn, status)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 'proposed')
            """,
            (
                treaty_key,
                proposer,
                target,
                treaty_type,
                json.dumps(stored_terms, ensure_ascii=False),
                int(terms.get("turn") or 0),
            ),
        )
    except Exception as error:
        if "UNIQUE" in str(error).upper():
            raise ValueError(f"盟约键已存在：{treaty_key}") from error
        raise
    db.conn.commit()
    result = {
        "treaty_id": int(cursor.lastrowid),
        "status": "proposed",
        "acceptance_chance": chance,
        "hard_blockers": [],
        "diplomacy_modifier": round(modifier, 2),
        "terms": stored_terms,
    }
    if state is not None:
        llm_config, agno_db = adjudication_runtime_from_state(state)
        adjudication = run_adjudication(
            db,
            state,
            "diplomacy",
            f"{proposer}:{target}",
            llm_config=llm_config,
            agno_db=agno_db,
            proposer=proposer,
            target=target,
            terms={**terms, "turn": int(getattr(state, "turn", terms.get("turn") or 0) or 0)},
        )
        result["adjudication"] = {
            "status": adjudication.get("status"),
            "kind": adjudication.get("kind"),
            "pending_adjudication": adjudication.get("pending_adjudication", {}),
        }
        if adjudication.get("status") in {"validated", "pending_review"}:
            _log(
                db,
                turn=int(getattr(state, "turn", terms.get("turn") or 0) or 0),
                power_a=proposer,
                power_b=target,
                treaty_id=int(cursor.lastrowid),
                field="ai_judge",
                old_value="",
                new_value=_diplomacy_adjudication_summary(adjudication),
                reason="AI裁判依据：使臣谈判反馈候选，不直接生效盟约。",
                actor=str(terms.get("envoy") or target),
            )
            db.conn.commit()
    return result


def _build_power_balance(db, proposer: str, target: str) -> Dict[str, object]:
    """构建双方军力对比数据。"""
    proposer_row = db.conn.execute(
        "SELECT id, name, military_strength, supply, cohesion FROM powers WHERE id=?", (proposer,)
    ).fetchone()
    target_row = db.conn.execute(
        "SELECT id, name, military_strength, supply, cohesion FROM powers WHERE id=?", (target,)
    ).fetchone()
    proposer_force = int(proposer_row["military_strength"]) if proposer_row else 0
    target_force = int(target_row["military_strength"]) if target_row else 0
    ratio = round(proposer_force / target_force, 2) if target_force > 0 else 0.0
    return {
        "proposer": proposer,
        "target": target,
        "proposer_force": proposer_force,
        "target_force": target_force,
        "ratio": ratio,
        "proposer_supply": int(proposer_row["supply"]) if proposer_row and proposer_row["supply"] is not None else 0,
        "target_supply": int(target_row["supply"]) if target_row and target_row["supply"] is not None else 0,
    }


def _build_strategic_context(db, proposer: str, target: str) -> Dict[str, object]:
    """构建战略态势数据（共同敌人、战争状态等）。"""
    # 找出与 proposer 处于 war 状态的势力
    proposer_enemies = set()
    rows = db.conn.execute(
        "SELECT power_a, power_b, status FROM diplomatic_relations WHERE status='war'"
    ).fetchall()
    for row in rows:
        if row["power_a"] == proposer:
            proposer_enemies.add(row["power_b"])
        elif row["power_b"] == proposer:
            proposer_enemies.add(row["power_a"])

    # 找出与 target 处于 war 状态的势力
    target_enemies = set()
    for row in rows:
        if row["power_a"] == target:
            target_enemies.add(row["power_b"])
        elif row["power_b"] == target:
            target_enemies.add(row["power_a"])

    common_enemies = list(proposer_enemies & target_enemies)
    
    # 找出 target 的所有关系状态
    target_relations = []
    rel_rows = db.conn.execute(
        "SELECT power_a, power_b, status FROM diplomatic_relations"
    ).fetchall()
    for row in rel_rows:
        if row["power_a"] == target or row["power_b"] == target:
            other = row["power_b"] if row["power_a"] == target else row["power_a"]
            target_relations.append({"power": other, "status": row["status"]})

    return {
        "proposer_enemies": list(proposer_enemies),
        "target_enemies": list(target_enemies),
        "common_enemies": common_enemies,
        "target_relations": target_relations,
    }


def _build_active_treaties(db, proposer: str, target: str) -> List[Dict[str, object]]:
    """获取双方当前的活跃条约。"""
    rows = db.conn.execute(
        """
        SELECT treaty_key, proposer, target, treaty_type, terms, start_turn, status
        FROM diplomacy_treaties
        WHERE status='active'
          AND ((proposer=? AND target=?) OR (proposer=? AND target=?))
        ORDER BY id
        """,
        (proposer, target, target, proposer),
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            "treaty_key": row["treaty_key"],
            "proposer": row["proposer"],
            "target": row["target"],
            "treaty_type": row["treaty_type"],
            "terms": json.loads(str(row["terms"] or "{}")),
            "start_turn": int(row["start_turn"]),
        })
    return result


def build_diplomacy_adjudication_pack(
    db,
    state: object,
    proposer: str,
    target: str,
    terms: Dict[str, object],
) -> Dict[str, object]:
    if proposer == target:
        raise ValueError("不能与自身缔约。")
    for power_id in (proposer, target):
        if db.conn.execute("SELECT 1 FROM powers WHERE id=?", (power_id,)).fetchone() is None:
            raise ValueError(f"势力不存在：{power_id}")
    relation = db.get_diplomatic_relation(proposer, target)
    envoy_name = str(terms.get("envoy") or "")
    envoy = _character(db, envoy_name)
    modifier = 0.0
    if envoy is not None:
        modifiers = evaluate_character_modifier(
            envoy,
            "negotiation",
            db=db,
            turn=int(getattr(state, "turn", terms.get("turn") or 0) or 0),
        )
        modifier = sum(float(item.delta) for item in modifiers)
    blockers = _hard_blockers(db, proposer, target, terms)
    chance = _clamp(
        round(
            40
            + int(relation["public_relation"]) * 0.20
            + int(relation["trust"]) * 0.20
            + modifier
        ),
        5,
        95,
    )
    missing = [key for key in CLAUSE_KEYS if key not in terms]
    allowed = ["counter_offer", "reject_terms"]
    if not missing and not blockers:
        allowed.extend(["propose_terms", "accept_terms"])
    if relation.get("status") in {"allied", "friendly", "neutral", "war", "hostile"}:
        allowed.append("breach_or_pressure")
    
    # 扩展 facts：添加军力对比、战略态势、活跃条约
    power_balance = _build_power_balance(db, proposer, target)
    strategic_context = _build_strategic_context(db, proposer, target)
    active_treaties = _build_active_treaties(db, proposer, target)
    
    return build_adjudication_pack(
        kind="diplomacy",
        turn=int(getattr(state, "turn", terms.get("turn") or 0) or 0),
        subject_id=f"{proposer}:{target}",
        facts={
            "proposer": proposer,
            "target": target,
            "relation": relation,
            "terms": terms,
            "envoy": {
                "name": envoy_name,
                "diplomacy_modifier": round(modifier, 2),
            },
            "hard_blockers": blockers,
            "missing_clause_keys": missing,
            "power_balance": power_balance,
            "strategic_context": strategic_context,
            "active_treaties": active_treaties,
        },
        rules={
            "clause_keys": list(CLAUSE_KEYS),
            "acceptance_chance": chance,
            "acceptance_rule": "关系、互信与使臣外交修正影响接受率；硬阻断不可由高外交覆盖。",
            "breach_rule": "违约必须通过 breach_treaty 结算互信、名分、婚姻/人质与战争风险。",
            "free_diplomacy_bounds": {
                "relation_delta_min": -30,
                "relation_delta_max": 30,
                "trust_delta_min": -20,
                "trust_delta_max": 20,
                "coordination_delta_min": -20,
                "coordination_delta_max": 20,
                "requires_fact_justification": True,
                "requires_historical_plausibility": True,
                "impossible_conditions": ["超自然力量", "跨时代技术", "凭空生成兵力"],
            },
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["free_treaty_activation", "unvalidated_territory_change", "ignore_existing_obligations"],
        ai_options=[{"outcome": item, "label": item} for item in allowed],
        audit={
            "acceptance_chance": chance,
            "hard_blockers": blockers,
            "diplomacy_modifier": round(modifier, 2),
            "power_balance": power_balance,
            "strategic_context": strategic_context,
        },
        source_tables=["diplomatic_relations", "diplomacy_treaties", "characters", "family_relations", "powers"],
    )


# ---------------------------------------------------------------------------
# 自由外交裁决边界常量
# ---------------------------------------------------------------------------

DIPLOMACY_DELTA_BOUNDS = {
    "relation_delta": (-30, 30),
    "trust_delta": (-20, 20),
    "coordination_delta": (-20, 20),
}

DIPLOMACY_FORBIDDEN_TEXT = {
    "割让": "不得写未获规则允许的领土变化",
    "易主": "不得写未获规则允许的领土变化",
    "条约生效": "不得用叙事直接使条约生效",
    "盟约生效": "不得用叙事直接使条约生效",
    "援军": "不得凭空生成援军",
    "增援": "不得凭空生成援军",
    "凭空生成兵力": "不得凭空生成援军",
}

# AI 推理中声称的事实关键词 → 需要在盘面事实中找到支撑
DIPLOMACY_CLAIM_KEYWORDS = {
    "共同敌人": "common_enemies",
    "军力优势": "proposer_superior",
    "军力远超": "proposer_superior",
}


def _check_diplomacy_fact_consistency(pack: Dict[str, object], proposal: Dict[str, object]) -> None:
    """检查 AI 推理中是否引用了裁决包中不存在的事实。
    
    如果 AI 声称'共同敌人'，那么 pack.facts.strategic_context.common_enemies 必须非空。
    如果 AI 声称'军力优势'，那么 pack.facts.power_balance.ratio 必须 > 1.0。
    """
    reasoning_text = " ".join(str(r) for r in proposal.get("reasoning", []))
    facts = pack.get("facts", {})
    strategic_context = facts.get("strategic_context", {})
    power_balance = facts.get("power_balance", {})
    
    # 检查共同敌人
    if "共同敌人" in reasoning_text:
        common_enemies = strategic_context.get("common_enemies", [])
        if not common_enemies:
            raise ValueError("AI 声称'共同敌人'，但盘面事实不支持（双方没有共同敌人）。")
    
    # 检查军力优势
    if "军力优势" in reasoning_text or "军力远超" in reasoning_text:
        ratio = power_balance.get("ratio", 0.0)
        if ratio <= 1.0:
            raise ValueError("AI 声称'军力优势'，但盘面事实不支持（提案方军力并不占优）。")


def _validate_free_diplomacy(
    pack: Dict[str, object],
    proposal: Dict[str, object],
) -> Dict[str, object]:
    """校验 AI 的自由外交提案是否在边界内。
    
    自由外交提案使用 diplomacy_action 字段（而非 outcome），并输出有界 delta 修正。
    """
    # 1. 可行性检查：impossible 方案退回标准外交
    feasibility = str(proposal.get("feasibility", "medium"))
    if feasibility == "impossible":
        return {
            "diplomacy_action": "标准外交",
            "relation_delta": 0,
            "trust_delta": 0,
            "coordination_delta": 0,
            "feasibility": "impossible",
            "reasoning": proposal.get("reasoning", []),
            "narrative": str(proposal.get("narrative", "")),
            "risk_note": str(proposal.get("risk_note", "")),
            "recommended_followup": str(proposal.get("recommended_followup", "")),
        }
    
    # 2. 提取并裁剪 deltas
    relation_delta = int(proposal.get("relation_delta", 0))
    trust_delta = int(proposal.get("trust_delta", 0))
    coordination_delta = int(proposal.get("coordination_delta", 0))
    
    rel_min, rel_max = DIPLOMACY_DELTA_BOUNDS["relation_delta"]
    trust_min, trust_max = DIPLOMACY_DELTA_BOUNDS["trust_delta"]
    coord_min, coord_max = DIPLOMACY_DELTA_BOUNDS["coordination_delta"]
    
    relation_delta = max(rel_min, min(rel_max, relation_delta))
    trust_delta = max(trust_min, min(trust_max, trust_delta))
    coordination_delta = max(coord_min, min(coord_max, coordination_delta))
    
    # 3. 无使臣时上限收紧（trust_delta 上限从 +20 降到 +10）
    facts = pack.get("facts", {})
    envoy = facts.get("envoy", {})
    has_envoy = bool(envoy.get("name"))
    if not has_envoy:
        trust_delta = max(trust_min, min(10, trust_delta))
    
    # 4. 事实一致性检查
    _check_diplomacy_fact_consistency(pack, proposal)
    
    # 5. 禁止文本检查（reasoning 和 narrative 都检查）
    reasoning_text = " ".join(str(r) for r in proposal.get("reasoning", []))
    narrative = str(proposal.get("narrative", ""))
    combined = f"{reasoning_text}\n{narrative}"
    for marker, message in DIPLOMACY_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)
    
    # 6. 也检查通用禁止文本（与战斗共享的）
    from ming_sim.adjudication import COMMON_FORBIDDEN_TEXT
    for marker, message in COMMON_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)
    
    return {
        "diplomacy_action": str(proposal.get("diplomacy_action", "自由外交")),
        "relation_delta": relation_delta,
        "trust_delta": trust_delta,
        "coordination_delta": coordination_delta,
        "feasibility": feasibility,
        "reasoning": proposal.get("reasoning", []),
        "narrative": narrative,
        "risk_note": str(proposal.get("risk_note", "")),
        "recommended_followup": str(proposal.get("recommended_followup", "")),
    }


def run_diplomacy_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """外交 AI 裁判：统一走自由路径。白名单路径已废弃。"""
    try:
        return _validate_free_diplomacy(pack, proposal)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}


def _log(
    db,
    *,
    turn: int,
    power_a: str,
    power_b: str,
    treaty_id: int,
    field: str,
    old_value: object,
    new_value: object,
    reason: str,
    actor: str,
) -> None:
    first, second = db._relation_pair(power_a, power_b)
    db.conn.execute(
        """
        INSERT INTO diplomacy_logs
        (turn, power_a, power_b, treaty_id, field, old_value, new_value, reason, actor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(turn), first, second, int(treaty_id), field,
            json.dumps(old_value, ensure_ascii=False) if isinstance(old_value, (dict, list)) else str(old_value),
            json.dumps(new_value, ensure_ascii=False) if isinstance(new_value, (dict, list)) else str(new_value),
            reason, actor,
        ),
    )


def accept_treaty(db, treaty_id: int) -> Dict[str, object]:
    row = db.conn.execute(
        "SELECT * FROM diplomacy_treaties WHERE id=?", (int(treaty_id),)
    ).fetchone()
    if row is None:
        raise ValueError(f"盟约不存在：{treaty_id}")
    if str(row["status"]) != "proposed":
        raise ValueError(f"盟约当前不可接受：{row['status']}")
    terms = json.loads(str(row["terms"] or "{}"))
    relation = db.get_diplomatic_relation(str(row["proposer"]), str(row["target"]))
    first, second = db._relation_pair(str(row["proposer"]), str(row["target"]))
    db.conn.execute(
        """
        UPDATE diplomatic_relations
        SET obligations=?, territorial_claims=?, marriage_hostages=?, military_coordination=?,
            public_relation=?, trust=?, status='allied', updated_at=CURRENT_TIMESTAMP
        WHERE power_a=? AND power_b=?
        """,
        (
            json.dumps(terms.get("obligations") or [], ensure_ascii=False),
            json.dumps(terms.get("territorial_claims") or {}, ensure_ascii=False),
            json.dumps(terms.get("marriage_hostages") or {}, ensure_ascii=False),
            _clamp(int(terms.get("military_coordination") or 0)),
            _clamp(int(relation["public_relation"]) + 5, -100, 100),
            _clamp(int(relation["trust"]) + 8),
            first,
            second,
        ),
    )
    db.conn.execute(
        "UPDATE diplomacy_treaties SET status='active', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(treaty_id),),
    )
    marriage = terms.get("marriage_hostages") or {}
    if isinstance(marriage, dict) and marriage.get("type") == "marriage":
        persons = [str(item) for item in (marriage.get("persons") or [])]
        if len(persons) == 2:
            db.conn.execute(
                """
                UPDATE family_relations SET status='active', updated_at=CURRENT_TIMESTAMP
                WHERE relation_type='political_marriage'
                  AND ((person_a=? AND person_b=?) OR (person_a=? AND person_b=?))
                """,
                (persons[0], persons[1], persons[1], persons[0]),
            )
    _log(
        db,
        turn=int(row["start_turn"] or 0),
        power_a=first,
        power_b=second,
        treaty_id=int(treaty_id),
        field="status",
        old_value="proposed",
        new_value="active",
        reason="双方接受盟约",
        actor=str(row["target"]),
    )
    db.conn.commit()
    item = db.list_diplomacy_treaties()
    return next(treaty for treaty in item if int(treaty["id"]) == int(treaty_id))


def breach_treaty(
    db,
    state: object,
    treaty_id: int,
    actor: str,
    action: Dict[str, object],
) -> Dict[str, object]:
    row = db.conn.execute(
        "SELECT * FROM diplomacy_treaties WHERE id=?", (int(treaty_id),)
    ).fetchone()
    if row is None:
        raise ValueError(f"盟约不存在：{treaty_id}")
    if str(row["status"]) != "active":
        raise ValueError(f"只有生效盟约可以违背：{row['status']}")
    parties = {str(row["proposer"]), str(row["target"])}
    if actor not in parties:
        raise ValueError("违约者不是盟约当事方。")
    other = next(item for item in parties if item != actor)
    relation = db.get_diplomatic_relation(actor, other)
    first, second = db._relation_pair(actor, other)
    old_trust = int(relation["trust"])
    old_public = int(relation["public_relation"])
    old_coordination = int(relation["military_coordination"])
    old_marriage = dict(relation.get("marriage_hostages") or {})
    marriage = dict(old_marriage)
    if marriage.get("status") == "active" or marriage.get("type") == "marriage":
        marriage["status"] = "broken"
        marriage["broken_by"] = actor
        persons = [str(item) for item in (marriage.get("persons") or [])]
        if len(persons) == 2:
            db.conn.execute(
                """
                UPDATE family_relations SET status='broken', updated_at=CURRENT_TIMESTAMP
                WHERE relation_type='political_marriage'
                  AND ((person_a=? AND person_b=?) OR (person_a=? AND person_b=?))
                """,
                (persons[0], persons[1], persons[1], persons[0]),
            )
    action_type = str(action.get("type") or "breach")
    war_triggered = action_type in {"attack", "declare_war", "seize_territory"}
    new_status = "war" if war_triggered else "hostile"
    new_trust = _clamp(old_trust - 30)
    new_public = _clamp(old_public - 15, -100, 100)
    new_coordination = _clamp(old_coordination - 25)
    db.conn.execute(
        """
        UPDATE diplomatic_relations
        SET public_relation=?, trust=?, military_coordination=?, marriage_hostages=?, status=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE power_a=? AND power_b=?
        """,
        (
            new_public,
            new_trust,
            new_coordination,
            json.dumps(marriage, ensure_ascii=False),
            new_status,
            first,
            second,
        ),
    )
    db.conn.execute(
        "UPDATE diplomacy_treaties SET status='breached', end_turn=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(getattr(state, "turn", 0)), int(treaty_id)),
    )
    if war_triggered:
        db.conn.execute("UPDATE powers SET stance='敌对' WHERE id IN (?, ?)", (actor, other))
    if actor == "liu_bei":
        state.metrics["名分"] = _clamp(int(state.metrics.get("名分", 50)) - 10)
        state.metrics["士族支持"] = _clamp(int(state.metrics.get("士族支持", 50)) - 8)
    elif other == "liu_bei":
        state.metrics["名分"] = _clamp(int(state.metrics.get("名分", 50)) + 2)
        state.metrics["士族支持"] = _clamp(int(state.metrics.get("士族支持", 50)) - 2)
    turn = int(getattr(state, "turn", 0))
    changes = (
        ("trust", old_trust, new_trust),
        ("public_relation", old_public, new_public),
        ("military_coordination", old_coordination, new_coordination),
        ("marriage_hostages", old_marriage, marriage),
        ("status", relation["status"], new_status),
    )
    for field, old_value, new_value in changes:
        if old_value != new_value:
            _log(
                db,
                turn=turn,
                power_a=first,
                power_b=second,
                treaty_id=int(treaty_id),
                field=field,
                old_value=old_value,
                new_value=new_value,
                reason=f"{actor}违背{row['treaty_type']}",
                actor=actor,
            )
    db.conn.commit()
    return {
        "treaty_id": int(treaty_id),
        "status": "breached",
        "actor": actor,
        "other_party": other,
        "war_triggered": war_triggered,
        "trust_delta": new_trust - old_trust,
        "public_relation_delta": new_public - old_public,
        "military_coordination_delta": new_coordination - old_coordination,
        "marriage_consequence": marriage,
        "broken_obligations": json.loads(str(row["terms"] or "{}")).get("obligations") or [],
    }


# ---------------------------------------------------------------------------
# 战争状态 → 外交持续漂移（第四期）
# ---------------------------------------------------------------------------


def apply_war_diplomatic_drift(db, state: object) -> list[dict]:
    """战争状态下外交关系每月持续漂移。幂等。

    每对处于 war 的关系：
    - public_relation -2（下限 -100）
    - trust -1（下限 0）
    - military_coordination 归零
    写入 diplomacy_logs 审计，reason='war_drift'。
    每对关系每月只漂移一次（按 turn + power_a + power_b + reason 去重）。
    """
    turn = int(getattr(state, "turn", 0))
    drifts: list[dict] = []

    war_relations = db.conn.execute(
        "SELECT * FROM diplomatic_relations WHERE status='war'",
    ).fetchall()

    for rel in war_relations:
        pa = str(rel["power_a"])
        pb = str(rel["power_b"])

        # 幂等守卫
        existing = db.conn.execute(
            "SELECT id FROM diplomacy_logs "
            "WHERE turn=? AND power_a=? AND power_b=? AND reason='war_drift' "
            "LIMIT 1",
            (turn, pa, pb),
        ).fetchone()
        if existing is not None:
            continue

        old_pr = int(rel["public_relation"] or 0)
        old_trust = int(rel["trust"] or 0)
        old_coord = int(rel["military_coordination"] or 0)

        new_pr = max(-100, old_pr - 2)
        new_trust = max(0, old_trust - 1)
        new_coord = 0

        db.conn.execute(
            "UPDATE diplomatic_relations "
            "SET public_relation=?, trust=?, military_coordination=? "
            "WHERE power_a=? AND power_b=?",
            (new_pr, new_trust, new_coord, pa, pb),
        )

        # 审计日志
        _log(db, turn=turn, power_a=pa, power_b=pb, treaty_id=0,
             field="public_relation", old_value=old_pr, new_value=new_pr,
             reason="war_drift", actor="system")
        _log(db, turn=turn, power_a=pa, power_b=pb, treaty_id=0,
             field="trust", old_value=old_trust, new_value=new_trust,
             reason="war_drift", actor="system")
        if old_coord != 0:
            _log(db, turn=turn, power_a=pa, power_b=pb, treaty_id=0,
                 field="military_coordination", old_value=old_coord, new_value=0,
                 reason="war_drift", actor="system")

        drifts.append({
            "power_a": pa, "power_b": pb,
            "public_relation_delta": new_pr - old_pr,
            "trust_delta": new_trust - old_trust,
        })

    db.conn.commit()
    return drifts
