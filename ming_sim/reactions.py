"""受控的人物与诸侯反应层：未知但可审计，绝不直接创设世界事实。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ming_sim.adjudication import record_pending_adjudication
from ming_sim.long_term import adjust_character_loyalty, adjust_faction_support
from ming_sim.ws_utils import clamp as _clamp_base


ALLOWED_EFFECT_KINDS = {
    "reputation_log", "faction_support", "loyalty_risk", "diplomacy_pressure",
    "envoy_acceptance", "suggestion", "situation_pressure", "pending_decision",
    "tactical_modifier", "negotiation_modifier", "none",
}
REQUIRED_PROPOSAL_FIELDS = {
    "actor", "reaction_kind", "level", "motive", "narrative",
    "allowed_effect_kind", "suggested_action", "audit_basis",
}
FORBIDDEN_PROPOSAL_FIELDS = {
    "changes", "death", "ending_status", "territory_change", "controlled_by",
    "resource_delta", "treaty_active", "title_grant", "army_spawn",
}


def _seed(state, batch_id: int, subject_id: str) -> str:
    raw = f"liu-bei-reaction:{state.turn}:{batch_id}:{subject_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def validate_reaction_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """校验提案只会落为日志、建议或待决，禁止直接写世界事实。"""
    missing = sorted(REQUIRED_PROPOSAL_FIELDS - set(proposal))
    if missing:
        return {"allowed": False, "reason": f"反应提案缺少字段：{'、'.join(missing)}"}
    forbidden = sorted(FORBIDDEN_PROPOSAL_FIELDS & set(proposal))
    if forbidden:
        return {"allowed": False, "reason": f"反应提案包含越权字段：{'、'.join(forbidden)}"}
    effect = str(proposal.get("allowed_effect_kind") or "")
    if effect not in ALLOWED_EFFECT_KINDS:
        return {"allowed": False, "reason": f"反应后果不允许：{effect or '未声明'}"}
    if str(proposal.get("level") or "") not in {"minor", "medium", "major"}:
        return {"allowed": False, "reason": "反应等级不合法"}
    return {"allowed": True, "reason": "白名单校验通过"}


def _llm_reaction_proposal(llm_config, facts: dict[str, Any], fallback: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """真实模型只负责候选叙事与动机；调用失败必回到规则候选。"""
    if llm_config is None or not getattr(llm_config, "api_key", "") or getattr(llm_config, "model", "") == "test":
        return fallback, "rules_fallback"
    try:
        from agno.agent import Agent
        from ming_sim.agents import parse_agent_json, run_agent_text
        from ming_sim.llm_config import for_role
        from ming_sim.llm_model import create_chat_model

        config = for_role(llm_config, "simulator")
        agent = Agent(
            name="天下反应提案器", id="sanguo-reaction-proposer",
            model=create_chat_model(config, temperature=0.8, top_p=0.9, max_tokens=min(900, max(400, config.max_tokens)), force_json_output=True),
            instructions=["只输出严格 JSON，不得输出 Markdown。你只能提出反应，不能改变任何世界事实。"],
            add_history_to_context=False, markdown=False,
        )
        prompt = (
            "根据以下已发生的硬规则事实，拟一条人物或诸侯反应候选。\n"
            "必须完整输出 actor/reaction_kind/level/motive/narrative/allowed_effect_kind/suggested_action/audit_basis。\n"
            "actor、reaction_kind、level 与 allowed_effect_kind 必须原样使用给定值；不得输出 changes、死亡、领土、资源、条约、称号、结局或援军字段。\n"
            f"事实与固定边界：{json.dumps({**facts, 'required_actor': fallback['actor'], 'required_kind': fallback['reaction_kind'], 'required_level': fallback['level'], 'required_effect_kind': fallback['allowed_effect_kind']}, ensure_ascii=False)}"
        )
        candidate = parse_agent_json(run_agent_text(agent, prompt, "天下反应"), "天下反应")
        if not isinstance(candidate, dict):
            raise ValueError("反应模型输出不是对象")
        return candidate, "llm"
    except Exception as error:  # 模型超时、合同失败等均不可打断世界结算。
        fallback = dict(fallback)
        fallback["narrative"] = f"{fallback['narrative']}（模型未能成文，已按规则保守记录。）"
        return fallback, f"rules_fallback:{type(error).__name__}"


def _draft_resources(draft: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(draft.get("resources_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def _reaction_intensity(value: str | None) -> str:
    if value in {"restrained", "standard", "stormy"}:
        return str(value)
    try:
        from ming_sim.llm_config import load_runtime_game
        configured = str(load_runtime_game().get("world_reaction_intensity") or "standard")
        return configured if configured in {"restrained", "standard", "stormy"} else "standard"
    except Exception:
        return "standard"


def _contested_claim(db, state, resources: dict[str, Any]) -> dict[str, Any] | None:
    if resources.get("sub_type") != "identity_promotion":
        return None
    action = str(resources.get("identity_action") or "")
    row = db.conn.execute(
        """SELECT id, declared_stage, legitimacy, unmet_conditions, external_pressure
        FROM political_claims WHERE turn=? AND action=? ORDER BY id DESC LIMIT 1""",
        (int(state.turn), action),
    ).fetchone()
    if row is None or str(row["legitimacy"]) == "名实相符":
        return None
    return dict(row)


def _diplomatic_subject(db, target: str) -> tuple[str, dict[str, Any]]:
    power = db.conn.execute(
        "SELECT id, name, leader, stance, agenda, military_strength, cohesion, supply FROM powers WHERE id=? OR name=? OR leader=? LIMIT 1",
        (target, target, target),
    ).fetchone()
    if power is None:
        return "荆州士人", {"target_power": None}
    relation = db.conn.execute(
        """SELECT public_relation, trust, military_coordination, status
        FROM diplomatic_relations
        WHERE (power_a='liu_bei' AND power_b=?) OR (power_a=? AND power_b='liu_bei') LIMIT 1""",
        (str(power["id"]), str(power["id"])),
    ).fetchone()
    actor = str(power["leader"] or power["name"])
    return actor, {
        "target_power": dict(power),
        "relation": dict(relation) if relation is not None else {"status": "unknown"},
    }


def _character_subject(db, state, kind: str, seed: str) -> tuple[str, dict[str, Any]]:
    rows = db.conn.execute(
        """SELECT name, faction, loyalty, ambition, closeness_to_liu_bei, style,
                  diplomacy, martial, stewardship, leadership, intelligence, politics, charisma
        FROM characters WHERE power_id='liu_bei' AND status='active' AND name!='刘备'"""
    ).fetchall()
    if not rows:
        return "军府诸将", {"character": None, "recent_loyalty": []}
    focus = "leadership" if kind == "military" else ("diplomacy" if kind == "diplomatic" else "politics")
    ranked = sorted(rows, key=lambda row: (-int(row[focus] or 0), int(row["loyalty"] or 50), str(row["name"])))
    # 从能力相近的前三人以存档种子选择，不把反应固定在同一位名臣身上。
    pool_size = min(3, len(ranked))

    # 检查是否使用新版随机流（通过 kv_store 版本标记）
    migrated = False
    try:
        row = db.conn.execute(
            "SELECT value FROM kv_store WHERE key='geopolitical_rng_migration_v1'"
        ).fetchone()
        migrated = row is not None and str(row["value"]) == "1"
    except Exception:
        migrated = False

    if migrated:
        # 新路径：使用 draw_int 走存档级确定性随机流
        from ming_sim.world_random import draw_int
        idx = draw_int(
            db, state=state,
            domain="reaction_character",
            subject_id=seed[:16],
            low=0, high=pool_size - 1,
            draw_kind="character_select",
        )
        chosen = ranked[int(idx)]
    else:
        # 旧路径：种子字节模运算（向后兼容旧存档）
        chosen = ranked[int(seed[:2], 16) % pool_size]
    logs = db.conn.execute(
        """SELECT delta, reason, source_kind FROM character_loyalty_logs
        WHERE character_name=? ORDER BY id DESC LIMIT 3""", (str(chosen["name"]),)
    ).fetchall()
    return str(chosen["name"]), {"character": dict(chosen), "recent_loyalty": [dict(row) for row in logs]}


def _reaction_subject(db, state, *, kind: str, target: str, seed: str, is_secret: bool) -> tuple[str, dict[str, Any]]:
    if kind == "diplomatic":
        actor, facts = _diplomatic_subject(db, target)
    else:
        actor, facts = _character_subject(db, state, kind, seed)
    faction_rows = db.conn.execute(
        "SELECT faction_key, label, support, agenda FROM political_faction_states WHERE status='active' ORDER BY faction_key"
    ).fetchall()
    facts["active_factions"] = [dict(row) for row in faction_rows]
    facts["knowledge_scope"] = "密令知情范围" if is_secret else "公开方略范围"
    return actor, facts


def has_pending_major_reactions(db) -> bool:
    return db.conn.execute(
        "SELECT 1 FROM reaction_events WHERE reaction_level='major' AND status='pending_decision' LIMIT 1"
    ).fetchone() is not None


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    """数值截断，默认边界 (0, 100)。委托至 ws_utils.clamp。"""
    return _clamp_base(value, low, high)


def apply_minor_reaction_effects(db, state, facts: dict[str, Any], *, reaction_id: int) -> list[dict[str, Any]]:
    """微小反应的唯一写入规则：只影响低忠诚人物或外交互信一格。"""
    effects: list[dict[str, Any]] = []
    context = facts.get("subject_context") if isinstance(facts.get("subject_context"), dict) else {}
    character = context.get("character") if isinstance(context.get("character"), dict) else {}
    name = str(character.get("name") or "")
    loyalty = int(character.get("loyalty") or 50)
    if name and loyalty < 45:
        adjust_character_loyalty(
            db, state, name, -1, f"对“{facts.get('title', '本月方略')}”心存疑虑",
            source_kind="reaction_event", source_id=f"reaction:{reaction_id}",
        )
        effects.append({"kind": "loyalty", "character": name, "delta": -1})
        return effects
    if str(facts.get("directive_type")) != "diplomatic":
        return effects
    power = context.get("target_power") if isinstance(context.get("target_power"), dict) else {}
    power_id = str(power.get("id") or "")
    if not power_id:
        return effects
    first, second = sorted(("liu_bei", power_id))
    relation = db.conn.execute(
        "SELECT trust FROM diplomatic_relations WHERE power_a=? AND power_b=?", (first, second)
    ).fetchone()
    if relation is None:
        return effects
    before = int(relation["trust"] or 0)
    after = _clamp(before - 1, -100, 100)
    if after == before:
        return effects
    db.conn.execute(
        "UPDATE diplomatic_relations SET trust=?, updated_at=CURRENT_TIMESTAMP WHERE power_a=? AND power_b=?",
        (after, first, second),
    )
    db.conn.execute(
        """INSERT INTO diplomacy_logs (turn, power_a, power_b, field, old_value, new_value, reason, actor)
        VALUES (?, ?, ?, 'trust', ?, ?, ?, ?)""",
        (int(state.turn), first, second, str(before), str(after), "天下反应：对本月外交方略保持保留", str(facts.get("actor") or "")),
    )
    effects.append({"kind": "diplomacy_trust", "power_id": power_id, "delta": -1})
    return effects


def _medium_suggestion_text(facts: dict[str, Any], actor: str) -> str:
    title = str(facts.get("title") or "本月方略")
    directive_type = str(facts.get("directive_type") or "other")
    context = facts.get("subject_context") if isinstance(facts.get("subject_context"), dict) else {}
    if directive_type == "diplomatic":
        relation = context.get("relation") if isinstance(context.get("relation"), dict) else {}
        trust = relation.get("trust", "未详")
        return f"【天下反应·{actor}】就“{title}”，宜先明定使臣权限与互信边界（当前互信 {trust}），再行交涉。"
    character = context.get("character") if isinstance(context.get("character"), dict) else {}
    name = str(character.get("name") or actor)
    if directive_type == "military":
        return f"【天下反应·{name}】就“{title}”，请先核主将、军心与补给，再定进退与援应。"
    return f"【天下反应·{name}】就“{title}”，请先察地方官与民情、士族态度，再定施行次序。"


def _claim_decision_effects(db, state, facts: dict[str, Any], choice: str, reaction_id: int) -> list[dict[str, Any]]:
    claim = facts.get("political_claim") if isinstance(facts.get("political_claim"), dict) else {}
    claim_id = int(claim.get("id") or 0)
    if not claim_id:
        return []
    rules = {
        "安定朝议": {"pressure": -3, "factions": {"veterans": 2, "jingzhou": 2}, "reputation": 1},
        "坚持颁行": {"pressure": 3, "factions": "all_active", "faction_delta": -2, "reputation": -2},
        "暂缓解释": {"pressure": -1, "factions": {}, "reputation": 0},
    }
    rule = rules.get(choice, rules["暂缓解释"])
    row = db.conn.execute("SELECT external_pressure FROM political_claims WHERE id=?", (claim_id,)).fetchone()
    if row is None:
        return []
    before = int(row["external_pressure"] or 0)
    after = _clamp(before + int(rule["pressure"]))
    db.conn.execute("UPDATE political_claims SET external_pressure=? WHERE id=?", (after, claim_id))
    effects: list[dict[str, Any]] = [{"kind": "external_pressure", "delta": after - before, "claim_id": claim_id}]
    faction_rule = rule.get("factions")
    if faction_rule == "all_active":
        faction_deltas = {str(row["faction_key"]): int(rule["faction_delta"]) for row in db.conn.execute(
            "SELECT faction_key FROM political_faction_states WHERE status='active'"
        ).fetchall()}
    else:
        faction_deltas = dict(faction_rule or {})
    for faction, delta in faction_deltas.items():
        after_support = adjust_faction_support(
            db, state, faction, int(delta), f"对称号宣称的裁断：{choice}",
            source_kind="reaction_decision", source_id=f"reaction:{reaction_id}",
        )
        effects.append({"kind": "faction_support", "faction": faction, "delta": int(delta), "after": after_support})
    reputation_delta = int(rule["reputation"])
    if reputation_delta:
        db.add_reputation_log(
            state, source_kind="reaction_decision", source_id=f"reaction:{reaction_id}", metric="仁义",
            delta=reputation_delta, summary=f"对称号宣称作出“{choice}”之裁断。", commit=False,
        )
        effects.append({"kind": "reputation", "metric": "仁义", "delta": reputation_delta})
    return effects


def resolve_major_reaction(db, state, reaction_id: int, choice: str) -> dict[str, Any]:
    """核定重大反应；规则层按预设选项施加可审计的有限后果。"""
    row = db.conn.execute(
        "SELECT * FROM reaction_events WHERE id=? AND reaction_level='major'", (int(reaction_id),)
    ).fetchone()
    if row is None:
        raise ValueError("重大天下反应不存在")
    if str(row["status"]) != "pending_decision":
        raise ValueError("该重大天下反应已核定")
    try:
        validation = json.loads(str(row["validation_result"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        validation = {}
    pending_id = int(validation.get("pending_adjudication_id") or 0) if isinstance(validation, dict) else 0
    if pending_id:
        db.conn.execute(
            "UPDATE pending_adjudications SET status='resolved', resolved_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_review'",
            (pending_id,),
        )
    try:
        facts = json.loads(str(row["rule_facts_snapshot"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        facts = {}
    chosen = str(choice or "暂缓解释")
    effects = _claim_decision_effects(db, state, facts if isinstance(facts, dict) else {}, chosen, int(reaction_id))
    outcome = f"已由主公裁定：{chosen}。"
    if effects:
        outcome += " 已记入天下压力、派系或口碑的规则后果。"
    db.conn.execute(
        "UPDATE reaction_events SET status='resolved', outcome_summary=?, applied_effects=? WHERE id=?",
        (outcome, json.dumps(effects, ensure_ascii=False), int(reaction_id)),
    )
    db.conn.commit()
    return {"id": int(reaction_id), "status": "resolved", "choice": chosen, "outcome_summary": outcome, "applied_effects": effects}


def run_reaction_layer(
    db, state, *, batch_id: int, drafts: list[dict[str, Any]], intensity: str | None = None, llm_config=None,
) -> dict[str, Any]:
    """生成确定性反应；强度只改变微小/中等反应频率。"""
    created, summaries, pending_count = 0, [], 0
    intensity = _reaction_intensity(intensity)
    for draft in drafts:
        subject_id = str(draft.get("id") or draft.get("title") or "draft")
        exists = db.conn.execute(
            "SELECT id FROM reaction_events WHERE turn=? AND batch_id=? AND subject_type='directive' AND subject_id=?",
            (int(state.turn), int(batch_id), subject_id),
        ).fetchone()
        if exists:
            continue
        kind = str(draft.get("directive_type") or "other")
        resources = _draft_resources(draft)
        level = "medium" if kind == "diplomatic" else "minor"
        target = str(draft.get("target") or "")
        seed = _seed(state, batch_id, subject_id)
        is_secret = bool(resources.get("secret") or resources.get("is_secret") or resources.get("sub_type") == "secret_order")
        actor, subject_facts = _reaction_subject(db, state, kind=kind, target=target, seed=seed, is_secret=is_secret)
        claim = _contested_claim(db, state, resources)
        if claim:
            level, kind, actor = "major", "political_claim", "天下士人"
        elif intensity == "restrained" and level == "medium":
            level = "minor"
        elif intensity == "stormy" and level == "minor" and int(seed[-1], 16) % 2 == 0:
            level = "medium"
        facts = {
            "title": str(draft.get("title") or ""), "actor": actor, "target": target,
            "directive_type": kind, "intensity": intensity, "political_claim": claim or {},
            "subject_context": subject_facts,
        }
        narrative = f"{actor}对“{facts['title']}”有所反应。"
        suggestion_id, status, effect_kind = 0, "resolved", "reputation_log"
        if level == "medium":
            effect_kind = "suggestion"
            narrative = f"{actor}对“{facts['title']}”提出附带条件，建议已入簿。"
        elif level == "major":
            effect_kind = "pending_decision"
            narrative = f"{actor}质疑“{facts['title']}”的名实，天下议论未定，需由你亲自回应。"
        fallback_proposal = {
            "actor": actor, "reaction_kind": kind, "level": level,
            "motive": "基于已发生方略与当前政治事实的受控反应",
            "narrative": narrative, "allowed_effect_kind": effect_kind,
            "suggested_action": "先安定朝议，再对外申明立场" if level == "major" else "",
            "audit_basis": facts,
        }
        proposal, proposal_source = _llm_reaction_proposal(llm_config, facts, fallback_proposal)
        validation = validate_reaction_proposal(proposal)
        if validation["allowed"] and (
            proposal.get("level") != level or proposal.get("allowed_effect_kind") != effect_kind
        ):
            validation = {"allowed": False, "reason": "模型改变了规则指定的反应等级或后果类型"}
        if validation["allowed"] and (
            proposal.get("actor") != actor or proposal.get("reaction_kind") != kind
        ):
            validation = {"allowed": False, "reason": "模型改变了规则指定的反应主体或类别"}
        validation["proposal_source"] = proposal_source
        if not validation["allowed"]:
            status = "rejected"
            narrative = "天下反应提案越出规则边界，已驳回，不产生任何世界后果。"
        elif level == "medium":
            suggestion_id = int(db.create_suggestion(
                int(state.turn), int(state.year), int(state.period),
                _medium_suggestion_text(facts, actor), source=f"天下反应·{actor}",
            ))
            status = "suggested"
        elif level == "major":
            status = "pending_decision"
            pending = record_pending_adjudication(
                db, state,
                {"turn": int(state.turn), "kind": "reaction_event", "subject_id": f"batch:{batch_id}:draft:{subject_id}",
                 "facts": facts, "options": ["安定朝议", "坚持颁行", "暂缓解释"]},
                "重大天下反应等待主公裁断", proposal,
            )
            validation["pending_adjudication_id"] = int(pending["id"])
            pending_count += 1
        cursor = db.conn.execute(
            """INSERT INTO reaction_events
            (turn,batch_id,subject_type,subject_id,reaction_level,reaction_kind,actor,target,seed,rule_facts_snapshot,ai_proposal,validation_result,status,outcome_summary,suggestion_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(state.turn), int(batch_id), "directive", subject_id, level, kind, actor, target,
             seed, json.dumps(facts, ensure_ascii=False), json.dumps(proposal, ensure_ascii=False),
             json.dumps(validation, ensure_ascii=False), status, narrative, suggestion_id),
        )
        applied_effects: list[dict[str, Any]] = []
        if validation["allowed"] and level == "minor":
            applied_effects = apply_minor_reaction_effects(db, state, facts, reaction_id=int(cursor.lastrowid))
            if applied_effects:
                db.conn.execute(
                    "UPDATE reaction_events SET applied_effects=? WHERE id=?",
                    (json.dumps(applied_effects, ensure_ascii=False), int(cursor.lastrowid)),
                )
        created += 1
        summaries.append(narrative)
    db.conn.commit()
    return {"created": created, "summaries": summaries, "pending_count": pending_count}
