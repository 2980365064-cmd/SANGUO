"""刘备政权五阶段身份与十槽简化官制。"""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# 自由人事路径边界常量
# ---------------------------------------------------------------------------

FREE_PERSONNEL_BOUNDS = {
    "efficiency_delta": (-10, 20),
}

PERSONNEL_FORBIDDEN_TEXT = {
    **COMMON_FORBIDDEN_TEXT,
}


STAGES = ("流亡军", "荆州立足", "益州治蜀", "汉中王", "称帝后")
JINGZHOU_NODES = {"xiangyang", "jiangling", "jiangxia", "jingnan"}

# 十槽官制 key 列表（与 content/sanguo_offices.json 对应）
GOVERNMENT_OFFICE_KEYS = frozenset({
    "chief_strategist", "military_chief", "civil_chief",
    "finance_chief", "diplomacy_chief", "intelligence_chief",
    "main_commander", "guard_commander", "governor", "theater_governor",
})

STAGE_SEMANTICS = {
    "流亡军": {"address": "主公", "meeting": "军议", "scene": "夏口军营", "imperial": False},
    "荆州立足": {"address": "主公", "meeting": "府议", "scene": "荆州治所", "imperial": False},
    "益州治蜀": {"address": "主公", "meeting": "成都军府议事", "scene": "成都军府", "imperial": False},
    "汉中王": {"address": "大王", "meeting": "王府议事", "scene": "汉中王府", "imperial": False},
    "称帝后": {"address": "陛下", "meeting": "朝会", "scene": "蜀汉宫城", "imperial": True},
}


def government_stage(year: int, month: int, world_state: Dict[str, object]) -> str:
    """年份仅供事件层参考，身份本身只由已实现的世界状态决定。"""
    del year, month
    if bool(world_state.get("proclaimed_emperor")):
        return "称帝后"
    titles = {str(item) for item in (world_state.get("titles") or [])}
    if "汉中王" in titles:
        return "汉中王"
    controlled = {str(item) for item in (world_state.get("controlled_nodes") or [])}
    if "chengdu" in controlled:
        return "益州治蜀"
    if controlled & JINGZHOU_NODES:
        return "荆州立足"
    return "流亡军"


def stage_semantics(stage: str) -> Dict[str, object]:
    if stage not in STAGE_SEMANTICS:
        raise ValueError(f"未知政权阶段：{stage}")
    return dict(STAGE_SEMANTICS[stage])


def office_effect(db, office_key: str) -> Dict[str, object]:
    definition = db.content.sanguo_offices.get(office_key)
    if definition is None:
        raise ValueError(f"未知三国职位：{office_key}")
    assignment = db.conn.execute(
        "SELECT character_name, target_id, appointed_turn FROM government_offices WHERE office_key=?",
        (office_key,),
    ).fetchone()
    vacancy_penalty = max(0, int(definition.get("vacancy_penalty") or 0))
    if assignment is None or not str(assignment["character_name"]):
        return {
            "office_key": office_key,
            "name": str(definition["name"]),
            "character_name": "",
            "target_id": "",
            "vacant": True,
            "efficiency": max(0, 100 - vacancy_penalty),
            "vacancy_penalty": vacancy_penalty,
            "action_blocked": False,
            "effect": str(definition.get("effect") or ""),
        }
    character_name = str(assignment["character_name"])
    ability_field = str(definition.get("ability_field") or "politics")
    character = db.conn.execute(
        f"SELECT status, {ability_field} AS ability_value FROM characters WHERE name=?",
        (character_name,),
    ).fetchone()
    active = character is not None and str(character["status"]) == "active"
    ability = int(character["ability_value"] or 50) if character else 0
    efficiency = max(0, min(120, round(80 + (ability - 50) * 0.4)))
    if not active:
        efficiency = max(0, efficiency - vacancy_penalty)
    return {
        "office_key": office_key,
        "name": str(definition["name"]),
        "character_name": character_name,
        "target_id": str(assignment["target_id"] or ""),
        "vacant": not active,
        "efficiency": efficiency,
        "ability_field": ability_field,
        "ability_value": ability,
        "vacancy_penalty": vacancy_penalty if not active else 0,
        "action_blocked": False,
        "effect": str(definition.get("effect") or ""),
    }


def appoint_office(
    db,
    state: object,
    office_key: str,
    character_name: str,
    target_id: str = "",
) -> Dict[str, object]:
    if office_key not in db.content.sanguo_offices:
        raise ValueError(f"未知三国职位：{office_key}")
    character = db.conn.execute(
        "SELECT status, power_id FROM characters WHERE name=?", (character_name,)
    ).fetchone()
    if character is None or str(character["status"]) != "active":
        raise ValueError("只能任命当前可用人物。")
    if str(character["power_id"]) != "liu_bei":
        raise ValueError("只能任命刘备集团当前人物。")
    old = db.conn.execute(
        "SELECT character_name FROM government_offices WHERE office_key=?", (office_key,)
    ).fetchone()
    old_name = str(old["character_name"] or "") if old else ""
    turn = int(getattr(state, "turn", 0))
    db.conn.execute(
        """
        INSERT INTO government_offices (office_key, character_name, target_id, appointed_turn)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(office_key) DO UPDATE SET
            character_name=excluded.character_name,
            target_id=excluded.target_id,
            appointed_turn=excluded.appointed_turn,
            updated_at=CURRENT_TIMESTAMP
        """,
        (office_key, character_name, target_id, turn),
    )
    db.conn.execute(
        """
        INSERT INTO government_office_logs
        (turn, office_key, old_character, new_character, target_id, reason)
        VALUES (?, ?, ?, ?, ?, '玩家任命')
        """,
        (turn, office_key, old_name, character_name, target_id),
    )
    db.conn.commit()
    # 任免的长期政治后果必须有结构化日志，供月报和人物档案追溯。
    from ming_sim.long_term import adjust_character_loyalty
    if old_name and old_name != character_name:
        adjust_character_loyalty(
            db, state, old_name, -3, f"被改任，原任{office_key}由{character_name}接替",
            source_kind="appointment", source_id=office_key,
        )
    if old_name != character_name:
        adjust_character_loyalty(
            db, state, character_name, 2, f"受任{office_key}",
            source_kind="appointment", source_id=office_key,
        )
    return office_effect(db, office_key)


def build_personnel_adjudication_pack(
    db,
    state: object,
    office_key: str,
    candidate_name: str = "",
    target_id: str = "",
) -> Dict[str, object]:
    if office_key not in db.content.sanguo_offices:
        raise ValueError(f"未知三国职位：{office_key}")
    definition = db.content.sanguo_offices[office_key]
    current = office_effect(db, office_key)
    ability_field = str(definition.get("ability_field") or "politics")
    candidates = []
    rows = db.conn.execute(
        f"""
        SELECT name, office, status, power_id, location, {ability_field} AS ability_value,
               loyalty, integrity, ambition, courage, closeness_to_liu_bei
        FROM characters
        WHERE power_id='liu_bei' AND status='active'
        ORDER BY ability_value DESC, name
        LIMIT 12
        """
    ).fetchall()
    for row in rows:
        candidates.append(dict(row))
    candidate = next((item for item in candidates if str(item["name"]) == candidate_name), None)
    if candidate is None and candidate_name:
        row = db.conn.execute(
            f"""
            SELECT name, office, status, power_id, location, {ability_field} AS ability_value,
                   loyalty, integrity, ambition, courage, closeness_to_liu_bei
            FROM characters WHERE name=?
            """,
            (candidate_name,),
        ).fetchone()
        candidate = dict(row) if row else None
    allowed = ["review_office", "keep_current"]
    if candidate and str(candidate.get("status")) == "active" and str(candidate.get("power_id")) == "liu_bei":
        allowed.append("appoint_candidate")
    return build_adjudication_pack(
        kind="personnel",
        turn=int(getattr(state, "turn", 0)),
        subject_id=office_key,
        facts={
            "office": {
                **current,
                "definition": {
                    "ability_field": ability_field,
                    "effect": str(definition.get("effect") or ""),
                    "vacancy_penalty": int(definition.get("vacancy_penalty") or 0),
                },
            },
            "candidate": candidate or {},
            "candidate_pool": candidates,
            "target_id": str(target_id or ""),
        },
        rules={
            "appointment_rule": "只能任命刘备集团当前 active 人物。",
            "authority_rule": "实际任命必须调用 appoint_office。",
            "efficiency_rule": "效率由职位能力字段与人物当前状态计算，空缺或不可用会触发惩罚。",
        },
        allowed_outcomes=allowed,
        forbidden_outcomes=["appoint_foreign_character", "appoint_inactive_character", "free_office_effect"],
        ai_options=[{"outcome": item, "label": item} for item in allowed],
        audit={"current_effect": current, "ability_field": ability_field},
        source_tables=["government_offices", "characters", "government_office_logs", "content.sanguo_offices"],
    )


def _validate_free_personnel(pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """校验 AI 的自由人事提案是否在边界内。

    AI 通过查询工具获取人事数据后，输出自由评估。
    校验器确保 efficiency_delta 在安全范围内，且 AI 的声称与盘面事实一致。
    """
    # 1. feasibility=impossible → 安全默认（维持现状）
    feasibility = str(proposal.get("feasibility", "medium"))
    if feasibility == "impossible":
        return {
            "personnel_action": "维持现状",
            "candidate": "",
            "efficiency_delta": 0,
            "feasibility": "impossible",
            "reasoning": proposal.get("reasoning", []),
            "narrative": str(proposal.get("narrative", "人事方案不可行，维持现状。")),
            "risk_note": str(proposal.get("risk_note", "")),
        }

    # 1b. 禁止字段检查
    check_forbidden_fields(proposal)

    # 2. 提取并裁剪 efficiency_delta
    efficiency_delta = int(proposal.get("efficiency_delta", 0))
    efficiency_delta = max(
        FREE_PERSONNEL_BOUNDS["efficiency_delta"][0],
        min(FREE_PERSONNEL_BOUNDS["efficiency_delta"][1], efficiency_delta),
    )

    # 3. 禁止文本检查
    reasoning_text = " ".join(str(r) for r in proposal.get("reasoning", []))
    narrative = str(proposal.get("narrative", ""))
    combined = f"{reasoning_text}\n{narrative}"
    for marker, message in PERSONNEL_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)

    # 4. 事实一致性检查
    facts = pack.get("facts", {})
    candidate = facts.get("candidate", {})
    office = facts.get("office", {})

    # 声称"候选人能力出众" → 检查 ability_value
    if "能力出众" in reasoning_text or "才华横溢" in reasoning_text:
        ability = int(candidate.get("ability_value", 50))
        if ability < 65:
            raise ValueError("AI 声称'候选人能力出众'，但盘面事实不支持（ability<65）。")

    # 声称"忠诚度可靠" → 检查 loyalty
    if "忠诚可靠" in reasoning_text or "忠心耿耿" in reasoning_text:
        loyalty = int(candidate.get("loyalty", 50))
        if loyalty < 60:
            raise ValueError("AI 声称'忠诚可靠'，但盘面事实不支持（loyalty<60）。")

    # 提议任命但候选人不存在或不活跃
    action = str(proposal.get("personnel_action", ""))
    candidate_name = str(proposal.get("candidate", ""))
    if action == "appoint_candidate" and candidate_name:
        if not candidate or str(candidate.get("status", "")) != "active":
            raise ValueError(f"候选人 {candidate_name} 不存在或不在 active 状态。")
        if str(candidate.get("power_id", "")) != "liu_bei":
            raise ValueError(f"候选人 {candidate_name} 不属于刘备集团。")

    return {
        "personnel_action": str(proposal.get("personnel_action", "自由人事评估")),
        "outcome": str(proposal.get("outcome") or proposal.get("personnel_action", "")),
        "candidate": candidate_name,
        "efficiency_delta": efficiency_delta,
        "feasibility": feasibility,
        "reasoning": proposal.get("reasoning", []),
        "narrative": narrative,
        "risk_note": str(proposal.get("risk_note", "")),
    }


def run_personnel_ai_judge(db, state: object, pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """人事 AI 裁判：统一走自由路径。"""
    try:
        return _validate_free_personnel(pack, proposal)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, pack, str(error), proposal)
        return {"status": "pending_review", "pending_adjudication": pending}
