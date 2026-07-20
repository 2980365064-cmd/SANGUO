"""统一裁决包协议与待核议登记。

裁决包只整理真实盘面与规则边界；AI 输出必须先校验成结构化变更，
不能用叙事文本直接改写世界。
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from agno.agent import Agent
from agno.db.sqlite import SqliteDb

from ming_sim.agents import parse_agent_json, run_agent_text
from ming_sim.llm_config import for_role as _llm_for_role
from ming_sim.llm_model import create_chat_model
from ming_sim.models import LLMConfig
from ming_sim.exceptions import LLMContractError, LLMUnavailable


PROTOCOL_VERSION = 1

COMMON_FORBIDDEN_OUTCOMES = [
    "unlisted_death",
    "spawn_army",
    "free_reinforcements",
    "unvalidated_territory_change",
    "unvalidated_treaty_effect",
    "ignore_supply",
    "revive_character",
]

COMMON_FORBIDDEN_FIELDS = {
    "death",
    "ending_status",
    "kill_character",
    "character_death",
    "army_spawn",
    "spawn_army",
    "manpower_delta",
    "reinforcements",
    "free_reinforcements",
    "region_control",
    "controlled_by",
    "territory_delta",
    "treaty_active",
    "ignore_supply",
    "revive_character",
}

COMMON_FORBIDDEN_TEXT = {
    "阵亡": "不得写未获规则允许的人物死亡",
    "死亡": "不得写未获规则允许的人物死亡",
    "处死": "不得写未获规则允许的人物死亡",
    "援军": "不得凭空生成援军",
    "增援": "不得凭空生成援军",
    "复活": "不得复活人物",
    "割让": "不得写未获规则允许的领土变化",
    "易主": "不得写未获规则允许的领土变化",
    "条约生效": "不得用叙事直接使条约生效",
    "忽略补给": "不得无视补给",
}


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return str(value)


def build_adjudication_pack(
    *,
    kind: str,
    turn: int,
    subject_id: str,
    facts: Mapping[str, Any],
    rules: Mapping[str, Any],
    allowed_outcomes: Sequence[str],
    forbidden_outcomes: Sequence[str] | None = None,
    ai_options: Sequence[Mapping[str, Any]] | None = None,
    randomness_bounds: Mapping[str, Any] | None = None,
    apply_contract: Mapping[str, Any] | None = None,
    audit: Mapping[str, Any] | None = None,
    source_tables: Sequence[str] | None = None,
) -> Dict[str, Any]:
    forbidden = list(dict.fromkeys(list(forbidden_outcomes or []) + COMMON_FORBIDDEN_OUTCOMES))
    policy = ADJUDICATION_KIND_POLICIES.get(str(kind), {})
    return {
        "protocol_version": PROTOCOL_VERSION,
        "kind": str(kind),
        "turn": int(turn),
        "subject_id": str(subject_id),
        "randomness_level": str(policy.get("randomness_level") or "narrative"),
        "randomness_bounds": json_safe(dict(randomness_bounds or {})),
        "apply_contract": json_safe(dict(apply_contract or {"mode": "log_only"})),
        "facts": json_safe(dict(facts)),
        "rules": json_safe(dict(rules)),
        "allowed_outcomes": [str(item) for item in allowed_outcomes],
        "forbidden_outcomes": forbidden,
        "ai_options": json_safe(list(ai_options or [])),
        "ai_proposal": {},
        "validated_changes": [],
        "audit": {
            "source_tables": [str(item) for item in (source_tables or [])],
            **json_safe(dict(audit or {})),
        },
    }


def _pack_prompt(pack: Mapping[str, Any]) -> str:
    return (
        "你是 SANGUO 的受控裁判。只能基于下列裁决包作出一个 JSON 提案；"
        "不得调用外部知识覆盖当前数据库盘面，不得创造裁决包外的兵力、粮草、人物死亡、援军、领土变化或条约结果。\n"
        "输出必须是一个 JSON object，不要 Markdown，不要代码块。\n\n"
        "JSON 字段：\n"
        "- outcome: 必须为空或来自 allowed_outcomes。\n"
        "- action: 外部势力行动时必须完整复制 ai_options/legal_candidates 中的一项候选。\n"
        "- tactic / actor: 战斗时必须来自 ai_options 中同一项。\n"
        "- narrative / reason / risk_note / recommended_followup: 只能解释裁决包内事实与判断。\n"
        "- changes: 数组；除非本裁决类规则明确要求，否则留空数组。\n\n"
        "裁决包如下：\n"
        f"{json.dumps(json_safe(dict(pack)), ensure_ascii=False, sort_keys=True)}"
    )


def run_adjudication_llm(
    llm_config: LLMConfig,
    agno_db: SqliteDb | None,
    pack: Mapping[str, Any],
    *,
    tag: str = "受控裁判",
) -> Dict[str, Any]:
    """调用真实模型生成裁决提案；这里只产候选，不验证、不落库。"""
    del agno_db  # 一次性裁判不需要历史，避免污染长期对话记忆。
    model_config = _llm_for_role(llm_config, "simulator")
    agent = Agent(
        name="SANGUO受控裁判",
        id=f"adjudication-{pack.get('kind', 'world')}",
        model=create_chat_model(
            model_config,
            temperature=0.75,
            top_p=0.85,
            max_tokens=min(1800, max(800, model_config.max_tokens)),
            force_json_output=True,
        ),
        instructions=[
            "你只输出严格 JSON。你可以带来不确定性和策略偏好，但必须服从裁决包。",
            "具体事实只能来自 facts/audit/rules/ai_options/allowed_outcomes。",
            "普通叙事不能改变世界；世界改变只能通过验证后的结构化 changes/action/tactic。",
        ],
        add_history_to_context=False,
        markdown=False,
    )
    raw = run_agent_text(agent, _pack_prompt(pack), tag)
    proposal = parse_agent_json(raw, tag)
    if not isinstance(proposal, dict):
        raise ValueError("裁判模型输出顶层必须是 JSON object。")
    return proposal


ADJUDICATION_KIND_POLICIES: Dict[str, Dict[str, Any]] = {
    "battle": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "decision"},
    "power_action": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "decision"},
    "diplomacy": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "apply_limited"},
    "secret_order": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "narrative"},
    "siege": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "modifier"},
    "region_investment": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "modifier"},
    "personnel": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "narrative"},
    "supply": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "modifier"},
    "world_event": {"auto_apply": False, "failure_policy": "pending_review", "mode": "llm", "randomness_level": "apply_limited"},
}


def attach_adjudication_runtime(state: object, llm_config: LLMConfig | None, agno_db: SqliteDb | None) -> None:
    """把本次月末结算的裁判运行环境挂到 state；不落库，只在进程内有效。"""
    setattr(state, "_adjudication_llm_config", llm_config)
    setattr(state, "_adjudication_agno_db", agno_db)


def adjudication_runtime_from_state(state: object) -> tuple[LLMConfig | None, SqliteDb | None]:
    return (
        getattr(state, "_adjudication_llm_config", None),
        getattr(state, "_adjudication_agno_db", None),
    )


def _policy_for(kind: str) -> Dict[str, Any]:
    return dict(ADJUDICATION_KIND_POLICIES.get(str(kind), {}))


def _proposal_summary(proposal: Mapping[str, Any] | None) -> str:
    if not isinstance(proposal, Mapping):
        return ""
    for key in ("reason", "summary", "narrative", "risk_note", "recommended_followup"):
        text = str(proposal.get(key) or "").strip()
        if text:
            return text
    outcome = str(proposal.get("outcome") or "").strip()
    return outcome


def _audit_reason(kind: str, proposal: Mapping[str, Any] | None, validated: Mapping[str, Any] | None = None) -> str:
    summary = _proposal_summary(proposal)
    outcome = str((validated or {}).get("outcome") or (proposal or {}).get("outcome") or "").strip()
    parts = [f"{kind} 模型裁判已通过验证"]
    if outcome:
        parts.append(f"结果：{outcome}")
    if summary:
        parts.append(summary)
    return "；".join(parts)


def _validated_changes(validated: Mapping[str, Any] | None) -> List[Any]:
    if not isinstance(validated, Mapping):
        return []
    changes = validated.get("validated_changes")
    return list(changes) if isinstance(changes, list) else []


def _base_result(
    *,
    status: str,
    kind: str,
    subject_id: str,
    pack: Mapping[str, Any],
    proposal: Mapping[str, Any] | None = None,
    validated: Mapping[str, Any] | None = None,
    reason: str = "",
) -> Dict[str, Any]:
    policy = _policy_for(kind)
    proposal_text = _proposal_summary(proposal)
    return {
        "status": status,
        "kind": kind,
        "subject_id": str(subject_id),
        "randomness_level": str(policy.get("randomness_level") or pack.get("randomness_level") or "narrative"),
        "proposal_summary": proposal_text,
        "validated_changes": json_safe(_validated_changes(validated)),
        "applied_changes": [],
        "audit_reason": reason or (_audit_reason(kind, proposal, validated) if proposal else ""),
        "pack": json_safe(dict(pack)),
    }


def _build_pack_for_kind(
    db,
    state: object,
    kind: str,
    subject_id: str,
    kwargs: Mapping[str, Any],
) -> Dict[str, Any]:
    """按分类懒加载构造裁决包，避免各玩法模块与本模块循环导入。"""
    if kind == "battle":
        from ming_sim.battle import build_battle_adjudication_pack

        battle_input = kwargs.get("battle_input")
        if not isinstance(battle_input, Mapping):
            raise ValueError("battle 裁决需要 battle_input。")
        return build_battle_adjudication_pack(db, state, dict(battle_input))
    if kind == "power_action":
        from ming_sim.power_ai import build_power_action_adjudication_pack

        return build_power_action_adjudication_pack(db, state, subject_id)
    if kind == "diplomacy":
        from ming_sim.diplomacy import build_diplomacy_adjudication_pack

        proposer = str(kwargs.get("proposer") or "")
        target = str(kwargs.get("target") or subject_id)
        terms = kwargs.get("terms") if isinstance(kwargs.get("terms"), Mapping) else {}
        return build_diplomacy_adjudication_pack(db, state, proposer, target, dict(terms))
    if kind == "secret_order":
        from ming_sim.db.secret_orders import build_secret_order_adjudication_pack

        return build_secret_order_adjudication_pack(db, state, int(subject_id), viewer=str(kwargs.get("viewer") or ""))
    if kind == "siege":
        from ming_sim.siege import build_siege_adjudication_pack

        return build_siege_adjudication_pack(db, state, int(subject_id))
    if kind == "region_investment":
        from ming_sim.national_focus import build_region_investment_adjudication_pack

        return build_region_investment_adjudication_pack(db, state, subject_id, str(kwargs.get("category") or ""))
    if kind == "personnel":
        from ming_sim.government import build_personnel_adjudication_pack

        return build_personnel_adjudication_pack(
            db,
            state,
            subject_id,
            candidate_name=str(kwargs.get("candidate_name") or ""),
            target_id=str(kwargs.get("target_id") or ""),
        )
    if kind == "supply":
        from ming_sim.supply import build_supply_adjudication_pack

        return build_supply_adjudication_pack(db, state, subject_id, requested_amount=int(kwargs.get("requested_amount") or 0))
    if kind == "world_event":
        from ming_sim.historical_events import build_world_event_adjudication_pack

        return build_world_event_adjudication_pack(db, state, event_id=subject_id)
    raise ValueError(f"未知裁决分类：{kind}")


def _validate_proposal_for_kind(
    db,
    state: object,
    kind: str,
    pack: Dict[str, Any],
    proposal: Dict[str, Any],
) -> Dict[str, Any]:
    if kind == "battle":
        from ming_sim.battle import validate_battle_ai_choice

        tactic = validate_battle_ai_choice(db, pack, proposal)
        return {
            "ai_proposal": json_safe(dict(proposal)),
            "validated_changes": [],
            "tactic": json_safe(tactic),
            "outcome": str(proposal.get("outcome") or ""),
        }
    if kind == "power_action":
        from ming_sim.power_ai import run_power_action_ai_judge

        return run_power_action_ai_judge(db, state, pack, proposal)
    if kind == "diplomacy":
        from ming_sim.diplomacy import run_diplomacy_ai_judge

        return run_diplomacy_ai_judge(db, state, pack, proposal)
    if kind == "secret_order":
        from ming_sim.db.secret_orders import run_secret_order_ai_judge

        return run_secret_order_ai_judge(db, state, pack, proposal)
    if kind == "siege":
        from ming_sim.siege import run_siege_ai_judge

        return run_siege_ai_judge(db, state, pack, proposal)
    if kind == "region_investment":
        from ming_sim.national_focus import run_region_investment_ai_judge

        return run_region_investment_ai_judge(db, state, pack, proposal)
    if kind == "personnel":
        from ming_sim.government import run_personnel_ai_judge

        return run_personnel_ai_judge(db, state, pack, proposal)
    if kind == "supply":
        from ming_sim.supply import run_supply_ai_judge

        return run_supply_ai_judge(db, state, pack, proposal)
    if kind == "world_event":
        from ming_sim.historical_events import run_world_event_ai_judge

        return run_world_event_ai_judge(db, state, pack, proposal)
    raise ValueError(f"未知裁决分类：{kind}")


def run_adjudication(
    db,
    state: object,
    kind: str,
    subject_id: str,
    *,
    llm_config: LLMConfig | None,
    agno_db: SqliteDb | None,
    mode: str = "llm",
    pack: Mapping[str, Any] | None = None,
    proposal: Mapping[str, Any] | None = None,
    **pack_kwargs: Any,
) -> Dict[str, Any]:
    """统一裁决调度器：模型只出候选，分类验证器决定是否可落库。"""
    clean_kind = str(kind)
    if clean_kind not in ADJUDICATION_KIND_POLICIES:
        raise ValueError(f"未知裁决分类：{clean_kind}")
    policy = ADJUDICATION_KIND_POLICIES[clean_kind]
    built_pack = dict(pack) if isinstance(pack, Mapping) else _build_pack_for_kind(
        db, state, clean_kind, str(subject_id), pack_kwargs
    )
    if str(policy.get("mode") or "llm") != "llm":
        reason = f"{clean_kind} 当前策略为 {policy.get('mode')}，不自动调用模型裁判。"
        result = _base_result(
            status="skipped", kind=clean_kind, subject_id=str(subject_id), pack=built_pack, reason=reason
        )
        result["reason"] = reason
        return result
    if mode != "llm" or llm_config is None:
        result = _base_result(
            status="skipped", kind=clean_kind, subject_id=str(subject_id), pack=built_pack, reason="未启用模型裁判。"
        )
        result["reason"] = "未启用模型裁判。"
        return result
    try:
        candidate = dict(proposal) if isinstance(proposal, Mapping) else run_adjudication_llm(
            llm_config,
            agno_db,
            built_pack,
            tag=f"统一裁决/{clean_kind}/{subject_id}",
        )
    except (LLMUnavailable, LLMContractError, ValueError) as error:
        pending = record_pending_adjudication(db, state, built_pack, str(error), {})
        result = _base_result(
            status="pending_review",
            kind=clean_kind,
            subject_id=str(subject_id),
            pack=built_pack,
            reason=f"模型输出不可用：{error}",
        )
        result["pending_adjudication"] = pending
        return result
    try:
        validated = _validate_proposal_for_kind(db, state, clean_kind, built_pack, candidate)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, built_pack, str(error), candidate)
        result = _base_result(
            status="pending_review",
            kind=clean_kind,
            subject_id=str(subject_id),
            pack=built_pack,
            proposal=candidate,
            reason=f"模型提案越界：{error}",
        )
        result["pending_adjudication"] = pending
        return result
    if validated.get("status") == "pending_review":
        pending = dict(validated.get("pending_adjudication") or {})
        result = _base_result(
            status="pending_review",
            kind=clean_kind,
            subject_id=str(subject_id),
            pack=built_pack,
            proposal=candidate,
            validated=validated,
            reason=str(pending.get("reason") or "模型提案需廷议核定"),
        )
        result["pending_adjudication"] = pending
        result["validated"] = json_safe(validated)
        return result
    result = _base_result(
        status="validated",
        kind=clean_kind,
        subject_id=str(subject_id),
        pack=built_pack,
        proposal=candidate,
        validated=validated,
    )
    result["proposal"] = json_safe(candidate)
    result["validated"] = json_safe(validated)
    return result


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _combined_text(proposal: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ("narrative", "reason", "risk_note", "recommended_followup", "summary"):
        if key in proposal:
            parts.append(str(proposal.get(key) or ""))
    return "\n".join(parts)


def validate_ai_proposal(
    pack: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    allowed_change_kinds: Sequence[str],
    extra_validator: Callable[[Mapping[str, Any], Mapping[str, Any]], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """把 AI 候选校验成可落库的受控提案。"""
    allowed_changes = {str(item) for item in allowed_change_kinds}
    forbidden_keys = sorted((COMMON_FORBIDDEN_FIELDS - allowed_changes) & set(_walk_keys(proposal)))
    if forbidden_keys:
        raise ValueError(f"AI 裁决包含非法字段：{','.join(forbidden_keys)}")
    text = _combined_text(proposal)
    for marker, message in COMMON_FORBIDDEN_TEXT.items():
        if marker in text:
            raise ValueError(message)
    outcome = str(proposal.get("outcome") or "")
    allowed_outcomes = {str(item) for item in pack.get("allowed_outcomes", [])}
    if outcome and outcome not in allowed_outcomes:
        raise ValueError(f"AI 裁决结果不在允许范围：{outcome}")
    changes = proposal.get("changes") or []
    if not isinstance(changes, list):
        raise ValueError("AI 裁决 changes 必须是数组。")
    for change in changes:
        if not isinstance(change, Mapping):
            raise ValueError("AI 裁决 change 必须是对象。")
        kind = str(change.get("kind") or "")
        if kind not in allowed_changes:
            raise ValueError(f"AI 裁决变更类型不被允许：{kind}")
    extra = extra_validator(pack, proposal) if extra_validator else {}
    return {
        "ai_proposal": json_safe(dict(proposal)),
        "validated_changes": json_safe(changes),
        "outcome": outcome,
        "extra": json_safe(extra),
    }


def record_pending_adjudication(
    db,
    state: object,
    pack: Mapping[str, Any],
    reason: str,
    rejected_proposal: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """登记待廷议核定的越界/失败裁决。"""
    turn = int(getattr(state, "turn", pack.get("turn", 0)) or 0)
    kind = str(pack.get("kind") or "")
    subject_id = str(pack.get("subject_id") or "")
    existing = db.conn.execute(
        """
        SELECT id, reason FROM pending_adjudications
        WHERE turn=? AND kind=? AND subject_id=? AND status='pending_review'
        ORDER BY id ASC LIMIT 1
        """,
        (turn, kind, subject_id),
    ).fetchone()
    if existing is not None:
        return {
            "id": int(existing["id"]),
            "turn": turn,
            "kind": kind,
            "subject_id": subject_id,
            "status": "pending_review",
            "reason": str(existing["reason"] or reason),
            "deduped": True,
        }
    cursor = db.conn.execute(
        """
        INSERT INTO pending_adjudications
        (turn, kind, subject_id, pack_json, rejected_proposal_json, reason, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending_review')
        """,
        (
            turn,
            kind,
            subject_id,
            json.dumps(json_safe(dict(pack)), ensure_ascii=False),
            json.dumps(json_safe(dict(rejected_proposal or {})), ensure_ascii=False),
            str(reason),
        ),
    )
    db.conn.commit()
    return {
        "id": int(cursor.lastrowid),
        "turn": turn,
        "kind": kind,
        "subject_id": subject_id,
        "status": "pending_review",
        "reason": str(reason),
    }


def _monthly_batch_subjects(db, state: object) -> List[tuple[str, str, Dict[str, Any]]]:
    """收集本月适合让模型参与的裁决对象；只读查询，不直接改变世界。"""
    subjects: List[tuple[str, str, Dict[str, Any]]] = []
    turn = int(getattr(state, "turn", 0) or 0)

    for row in db.conn.execute("SELECT id FROM powers WHERE id<>'liu_bei' ORDER BY id").fetchall():
        subjects.append(("power_action", str(row["id"]), {}))

    diplomacy_rows = db.conn.execute(
        """
        SELECT proposer, target, terms FROM diplomacy_treaties
        WHERE status='proposed'
        ORDER BY id
        """
    ).fetchall()
    for row in diplomacy_rows:
        try:
            terms = json.loads(str(row["terms"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            terms = {}
        if not isinstance(terms, dict):
            terms = {}
        proposer = str(row["proposer"])
        target = str(row["target"])
        subjects.append(("diplomacy", f"{proposer}:{target}", {"proposer": proposer, "target": target, "terms": terms}))

    for row in db.conn.execute(
        "SELECT id, minister_name FROM secret_orders WHERE status IN ('active', 'pending_review') ORDER BY id"
    ).fetchall():
        subjects.append(("secret_order", str(row["id"]), {"viewer": str(row["minister_name"] or "")}))

    for row in db.conn.execute("SELECT id FROM sieges WHERE status='active' ORDER BY id").fetchall():
        subjects.append(("siege", str(row["id"]), {}))

    for row in db.conn.execute(
        "SELECT region_id, category FROM region_investments WHERE status='active' ORDER BY region_id"
    ).fetchall():
        subjects.append(("region_investment", str(row["region_id"]), {"category": str(row["category"] or "")}))

    office_rows = db.conn.execute("SELECT office_key, character_name, target_id FROM government_offices ORDER BY office_key").fetchall()
    used_offices = {str(row["office_key"]) for row in office_rows}
    for row in office_rows:
        subjects.append((
            "personnel",
            str(row["office_key"]),
            {"candidate_name": str(row["character_name"] or ""), "target_id": str(row["target_id"] or "")},
        ))
    for office_key in sorted(getattr(getattr(db, "content", None), "sanguo_offices", {}) or {}):
        if str(office_key) not in used_offices:
            subjects.append(("personnel", str(office_key), {}))

    for row in db.conn.execute("SELECT id FROM armies WHERE active=1 ORDER BY id").fetchall():
        subjects.append(("supply", str(row["id"]), {}))

    try:
        content_events = getattr(getattr(db, "content", None), "events", {})
        if isinstance(content_events, Mapping):
            event_items = sorted(content_events.items())
        else:
            event_items = [(str(getattr(event, "id", "") or (event.get("id") if isinstance(event, Mapping) else "")), event) for event in (content_events or [])]
        for event_id, event in event_items:
            is_historical = bool(
                getattr(event, "is_historical", False)
                if not isinstance(event, Mapping)
                else event.get("is_historical")
            )
            if not is_historical:
                continue
            state_row = db.conn.execute(
                "SELECT status FROM historical_event_states WHERE event_id=?", (str(event_id),)
            ).fetchone()
            status = str(state_row["status"]) if state_row is not None else "scheduled"
            if status in {"resolved", "superseded", "expired"}:
                continue
            window = getattr(event, "window", None)
            start_turn = int(getattr(window, "start_turn", 0) or 0) if window else 0
            end_turn = int(getattr(window, "end_turn", 999999) or 999999) if window else 999999
            del start_turn, end_turn
            subjects.append(("world_event", str(event_id), {}))
    except Exception:
        pass

    return subjects


def _has_existing_adjudication_trace(db, turn: int, kind: str, subject_id: str) -> bool:
    checks = {
        "power_action": (
            "SELECT 1 FROM power_ai_actions WHERE turn=? AND power_id=? LIMIT 1",
            (turn, subject_id),
        ),
        "supply": (
            "SELECT 1 FROM army_logs WHERE turn=? AND army_id=? AND field='ai_judge' LIMIT 1",
            (turn, subject_id),
        ),
        "secret_order": (
            "SELECT 1 FROM secret_orders WHERE id=? AND sim_note LIKE '%AI裁判%' LIMIT 1",
            (subject_id,),
        ),
        "siege": (
            "SELECT 1 FROM sieges WHERE id=? AND details LIKE '%ai_judge%' LIMIT 1",
            (subject_id,),
        ),
        "region_investment": (
            "SELECT 1 FROM region_investment_logs WHERE turn=? AND region_id=? AND reason LIKE '%AI裁判%' LIMIT 1",
            (turn, subject_id),
        ),
        "world_event": (
            "SELECT 1 FROM historical_chronicle WHERE turn=? AND event_id=? AND summary LIKE '%AI裁判%' LIMIT 1",
            (turn, subject_id),
        ),
    }
    if kind == "diplomacy":
        parts = subject_id.split(":", 1)
        if len(parts) != 2:
            return False
        sql = (
            "SELECT 1 FROM diplomacy_logs WHERE turn=? AND "
            "((power_a=? AND power_b=?) OR (power_a=? AND power_b=?)) "
            "AND reason LIKE '%AI裁判%' LIMIT 1"
        )
        args = (turn, parts[0], parts[1], parts[1], parts[0])
    else:
        item = checks.get(kind)
        if item is None:
            return False
        sql, args = item
    try:
        return db.conn.execute(sql, args).fetchone() is not None
    except Exception:
        return False


def run_monthly_adjudication_batch(db, state: object) -> Dict[str, Any]:
    """月末统一模型随机性批处理；真实世界变更仍交给各分类既有结构化链路。"""
    llm_config, agno_db = adjudication_runtime_from_state(state)
    if llm_config is None:
        return {"status": "skipped", "reason": "未启用模型裁判。", "results": [], "summary": {"total": 0}}
    results: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for kind, subject_id, kwargs in _monthly_batch_subjects(db, state):
        key = (kind, subject_id)
        if key in seen:
            continue
        seen.add(key)
        turn = int(getattr(state, "turn", 0) or 0)
        if _has_existing_adjudication_trace(db, turn, kind, subject_id):
            continue
        pending = db.conn.execute(
            """
            SELECT 1 FROM pending_adjudications
            WHERE turn=? AND kind=? AND subject_id=? AND status='pending_review'
            LIMIT 1
            """,
            (turn, kind, subject_id),
        ).fetchone()
        if pending is not None:
            continue
        try:
            results.append(
                run_adjudication(
                    db,
                    state,
                    kind,
                    subject_id,
                    llm_config=llm_config,
                    agno_db=agno_db,
                    **kwargs,
                )
            )
        except ValueError as error:
            results.append({
                "status": "unavailable",
                "kind": kind,
                "subject_id": subject_id,
                "reason": str(error),
                "randomness_level": str(_policy_for(kind).get("randomness_level") or ""),
                "proposal_summary": "",
                "validated_changes": [],
                "applied_changes": [],
                "audit_reason": str(error),
            })
    summary = {
        "total": len(results),
        "validated": sum(1 for item in results if item.get("status") == "validated"),
        "pending_review": sum(1 for item in results if item.get("status") == "pending_review"),
        "skipped": sum(1 for item in results if item.get("status") == "skipped"),
        "unavailable": sum(1 for item in results if item.get("status") == "unavailable"),
    }
    return {"status": "completed", "results": json_safe(results), "summary": summary}
