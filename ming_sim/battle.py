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
    check_forbidden_fields,
    record_pending_adjudication,
    run_adjudication,
)
from ming_sim.national_focus import national_focus_modifier
from ming_sim.sanguo_rules import find_strategic_route, require_city_node
from ming_sim.world_simulation import battle_environment
from ming_sim.military import composition_multiplier, morale_delta, normalize_composition, proportional_losses


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
        return "同地"
    edge = find_strategic_route(db, source, target)
    if edge is None:
        raise ValueError(f"{source} 与 {target} 之间无直连路线。")
    return edge.kind


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


def _army_score(db, army, node_id: str, side: str, *, audit: bool, turn: int, enemy_composition: Dict[str, int] | None = None) -> Tuple[float, Dict[str, object]]:
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
    composition = normalize_composition(json.loads(str(army["troop_composition"] or "{}")))
    enemy_composition = enemy_composition or {}
    composition_multiplier_value, composition_notes = composition_multiplier(composition, enemy_composition, kind)
    offices = db.conn.execute(
        "SELECT rank, merit FROM character_military_records WHERE character_name=?",
        (str(army["commander"]),),
    ).fetchone()
    merit = int(offices["merit"] or 0) if offices else 0
    rank = str(offices["rank"] or "裨将") if offices else "裨将"
    deputy_bonus = 0.03 if str(army["deputy_commander"] or "") else 0.0
    adjutant_bonus = max(0.0, (int(army["discipline"] or 0) - 50) / 1000) if str(army["military_adjutant"] or "") else 0.0
    office_multiplier = 1 + deputy_bonus + adjutant_bonus
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
        composition_multiplier_value,
        office_multiplier,
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
        "troop_composition": composition,
        "composition_multiplier": round(composition_multiplier_value, 3),
        "composition_notes": composition_notes,
        "commander_rank": rank,
        "commander_merit": merit,
        "office_multiplier": round(office_multiplier, 3),
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
    attacker_composition: Dict[str, int] = {}
    defender_composition: Dict[str, int] = {}
    for army in attackers:
        for troop, amount in normalize_composition(json.loads(str(army["troop_composition"] or "{}"))).items():
            attacker_composition[troop] = attacker_composition.get(troop, 0) + amount
    for army in defenders:
        for troop, amount in normalize_composition(json.loads(str(army["troop_composition"] or "{}"))).items():
            defender_composition[troop] = defender_composition.get(troop, 0) + amount
    attacker_breakdown = [_army_score(db, army, node_id, "attacker", audit=audit, turn=turn, enemy_composition=defender_composition) for army in attackers]
    defender_breakdown = [_army_score(db, army, node_id, "defender", audit=audit, turn=turn, enemy_composition=attacker_composition) for army in defenders]
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
    environment = battle_environment(db, state, str(calculation["terrain"]["kind"]), node_id=node_id)
    
    # 获取区域状态数据（用于事实一致性检查）
    # regional_world_states 以郡 ID 为主键，需从城池获取所属郡
    regional_state = {}
    commandery_id = ""
    city_row = db.conn.execute(
        "SELECT commandery_id FROM administrative_cities WHERE id=?", (node_id,)
    ).fetchone()
    if city_row:
        commandery_id = str(city_row["commandery_id"])
    lookup_id = commandery_id or node_id
    regional_row = db.conn.execute(
        "SELECT * FROM regional_world_states WHERE region_id=?", (lookup_id,)
    ).fetchone()
    if regional_row:
        regional_state = dict(regional_row)
    
    # 获取防守方军队的原始 supply 值（用于事实一致性检查）
    defender_supply = {}
    for defender_id in defender_ids:
        row = db.conn.execute(
            "SELECT id, supply, supply_combat_multiplier FROM armies WHERE id=?",
            (defender_id,)
        ).fetchone()
        if row:
            defender_supply[str(defender_id)] = {
                "supply": int(row["supply"] or 0),
                "supply_combat_multiplier": float(row["supply_combat_multiplier"] or 1.0),
            }
    
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
            "environment": environment,
            "regional_state": regional_state,  # 新增：区域状态数据
        },
        rules={
            "weights": {"hard_rules": 0.6, "ai_tactic": 0.4},
            "environment_bounds": {"probability_delta": [-8, 8]},
            "random_rule": "1-100 <= final_probability 时攻方获胜",
            "commander_fate_gate": "仅在战果差距达到规则阈值时允许被俘/重伤/撤退；不允许战役直接写死亡。",
            "territory_rule": "野战/突袭不得直接改变郡县归属；夺城必须走围城或专门规则。",
        },
        allowed_outcomes=_allowed_outcomes(hard_probability),
        forbidden_outcomes=list(BATTLE_FORBIDDEN_OUTCOMES),
        ai_options=_available_tactic_options(db, calculation),
        audit={**calculation, "environment": environment},
        source_tables=["armies", "characters", "administrative_cities", "strategic_routes", "national_focus_effects"],
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


def _validate_free_tactic(pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """校验 AI 的自由战术提案是否在边界内。
    
    自由战术路径：玩家用自然语言描述战术意图，AI 基于裁决包事实评估可行性，
    输出有界修正。与基准战术路径（TACTIC_RULES 白名单）互补。
    
    安全边界：
    - delta 范围：[-5, +15]
    - 无特性匹配时 delta 上限 +10，有特性匹配时上限 +15
    - actor 必须是参战统帅
    - feasibility=impossible 退回正面交锋
    - 禁止文本检查（reasoning 和 narrative 都不能写死亡/领土/增兵等）
    - 事实一致性检查（AI 声称的条件必须在盘面中存在）
    """
    # 提取字段（带默认值）
    tactic_name = str(proposal.get("tactic_name") or "custom").strip()
    actor = str(proposal.get("actor") or "").strip()
    delta = int(proposal.get("delta", 0))
    feasibility = str(proposal.get("feasibility", "medium")).strip()
    reasoning = proposal.get("reasoning") or []
    narrative = str(proposal.get("narrative") or "")
    
    # 1. actor 必须是参战统帅
    calculation = pack.get("audit")
    if not isinstance(calculation, dict):
        raise ValueError("裁决包缺少战斗审计数据。")
    attacker_commanders = {
        str(item["commander"])
        for item in calculation["army_breakdown"]["attackers"]  # type: ignore[index]
    }
    if actor not in attacker_commanders:
        raise ValueError("执行者必须是已参战的攻方统帅")
    
    # 2. feasibility=impossible 退回正面交锋
    if feasibility == "impossible":
        return {
            "tactic": "正面交锋",
            "actor": actor,
            "delta": 0,
            "narrative": "方案不可行，退回正面交锋。",
        }
    
    # 3. 禁止文本检查（reasoning 和 narrative 都不能包含禁止文本）
    reasoning_text = " ".join(str(r) for r in reasoning) if isinstance(reasoning, list) else str(reasoning)
    combined_text = f"{reasoning_text}\n{narrative}"
    for marker, message in BATTLE_FORBIDDEN_TEXT.items():
        if marker in combined_text:
            raise ValueError(message)
    
    # 4. delta 边界检查
    DELTA_MIN = -5
    DELTA_MAX = 15
    DELTA_MAX_WITHOUT_TRAIT = 10
    
    if delta < DELTA_MIN:
        delta = DELTA_MIN
    if delta > DELTA_MAX:
        delta = DELTA_MAX
    
    # 5. 检查是否有特性匹配（用于 delta 上限）
    has_trait_match = False
    character = None
    # 从 pack 中获取人物数据
    facts = pack.get("facts", {})
    army_breakdown = facts.get("army_breakdown", {})
    attackers = army_breakdown.get("attackers", [])
    for attacker in attackers:
        if str(attacker.get("commander", "")) == actor:
            # 检查是否有相关特性
            trait_modifiers = attacker.get("trait_modifiers", [])
            if trait_modifiers:
                has_trait_match = True
            break
    
    # 无特性匹配时上限 +10
    if not has_trait_match and delta > DELTA_MAX_WITHOUT_TRAIT:
        delta = DELTA_MAX_WITHOUT_TRAIT
    
    # 6. 事实一致性检查（AI 声称的条件必须在盘面中存在）
    facts_text = json.dumps(facts, ensure_ascii=False)
    claim_keywords = {
        "瘟疫": ("epidemic_pressure", 60),
        "疫病": ("epidemic_pressure", 60),
        "粮草不济": ("supply", None),
        "粮草不足": ("supply", None),
        "断粮": ("supply", None),
        "士气低落": ("morale", None),
        "防备松懈": ("discipline", None),
        "暴雨": ("weather", None),
        "大雨": ("weather", None),
    }
    for keyword, (fact_key, threshold) in claim_keywords.items():
        if keyword in reasoning_text:
            # 检查盘面事实是否支持该声称
            if not _fact_supports_claim(facts, fact_key, threshold, keyword):
                raise ValueError(f"AI 声称'{keyword}'，但裁决包事实不支持")
    
    # 7. 通过，返回校验结果
    return {
        "tactic": tactic_name,
        "actor": actor,
        "delta": delta,
        "narrative": narrative,
        "feasibility": feasibility,
        "reasoning": reasoning if isinstance(reasoning, list) else [reasoning],
    }


def _fact_supports_claim(facts: Dict[str, object], fact_key: str, threshold: int | None, keyword: str) -> bool:
    """检查盘面事实是否支持 AI 的声称。
    
    例如：AI 声称"瘟疫"，但 epidemic_pressure 只有 10，则不支持。
    """
    # 检查区域状态（regional_world_states）
    regional_state = facts.get("regional_state", {})
    environment = facts.get("environment", {})
    
    # 检查 epidemic_pressure
    if fact_key == "epidemic_pressure":
        epidemic_pressure = int(regional_state.get("epidemic_pressure", 0))
        min_threshold = threshold if threshold is not None else 60
        return epidemic_pressure >= min_threshold
    
    # 检查天气
    if fact_key == "weather":
        probability_delta = environment.get("probability_delta", 0)
        # 如果声称"暴雨/大雨"，检查 weather narrative 中是否有相关词
        narrative = str(environment.get("narrative", ""))
        if "暴雨" in narrative or "大雨" in narrative:
            return True
        # 或者检查 probability_delta
        if probability_delta > 0:
            return True
        return False
    
    # 检查军队状态（supply, morale, discipline）
    if fact_key == "supply":
        # 检查防守方军队的 supply
        army_breakdown = facts.get("army_breakdown", {})
        defenders = army_breakdown.get("defenders", [])
        for defender in defenders:
            supply = int(defender.get("supply_multiplier", 1.0) * 100)
            if supply < 50:  # 补给不足 50% 认为"粮草不济"
                return True
        return False
    
    if fact_key == "morale":
        # 检查防守方军队的 morale
        army_breakdown = facts.get("army_breakdown", {})
        defenders = army_breakdown.get("defenders", [])
        for defender in defenders:
            morale = int(defender.get("morale", 50))
            if morale < 40:  # 士气低于 40 认为"士气低落"
                return True
        return False
    
    if fact_key == "discipline":
        # 检查防守方军队的 discipline
        army_breakdown = facts.get("army_breakdown", {})
        defenders = army_breakdown.get("defenders", [])
        for defender in defenders:
            discipline = int(defender.get("discipline", 50))
            if discipline < 40:  # 纪律低于 40 认为"防备松懈"
                return True
        return False
    
    # 默认返回 True（不阻止）
    return True


def validate_battle_plan(
    db,
    battle_input: Dict[str, object],
    ai_choice: Dict[str, object],
    state: object | None = None,
) -> Dict[str, object]:
    """校验战斗计划。统一走自由战术路径（白名单已废弃）。"""
    pack = build_battle_adjudication_pack(db, state, battle_input)
    return validate_battle_ai_choice(db, pack, ai_choice)


def validate_battle_ai_choice(db, pack: Dict[str, object], ai_choice: Dict[str, object]) -> Dict[str, object]:
    """校验 AI/参谋输出是否仍在裁决包边界内。

    统一走自由战术路径（_validate_free_tactic）。白名单路径已废弃。
    """
    # 禁止字段检查（如 reinforcements, spawn_army 等）
    check_forbidden_fields(ai_choice)

    narrative = str(ai_choice.get("narrative") or "")
    risk_note = str(ai_choice.get("risk_note") or "")
    recommended_followup = str(ai_choice.get("recommended_followup") or "")
    combined = f"{narrative}\n{risk_note}\n{recommended_followup}"
    for marker, message in BATTLE_FORBIDDEN_TEXT.items():
        if marker in combined:
            raise ValueError(message)

    # 统一走自由战术路径
    # 兼容：如果 AI 使用 tactic 字段而非 tactic_name，自动映射
    choice = dict(ai_choice)
    if "tactic" in choice and "tactic_name" not in choice:
        choice["tactic_name"] = choice["tactic"]

    result = _validate_free_tactic(pack, choice)

    result["risk_note"] = risk_note
    result["recommended_followup"] = recommended_followup
    return result


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
        battle_input = pack.get("battle_input") or {}
        result = run_adjudication(
            db,
            state,
            "battle",
            str(pack.get("subject_id") or ""),
            llm_config=llm_config,
            agno_db=agno_db,
            battle_input=battle_input,
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
    morale_change, morale_reasons = morale_delta(
        casualty_rate=casualty_rate, won=won, discipline=int(army["discipline"] or 50),
        has_deputy=bool(army["deputy_commander"]), has_adjutant=bool(army["military_adjutant"]),
    )
    new_morale = max(0, min(100, old_morale + morale_change))
    new_fatigue = max(0, min(100, old_fatigue + (8 if won else 15)))
    status = "战胜整备" if won else "战败撤退"
    original_composition = normalize_composition(json.loads(str(army["troop_composition"] or "{}")))
    remaining_composition = proportional_losses(original_composition, casualties)
    db.conn.execute(
        "UPDATE armies SET manpower=?, troop_composition=?, troop_type=?, morale=?, fatigue=?, status=? WHERE id=?",
        (new_manpower, json.dumps(remaining_composition, ensure_ascii=False), "、".join(remaining_composition), new_morale, new_fatigue, status, army["id"]),
    )
    reason = "结构化战役结算：" + "、".join(morale_reasons)
    db.log_army_rule_change(state, str(army["id"]), "manpower", old_manpower, new_manpower, reason, actor="战役系统")
    db.log_army_rule_change(state, str(army["id"]), "morale", old_morale, new_morale, reason, actor="战役系统")
    db.log_army_rule_change(state, str(army["id"]), "fatigue", old_fatigue, new_fatigue, reason, actor="战役系统")
    db.log_army_rule_change(state, str(army["id"]), "troop_composition", original_composition, remaining_composition, reason, actor="战役系统")
    return {
        "army_id": str(army["id"]),
        "casualties": casualties,
        "troop_composition_before": original_composition,
        "troop_composition_after": remaining_composition,
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


def _award_battle_merit(db, state, armies, *, won: bool, source_ref: str) -> list[Dict[str, object]]:
    """战功完全来自已经结算的战役事实；UNIQUE 守卫保证重放不重复累加。"""
    awarded = []
    for army in armies:
        commander = str(army["commander"] or "")
        if not commander:
            continue
        delta = 12 if won else 3
        if int(army["morale"] or 0) >= 70:
            delta += 2
        try:
            cur = db.conn.execute(
                "INSERT INTO military_merit_logs (turn, character_name, army_id, source_type, source_ref, merit_delta, details_json) VALUES (?, ?, ?, 'battle', ?, ?, ?)",
                (int(getattr(state, "turn", 0)), commander, str(army["id"]), source_ref, delta, json.dumps({"won": won}, ensure_ascii=False)),
            )
        except Exception:
            continue
        if cur.rowcount:
            db.conn.execute(
                "INSERT OR IGNORE INTO character_military_records (character_name) VALUES (?)", (commander,)
            )
            db.conn.execute("UPDATE character_military_records SET merit=merit+?, updated_turn=? WHERE character_name=?", (delta, int(getattr(state, "turn", 0)), commander))
            awarded.append({"character": commander, "army_id": str(army["id"]), "merit_delta": delta})
    return awarded


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
    environment = battle_environment(db, state, str(calculation["terrain"]["kind"]), node_id=node_id)
    environment_delta = int(environment["probability_delta"])
    tactic_component = max(30, min(70, 50 + int(tactic["delta"]) * 2))
    final_probability = round(max(5, min(95, hard_probability * 0.6 + tactic_component * 0.4 + environment_delta)), 2)
    # 稳定 battle_subject_id：node + sorted attacker/defender ids
    battle_subject_id = f"{node_id}:{sorted(attacker_ids)}:{sorted(defender_ids)}"
    from ming_sim.world_random import draw_int
    roll = draw_int(
        db, state=state, domain="battle", subject_id=battle_subject_id,
        low=1, high=100, draw_kind="resolution",
        metadata={
            "final_probability": final_probability,
            "hard_probability": hard_probability,
            "environment_delta": environment_delta,
            "tactic_component": tactic_component,
        },
    )
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
    merit_awards = _award_battle_merit(db, state, attackers, won=attacker_won, source_ref=f"battle:{turn}:{battle_subject_id}")
    merit_awards += _award_battle_merit(db, state, defenders, won=not attacker_won, source_ref=f"battle:{turn}:{battle_subject_id}")
    margin = abs(roll - final_probability)
    fates = _commander_fates(db, defenders if attacker_won else attackers, margin, node_id)
    result: Dict[str, object] = {
        "battle_id": 0,
        "turn": turn,
        "node_id": node_id,
        "winner": winner,
        "weights": {"hard_rules": 0.6, "ai_tactic": 0.4},
        "hard_probability": hard_probability,
        "environment_probability_delta": environment_delta,
        "environment": environment,
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
            "merit_awards": merit_awards,
            "attribute_log_context": "battle_command",
            "random_rule": "1-100 <= final_probability 时攻方获胜",
            "environment": environment,
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
