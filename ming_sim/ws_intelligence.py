"""情报网络（intelligence network）模块。

从 world_simulation.py 中提取。负责：
- 外部情报记录与验证
- 观察路径判定（接壤 / 使者 / 商旅网络）
- 回合情报报告生成
- 事件情报报告生成
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable

from ming_sim.world_random import draw_int, draw_weighted
from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list, status_terminal as _status_terminal
from ming_sim.ws_utils import get_turn, to_json
from ming_sim.ws_common import seed_for as _seed_for, get_or_create_relation as _get_or_create_relation


# ---------------------------------------------------------------------------
# 外部情报记录
# ---------------------------------------------------------------------------

def record_external_intelligence(
    db, state: object, *, power_id: str, visibility: str, title: str, summary: str,
    evidence_refs: Iterable[str],
    source_type: str = "system",
    source_ref: str = "",
    reliability: int = 50,
    verification_status: str = "unverified",
    valid_until_turn: int = 0,
    true_subject_ref: str = "",
    parent_report_id: int = 0,
) -> Dict[str, Any]:
    """记录一条外部情报。保留旧调用兼容默认值。

    若未指定 valid_until_turn，默认为当前回合 + 2。
    visibility 只接受 rumor/assessment/confirmed，否则降级为 rumor。
    """
    visibility = visibility if visibility in {"rumor", "assessment", "confirmed"} else "rumor"
    usable = (visibility == "confirmed" and verification_status == "confirmed")
    turn = get_turn(state)
    if valid_until_turn <= 0:
        valid_until_turn = turn + 2
    cursor = db.conn.execute(
        """INSERT INTO external_intelligence_reports
        (turn, power_id, visibility, title, summary, evidence_json, usable_as_fact,
         source_type, source_ref, reliability, verification_status,
         valid_until_turn, true_subject_ref, parent_report_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            turn, power_id, visibility, title, summary,
            to_json(list(evidence_refs)), int(usable),
            source_type, source_ref, int(reliability), verification_status,
            int(valid_until_turn), true_subject_ref, int(parent_report_id),
        ),
    )
    db.conn.commit()
    return {
        "id": int(cursor.lastrowid), "power_id": power_id, "visibility": visibility,
        "title": title, "summary": summary, "usable_as_fact": usable,
        "source_type": source_type, "reliability": int(reliability),
        "verification_status": verification_status, "valid_until_turn": int(valid_until_turn),
        "true_subject_ref": true_subject_ref,
    }


def validate_simulation_evidence(proposal: Dict[str, Any], allowed_refs: Iterable[str]) -> None:
    refs = proposal.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        raise ValueError("AI 提案必须给出 evidence_refs。")
    allowed = set(allowed_refs)
    if not set(str(item) for item in refs).issubset(allowed):
        raise ValueError("AI 提案引用了裁决包外的证据。")


# ---------------------------------------------------------------------------
# 观察路径：内部辅助函数（L 组）
# ---------------------------------------------------------------------------

def _is_bordering_liu_bei(db, node_id: str) -> bool:
    """检查 node_id 是否与刘备控制区接壤。通过 strategic_nodes 桥接城池路线与行政控制。

    node_id 可以是城池节点 ID (city:*) 或郡 ID (bare)。
    """
    if not node_id:
        return False
    node_id = str(node_id)
    if node_id.startswith("city:"):
        # 城池节点：直接查路线邻接
        row = db.conn.execute(
            """SELECT 1 FROM strategic_routes sr
               JOIN strategic_nodes sn ON (sr.source = sn.id OR sr.target = sn.id)
               JOIN administrative_cities ac ON sn.id = ac.id
               WHERE (sr.source = ? OR sr.target = ?)
                 AND ac.controlled_by = 'liu_bei'
                 AND sn.id != ?
               LIMIT 1""",
            (node_id, node_id, node_id),
        ).fetchone()
        return row is not None
    # 郡 ID：查该郡下所有城池是否有与刘备控制区相邻的
    row = db.conn.execute(
        """SELECT 1 FROM administrative_cities ac
           JOIN strategic_routes sr ON (sr.source = ac.id OR sr.target = ac.id)
           JOIN administrative_cities ac2 ON (sr.source = ac2.id OR sr.target = ac2.id)
           WHERE ac.commandery_id = ?
             AND ac2.controlled_by = 'liu_bei'
             AND ac.id != ac2.id
           LIMIT 1""",
        (node_id,),
    ).fetchone()
    return row is not None


def _is_power_bordering_liu_bei(db, power_id: str) -> bool:
    """检查 power_id 的任意控制区是否与刘备控制区接壤。

    用于内部动态等没有具体节点的场景，基于势力控制区整体判断。
    通过 strategic_nodes 桥接城池路线与行政控制。
    """
    if not power_id:
        return False
    row = db.conn.execute(
        """SELECT 1 FROM strategic_routes sr
           JOIN strategic_nodes sn1 ON sr.source = sn1.id
           JOIN strategic_nodes sn2 ON sr.target = sn2.id
           JOIN administrative_cities ac1 ON sn1.id = ac1.id
           JOIN administrative_cities ac2 ON sn2.id = ac2.id
           WHERE ac1.controlled_by = 'liu_bei'
             AND ac2.controlled_by = ?
             AND sn1.id != sn2.id
           LIMIT 1""",
        (power_id,),
    ).fetchone()
    return row is not None


def _has_active_envoy(db, power_id: str) -> bool:
    """检查刘备是否对该势力有活跃使者。"""
    row = db.conn.execute(
        "SELECT 1 FROM envoy_missions WHERE target_power=? AND status NOT IN ('completed', 'failed') LIMIT 1",
        (power_id,),
    ).fetchone()
    return row is not None


def _can_merchant_network(db, power_id: str) -> bool:
    """检查商旅网络条件：非战争关系且至少一条相邻路线道路 > -20。

    委托至统一 API can_merchant_network_unified。
    """
    return can_merchant_network_unified(db, "liu_bei", power_id)


def _determine_source_and_visibility(db, power_id: str, action: dict) -> tuple[str, str, int]:
    """确定情报来源类型、可见性和可信度。

    返回 (source_type, visibility, reliability)。
    """
    action_type = str(action.get("action_type") or "")
    target_power = str(action.get("target_power") or "")
    army_id = str(action.get("army_id") or "")

    # direct_contact: 对刘备 attack/siege/declare_war
    if target_power == "liu_bei" or action_type in {"attack", "siege", "declare_war"}:
        return "direct_contact", "confirmed", 100

    # border_observer: 行动节点与刘备控制区接壤
    node_id = str(action.get("target_node") or "")
    if not node_id and army_id:
        army_row = db.conn.execute(
            "SELECT station_node FROM armies WHERE id=?", (army_id,)
        ).fetchone()
        if army_row:
            node_id = str(army_row["station_node"] or "")
    if _is_bordering_liu_bei(db, node_id):
        return "border_observer", "assessment", 75

    # envoy: 刘备对该势力有活跃使者
    if _has_active_envoy(db, power_id):
        return "envoy", "assessment", 85

    # merchant_network: 非战争关系 + 相邻路线道路 > -20
    if _can_merchant_network(db, power_id):
        return "merchant_network", "rumor", 45

    # fallback
    return "system", "rumor", 30


# ---------------------------------------------------------------------------
# 统一观察路径 API（J/N 组合并）
# ---------------------------------------------------------------------------

def is_bordering(db, power_a: str, power_b: str) -> bool:
    """检查 power_a 与 power_b 的控制区是否接壤。

    通过 strategic_nodes 桥接城池路线与行政控制。
    """
    if not power_a or not power_b or power_a == power_b:
        return False
    row = db.conn.execute(
        """SELECT 1 FROM strategic_routes sr
           JOIN strategic_nodes sn1 ON sr.source = sn1.id
           JOIN strategic_nodes sn2 ON sr.target = sn2.id
           JOIN administrative_cities ac1 ON sn1.id = ac1.id
           JOIN administrative_cities ac2 ON sn2.id = ac2.id
           WHERE ac1.controlled_by = ?
             AND ac2.controlled_by = ?
             AND sn1.id != sn2.id
           LIMIT 1""",
        (power_a, power_b),
    ).fetchone()
    return row is not None


def has_active_envoy_unified(db, observer_power: str, target_power: str) -> bool:
    """检查 observer_power 是否对 target_power 有活跃使者。

    统一了 _has_active_envoy（J 组）和 _has_active_envoy_for（N 组）。
    """
    row = db.conn.execute(
        "SELECT 1 FROM envoy_missions WHERE target_power=? AND status NOT IN ('completed','failed') LIMIT 1",
        (target_power,),
    ).fetchone()
    return row is not None


def can_merchant_network_unified(db, power_a: str, power_b: str) -> bool:
    """检查 power_a 与 power_b 之间是否有商旅路线（非战争 + 道路 > -20）。

    通过 strategic_nodes + administrative_cities 桥接城池路线与行政控制。
    """
    if not power_a or not power_b or power_a == power_b:
        return False
    first, second = db._relation_pair(power_a, power_b)
    row = db.conn.execute(
        """SELECT 1
           FROM strategic_routes sr
           JOIN strategic_nodes sn1 ON sr.source = sn1.id
           JOIN strategic_nodes sn2 ON sr.target = sn2.id
           JOIN administrative_cities ac1 ON sn1.id = ac1.id
           JOIN administrative_cities ac2 ON sn2.id = ac2.id
           LEFT JOIN diplomatic_relations dr ON
             dr.power_a = ? AND dr.power_b = ? AND dr.status = 'war'
           LEFT JOIN regional_world_states rws1 ON
             rws1.region_id = ac1.commandery_id
             AND rws1.turn = (SELECT MAX(turn) FROM regional_world_states WHERE region_id = ac1.commandery_id)
           LEFT JOIN regional_world_states rws2 ON
             rws2.region_id = ac2.commandery_id
             AND rws2.turn = (SELECT MAX(turn) FROM regional_world_states WHERE region_id = ac2.commandery_id)
           WHERE ac1.controlled_by = ?
             AND ac2.controlled_by = ?
             AND sn1.id != sn2.id
             AND dr.power_a IS NULL
             AND (COALESCE(rws1.road_condition, 0) > -20 OR COALESCE(rws2.road_condition, 0) > -20)
           LIMIT 1""",
        (first, second, power_a, power_b),
    ).fetchone()
    return row is not None


def determine_observation_source(
    db, observer_power: str, target_powers: set[str],
) -> tuple[str | None, str, int]:
    """确定观察者对目标势力的最佳观察来源。

    统一了 _determine_source_and_visibility（J 组）和 _reaction_source_and_visibility（N 组）。

    返回 (source_type, visibility, reliability)。
    source_type=None 表示不可观测。
    """
    for tp in target_powers:
        if tp == observer_power:
            continue
        if is_bordering(db, observer_power, tp):
            return "border_observer", "assessment", 75
    for tp in target_powers:
        if tp == observer_power:
            continue
        if has_active_envoy_unified(db, observer_power, tp):
            return "envoy", "assessment", 85
    for tp in target_powers:
        if tp == observer_power:
            continue
        if can_merchant_network_unified(db, observer_power, tp):
            return "merchant_network", "rumor", 45
    return None, "", 0


# ---------------------------------------------------------------------------
# 回合情报报告
# ---------------------------------------------------------------------------

def build_intelligence_reports_for_turn(
    db, state, power_actions: list[dict], internal_dynamics: list[dict],
) -> list[dict]:
    """为当前回合生成情报报告。

    遍历 power_ai_actions 和 power_internal_dynamics，按来源规则生成情报。
    商旅传闻通过 draw_int 决定准确/夸大/误判。
    """
    turn = get_turn(state)
    reports: list[dict] = []

    # 处理 power_ai_actions
    for action in power_actions:
        if action.get("status") == "pending_review":
            continue
        power_id = str(action.get("power_id") or "")
        action_type = str(action.get("action", {}).get("action_type") or "")
        action_id = int(action.get("id") or 0)
        if not power_id or not action_type:
            continue

        source_type, visibility, reliability = _determine_source_and_visibility(
            db, power_id, action.get("action", {})
        )
        true_ref = f"power_ai_actions:{action_id}"
        reasons = action.get("action", {}).get("reasons", [])
        base_title = f"{power_id}：{action_type}"
        base_summary = "；".join(str(r) for r in reasons[:3]) or "外部势力正在调整方略。"

        # 商旅传闻误判机制
        if source_type == "merchant_network":
            interpretation = draw_int(
                db, state=state,
                domain="intelligence_report",
                subject_id=f"report:{true_ref}",
                low=1, high=100,
                draw_kind="interpretation",
            )
            if interpretation <= 50:
                # 准确
                title = base_title
                summary = base_summary
            elif interpretation <= 80:
                # 夸大
                title = f"{power_id}：或有{action_type}之举"
                summary = f"传言集兵于{action.get('action', {}).get('target_node', '边境')}，规模恐将扩大。"
            else:
                # 误判：在同一势力的相邻地区间误指
                target_node = str(action.get("action", {}).get("target_node") or "")
                neighbors = db.conn.execute(
                    "SELECT target FROM strategic_routes WHERE source=? UNION "
                    "SELECT source FROM strategic_routes WHERE target=?",
                    (target_node, target_node),
                ).fetchall()
                if neighbors:
                    import random as _rng
                    # 使用确定性选择（基于 turn + power_id 哈希）
                    seed_val = int(hashlib.sha256(f"{turn}:{power_id}:misdirect".encode()).hexdigest()[:8], 16)
                    _local_rng = _rng.Random(seed_val)
                    fake_node = str(neighbors[_local_rng.randint(0, len(neighbors) - 1)][0])
                    title = f"{power_id}：疑似{action_type}（{fake_node}）"
                    summary = f"商旅传闻：{power_id}或于{fake_node}方向有异动，待核实。"
                else:
                    title = base_title
                    summary = base_summary
        else:
            title = base_title
            summary = base_summary

        report = record_external_intelligence(
            db, state, power_id=power_id, visibility=visibility,
            title=title, summary=summary,
            evidence_refs=[true_ref, f"world_context:{turn}"],
            source_type=source_type,
            source_ref=true_ref,
            reliability=reliability,
            verification_status="unverified" if visibility != "confirmed" else "confirmed",
            valid_until_turn=turn + 2,
            true_subject_ref=true_ref,
        )
        reports.append(report)

    # 处理 internal_dynamics
    for dyn in internal_dynamics:
        power_id = str(dyn.get("power_id") or "")
        dyn_type = str(dyn.get("dynamic_type") or "")
        dyn_id = int(dyn.get("id") or 0)
        if not power_id or not dyn_type:
            continue

        true_ref = f"power_internal_dynamics:{dyn_id}"

        # 内部动态的来源判断
        if _is_power_bordering_liu_bei(db, power_id):  # 内部动态基于势力控制区判断接壤
            source_type, visibility, reliability = "border_observer", "assessment", 60
        elif _has_active_envoy(db, power_id):
            source_type, visibility, reliability = "envoy", "assessment", 70
        elif _can_merchant_network(db, power_id):
            source_type, visibility, reliability = "merchant_network", "rumor", 40
        else:
            source_type, visibility, reliability = "system", "rumor", 30

        title = str(dyn.get("title") or f"{power_id}：{dyn_type}")
        summary = str(dyn.get("summary") or "内部状态变化。")

        report = record_external_intelligence(
            db, state, power_id=power_id, visibility=visibility,
            title=title, summary=summary,
            evidence_refs=[true_ref, f"world_context:{turn}"],
            source_type=source_type,
            source_ref=true_ref,
            reliability=reliability,
            verification_status="unverified",
            valid_until_turn=turn + 2,
            true_subject_ref=true_ref,
        )
        reports.append(report)

    return reports


# ---------------------------------------------------------------------------
# 情报核验
# ---------------------------------------------------------------------------

def resolve_intelligence_verification(db, state) -> list[dict]:
    """处理情报核验与过期。

    每月结算时：
    - 过期报告标记 expired
    - 后续真实行动确认或辟谣旧报告
    - 更新 usable_as_fact
    """
    turn = get_turn(state)
    changes: list[dict] = []

    # 1. 过期处理
    expired = db.conn.execute(
        "SELECT id FROM external_intelligence_reports "
        "WHERE verification_status='unverified' AND valid_until_turn > 0 AND valid_until_turn < ?",
        (turn,),
    ).fetchall()
    for row in expired:
        db.conn.execute(
            "UPDATE external_intelligence_reports "
            "SET verification_status='expired', resolution_turn=?, resolution_summary=?, "
            "usable_as_fact=0 WHERE id=?",
            (turn, f"超过有效期（{turn}回合）未获证实", int(row["id"])),
        )
        changes.append({"id": int(row["id"]), "change": "expired"})

    # 2. 确认/辟谣：查找本回合新的 power_ai_actions，与旧 unverified 报告比对
    new_actions = db.conn.execute(
        "SELECT id, power_id, action_type, action_json FROM power_ai_actions "
        "WHERE turn=? AND status='executed'",
        (turn,),
    ).fetchall()
    for act in new_actions:
        true_ref = f"power_ai_actions:{int(act['id'])}"
        act_type = str(act["action_type"])
        act_json = json.loads(str(act["action_json"] or "{}"))
        act_target = str(act_json.get("target_power") or act_json.get("target_node") or "")

        # 查找引用同一真源的旧 unverified 报告
        old_reports = db.conn.execute(
            "SELECT id, true_subject_ref, title, power_id FROM external_intelligence_reports "
            "WHERE verification_status='unverified' AND true_subject_ref != '' AND valid_until_turn >= ?",
            (turn,),
        ).fetchall()
        for old in old_reports:
            old_ref = str(old["true_subject_ref"])
            # 如果旧报告引用的真源与本行动相同 → 确认
            if old_ref == true_ref:
                db.conn.execute(
                    "UPDATE external_intelligence_reports "
                    "SET verification_status='confirmed', resolution_turn=?, resolution_summary=?, "
                    "usable_as_fact=1 WHERE id=?",
                    (turn, f"已由 {true_ref} 证实", int(old["id"])),
                )
                changes.append({"id": int(old["id"]), "change": "confirmed"})
            # 如果旧报告与当前行动势力相同但 action_type 或 target 不同 → 辟谣
            elif str(old["power_id"]) == str(act["power_id"]):
                old_title = str(old["title"])
                # 如果新行动类型不在旧标题中，且（有目标或行动类型确实不同）→ 辟谣
                if act_type not in old_title:
                    if not act_target or act_target not in old_title:
                        db.conn.execute(
                            "UPDATE external_intelligence_reports "
                            "SET verification_status='refuted', resolution_turn=?, resolution_summary=?, "
                            "usable_as_fact=0 WHERE id=?",
                            (turn, f"实际情况与传闻不符：{act_type}", int(old["id"])),
                        )
                        changes.append({"id": int(old["id"]), "change": "refuted"})

    db.conn.commit()
    return changes


# ---------------------------------------------------------------------------
# 事件情报报告
# ---------------------------------------------------------------------------

def build_incident_intelligence_reports(
    db, state, incidents: list[dict],
) -> list[dict]:
    """为区域事件生成外部情报报告。幂等。

    规则：
    - 刘备控制区的事件不生成外部情报。
    - 重大事件（dramatic）：接壤势力 → border_observer (65)。
    - 普通事件（ordinary）：有活跃使者 → envoy (70)。
    - 商旅网络条件满足 → rumor (40)。
    - 同一 (incident_id, observing_power) 最多一条报告（通过 source_ref 去重）。
    """
    turn = get_turn(state)
    reports: list[dict] = []

    for inc in incidents:
        inc_id = int(inc.get("id") or 0)
        region_id = str(inc.get("region_id") or "")
        tier = str(inc.get("tier") or "ordinary")
        title = str(inc.get("title") or "")
        summary = str(inc.get("summary") or "")

        if not region_id or not inc_id:
            continue

        # 找到事件发生地区的控制势力
        ctrl_row = db.conn.execute(
            "SELECT controlled_by FROM regions WHERE id=?", (region_id,),
        ).fetchone()
        if ctrl_row is None:
            continue
        controller = str(ctrl_row["controlled_by"])

        # 刘备控制区的事件不生成外部情报
        if controller == "liu_bei":
            continue

        # 该势力已灭亡/停用则跳过
        power_row = db.conn.execute(
            "SELECT status FROM powers WHERE id=?", (controller,),
        ).fetchone()
        if power_row is None or _status_terminal(str(power_row["status"])):
            continue

        # 确定刘备如何观测到此事件
        source_type, visibility, reliability = _incident_source_rules(
            db, region_id, controller, tier,
        )
        if source_type is None:
            continue

        # 幂等守卫：source_ref 唯一标识 (incident, power)
        source_ref_val = f"incident_intel:{inc_id}:{controller}"
        existing = db.conn.execute(
            "SELECT id FROM external_intelligence_reports WHERE source_ref=?",
            (source_ref_val,),
        ).fetchone()
        if existing is not None:
            continue

        true_ref = f"regional_incidents:{inc_id}"
        intel_title = f"{controller}辖内：{title}" if title else f"{controller}辖内异动"
        intel_summary = summary or "区域事件引发外部关注。"

        report = record_external_intelligence(
            db, state, power_id=controller, visibility=visibility,
            title=intel_title, summary=intel_summary,
            evidence_refs=[true_ref, f"world_context:{turn}"],
            source_type=source_type,
            source_ref=source_ref_val,
            reliability=reliability,
            verification_status="unverified" if visibility != "confirmed" else "confirmed",
            valid_until_turn=turn + 3,
            true_subject_ref=true_ref,
        )
        reports.append(report)

    return reports


def _incident_source_rules(
    db, region_id: str, controller: str, tier: str,
) -> tuple[str | None, str, int]:
    """根据事件类型和控制势力确定情报来源。

    返回 (source_type, visibility, reliability)。source_type=None 表示不生成。
    """
    # border_observer：事件地区与刘备控制区接壤
    if _is_bordering_liu_bei(db, region_id):
        return "border_observer", "assessment", 65

    # envoy：刘备对该势力有活跃使者
    if _has_active_envoy(db, controller):
        # 重大事件：envoy 级别更高
        if tier == "dramatic":
            return "envoy", "assessment", 75
        return "envoy", "assessment", 70

    # merchant_network：非战争 + 相邻路线道路 > -20
    # 普通事件必须有使者才能被观测到；重大事件可通过商旅传闻
    if tier == "dramatic" and _can_merchant_network(db, controller):
        return "merchant_network", "rumor", 40

    # 无观测途径
    return None, "rumor", 0
