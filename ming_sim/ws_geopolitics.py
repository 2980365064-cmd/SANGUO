"""地缘政治反应：第三方势力对战果、围城、违约的观察与反应链。

编排层 — 协调 ws_reaction_rules（决策）和 ws_reaction_effects（效果）。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list, status_terminal as _status_terminal
from ming_sim.ws_utils import get_turn, get_year, get_period, to_json
from ming_sim.ws_common import seed_for as _seed_for, get_relation as _get_relation, get_or_create_relation as _get_or_create_relation
from ming_sim.ws_intelligence import record_external_intelligence

# 反应规则（决策层）
from ming_sim.ws_reaction_rules import (
    _eligible_third_parties,
    _determine_reaction_type,
    _battle_or_siege_reaction_legacy,
    _battle_or_siege_reaction_v2,
    _battle_or_siege_reaction,
    _treaty_breach_reaction_legacy,
    _treaty_breach_reaction_v2,
    _treaty_breach_reaction,
    _maybe_create_delayed_reaction,
    _check_delayed_condition,
)

# 反应效果（效果层）
from ming_sim.ws_reaction_effects import (
    _is_power_observable,
    _reaction_source_and_visibility,
    _compute_soft_effects,
    _compute_action_hints,
    apply_geopolitical_reaction_effects,
    build_geopolitical_intelligence_reports,
    select_player_visible_world_dynamics,
    # 向后兼容别名
    _is_bordering_liu_bei_via,
    _has_active_envoy_for,
    _can_merchant_network_between,
)


# ---------------------------------------------------------------------------
# 灾害/动乱连锁反应（incident chains）
# ---------------------------------------------------------------------------


def generate_incident_diplomatic_reactions(
    db, state, incidents: list[dict],
) -> list[dict]:
    """为区域重大事件生成外势外交反应。幂等，每势力每月最多一条。"""
    turn = get_turn(state)
    reactions: list[dict] = []

    reacted_powers: set[str] = set()

    for inc in incidents:
        if str(inc.get("tier") or "") != "dramatic":
            continue
        region_id = str(inc.get("region_id") or "")
        inc_type = str(inc.get("incident_type") or "")
        inc_id = int(inc.get("id") or 0)
        if not region_id or not inc_id:
            continue

        ctrl_row = db.conn.execute(
            "SELECT controlled_by FROM regions WHERE id=?", (region_id,),
        ).fetchone()
        if ctrl_row is None:
            continue
        controller = str(ctrl_row["controlled_by"])
        if controller == "liu_bei":
            continue

        power_row = db.conn.execute(
            "SELECT status, cohesion FROM powers WHERE id=?", (controller,),
        ).fetchone()
        if power_row is None or _status_terminal(str(power_row["status"])):
            continue

        if controller in reacted_powers:
            continue

        existing = db.conn.execute(
            "SELECT id FROM diplomacy_logs "
            "WHERE turn=? AND power_a=? AND power_b='liu_bei' AND reason='incident_chain'",
            (turn, controller),
        ).fetchone()
        if existing is not None:
            reacted_powers.add(controller)
            continue

        reaction_kind = "none"

        if inc_type in ("drought", "flood", "epidemic"):
            reaction_kind = "diplomacy_pressure"
            relation = _get_or_create_relation(db, controller, "liu_bei")
            if relation is not None:
                old_pr = int(relation["public_relation"] or 0)
                new_pr = max(-100, min(100, old_pr + 3))
                db.conn.execute(
                    "UPDATE diplomatic_relations SET public_relation=? "
                    "WHERE power_a=? AND power_b=?",
                    (new_pr, relation["power_a"], relation["power_b"]),
                )
                db.conn.execute(
                    """INSERT INTO diplomacy_logs
                    (turn, power_a, power_b, field, old_value, new_value, reason, actor)
                    VALUES (?, ?, ?, 'public_relation', ?, ?, 'incident_chain', ?)""",
                    (turn, relation["power_a"], relation["power_b"],
                     str(old_pr), str(new_pr), controller),
                )

        elif inc_type in ("bandit_surge", "refugee_influx"):
            if _at_war_with_liu_bei(db, controller):
                reaction_kind = "opportunistic_posture"
                old_coh = int(power_row["cohesion"] or 0)
                new_coh = max(0, old_coh - 2)
                db.conn.execute(
                    "UPDATE powers SET cohesion=? WHERE id=?",
                    (new_coh, controller),
                )
                db.conn.execute(
                    """INSERT INTO power_logs
                    (turn, year, period, power_id, field, old_value, new_value, delta, reason)
                    VALUES (?, ?, ?, ?, 'cohesion', ?, ?, ?, 'incident_chain')""",
                    (turn, get_year(state),
                     get_period(state),
                     controller, str(old_coh), str(new_coh), -2),
                )
                db.conn.execute(
                    """INSERT INTO diplomacy_logs
                    (turn, power_a, power_b, field, old_value, new_value, reason, actor)
                    VALUES (?, ?, 'liu_bei', 'cohesion', ?, ?, 'incident_chain', ?)""",
                    (turn, controller, str(old_coh), str(new_coh), controller),
                )

        reacted_powers.add(controller)
        reactions.append({
            "power_id": controller,
            "incident_id": inc_id,
            "reaction_kind": reaction_kind,
            "turn": turn,
        })

    db.conn.commit()
    return reactions


def _at_war_with_liu_bei(db, power_id: str) -> bool:
    """检查 power_id 是否与刘备处于战争状态。"""
    first, second = db._relation_pair(power_id, "liu_bei")
    row = db.conn.execute(
        "SELECT status FROM diplomatic_relations WHERE power_a=? AND power_b=?",
        (first, second),
    ).fetchone()
    return row is not None and str(row["status"]) == "war"


# ---------------------------------------------------------------------------
# 跨势力态势与有限反应链
# ---------------------------------------------------------------------------


def _battle_powers(db, battle: dict) -> tuple[str, str]:
    """从一场野战的 attacker_ids / defender_ids 提取攻守双方势力。"""
    attacker_ids = _decode(battle.get("attacker_ids"), [])
    defender_ids = _decode(battle.get("defender_ids"), [])
    if not isinstance(attacker_ids, list):
        attacker_ids = _safe_list(attacker_ids)
    if not isinstance(defender_ids, list):
        defender_ids = _safe_list(defender_ids)
    attacker_power = ""
    for aid in attacker_ids:
        if not isinstance(aid, str):
            continue
        row = db.conn.execute(
            "SELECT owner_power FROM armies WHERE id=?", (aid,)
        ).fetchone()
        if row is not None:
            attacker_power = str(row["owner_power"])
            break
    defender_power = ""
    for did in defender_ids:
        if not isinstance(did, str):
            continue
        row = db.conn.execute(
            "SELECT owner_power FROM armies WHERE id=?", (did,)
        ).fetchone()
        if row is not None:
            defender_power = str(row["owner_power"])
            break
    return attacker_power, defender_power


def _siege_powers(db, siege: dict) -> tuple[str, str]:
    """从一次围城提取攻守双方势力。"""
    defender_power = str(siege.get("defender_power") or "")
    attacker_power = ""
    army_id = str(siege.get("attacker_army_id") or "")
    if army_id:
        row = db.conn.execute(
            "SELECT owner_power FROM armies WHERE id=?", (army_id,)
        ).fetchone()
        if row is not None:
            attacker_power = str(row["owner_power"])
    if not defender_power:
        node_id = str(siege.get("target_node") or "")
        if node_id:
            row = db.conn.execute(
                "SELECT controlled_by FROM regions WHERE id=?", (node_id,)
            ).fetchone()
            if row is not None:
                defender_power = str(row["controlled_by"])
    return attacker_power, defender_power


def _power_loses_ratio(result: dict) -> float:
    """估算战败方的兵力损失比例。基于 army_breakdown。"""
    breakdown = _decode(result.get("army_breakdown"), [])
    if not isinstance(breakdown, list) or not breakdown:
        return 0.0
    total_before = sum(int(e.get("manpower_before") or 0) for e in breakdown if isinstance(e, dict))
    total_after = sum(int(e.get("manpower_after") or 0) for e in breakdown if isinstance(e, dict))
    if total_before <= 0:
        return 0.0
    return max(0.0, min(1.0, (total_before - total_after) / total_before))


def _battle_is_significant(battle: dict, result: dict) -> bool:
    """判断一场野战是否达到重大事件阈值。

    条件（满足任一即算重大）：
    - 纸面劣势方获胜（final_probability < 40 但 winner 是该方）
    - 总损失比 ≥ 15%
    - 涉及刘备势力
    """
    # 纸面逆转：final_probability 表示攻方胜率
    final_prob = int(result.get("final_probability") or 50)
    winner_side = str(result.get("winner") or "")
    if winner_side == "attacker" and final_prob < 40:
        return True
    if winner_side == "defender" and final_prob > 60:
        return True

    # 高损失
    if _power_loses_ratio(result) >= 0.15:
        return True

    # 多军参战（任一方 ≥2 军）
    attacker_ids = _decode(battle.get("attacker_ids"), [])
    defender_ids = _decode(battle.get("defender_ids"), [])
    if not isinstance(attacker_ids, list):
        attacker_ids = []
    if not isinstance(defender_ids, list):
        defender_ids = []
    if len(attacker_ids) >= 2 or len(defender_ids) >= 2:
        return True

    # 涉及刘备
    if str(battle.get("attacker_power") or "") == "liu_bei" or str(battle.get("defender_power") or "") == "liu_bei":
        return True
    return False


def collect_significant_battle_outcomes(db, state) -> list[dict]:
    """收集本回合重大野战结果。"""
    turn = get_turn(state)
    rows = db.conn.execute(
        "SELECT * FROM battles WHERE turn=? AND status='resolved'",
        (turn,),
    ).fetchall()
    results: list[dict] = []
    for row in rows:
        battle = dict(row)
        result = _decode(battle.get("result"), {})
        if not isinstance(result, dict):
            result = {}
        attacker_power, defender_power = _battle_powers(db, battle)
        if not attacker_power or not defender_power:
            continue
        # 附加势力信息供 _battle_is_significant 使用
        battle["attacker_power"] = attacker_power
        battle["defender_power"] = defender_power
        if not _battle_is_significant(battle, result):
            continue
        winner_side = str(result.get("winner") or "")
        if winner_side == "attacker":
            winner_power = attacker_power
            loser_power = defender_power
        else:
            winner_power = defender_power
            loser_power = attacker_power
        breakdown = _decode(result.get("army_breakdown"), [])
        if not isinstance(breakdown, list):
            breakdown = []
        initial = sum(int(e.get("manpower_before") or 0) for e in breakdown if isinstance(e, dict))
        remaining = sum(int(e.get("manpower_after") or 0) for e in breakdown if isinstance(e, dict))
        results.append({
            "source_kind": "battle",
            "source_ref": f"battle:{int(row['id'])}",
            "battle_id": int(row["id"]),
            "attacker_power": attacker_power,
            "defender_power": defender_power,
            "winner": winner_side,
            "winner_power": winner_power,
            "loser_power": loser_power,
            "initial_strength": initial,
            "remaining_strength": remaining,
            "evidence": {
                "source_kind": "battle",
                "battle_id": int(row["id"]),
                "initial_strength": initial,
                "remaining_strength": remaining,
                "winner_power": winner_power,
            },
        })
    return results


def collect_significant_siege_outcomes(db, state) -> list[dict]:
    """收集本回合重大围城结果。"""
    turn = get_turn(state)
    rows = db.conn.execute(
        "SELECT * FROM sieges WHERE last_turn=? AND status IN ('fallen', 'repelled', 'conquered', 'failed', 'withdrawn', 'relief_defeat')",
        (turn,),
    ).fetchall()
    results: list[dict] = []
    for row in rows:
        siege = dict(row)
        attacker_power, defender_power = _siege_powers(db, siege)
        if not attacker_power or not defender_power:
            continue
        details = _decode(siege.get("details"), {})
        if not isinstance(details, dict):
            details = {}
        garrison = int(details.get("garrison_strength") or 0)
        assault = int(details.get("assault_strength") or 0)
        total = garrison + assault
        status = str(row["status"])
        if status in ("fallen", "conquered"):
            winner_power = attacker_power
            loser_power = defender_power
        else:
            winner_power = defender_power
            loser_power = attacker_power
        results.append({
            "source_kind": "siege",
            "source_ref": f"siege:{int(row['id'])}",
            "battle_id": int(row["id"]),
            "attacker_power": attacker_power,
            "defender_power": defender_power,
            "winner_power": winner_power,
            "loser_power": loser_power,
            "initial_strength": total,
            "remaining_strength": garrison if status in ("repelled", "failed", "withdrawn", "relief_defeat") else 0,
            "evidence": {
                "source_kind": "siege",
                "siege_id": int(row["id"]),
                "garrison_strength": garrison,
                "assault_strength": assault,
                "winner_power": winner_power,
                "status": status,
            },
        })
    return results


def collect_treaty_breach_outcomes(db, state) -> list[dict]:
    """收集本回合重大违约事件。"""
    turn = get_turn(state)
    rows = db.conn.execute(
        "SELECT * FROM diplomacy_treaties WHERE end_turn=? AND status IN ('breached', 'broken')",
        (turn,),
    ).fetchall()
    results: list[dict] = []
    for row in rows:
        treaty = dict(row)
        actor_power = str(treaty.get("proposer") or "")
        target_power = str(treaty.get("target") or "")
        if not actor_power or not target_power:
            continue
        results.append({
            "source_kind": "treaty_breach",
            "source_ref": f"treaty:{int(row['id'])}",
            "actor_power": actor_power,
            "target_power": target_power,
            "treaty_type": str(treaty.get("treaty_type") or ""),
            "evidence": {
                "source_kind": "treaty_breach",
                "treaty_id": int(row["id"]),
                "treaty_type": str(treaty.get("treaty_type") or ""),
                "actor_power": actor_power,
                "target_power": target_power,
            },
        })
    return results


# ---------------------------------------------------------------------------
# 地缘反应生成（编排）
# ---------------------------------------------------------------------------


def generate_geopolitical_reactions(
    db, state, source_events: list[dict],
) -> list[dict]:
    """为重大外部事实生成第三方地缘反应。幂等。"""
    turn = get_turn(state)
    reactions: list[dict] = []
    global_count = 0
    reacted_powers_this_turn: set[str] = set()

    for evt in source_events:
        source_kind = str(evt.get("source_kind") or "")
        source_ref = str(evt.get("source_ref") or "")
        if not source_kind or not source_ref:
            continue

        direct_powers: set[str] = set()
        if source_kind == "treaty_breach":
            direct_powers = {
                str(evt.get("actor_power") or ""),
                str(evt.get("target_power") or ""),
            }
        else:
            direct_powers = {
                str(evt.get("attacker_power") or ""),
                str(evt.get("defender_power") or ""),
            }
        direct_powers.discard("")

        third_parties = _eligible_third_parties(db, direct_powers)
        per_source_count = 0

        for actor_power in third_parties:
            if global_count >= 4:
                break
            if per_source_count >= 2:
                break
            if actor_power in reacted_powers_this_turn:
                continue

            existing = db.conn.execute(
                "SELECT id FROM geopolitical_reactions "
                "WHERE turn=? AND source_ref=? AND actor_power_id=?",
                (turn, source_ref, actor_power),
            ).fetchone()
            if existing is not None:
                per_source_count += 1
                reacted_powers_this_turn.add(actor_power)
                continue

            reaction_type, target_power, severity = _determine_reaction_type(
                db, state, actor_power, evt, direct_powers,
            )
            if reaction_type is None:
                continue

            source_type, visibility, reliability = _reaction_source_and_visibility(
                db, actor_power, direct_powers,
            )
            if source_type is None:
                continue

            evidence = {
                "source_kind": source_kind,
                "source_ref": source_ref,
                "actor_power": actor_power,
                "target_power": target_power,
                "direct_powers": sorted(direct_powers),
                "observation_source": source_type,
                "reliability": reliability,
                "event_evidence": evt.get("evidence", {}),
            }

            slot_key = f"selection_slot_{per_source_count + 1}"

            soft_effects = _compute_soft_effects(reaction_type, severity)
            action_hints = _compute_action_hints(reaction_type, evt, actor_power, target_power)

            cursor = db.conn.execute(
                """INSERT INTO geopolitical_reactions
                (turn, source_kind, source_ref, actor_power_id, target_power_id,
                 reaction_type, severity, visibility, evidence_json, draw_refs_json,
                 soft_effects_json, action_hint_json, status, effects_applied_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'resolved', ?)""",
                (
                    turn, source_kind, source_ref, actor_power, target_power,
                    reaction_type, int(severity), visibility,
                    to_json(evidence),
                    to_json([slot_key]),
                    to_json(soft_effects),
                    to_json(action_hints),
                    f"turn_{turn}",
                ),
            )
            reaction_record = {
                "id": int(cursor.lastrowid),
                "turn": turn,
                "source_kind": source_kind,
                "source_ref": source_ref,
                "actor_power_id": actor_power,
                "target_power_id": target_power,
                "reaction_type": reaction_type,
                "severity": int(severity),
                "visibility": visibility,
                "evidence": evidence,
                "soft_effects": soft_effects,
                "action_hints": action_hints,
                "observation_source": source_type,
                "reliability": reliability,
            }
            reactions.append(reaction_record)
            per_source_count += 1
            global_count += 1
            reacted_powers_this_turn.add(actor_power)

            # 尝试创建延迟反应
            _maybe_create_delayed_reaction(
                db, state, actor_power, evt,
                reaction_type, target_power, severity,
            )

    db.conn.commit()
    return reactions


# ---------------------------------------------------------------------------
# 延迟反应结算（编排层调用规则层）
# ---------------------------------------------------------------------------


def resolve_delayed_reactions(db, state) -> list[dict]:
    """每回合结算时调用：执行到期的延迟反应。"""
    turn = get_turn(state)
    pending = db.conn.execute(
        "SELECT * FROM delayed_geopolitical_reactions WHERE fire_turn=? AND status='pending'",
        (turn,),
    ).fetchall()

    fired: list[dict] = []
    for row in pending:
        row_id = int(row["id"])
        actor_power = str(row["actor_power_id"])
        source_ref = str(row["source_ref"])
        reaction_type = str(row["reaction_type"])
        target_power = str(row["target_power_id"])
        severity = int(row["severity"])
        condition = _decode(row["condition_json"], {})

        if not _check_delayed_condition(db, actor_power, target_power, condition):
            db.conn.execute(
                "UPDATE delayed_geopolitical_reactions SET status='cancelled' WHERE id=?",
                (row_id,),
            )
            continue

        reaction = {
            "turn": turn,
            "source_kind": "delayed",
            "source_ref": source_ref,
            "actor_power_id": actor_power,
            "target_power_id": target_power,
            "reaction_type": reaction_type,
            "severity": severity,
            "visibility": "assessment",
            "evidence": {
                "source_kind": "delayed",
                "trigger_turn": int(row["trigger_turn"]),
                "fire_turn": turn,
            },
            "draw_refs": [],
            "soft_effects": _compute_soft_effects(reaction_type, severity),
            "action_hints": _compute_action_hints(reaction_type, {}, actor_power, target_power),
        }

        existing = db.conn.execute(
            "SELECT id FROM geopolitical_reactions "
            "WHERE turn=? AND source_ref=? AND actor_power_id=?",
            (turn, source_ref, actor_power),
        ).fetchone()
        if existing is None:
            db.conn.execute(
                """INSERT INTO geopolitical_reactions
                (turn, source_kind, source_ref, actor_power_id, target_power_id,
                 reaction_type, severity, visibility, evidence_json, draw_refs_json,
                 soft_effects_json, action_hint_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'resolved_local')""",
                (
                    turn, "delayed", source_ref, actor_power, target_power,
                    reaction_type, severity, "assessment",
                    to_json(reaction["evidence"]),
                    to_json(reaction["draw_refs"]),
                    to_json(reaction["soft_effects"]),
                    to_json(reaction["action_hints"]),
                ),
            )
            fired.append(reaction)

        db.conn.execute(
            "UPDATE delayed_geopolitical_reactions SET status='fired' WHERE id=?",
            (row_id,),
        )

    return fired
