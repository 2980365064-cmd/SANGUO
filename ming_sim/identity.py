"""称号宣称与天下大势后果的硬规则。"""
from __future__ import annotations
import json
from typing import Any, Dict
from ming_sim.long_term import long_term_summary, adjust_faction_support

YIZHOU_CORE_NODES = ("chengdu", "jiangzhou", "yongan")

def _owned_nodes(db) -> set[str]:
    return {str(row["id"]) for row in db.conn.execute("SELECT id FROM regions WHERE controlled_by='liu_bei'").fetchall()}

def _current_stage(db) -> str:
    if db.kv_get("proclaimed_emperor") == "1": return "称帝后"
    if db.kv_get("identity_hanzhong_granted") == "1": return "汉中王"
    nodes = _owned_nodes(db)
    if "chengdu" in nodes: return "益州治蜀"
    if nodes & {"xiangyang", "jiangling", "jiangxia", "jingnan"}: return "荆州立足"
    return "流亡军"

def _conditions(db, state: object, action: str) -> list[str]:
    metrics, nodes = dict(getattr(state, "metrics", {}) or {}), _owned_nodes(db)
    reputation = int(long_term_summary(db, state)["reputation"]["score"])
    unmet: list[str] = []
    if action == "promote_hanzhong":
        if "chengdu" not in nodes: unmet.append("未控制成都")
        if not nodes.intersection(YIZHOU_CORE_NODES): unmet.append("未掌握益州核心节点")
        if int(metrics.get("名分", 0)) < 80: unmet.append("名分不足八十")
        if reputation < 60: unmet.append("天下口碑不足六十")
    elif action == "proclaim_emperor":
        if _current_stage(db) != "汉中王": unmet.append("未先称汉中王")
        row = db.conn.execute("SELECT status FROM characters WHERE name='刘备'").fetchone()
        if row is None or str(row["status"]) != "active": unmet.append("刘备不可主持进位")
        if "chengdu" not in nodes or not nodes.intersection(YIZHOU_CORE_NODES): unmet.append("益州核心未稳")
        if int(metrics.get("名分", 0)) < 85: unmet.append("名分不足八十五")
        if reputation < 70: unmet.append("天下口碑不足七十")
    else: raise ValueError(f"未知身份行动：{action}")
    if int(getattr(state, "collapse_turns", 0)) > 0 or int(getattr(state, "chengdu_crisis_turns", 0)) > 0: unmet.append("军政危机未解")
    return unmet

def _pressure(db) -> int:
    row = db.conn.execute("SELECT COALESCE(SUM(external_pressure),0) FROM political_claims WHERE status='active'").fetchone()
    return int(row[0] or 0)

def identity_summary(db, state: object) -> Dict[str, Any]:
    stage = _current_stage(db)
    if stage == "称帝后":
        return {"stage": stage, "next_stage": "", "eligible": True, "legitimacy": "名实相符", "unmet_conditions": [], "available_action": "", "political_pressure": "身份已至终阶。", "external_pressure": _pressure(db), "consequence_preview": []}
    action, next_stage = ("proclaim_emperor", "称帝后") if stage == "汉中王" else ("promote_hanzhong", "汉中王")
    unmet = _conditions(db, state, action)
    legitimacy = "名实相符" if not unmet else ("僭越" if len(unmet) >= 3 else "存疑")
    severity = len(unmet) + (2 if action == "proclaim_emperor" else 0)
    return {"stage": stage, "next_stage": next_stage, "eligible": not unmet, "legitimacy": legitimacy, "unmet_conditions": unmet, "available_action": action, "external_pressure": _pressure(db), "consequence_preview": [] if not unmet else ["名分、天下口碑与士族支持下降", "群臣派系反对，外交初始接受度下降"], "political_pressure": "名实已备，可从容颁令。" if not unmet else f"仍可宣称{next_stage}，但将承受{severity}级天下压力：{'；'.join(unmet)}。"}

def apply_identity_promotion(db, state: object, action: str) -> Dict[str, Any]:
    summary = identity_summary(db, state)
    if summary["available_action"] != action: raise ValueError("该称号已不可再宣称")
    unmet = list(summary["unmet_conditions"])
    severity = len(unmet) + (2 if action == "proclaim_emperor" else 0)
    legitimacy = str(summary["legitimacy"])
    declared_stage = "称帝后" if action == "proclaim_emperor" else "汉中王"
    consequences: Dict[str, int] = {}
    if severity:
        consequences = {"名分": -min(18, 3 * severity), "士族支持": -min(16, 3 * severity), "军心": -min(10, severity)}
        for key, delta in consequences.items(): state.metrics[key] = max(0, int(state.metrics.get(key, 0)) + delta)
        db.add_reputation_log(state, source_kind="political_claim", source_id=action, metric="仁义", delta=-min(20, 4 * severity), summary=f"{declared_stage}名实未备，天下多有质疑。")
        for faction in ("veterans", "jingzhou", "local", "yizhou"): adjust_faction_support(db, state, faction, -min(10, severity * 2), f"{declared_stage}宣称引发疑虑", source_kind="political_claim", source_id=action)
    else:
        db.add_reputation_log(state, source_kind="political_claim", source_id=action, metric="仁义", delta=4, summary=f"{declared_stage}名实相符，天下多有响应。")
    db.conn.execute("INSERT INTO political_claims (turn,year,period,action,declared_stage,legitimacy,unmet_conditions,consequences,external_pressure) VALUES (?,?,?,?,?,?,?,?,?)", (int(state.turn), int(state.year), int(state.period), action, declared_stage, legitimacy, json.dumps(unmet, ensure_ascii=False), json.dumps(consequences, ensure_ascii=False), severity * 4))
    if action == "promote_hanzhong":
        db.kv_set("identity_hanzhong_granted", "1"); db.conn.execute("UPDATE characters SET office='汉中王' WHERE name='刘备'")
    else:
        db.kv_set("proclaimed_emperor", "1"); db.conn.execute("UPDATE characters SET office='大汉皇帝' WHERE name='刘备'")
    db.conn.commit()
    from ming_sim.government import government_stage
    state.stage = government_stage(int(state.year), int(state.period), {"controlled_nodes": list(_owned_nodes(db)), "titles": ["汉中王"] if db.kv_get("identity_hanzhong_granted") == "1" else [], "proclaimed_emperor": db.kv_get("proclaimed_emperor") == "1"})
    db.save_state(state)
    return {"action": action, "stage": state.stage, "summary": identity_summary(db, state)}
