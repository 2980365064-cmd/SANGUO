"""三国战役预览与 60/40 可审计裁决。"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from typing import Dict, List, Sequence, Tuple

from ming_sim.character_effects import evaluate_character_modifier, evaluate_trait_modifiers
from ming_sim.adjudication import (
    adjudication_runtime_from_state,
    build_adjudication_pack,
    record_pending_adjudication,
    run_adjudication,
)
from ming_sim.national_focus import national_focus_modifier
from ming_sim.sanguo_rules import province_block_between


TACTIC_RULES = {
    "正面交锋": {"delta": 0},
    "佯攻诱敌": {"delta": 7, "min_intelligence": 75},
    "夜袭": {"delta": 7, "min_intelligence": 70, "min_courage": 70},
    "火攻": {"delta": 10, "trait": "火攻"},
    "水战突击": {"delta": 10, "trait": "水战", "terrain": "江河"},
    "山地伏击": {"delta": 10, "trait": "山地", "terrain": "山道"},
}

BATTLE_FORBIDDEN_OUTCOMES = [
    "new_reinforcements",
    "unlisted_death",
    "unearned_capture",
    "territory_change_without_siege",
    "ignore_supply",
    "revive_character",
]

BATTLE_FORBIDDEN_TEXT = {
    "援军": "不得凭空生成援军",
    "增援": "不得凭空生成援军",
    "阵亡": "不得写未获规则允许的人物死亡",
    "死亡": "不得写未获规则允许的人物死亡",
    "处死": "不得写未获规则允许的人物死亡",
    "割让": "不得写未获规则允许的领土变化",
    "易主": "不得写未获规则允许的领土变化",
    "复活": "不得复活人物",
    "忽略补给": "不得无视补给",
}


def _character(db, name: str):
    base = db.content.characters.get(name)
    if base is None:
        return None
    row = db.conn.execute(
        """
        SELECT martial, leadership, intelligence, politics, diplomacy, charisma,
               loyalty, integrity, ambition, courage, closeness_to_liu_bei,
               personal_skills, core_tier, power_id, location, status
        FROM characters WHERE name=?
        """,
        (name,),
    ).fetchone()
    if row is None:
        return base
    try:
        skills = json.loads(str(row["personal_skills"] or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        skills = []
    return replace(
        base,
        martial=int(row["martial"] or 50),
        leadership=int(row["leadership"] or 50),
        intelligence=int(row["intelligence"] or 50),
        politics=int(row["politics"] or 50),
        diplomacy=int(row["diplomacy"] or 50),
        charisma=int(row["charisma"] or 50),
        loyalty=int(row["loyalty"] or 50),
        integrity=int(row["integrity"] or 50),
        ambition=int(row["ambition"] or 50),
        courage=int(row["courage"] or 50),
        closeness_to_liu_bei=int(row["closeness_to_liu_bei"] or 0),
        personal_skills=[str(item) for item in skills] if isinstance(skills, list) else [],
        core_tier=str(row["core_tier"] or "3"),
        power_id=str(row["power_id"] or base.power_id),
        location=str(row["location"] or base.location),
        status=str(row["status"] or base.status),
    )


def _route_kind(db, source: str, target: str) -> str:
    if source == target:
        return "州块"
    try:
        return province_block_between(db, source, target).kind
    except ValueError as error:
        raise ValueError(str(error)) from error


def _load_armies(db, army_ids: Sequence[str]) -> List[object]:
    if not army_ids:
        raise ValueError("参战军队不能为空。")
    rows = []
    for army_id in army_ids:
        row = db.conn.execute(
            "SELECT * FROM armies WHERE id=? AND active=1", (str(army_id),)
        ).fetchone()
        if row is None:
            raise ValueError(f"军队不存在或已失效：{army_id}")
        rows.append(row)
    if len({str(row["owner_power"]) for row in rows}) != 1:
        raise ValueError("同一方参战军队必须属于同一势力。")
    return rows


def _terrain_multiplier(side: str, kind: str) -> float:
    if side == "defender":
        return 1.05 if kind in {"江河", "山道", "关隘"} else 1.0
    return {"江河": 0.85, "山道": 0.85, "关隘": 0.75}.get(kind, 1.0)


def _army_score(db, army, node_id: str, side: str, *, audit: bool, turn: int) -> Tuple[float, Dict[str, object]]:
    kind = _route_kind(db, str(army["station_node"]), node_id)
    commander = _character(db, str(army["commander"]))
    leadership = int(getattr(commander, "leadership", 50))
    attribute_modifiers = (
        evaluate_character_modifier(
            commander, "battle_command", db=db if audit else None, turn=turn
        )
        if commander is not None
        else []
    )
    attribute_pct = sum(float(item.delta) for item in attribute_modifiers)
    trait_modifiers = []
    if commander is not None:
        trait_modifiers.extend(
            evaluate_trait_modifiers(commander, "field_battle", db.content.character_traits)
        )
        terrain_context = {
            "江河": "river_battle",
            "山道": "mountain_battle",
            "普通路": "plain_battle",
        }.get(kind)
        if terrain_context:
            trait_modifiers.extend(
                evaluate_trait_modifiers(commander, terrain_context, db.content.character_traits)
            )
    trait_pct = sum(float(item.delta) for item in trait_modifiers)
    training = int(army["training"] or 0)
    equipment = int(army["equipment"] or 0)
    morale = int(army["morale"] or 0)
    discipline = int(army["discipline"] or 0)
    fatigue = int(army["fatigue"] or 0)
    quality = (training + equipment + morale + discipline) / 4
    quality_multiplier = 0.5 + quality / 100
    command_multiplier = max(0.5, 1 + attribute_pct / 100)
    fatigue_multiplier = max(0.4, 1 - fatigue / 150)
    supply_multiplier = float(army["supply_combat_multiplier"] or 1.0)
    hazard_multiplier = float(army["hazard_combat_multiplier"] or 1.0)
    terrain_multiplier = _terrain_multiplier(side, kind)
    trait_multiplier = max(0.5, 1 + trait_pct / 100)
    focus_pct = 0.0
    if str(army["owner_power"]) == "liu_bei":
        if kind == "江河":
            focus_pct += national_focus_modifier(db, "river_battle_pct")
        if kind == "普通路" and "骑" in str(army["troop_type"]):
            focus_pct += national_focus_modifier(db, "plain_cavalry_pct")
    focus_multiplier = max(0.5, 1 + focus_pct / 100)
    score = max(1.0, int(army["manpower"] or 0))
    for multiplier in (
        quality_multiplier,
        command_multiplier,
        fatigue_multiplier,
        supply_multiplier,
        hazard_multiplier,
        terrain_multiplier,
        trait_multiplier,
        focus_multiplier,
    ):
        score *= multiplier
    breakdown = {
        "army_id": str(army["id"]),
        "name": str(army["name"]),
        "commander": str(army["commander"]),
        "manpower": int(army["manpower"] or 0),
        "leadership": leadership,
        "training": training,
        "equipment": equipment,
        "morale": morale,
        "discipline": discipline,
        "fatigue": fatigue,
        "quality_multiplier": round(quality_multiplier, 3),
        "command_multiplier": round(command_multiplier, 3),
        "supply_multiplier": round(supply_multiplier, 3),
        "hazard_multiplier": round(hazard_multiplier, 3),
        "fatigue_multiplier": round(fatigue_multiplier, 3),
        "terrain_multiplier": round(terrain_multiplier, 3),
        "trait_multiplier": round(trait_multiplier, 3),
        "focus_multiplier": round(focus_multiplier, 3),
        "attribute_modifiers": [
            {"attribute": item.attribute, "raw_value": item.raw_value, "delta": item.delta}
            for item in attribute_modifiers
        ],
        "trait_modifiers": [
            {"trait": item.reason, "context": item.context, "delta": item.delta}
            for item in trait_modifiers
        ],
        "route_kind": kind,
        "score": round(score, 2),
    }
    return score, breakdown


def _battle_calculation(
    db,
    attacker_ids: Sequence[str],
    defender_ids: Sequence[str],
    node_id: str,
    *,
    audit: bool = False,
    turn: int = 0,
) -> Dict[str, object]:
    if db.conn.execute("SELECT 1 FROM strategic_nodes WHERE id=?", (node_id,)).fetchone() is None:
        raise ValueError(f"战役节点不存在：{node_id}")
    attackers = _load_armies(db, attacker_ids)
    defenders = _load_armies(db, defender_ids)
    if str(attackers[0]["owner_power"]) == str(defenders[0]["owner_power"]):
        raise ValueError("攻守双方不能属于同一势力。")
    for defender in defenders:
        if str(defender["station_node"]) != node_id:
            raise ValueError(f"守军 {defender['id']} 不在战役节点 {node_id}。")
    attacker_breakdown = [
        _army_score(db, army, node_id, "attacker", audit=audit, turn=turn)
        for army in attackers
    ]
    defender_breakdown = [
        _army_score(db, army, node_id, "defender", audit=audit, turn=turn)
        for army in defenders
    ]
    attacker_score = sum(item[0] for item in attacker_breakdown)
    defender_score = sum(item[0] for item in defender_breakdown)
    hard_probability = round(
        max(10.0, min(90.0, 50 + 40 * (attacker_score - defender_score) / (attacker_score + defender_score))),
        2,
    )
    terrain_kinds = [item[1]["route_kind"] for item in attacker_breakdown]
    priority = {"关隘": 4, "江河": 3, "山道": 2, "普通路": 1}
    primary_terrain = max(terrain_kinds, key=lambda item: priority.get(str(item), 0))
    return {
        "node_id": node_id,
        "attacker_ids": [str(item) for item in attacker_ids],
        "defender_ids": [str(item) for item in defender_ids],
        "hard_probability": hard_probability,
        "hard_scores": {
            "attacker": round(attacker_score, 2),
            "defender": round(defender_score, 2),
        },
        "army_breakdown": {
            "attackers": [item[1] for item in attacker_breakdown],
            "defenders": [item[1] for item in defender_breakdown],
        },
        "terrain": {"kind": primary_terrain, "attacker_routes": terrain_kinds},
    }


def preview_battle(db, attacker_ids: List[str], defender_ids: List[str], node_id: str) -> Dict[str, object]:
    calculation = _battle_calculation(db, attacker_ids, defender_ids, node_id)
    hard = float(calculation.pop("hard_probability"))
    calculation.update(
        {
            "win_probability_range": [max(0, round(hard - 12)), min(100, round(hard + 12))],
            "major_factors": [
                "兵力与训练装备",
                "统率与智略",
                "士气与疲劳",
                "粮秣与险路状态",
                f"地形：{calculation['terrain']['kind']}",
                "人物特性",
            ],
            "duration_turns": 1,
        }
    )
    return calculation


def _allowed_outcomes(hard_probability: float) -> List[str]:
    outcomes = ["attacker_minor_win", "stalemate", "defender_minor_win"]
    if hard_probability >= 65:
        outcomes.insert(0, "attacker_major_win")
    if hard_probability <= 35:
        outcomes.append("defender_major_win")
    return outcomes


def _available_tactic_options(db, calculation: Dict[str, object]) -> List[Dict[str, object]]:
    options: List[Dict[str, object]] = []
    attacker_commanders = [
        str(item["commander"])
        for item in calculation["army_breakdown"]["attackers"]  # type: ignore[index]
    ]
    for actor in attacker_commanders:
        character = _character(db, actor)
        if character is None:
            continue
        for tactic, rule in TACTIC_RULES.items():
            required_trait = str(rule.get("trait") or "")
            required_terrain = str(rule.get("terrain") or "")
            terrain = str(calculation["terrain"]["kind"])  # type: ignore[index]
            if required_trait and required_trait not in character.personal_skills:
                continue
            if required_terrain and terrain not in {required_terrain, "州块"}:
                continue
            if int(getattr(character, "intelligence", 50)) < int(rule.get("min_intelligence") or 0):
                continue
            if int(getattr(character, "courage", 50)) < int(rule.get("min_courage") or 0):
                continue
            options.append({
                "tactic": tactic,
                "actor": actor,
                "delta": int(rule.get("delta") or 0),
            })
    return options


def build_battle_adjudication_pack(
    db,
    state: object,
    battle_input: Dict[str, object],
) -> Dict[str, object]:
    """把真实盘面整理成战斗裁决包；AI 只应在此包边界内发挥。"""
    attacker_ids = [str(item) for item in battle_input.get("attacker_ids", [])]
    defender_ids = [str(item) for item in battle_input.get("defender_ids", [])]
    node_id = str(battle_input.get("node_id") or "")
    turn = int(getattr(state, "turn", 0))
    calculation = _battle_calculation(db, attacker_ids, defender_ids, node_id, audit=True, turn=turn)
    hard_probability = float(calculation["hard_probability"])
    battle_input_payload = {
        "attacker_ids": attacker_ids,
        "defender_ids": defender_ids,
        "node_id": node_id,
    }
    pack = build_adjudication_pack(
        kind="battle",
        turn=turn,
        subject_id=node_id,
        facts={
            "node_id": node_id,
            "terrain": calculation["terrain"],
            "hard_scores": calculation["hard_scores"],
            "army_breakdown": calculation["army_breakdown"],
        },
        rules={
            "weights": {"hard_rules": 0.6, "ai_tactic": 0.4},
            "random_rule": "1-100 <= final_probability 时攻方获胜",
            "commander_fate_gate": "仅在战果差距达到规则阈值时允许被俘/重伤/撤退；不允许战役直接写死亡。",
            "territory_rule": "野战/突袭不得直接改变郡县归属；夺城必须走围城或专门规则。",
        },
        allowed_outcomes=_allowed_outcomes(hard_probability),
        forbidden_outcomes=list(BATTLE_FORBIDDEN_OUTCOMES),
        ai_options=_available_tactic_options(db, calculation),
        audit=calculation,
        source_tables=["armies", "characters", "strategic_nodes", "strategic_routes", "national_focus_effects"],
    )
    pack.update({
        "battle_input": battle_input_payload,
        "probabilities": {
            "attacker_base": hard_probability,
            "attacker_base_range": [max(0, round(hard_probability - 12)), min(100, round(hard_probability + 12))],
        },
    })
    return pack


def _validate_ai_choice(db, calculation: Dict[str, object], ai_choice: Dict[str, object]) -> Dict[str, object]:
    forbidden = {
        "reinforcements": "不得凭空生成援军",
        "援军": "不得凭空生成援军",
        "revive": "不得复活人物",
        "复活": "不得复活人物",
        "ignore_supply": "不得无视补给",
        "忽略补给": "不得无视补给",
    }
    for key, message in forbidden.items():
        if key in ai_choice:
            raise ValueError(message)
    tactic = str(ai_choice.get("tactic") or "").strip()
    if tactic not in TACTIC_RULES:
        raise ValueError(f"计策不在白名单：{tactic}")
    actor = str(ai_choice.get("actor") or "").strip()
    attacker_commanders = {
        str(item["commander"])
        for item in calculation["army_breakdown"]["attackers"]  # type: ignore[index]
    }
    if actor not in attacker_commanders:
        raise ValueError("计策执行者必须是已参战的攻方统帅。")
    character = _character(db, actor)
    if character is None:
        raise ValueError(f"计策执行者未建档：{actor}")
    rule = TACTIC_RULES[tactic]
    required_trait = str(rule.get("trait") or "")
    if required_trait and required_trait not in character.personal_skills:
        raise ValueError(f"{tactic}需要{required_trait}特性。")
    required_terrain = str(rule.get("terrain") or "")
    terrain = str(calculation["terrain"]["kind"])  # type: ignore[index]
    if required_terrain and terrain not in {required_terrain, "州块"}:
        raise ValueError(f"{tactic}只可用于{required_terrain}地形。")
    if int(getattr(character, "intelligence", 50)) < int(rule.get("min_intelligence") or 0):
        raise ValueError(f"{tactic}所需智略不足。")
    if int(getattr(character, "courage", 50)) < int(rule.get("min_courage") or 0):
        raise ValueError(f"{tactic}所需胆略不足。")
    return {
        "tactic": tactic,
        "actor": actor,
        "delta": int(rule.get("delta") or 0),
        "narrative": str(ai_choice.get("narrative") or ""),
    }


def validate_battle_plan(
    db,
    battle_input: Dict[str, object],
    ai_choice: Dict[str, object],
) -> Dict[str, object]:
    calculation = _battle_calculation(
        db,
        [str(item) for item in battle_input.get("attacker_ids", [])],
        [str(item) for item in battle_input.get("defender_ids", [])],
        str(battle_input.get("node_id") or ""),
    )
    return _validate_ai_choice(db, calculation, ai_choice)


def validate_battle_ai_choice(db, pack: Dict[str, object], ai_choice: Dict[str, object]) -> Dict[str, object]:
    """校验 AI/参谋输出是否仍在裁决包边界内。"""
    narrative = str(ai_choice.get("narrative") or "")
    risk_note = str(ai_choice.get("risk_note") or "")
    recommended_followup = str(ai_choice.get("recommended_followup") or "")
    combined = f"{narrative}\n{risk_note}\n{recommended_followup}"
    for marker, message in BATTLE_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)
    calculation = pack.get("audit")
    if not isinstance(calculation, dict):
        raise ValueError("裁决包缺少战斗审计数据。")
    tactic = _validate_ai_choice(db, calculation, ai_choice)
    tactic["risk_note"] = risk_note
    tactic["recommended_followup"] = recommended_followup
    return tactic


def run_battle_ai_choice(
    db,
    pack: Dict[str, object],
    ai_choice: Dict[str, object] | None = None,
    state: object | None = None,
    llm_config: object | None = None,
    agno_db: object | None = None,
) -> Dict[str, object]:
    """战斗 AI 参谋出口。真实 LLM 只产候选，战法仍走同一验证器。"""
    candidate = dict(ai_choice or {})
    if not candidate and llm_config is not None:
        result = run_adjudication(
            db,
            state,
            "battle",
            str(pack.get("subject_id") or ""),
            llm_config=llm_config,
            agno_db=agno_db,
            pack=pack,
        )
        if result["status"] == "validated":
            tactic = dict((result.get("validated") or {}).get("tactic") or {})
            if tactic:
                return tactic
        if result["status"] == "pending_review" and state is not None:
            pending = dict(result.get("pending_adjudication") or {})
            raise ValueError(f"战斗裁决暂停待核议：{pending.get('id', 0)}")
    if not candidate:
        options = pack.get("ai_options") if isinstance(pack.get("ai_options"), list) else []
        first = options[0] if options else {}
        candidate = {
            "tactic": str(first.get("tactic") or "正面交锋") if isinstance(first, dict) else "正面交锋",
            "actor": str(first.get("actor") or "") if isinstance(first, dict) else "",
            "narrative": "按裁决包采取稳妥战法。",
        }
    try:
        return validate_battle_ai_choice(db, pack, candidate)
    except ValueError as error:
        if state is not None:
            pending = record_pending_adjudication(db, state, pack, str(error), candidate)
            raise ValueError(f"战斗裁决暂停待核议：{pending['id']}") from error
        options = pack.get("ai_options") if isinstance(pack.get("ai_options"), list) else []
        default = next(
            (item for item in options if isinstance(item, dict) and item.get("tactic") == "正面交锋"),
            options[0] if options else {},
        )
        fallback = {
            "tactic": str(default.get("tactic") or "正面交锋") if isinstance(default, dict) else "正面交锋",
            "actor": str(default.get("actor") or "") if isinstance(default, dict) else "",
            "narrative": "参谋输出越界，已按裁决包退回默认战法。",
        }
        tactic = validate_battle_ai_choice(db, pack, fallback)
        tactic["ai_choice_rejected_reason"] = str(error)
        return tactic


def resolve_battle_from_pack(
    db,
    state: object,
    pack: Dict[str, object],
    ai_choice: Dict[str, object],
) -> Dict[str, object]:
    battle_input = pack.get("battle_input")
    if not isinstance(battle_input, dict):
        raise ValueError("裁决包缺少 battle_input。")
    return resolve_battle(db, state, battle_input, validate_battle_ai_choice(db, pack, ai_choice))


def _apply_army_outcome(db, state, army, casualty_rate: float, won: bool) -> Dict[str, object]:
    old_manpower = int(army["manpower"] or 0)
    old_morale = int(army["morale"] or 0)
    old_fatigue = int(army["fatigue"] or 0)
    casualties = min(old_manpower, round(old_manpower * casualty_rate))
    new_manpower = old_manpower - casualties
    new_morale = max(0, min(100, old_morale + (3 if won else -10)))
    new_fatigue = max(0, min(100, old_fatigue + (8 if won else 15)))
    status = "战胜整备" if won else "战败撤退"
    db.conn.execute(
        "UPDATE armies SET manpower=?, morale=?, fatigue=?, status=? WHERE id=?",
        (new_manpower, new_morale, new_fatigue, status, army["id"]),
    )
    reason = "结构化战役结算"
    db.log_army_rule_change(state, str(army["id"]), "manpower", old_manpower, new_manpower, reason, actor="战役系统")
    db.log_army_rule_change(state, str(army["id"]), "morale", old_morale, new_morale, reason, actor="战役系统")
    db.log_army_rule_change(state, str(army["id"]), "fatigue", old_fatigue, new_fatigue, reason, actor="战役系统")
    return {
        "army_id": str(army["id"]),
        "casualties": casualties,
        "manpower_before": old_manpower,
        "manpower_after": new_manpower,
        "manpower_delta": new_manpower - old_manpower,
        "morale_before": old_morale,
        "morale_after": new_morale,
        "morale_delta": new_morale - old_morale,
        "fatigue_before": old_fatigue,
        "fatigue_after": new_fatigue,
        "fatigue_delta": new_fatigue - old_fatigue,
        "status": status,
    }


def _commander_fates(db, losing_armies: Sequence[object], margin: float, node_id: str) -> List[Dict[str, str]]:
    if margin < 15:
        return []
    fates: List[Dict[str, str]] = []
    seen = set()
    for army in losing_armies:
        name = str(army["commander"])
        if name in seen:
            continue
        seen.add(name)
        row = db.conn.execute(
            "SELECT core_tier, status FROM characters WHERE name=?", (name,)
        ).fetchone()
        tier = str(row["core_tier"] or "3") if row else "3"
        if tier in {"S", "1"}:
            outcome = "被俘" if margin >= 35 else ("重伤" if margin >= 25 else "撤退")
        else:
            outcome = "失势" if margin >= 30 else "撤退"
        if outcome == "被俘":
            db.conn.execute(
                "UPDATE characters SET status='imprisoned', status_reason='战役被俘', location=? WHERE name=?",
                (node_id, name),
            )
        else:
            db.conn.execute(
                "UPDATE characters SET status_reason=? WHERE name=?",
                (f"战役{outcome}", name),
            )
        fates.append({"name": name, "core_tier": tier, "outcome": outcome})
    return fates


def resolve_battle(
    db,
    state: object,
    battle_input: Dict[str, object],
    ai_choice: Dict[str, object] | None,
    llm_config: object | None = None,
    agno_db: object | None = None,
) -> Dict[str, object]:
    attacker_ids = [str(item) for item in battle_input.get("attacker_ids", [])]
    defender_ids = [str(item) for item in battle_input.get("defender_ids", [])]
    node_id = str(battle_input.get("node_id") or "")
    turn = int(getattr(state, "turn", 0))
    prebattle_preview = preview_battle(db, attacker_ids, defender_ids, node_id)
    pack = build_battle_adjudication_pack(db, state, battle_input)
    if ai_choice:
        tactic = validate_battle_ai_choice(db, pack, ai_choice)
    else:
        tactic = run_battle_ai_choice(db, pack, None, state=state, llm_config=llm_config, agno_db=agno_db)
    calculation = _battle_calculation(
        db, attacker_ids, defender_ids, node_id, audit=True, turn=turn
    )
    hard_probability = float(calculation["hard_probability"])
    tactic_component = max(30, min(70, 50 + int(tactic["delta"]) * 2))
    final_probability = round(hard_probability * 0.6 + tactic_component * 0.4, 2)
    roll = int(random.randint(1, 100))
    attacker_won = roll <= final_probability
    winner = "attacker" if attacker_won else "defender"
    attackers = _load_armies(db, attacker_ids)
    defenders = _load_armies(db, defender_ids)
    variability = (roll % 4) / 100
    winner_rate = 0.05 + variability
    loser_rate = 0.18 + variability
    changes: List[Dict[str, object]] = []
    for army in attackers:
        changes.append(_apply_army_outcome(db, state, army, winner_rate if attacker_won else loser_rate, attacker_won))
    for army in defenders:
        changes.append(_apply_army_outcome(db, state, army, loser_rate if attacker_won else winner_rate, not attacker_won))
    margin = abs(roll - final_probability)
    fates = _commander_fates(db, defenders if attacker_won else attackers, margin, node_id)
    result: Dict[str, object] = {
        "battle_id": 0,
        "turn": turn,
        "node_id": node_id,
        "winner": winner,
        "weights": {"hard_rules": 0.6, "ai_tactic": 0.4},
        "hard_probability": hard_probability,
        "ai_tactic_component": tactic_component,
        "final_probability": final_probability,
        "random_roll": roll,
        "ai_tactic": tactic,
        "hard_scores": calculation["hard_scores"],
        "terrain": calculation["terrain"],
        "army_breakdown": calculation["army_breakdown"],
        "adjudication_pack": pack,
        "allowed_outcomes": pack["allowed_outcomes"],
        "forbidden_outcomes": pack["forbidden_outcomes"],
        "commander_fates": fates,
        "audit": {
            "army_changes": changes,
            "attribute_log_context": "battle_command",
            "random_rule": "1-100 <= final_probability 时攻方获胜",
        },
    }
    cursor = db.conn.execute(
        """
        INSERT INTO battles
        (turn, node_id, attacker_ids, defender_ids, preview, ai_choice, random_roll, result, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'resolved')
        """,
        (
            turn,
            node_id,
            json.dumps(attacker_ids, ensure_ascii=False),
            json.dumps(defender_ids, ensure_ascii=False),
            json.dumps(prebattle_preview, ensure_ascii=False),
            json.dumps(tactic, ensure_ascii=False),
            roll,
            json.dumps(result, ensure_ascii=False),
        ),
    )
    result["battle_id"] = int(cursor.lastrowid)
    db.conn.execute(
        "UPDATE battles SET result=? WHERE id=?",
        (json.dumps(result, ensure_ascii=False), int(cursor.lastrowid)),
    )
    db.conn.commit()
    return result


def resolve_battle_orders_for_turn(
    db,
    state: object,
    llm_config: object | None = None,
    agno_db: object | None = None,
) -> List[Dict[str, object]]:
    turn = int(getattr(state, "turn", 0))
    runtime_llm, runtime_agno = adjudication_runtime_from_state(state)
    llm_config = llm_config if llm_config is not None else runtime_llm
    agno_db = agno_db if agno_db is not None else runtime_agno
    rows = db.conn.execute(
        "SELECT id, army_id, payload FROM army_orders WHERE turn=? AND status='issued' AND order_type='突袭' ORDER BY id",
        (turn,),
    ).fetchall()
    results: List[Dict[str, object]] = []
    for row in rows:
        order_id = int(row["id"])
        try:
            payload = json.loads(str(row["payload"] or "{}"))
            target = str(payload.get("target") or payload.get("to") or "")
            commander_row = db.conn.execute(
                "SELECT commander FROM armies WHERE id=?", (str(row["army_id"]),)
            ).fetchone()
            explicit_choice = payload.get("ai_choice") if isinstance(payload.get("ai_choice"), dict) else None
            fallback_choice = {
                "tactic": "正面交锋",
                "actor": str(commander_row["commander"] if commander_row else ""),
            }
            result = resolve_battle(
                db,
                state,
                {
                    "attacker_ids": [str(row["army_id"])],
                    "defender_ids": payload.get("defender_ids") or [],
                    "node_id": target,
                },
                explicit_choice if (explicit_choice or llm_config is not None) else fallback_choice,
                llm_config=llm_config,
                agno_db=agno_db,
            )
            order_result = {
                "order_id": order_id,
                "status": "resolved",
                "battle_id": result["battle_id"],
                "winner": result["winner"],
            }
            status = "resolved"
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            order_result = {"order_id": order_id, "status": "rejected", "reason": str(error)}
            status = "rejected"
        db.conn.execute(
            "UPDATE army_orders SET status=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, json.dumps(order_result, ensure_ascii=False), order_id),
        )
        results.append(order_result)
    db.conn.commit()
    return results
