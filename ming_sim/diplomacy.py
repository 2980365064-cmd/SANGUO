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
        },
        rules={
            "clause_keys": list(CLAUSE_KEYS),
            "acceptance_chance": chance,
            "acceptance_rule": "关系、互信与使臣外交修正影响接受率；硬阻断不可由高外交覆盖。",
            "breach_rule": "违约必须通过 breach_treaty 结算互信、名分、婚姻/人质与战争风险。",
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["free_treaty_activation", "unvalidated_territory_change", "ignore_existing_obligations"],
        ai_options=[{"outcome": item, "label": item} for item in allowed],
        audit={
            "acceptance_chance": chance,
            "hard_blockers": blockers,
            "diplomacy_modifier": round(modifier, 2),
        },
        source_tables=["diplomatic_relations", "diplomacy_treaties", "characters", "family_relations"],
    )


def run_diplomacy_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    try:
        return validate_ai_proposal(
            pack,
            proposal,
            allowed_change_kinds=[
                "treaty_proposal", "treaty_status", "relation_status", "trust",
                "public_relation", "military_coordination", "marriage_hostages",
            ],
        )
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
