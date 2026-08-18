"""地缘反应效果：软效果计算、数据库写入、情报报告。

从 ws_geopolitics.py 提取。负责：
- 计算反应软效果（public_relation/trust/military_coordination delta）
- 计算行动候选评分影响
- 应用反应效果到 diplomatic_relations
- 生成情报报告
- 选择玩家可见世界动态
- 观察路径判定辅助
"""
from __future__ import annotations

import json
from typing import Any, Dict

from ming_sim.ws_utils import decode_json as _decode, to_json
from ming_sim.ws_utils import get_turn
from ming_sim.ws_common import get_relation as _get_relation
from ming_sim.ws_intelligence import (
    is_bordering, has_active_envoy_unified, can_merchant_network_unified,
    record_external_intelligence,
)


def _is_power_observable(db, actor_power: str, event_powers: set[str]) -> bool:
    """判断 actor_power 是否对事件中任一势力有观察路径。"""
    for ep in event_powers:
        if ep == actor_power:
            continue
        if is_bordering(db, actor_power, ep):
            return True
        if has_active_envoy_unified(db, actor_power, ep):
            return True
        if can_merchant_network_unified(db, actor_power, ep):
            return True
    return False


def _reaction_source_and_visibility(
    db, actor_power: str, event_powers: set[str],
) -> tuple[str | None, str, int]:
    """确定第三方势力对事件的观察来源。

    返回 (source_type, visibility, reliability)。source_type=None 表示不可观测。
    """
    for ep in event_powers:
        if ep == actor_power:
            continue
        if is_bordering(db, actor_power, ep):
            return "border_observer", "assessment", 75
    for ep in event_powers:
        if ep == actor_power:
            continue
        if has_active_envoy_unified(db, actor_power, ep):
            return "envoy", "assessment", 85
    for ep in event_powers:
        if ep == actor_power:
            continue
        if can_merchant_network_unified(db, actor_power, ep):
            return "merchant_network", "rumor", 45
    return None, "", 0


# 向后兼容别名 — 消除原 3 层委托链
_is_bordering_liu_bei_via = is_bordering
_has_active_envoy_for = has_active_envoy_unified
_can_merchant_network_between = can_merchant_network_unified


def _compute_soft_effects(reaction_type: str, severity: int) -> dict:
    """计算反应的软效果。

    返回 dict，字段包括：
    - public_relation_delta: [-4, +4]
    - trust_delta: [-3, +3]
    - military_coordination_delta: [-10, +10]
    """
    effects: dict = {}
    if reaction_type == "opportunism":
        effects["trust_delta"] = -min(3, max(2, severity))
    elif reaction_type == "balancing":
        effects["public_relation_delta"] = min(4, max(2, severity))
    elif reaction_type == "caution":
        effects["military_coordination_delta"] = -min(10, max(5, severity * 5))
    elif reaction_type == "condemnation":
        effects["trust_delta"] = -min(3, max(2, severity))
        effects["public_relation_delta"] = -min(4, max(2, severity))
    elif reaction_type == "reassurance":
        effects["public_relation_delta"] = min(4, max(2, severity))
    return effects


def _compute_action_hints(
    reaction_type: str, evt: dict, actor_power: str, target_power: str,
) -> dict:
    """计算反应的行动候选评分影响。

    返回 dict，字段 action_score_deltas 为 list[dict]，每项：
    - action_type: str
    - target_power: str
    - delta: [-12, +12]
    """
    hints: dict = {"action_score_deltas": []}
    deltas = hints["action_score_deltas"]

    if reaction_type == "opportunism":
        loser = str(evt.get("loser_power") or target_power)
        deltas.append({
            "action_type": "attack", "target_power": loser, "delta": 10,
        })
        deltas.append({
            "action_type": "siege", "target_power": loser, "delta": 8,
        })
    elif reaction_type == "balancing":
        winner = str(evt.get("winner_power") or target_power)
        deltas.append({
            "action_type": "fortify", "target_power": winner, "delta": 8,
        })
        deltas.append({
            "action_type": "resupply", "target_power": winner, "delta": 6,
        })
        deltas.append({
            "action_type": "propose_alliance", "target_power": winner, "delta": 5,
        })
    elif reaction_type == "caution":
        for tp in (str(evt.get("attacker_power") or ""), str(evt.get("defender_power") or "")):
            if tp and tp != actor_power:
                deltas.append({
                    "action_type": "fortify", "target_power": tp, "delta": 6,
                })
    elif reaction_type == "condemnation":
        breacher = str(evt.get("actor_power") or target_power)
        deltas.append({
            "action_type": "seek_peace", "target_power": breacher, "delta": -8,
        })
        deltas.append({
            "action_type": "propose_alliance", "target_power": breacher, "delta": -10,
        })
    elif reaction_type == "reassurance":
        victim = str(evt.get("target_power") or target_power)
        deltas.append({
            "action_type": "propose_alliance", "target_power": victim, "delta": 8,
        })
        deltas.append({
            "action_type": "seek_peace", "target_power": victim, "delta": 5,
        })
    return hints


def apply_geopolitical_reaction_effects(db, state, reaction: dict) -> dict:
    """一次性应用地缘反应的软效果。幂等。

    修改 diplomatic_relations 的 public_relation / trust / military_coordination。
    """
    turn = get_turn(state)
    reaction_id = int(reaction.get("id") or 0)
    if reaction_id <= 0:
        return {}

    # 幂等守卫
    existing = db.conn.execute(
        "SELECT effects_applied_at FROM geopolitical_reactions WHERE id=?",
        (reaction_id,),
    ).fetchone()
    if existing is None:
        return {}
    if existing["effects_applied_at"] is not None and str(existing["effects_applied_at"]) != "":
        return {}

    actor = str(reaction.get("actor_power_id") or "")
    target = str(reaction.get("target_power_id") or "")
    soft_effects = reaction.get("soft_effects") or {}
    if isinstance(soft_effects, str):
        try:
            soft_effects = json.loads(soft_effects)
        except (TypeError, ValueError, json.JSONDecodeError):
            soft_effects = {}

    relation = _get_relation(db, actor, target)
    applied: dict = {}
    if relation is not None:
        first = str(relation["power_a"])
        second = str(relation["power_b"])

        pr_delta = int(soft_effects.get("public_relation_delta") or 0)
        pr_delta = max(-4, min(4, pr_delta))
        if pr_delta != 0:
            old_pr = int(relation["public_relation"] or 0)
            new_pr = max(-100, min(100, old_pr + pr_delta))
            db.conn.execute(
                "UPDATE diplomatic_relations SET public_relation=? WHERE power_a=? AND power_b=?",
                (new_pr, first, second),
            )
            applied["public_relation_delta"] = new_pr - old_pr

        trust_delta = int(soft_effects.get("trust_delta") or 0)
        trust_delta = max(-3, min(3, trust_delta))
        if trust_delta != 0:
            old_trust = int(relation["trust"] or 0)
            new_trust = max(0, min(100, old_trust + trust_delta))
            db.conn.execute(
                "UPDATE diplomatic_relations SET trust=? WHERE power_a=? AND power_b=?",
                (new_trust, first, second),
            )
            applied["trust_delta"] = new_trust - old_trust

        coord_delta = int(soft_effects.get("military_coordination_delta") or 0)
        coord_delta = max(-10, min(10, coord_delta))
        if coord_delta != 0:
            old_coord = int(relation["military_coordination"] or 0)
            new_coord = max(0, min(100, old_coord + coord_delta))
            db.conn.execute(
                "UPDATE diplomatic_relations SET military_coordination=? WHERE power_a=? AND power_b=?",
                (new_coord, first, second),
            )
            applied["military_coordination_delta"] = new_coord - old_coord

    db.conn.execute(
        "UPDATE geopolitical_reactions SET effects_applied_at=? WHERE id=?",
        (f"turn_{turn}", reaction_id),
    )
    db.conn.commit()
    return applied


def build_geopolitical_intelligence_reports(
    db, state, reactions: list[dict],
) -> list[dict]:
    """为地缘反应生成分层情报报告。幂等。"""
    turn = get_turn(state)
    reports: list[dict] = []

    for rxn in reactions:
        actor_power = str(rxn.get("actor_power_id") or "")
        if not actor_power:
            continue
        source_type = str(rxn.get("observation_source") or "")
        reliability = int(rxn.get("reliability") or 0)
        visibility = str(rxn.get("visibility") or "hidden")
        if source_type == "" or reliability <= 0:
            continue

        reaction_id = int(rxn.get("id") or 0)
        source_ref_val = f"geopolitical_intel:{reaction_id}:liu_bei"
        existing = db.conn.execute(
            "SELECT id FROM external_intelligence_reports WHERE source_ref=?",
            (source_ref_val,),
        ).fetchone()
        if existing is not None:
            continue

        reaction_type = str(rxn.get("reaction_type") or "")
        type_label = {
            "opportunism": "伺机而动",
            "balancing": "扶弱抑强",
            "caution": "审慎观望",
            "condemnation": "公开谴责",
            "reassurance": "安抚保证",
        }.get(reaction_type, reaction_type)

        target_power = str(rxn.get("target_power_id") or "")
        source_ref = str(rxn.get("source_ref") or "")
        intel_title = f"{actor_power}对{source_ref}反应：{type_label}"
        intel_summary = f"{actor_power}就{source_ref}作出{type_label}姿态，目标指向{target_power}。"

        evidence_refs = [source_ref, f"geopolitical_reactions:{reaction_id}"]
        true_ref = f"geopolitical_reactions:{reaction_id}"

        report = record_external_intelligence(
            db, state, power_id=actor_power, visibility=visibility,
            title=intel_title, summary=intel_summary,
            evidence_refs=evidence_refs,
            source_type=source_type,
            source_ref=source_ref_val,
            reliability=reliability,
            verification_status="unverified" if visibility != "confirmed" else "confirmed",
            valid_until_turn=turn + 3,
            true_subject_ref=true_ref,
        )
        reports.append(report)

    return reports


def select_player_visible_world_dynamics(db, state) -> list[dict]:
    """为玩家选择 3–5 条可见外部动态。

    排序优先级：直接威胁刘备 > 已确认 > 接壤 > 使者 > 商旅。
    """
    turn = get_turn(state)

    all_reports = db.conn.execute(
        "SELECT * FROM external_intelligence_reports WHERE turn=? ORDER BY id",
        (turn,),
    ).fetchall()
    if not all_reports:
        return []

    scored: list[dict] = []
    for r in all_reports:
        report = dict(r)
        source_type = str(report.get("source_type") or "system")
        visibility = str(report.get("visibility") or "rumor")
        verification_status = str(report.get("verification_status") or "unverified")
        reliability = int(report.get("reliability") or 50)

        if verification_status == "debunked":
            continue

        score = reliability
        if source_type == "direct_contact":
            score += 200
        elif source_type == "border_observer":
            score += 50
        elif source_type == "envoy":
            score += 30

        if visibility == "confirmed":
            score += 100
        elif visibility == "assessment":
            score += 50

        report["score"] = score
        scored.append(report)

    scored.sort(key=lambda x: x["score"], reverse=True)

    # 分类计数
    confirmed_count = 0
    assessment_count = 0
    rumor_count = 0
    per_power: dict[str, int] = {}
    selected: list[dict] = []

    for report in scored:
        if len(selected) >= 5:
            break
        vis = str(report.get("visibility") or "rumor")
        power_id = str(report.get("power_id") or "")

        # 直接威胁不受上限约束
        source_type = str(report.get("source_type") or "")
        if source_type == "direct_contact":
            selected.append(report)
            per_power[power_id] = per_power.get(power_id, 0) + 1
            continue

        # 普通动态计数
        if vis == "confirmed" and confirmed_count >= 2:
            continue
        if vis == "assessment" and assessment_count >= 2:
            continue
        if vis == "rumor" and rumor_count >= 1:
            continue

        # 同势力最多两条
        if per_power.get(power_id, 0) >= 2:
            continue

        selected.append(report)
        per_power[power_id] = per_power.get(power_id, 0) + 1
        if vis == "confirmed":
            confirmed_count += 1
        elif vis == "assessment":
            assessment_count += 1
        else:
            rumor_count += 1

    results: list[dict] = []
    for r in selected:
        results.append({
            "id": r["id"],
            "power_id": str(r["power_id"]),
            "title": str(r["title"]),
            "summary": str(r["summary"]),
            "visibility": str(r["visibility"]),
            "source_type": str(r["source_type"]),
            "reliability": int(r["reliability"]),
            "score": int(r["score"]),
        })

    return results
