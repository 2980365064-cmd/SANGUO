"""地缘反应规则：反应类型决策逻辑。

从 ws_geopolitics.py 提取。负责：
- 第三方势力枚举
- 战果/围城/违约反应类型判定（legacy + v2）
- 延迟反应创建与条件检查
"""
from __future__ import annotations

from typing import Any, Dict

from ming_sim.world_random import draw_int, draw_weighted
from ming_sim.ws_utils import status_terminal as _status_terminal, to_json
from ming_sim.ws_utils import get_turn, get_year, get_period
from ming_sim.ws_common import get_relation as _get_relation


def _eligible_third_parties(db, direct_powers: set[str]) -> list[str]:
    """枚举合格的第三方势力。"""
    rows = db.conn.execute(
        "SELECT id, status FROM powers WHERE id NOT IN ('liu_bei')",
    ).fetchall()
    eligible: list[str] = []
    for row in rows:
        pid = str(row["id"])
        if pid in direct_powers:
            continue
        if _status_terminal(str(row["status"] or "")):
            continue
        eligible.append(pid)
    return eligible


def _determine_reaction_type(
    db, state, actor_power: str, evt: dict, direct_powers: set[str],
) -> tuple[str | None, str, int]:
    """根据规则表确定反应类型。

    返回 (reaction_type, target_power, severity)。reaction_type=None 表示不产生反应。

    通过 kv_store["geopolitical_rng_v1"] 版本标记选择路径：
    - v0（旧存档）：纯确定性规则链
    - v1（新存档）：draw_weighted 加权选择
    """
    source_kind = str(evt.get("source_kind") or "")

    # 检查是否使用新版随机反应
    use_rng = False
    try:
        row = db.conn.execute(
            "SELECT value FROM kv_store WHERE key='geopolitical_rng_v1'"
        ).fetchone()
        use_rng = row is not None and str(row["value"]) == "1"
    except Exception:
        use_rng = False

    if source_kind in ("battle", "siege"):
        if use_rng:
            return _battle_or_siege_reaction_v2(db, state, actor_power, evt, direct_powers)
        return _battle_or_siege_reaction_legacy(db, actor_power, evt, direct_powers)
    if source_kind == "treaty_breach":
        if use_rng:
            return _treaty_breach_reaction_v2(db, state, actor_power, evt, direct_powers)
        return _treaty_breach_reaction_legacy(db, actor_power, evt, direct_powers)
    return None, "", 0


# ---------------------------------------------------------------------------
# 战果/围城反应 — 旧版（纯确定性规则链，向后兼容）
# ---------------------------------------------------------------------------

def _battle_or_siege_reaction_legacy(
    db, actor_power: str, evt: dict, direct_powers: set[str],
) -> tuple[str | None, str, int]:
    """战果类反应判断（旧版）。严重度由关系紧张程度确定性决定。"""
    winner_power = str(evt.get("winner_power") or "")
    loser_power = str(evt.get("loser_power") or "")

    rel_winner = _get_relation(db, actor_power, winner_power)
    rel_loser = _get_relation(db, actor_power, loser_power)

    trust_winner = int(rel_winner["trust"]) if rel_winner else 0
    trust_loser = int(rel_loser["trust"]) if rel_loser else 0
    pr_winner = int(rel_winner["public_relation"]) if rel_winner else 0
    pr_loser = int(rel_loser["public_relation"]) if rel_loser else 0

    # 与败方关系差且胜方邻近 → opportunism
    if pr_loser <= -20 and trust_loser <= 20:
        severity = 3 if (pr_loser <= -40 or trust_loser <= 10) else 2
        return "opportunism", loser_power, severity

    # 与胜方关系差且双方均紧张 → caution
    if pr_winner <= -30 and pr_loser <= -30:
        return "caution", winner_power, 2

    # 邻近盟友或高信任对象受挫 → balancing
    status_winner = str(rel_winner["status"] or "") if rel_winner else ""
    if trust_winner >= 50 or status_winner in ("allied", "friendly"):
        severity = 3 if trust_winner >= 70 else 2
        return "balancing", winner_power, severity

    return None, "", 0


# ---------------------------------------------------------------------------
# 战果/围城反应 — 新版（draw_weighted 加权选择）
# ---------------------------------------------------------------------------

def _battle_or_siege_reaction_v2(
    db, state, actor_power: str, evt: dict, direct_powers: set[str],
) -> tuple[str | None, str, int]:
    """战果类反应判断（新版）。使用 draw_weighted 在候选反应间加权选择。"""
    winner_power = str(evt.get("winner_power") or "")
    loser_power = str(evt.get("loser_power") or "")

    rel_winner = _get_relation(db, actor_power, winner_power)
    rel_loser = _get_relation(db, actor_power, loser_power)

    trust_winner = int(rel_winner["trust"]) if rel_winner else 0
    trust_loser = int(rel_loser["trust"]) if rel_loser else 0
    pr_winner = int(rel_winner["public_relation"]) if rel_winner else 0
    pr_loser = int(rel_loser["public_relation"]) if rel_loser else 0
    status_winner = str(rel_winner["status"] or "") if rel_winner else ""

    # 构建候选反应池
    candidates = []

    # opportunism: 与败方关系差 → 趁火打劫
    if pr_loser <= -20 and trust_loser <= 20:
        base_weight = 60 + abs(pr_loser) + (20 - trust_loser)
        severity = 3 if (pr_loser <= -40 or trust_loser <= 10) else 2
        candidates.append({
            "key": "opportunism",
            "weight": base_weight,
            "target": loser_power,
            "severity": severity,
        })

    # caution: 双方关系都差 → 审慎观望
    if pr_winner <= -30 and pr_loser <= -30:
        base_weight = 40 + abs(pr_winner + pr_loser) // 2
        candidates.append({
            "key": "caution",
            "weight": base_weight,
            "target": winner_power,
            "severity": 2,
        })

    # balancing: 盟友或高信任对象 → 扶弱抑强
    if trust_winner >= 50 or status_winner in ("allied", "friendly"):
        base_weight = 50 + trust_winner
        severity = 3 if trust_winner >= 70 else 2
        candidates.append({
            "key": "balancing",
            "weight": base_weight,
            "target": winner_power,
            "severity": severity,
        })

    if not candidates:
        return None, "", 0

    # draw_weighted 选择
    source_ref = str(evt.get("source_ref") or "")
    chosen = draw_weighted(
        db, state=state,
        domain="geopolitical_reaction",
        subject_id=f"{actor_power}:{source_ref}",
        choices=candidates,
        draw_kind="battle_or_siege",
    )

    if chosen is None:
        return None, "", 0

    return chosen["key"], chosen["target"], chosen["severity"]


# ---------------------------------------------------------------------------
# 违约反应 — 旧版（纯确定性规则链，向后兼容）
# ---------------------------------------------------------------------------

def _treaty_breach_reaction_legacy(
    db, actor_power: str, evt: dict, direct_powers: set[str],
) -> tuple[str | None, str, int]:
    """违约类反应判断（旧版）。严重度由关系确定性决定。"""
    breacher = str(evt.get("actor_power") or "")
    victim = str(evt.get("target_power") or "")

    rel_breacher = _get_relation(db, actor_power, breacher)
    rel_victim = _get_relation(db, actor_power, victim)

    trust_breacher = int(rel_breacher["trust"]) if rel_breacher else 0
    trust_victim = int(rel_victim["trust"]) if rel_victim else 0
    pr_victim = int(rel_victim["public_relation"]) if rel_victim else 0

    # 与违约方有高信任或条约关系 → condemnation
    status_breacher = str(rel_breacher["status"] or "") if rel_breacher else ""
    if trust_breacher >= 50 or status_breacher in ("allied",):
        severity = 3 if trust_breacher >= 70 else 2
        return "condemnation", breacher, severity

    # 与受害方关系较好 → reassurance
    if pr_victim >= 30 or trust_victim >= 40:
        severity = 3 if (pr_victim >= 50 or trust_victim >= 60) else 2
        return "reassurance", victim, severity

    return None, "", 0


# ---------------------------------------------------------------------------
# 违约反应 — 新版（draw_weighted 加权选择）
# ---------------------------------------------------------------------------

def _treaty_breach_reaction_v2(
    db, state, actor_power: str, evt: dict, direct_powers: set[str],
) -> tuple[str | None, str, int]:
    """违约类反应判断（新版）。使用 draw_weighted 在候选反应间加权选择。"""
    breacher = str(evt.get("actor_power") or "")
    victim = str(evt.get("target_power") or "")

    rel_breacher = _get_relation(db, actor_power, breacher)
    rel_victim = _get_relation(db, actor_power, victim)

    trust_breacher = int(rel_breacher["trust"]) if rel_breacher else 0
    trust_victim = int(rel_victim["trust"]) if rel_victim else 0
    pr_victim = int(rel_victim["public_relation"]) if rel_victim else 0
    status_breacher = str(rel_breacher["status"] or "") if rel_breacher else ""

    candidates = []

    # condemnation: 与违约方有高信任/条约关系
    if trust_breacher >= 50 or status_breacher == "allied":
        weight = 50 + trust_breacher * 1.5
        severity = 3 if trust_breacher >= 70 else 2
        candidates.append({
            "key": "condemnation",
            "weight": weight,
            "target": breacher,
            "severity": severity,
        })

    # reassurance: 与受害方关系好
    if pr_victim >= 30 or trust_victim >= 40:
        weight = 40 + pr_victim + trust_victim
        severity = 3 if (pr_victim >= 50 or trust_victim >= 60) else 2
        candidates.append({
            "key": "reassurance",
            "weight": weight,
            "target": victim,
            "severity": severity,
        })

    if not candidates:
        return None, "", 0

    source_ref = str(evt.get("source_ref") or "")
    chosen = draw_weighted(
        db, state=state,
        domain="geopolitical_reaction",
        subject_id=f"{actor_power}:{source_ref}",
        choices=candidates,
        draw_kind="treaty_breach",
    )

    if chosen is None:
        return None, "", 0

    return chosen["key"], chosen["target"], chosen["severity"]


# 保留原名作为兼容别名
_battle_or_siege_reaction = _battle_or_siege_reaction_legacy
_treaty_breach_reaction = _treaty_breach_reaction_legacy


# ---------------------------------------------------------------------------
# 延迟反应机制（跨回合连锁）
# ---------------------------------------------------------------------------

def _maybe_create_delayed_reaction(
    db, state, actor_power: str, evt: dict,
    reaction_type: str, target_power: str, severity: int,
) -> bool:
    """某些条件下，反应不在当月执行，而是延迟 1-3 回合。

    返回 True 表示已创建延迟反应，False 表示应即时执行。
    """
    # 通过 kv_store 检查是否启用延迟反应
    try:
        row = db.conn.execute(
            "SELECT value FROM kv_store WHERE key='ws_enable_delayed_reactions'"
        ).fetchone()
        if row is None or str(row["value"]) != "1":
            return False
    except Exception:
        return False

    # 延迟条件：反应类型为 balancing 或 caution（需要集结/准备时间）
    if reaction_type not in ("balancing", "caution"):
        return False

    # 延迟 1-3 回合
    delay = draw_int(
        db, state=state,
        domain="delayed_reaction",
        subject_id=f"{actor_power}:{evt.get('source_ref', '')}",
        low=1, high=3,
        draw_kind="delay_turns",
    )

    turn = get_turn(state)
    source_ref = str(evt.get("source_ref") or "")

    condition = {
        "requires_non_war": reaction_type == "balancing",
    }

    db.conn.execute(
        """INSERT OR IGNORE INTO delayed_geopolitical_reactions
        (trigger_turn, fire_turn, actor_power_id, source_ref,
         reaction_type, target_power_id, severity, condition_json, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (turn, turn + int(delay), actor_power, source_ref,
         reaction_type, target_power, severity, to_json(condition)),
    )
    return True


def _check_delayed_condition(db, actor_power: str, target_power: str, condition: dict) -> bool:
    """检查延迟反应的执行条件是否仍然满足。"""
    if condition.get("requires_non_war"):
        first, second = db._relation_pair(actor_power, target_power)
        row = db.conn.execute(
            "SELECT status FROM diplomatic_relations WHERE power_a=? AND power_b=?",
            (first, second),
        ).fetchone()
        if row and str(row["status"]) == "war":
            return False
    return True
