"""每月总计：把已裁定世界变化聚合成玩家回合开始的主入口。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from ming_sim.government import office_effect


SECTION_ORDER = (
    ("pending", "待核议"),
    ("adjudication", "裁决概览"),
    ("military", "军事"),
    ("internal", "内政"),
    ("regional", "区域局势"),
    ("geopolitical", "天下态势"),
    ("diplomacy", "外交"),
    ("personnel", "人事"),
    ("secret", "密令暗流"),
    ("world", "天下动向"),
    ("reactions", "人物与天下反应"),
    ("reputation", "仁义口碑"),
)

MONTH_TEXT = {
    1: "正月", 2: "二月", 3: "三月", 4: "四月", 5: "五月", 6: "六月",
    7: "七月", 8: "八月", 9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
}


def _decode(value: object, fallback: object) -> object:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _row_dict(row: object) -> Dict[str, Any]:
    return dict(row)  # sqlite3.Row and local row-like fixtures both support dict().


def _safe_name(db, table: str, key: str, value: str, fallback: str) -> str:
    row = db.conn.execute(f"SELECT name FROM {table} WHERE {key}=?", (value,)).fetchone()
    return str(row["name"]) if row is not None else fallback


def _period_title(year: int, month: int) -> str:
    era_year = max(1, int(year) - 195)
    return f"建安{_chinese_number(era_year)}年{MONTH_TEXT.get(int(month), f'{month}月')}军政总计"


def _chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value <= 10:
        return "十" if value == 10 else digits[value]
    if value < 20:
        return "十" + digits[value % 10]
    tens, ones = divmod(value, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")


def _section(section_id: str, summary: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    label = dict(SECTION_ORDER)[section_id]
    return {"id": section_id, "title": label, "summary": summary, "items": items}


def _battle_items(db, turn: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    rows = db.conn.execute("SELECT * FROM battles WHERE turn=? ORDER BY id DESC", (turn,)).fetchall()
    for row in rows:
        result = _decode(row["result"], {})
        if not isinstance(result, dict):
            result = {}
        node_id = str(row["node_id"])
        node_name = _safe_name(db, "strategic_nodes", "id", node_id, node_id)
        attacker_ids = [str(item) for item in _decode(row["attacker_ids"], []) if item]
        defender_ids = [str(item) for item in _decode(row["defender_ids"], []) if item]
        army_changes = ((result.get("audit") or {}).get("army_changes") or []) if isinstance(result.get("audit"), dict) else []
        casualty = sum(abs(int(item.get("manpower_delta") or 0)) for item in army_changes if isinstance(item, dict))
        winner = "攻方胜" if result.get("winner") == "attacker" else "守方胜"
        tactic = (result.get("ai_tactic") or {}).get("tactic") if isinstance(result.get("ai_tactic"), dict) else ""
        summary = f"{node_name}战役{winner}，参战 {len(attacker_ids)} 对 {len(defender_ids)} 支军，伤亡约 {casualty} 人。"
        if tactic:
            summary += f" 计策采用「{tactic}」。"
        items.append({
            "id": f"battle:{int(row['id'])}",
            "kind": "战役",
            "title": f"{node_name}战役",
            "summary": summary,
            "action": {"entry": "军令", "label": "召军府复盘"},
            "audit": {
                "battle_id": int(row["id"]),
                "random_roll": int(result.get("random_roll") or row["random_roll"] or 0),
                "final_probability": result.get("final_probability"),
                "hard_probability": result.get("hard_probability"),
                "weights": result.get("weights") or {},
                "ai_tactic": result.get("ai_tactic") or {},
                "terrain": result.get("terrain") or {},
                "army_breakdown": result.get("army_breakdown") or {},
                "army_changes": army_changes,
                "commander_fates": result.get("commander_fates") or [],
            },
        })
    return items


def _army_pressure_items(db, turn: int) -> List[Dict[str, Any]]:
    items = []
    fields = {"supply", "morale", "fatigue", "manpower", "supply_combat_multiplier"}
    rows = db.conn.execute(
        """
        SELECT al.*, a.name AS army_name
        FROM army_logs al
        LEFT JOIN armies a ON a.id=al.army_id
        WHERE al.turn=? AND al.field IN ({})
        ORDER BY al.id DESC
        LIMIT 10
        """.format(",".join("?" for _ in fields)),
        (turn, *sorted(fields)),
    ).fetchall()
    for row in rows:
        army_name = str(row["army_name"] or row["army_id"])
        items.append({
            "id": f"army-log:{int(row['id'])}",
            "kind": "补给军情",
            "title": army_name,
            "summary": f"{army_name}{row['field']}由{row['old_value']}至{row['new_value']}（{row['reason']}）。",
            "action": {"entry": "军令", "label": "议补给整训"},
            "audit": {},
        })
    return items


def _internal_items(db, turn: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    investments = db.conn.execute(
        """
        SELECT ril.*, r.name AS region_name
        FROM region_investment_logs ril
        LEFT JOIN regions r ON r.id=ril.region_id
        WHERE ril.turn=?
        ORDER BY ril.id DESC
        """,
        (turn,),
    ).fetchall()
    for row in investments:
        region_name = str(row["region_name"] or row["region_id"])
        items.append({
            "id": f"investment-log:{int(row['id'])}",
            "kind": "郡县投资",
            "title": region_name,
            "summary": f"{region_name}推进{row['category']}，进度 {row['progress_before']}→{row['progress_after']}，耗军资 {row['resource_cost']}。",
            "action": {"entry": "军令", "label": "查看郡县"},
            "audit": _row_dict(row),
        })
    active = db.conn.execute(
        """
        SELECT ri.*, r.name AS region_name
        FROM region_investments ri
        LEFT JOIN regions r ON r.id=ri.region_id
        WHERE ri.status='active'
        ORDER BY ri.region_id
        """
    ).fetchall()
    for row in active:
        region_name = str(row["region_name"] or row["region_id"])
        items.append({
            "id": f"investment:{row['region_id']}",
            "kind": "郡县投资",
            "title": region_name,
            "summary": f"{region_name}正在推进{row['category']}，当前进度 {row['progress']}%。",
            "action": {"entry": "军令", "label": "查看郡县"},
            "audit": _row_dict(row),
        })
    return items


def _regional_items(db, turn: int) -> List[Dict[str, Any]]:
    """区域局势 section：本月区域事件 + 重大事件待议。"""
    items: List[Dict[str, Any]] = []
    for row in db.conn.execute(
        "SELECT * FROM regional_incidents WHERE turn=? ORDER BY CASE tier WHEN 'dramatic' THEN 0 ELSE 1 END, id",
        (turn,),
    ).fetchall():
        region = _safe_name(db, "regions", "id", str(row["region_id"]), str(row["region_id"]))
        tier_label = "重大" if str(row["tier"]) == "dramatic" else "区域"
        local_effects = _decode(row["local_effects_json"], [])
        effects_summary = "；".join(
            f"{_effect_label(e.get('field', ''))}{_effect_delta(e.get('delta', 0))}"
            for e in local_effects
            if isinstance(e, dict)
        ) or "无显著变化"
        items.append({
            "id": f"regional_incident:{int(row['id'])}",
            "kind": f"{tier_label}事件",
            "title": str(row["title"]),
            "summary": f"{region}：{str(row['summary'])}。局部后果：{effects_summary}",
            "action": {"entry": "方略", "label": "查看待议策略" if str(row["tier"]) == "dramatic" else "查看详情"},
            "audit": {
                "region_id": str(row["region_id"]),
                "region_name": region,
                "tier": str(row["tier"]),
                "visibility": str(row["visibility"]),
                "local_effects": local_effects,
                "draw_refs": _decode(row["draw_refs_json"], []),
            },
        })
    return items


def _geopolitical_items(db, turn: int) -> List[Dict[str, Any]]:
    """天下态势 section：本月地缘反应记录。"""
    items: List[Dict[str, Any]] = []
    rows = db.conn.execute(
        "SELECT * FROM geopolitical_reactions WHERE turn=? ORDER BY id",
        (turn,),
    ).fetchall()
    reaction_label = {
        "opportunism": "伺机而动",
        "balancing": "扶弱抑强",
        "caution": "审慎观望",
        "condemnation": "公开谴责",
        "reassurance": "安抚保证",
    }
    source_label = {
        "battle": "野战",
        "siege": "围城",
        "treaty_breach": "违约",
    }
    for row in rows:
        actor = _safe_name(db, "powers", "id", str(row["actor_power_id"]), str(row["actor_power_id"]))
        target = _safe_name(db, "powers", "id", str(row["target_power_id"]), str(row["target_power_id"]))
        rxn_type = str(row["reaction_type"] or "")
        src_kind = str(row["source_kind"] or "")
        soft = _decode(row["soft_effects_json"], {})
        effect_label = {
            "public_relation_delta": "公开关系",
            "trust_delta": "互信",
            "military_coordination_delta": "军事协调",
            "power_action_score_delta": "行动倾向",
        }
        changes = "；".join(
            f"{effect_label.get(k, k)}{v:+d}"
            for k, v in soft.items() if isinstance(v, int) and v != 0
        ) or "无显著变化"
        items.append({
            "id": f"geopolitical:{int(row['id'])}",
            "kind": "天下态势",
            "title": f"{actor}{reaction_label.get(rxn_type, rxn_type)}",
            "summary": (
                f"因{source_label.get(src_kind, src_kind)}（{str(row['source_ref'] or '')}），"
                f"{actor}对{target}作出{reaction_label.get(rxn_type, rxn_type)}姿态。"
                f"有界变动：{changes}"
            ),
            "action": {"entry": "外交", "label": "查看反应依据"},
            "audit": {
                "source_kind": src_kind,
                "source_ref": str(row["source_ref"] or ""),
                "actor_power": actor,
                "target_power": target,
                "reaction_type": rxn_type,
                "severity": int(row["severity"] or 0),
                "soft_effects": soft,
                "evidence": _decode(row["evidence_json"], {}),
                "action_hints": _decode(row["action_hint_json"], {}),
            },
        })
    return items


def _effect_label(field: str) -> str:
    """将字段名翻译为中文标签。"""
    return {
        "public_support": "民心",
        "unrest": "动乱",
        "military_pressure": "军压",
        "road_condition": "道路",
        "grain_transport_pressure": "粮运",
        "harvest_outlook": "收成",
        "epidemic_pressure": "疫病",
        "disaster_risk": "灾害",
        "hazard_combat_multiplier": " hazard 战",
        "supply_combat_multiplier": "补给战",
    }.get(field, field)


def _effect_delta(delta: object) -> str:
    """格式化带符号 delta。"""
    try:
        d = int(delta)
    except (TypeError, ValueError):
        return ""
    if d == 0:
        return "±0"
    return f"{'+' if d > 0 else ''}{d}"


def _diplomacy_items(db, turn: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    envoys = db.conn.execute(
        "SELECT * FROM envoy_missions WHERE status='active' OR turn=? ORDER BY id DESC",
        (turn,),
    ).fetchall()
    for row in envoys:
        target = _safe_name(db, "powers", "id", str(row["target_power"]), str(row["target_power"]))
        status = "在途" if str(row["status"]) == "active" else str(row["status"])
        items.append({
            "id": f"envoy:{int(row['id'])}",
            "kind": "使臣谈判",
            "title": f"{row['envoy']}赴{target}",
            "summary": f"{row['envoy']}赴{target}{status}，目标：{row['goal']}。",
            "action": {"entry": "外交", "label": "修改条款"},
            "audit": _row_dict(row),
        })
    logs = db.conn.execute(
        "SELECT * FROM diplomacy_logs WHERE turn=? ORDER BY id DESC LIMIT 8",
        (turn,),
    ).fetchall()
    for row in logs:
        items.append({
            "id": f"diplomacy-log:{int(row['id'])}",
            "kind": "盟约变化",
            "title": str(row["field"]),
            "summary": f"{row['power_a']}与{row['power_b']}：{row['field']}由{row['old_value']}至{row['new_value']}（{row['reason']}）。",
            "action": {"entry": "外交", "label": "召使臣回报"},
            "audit": _row_dict(row),
        })
    return items


def _personnel_items(db, turn: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    rows = db.conn.execute(
        "SELECT * FROM government_office_logs WHERE turn=? ORDER BY id DESC",
        (turn,),
    ).fetchall()
    for row in rows:
        effect = office_effect(db, str(row["office_key"]))
        items.append({
            "id": f"office-log:{int(row['id'])}",
            "kind": "任事",
            "title": str(effect.get("name") or row["office_key"]),
            "summary": f"{row['new_character']}任{effect.get('name') or row['office_key']}，效率 {effect.get('efficiency')}。",
            "action": {"entry": "朝议", "label": "议人事"},
            "audit": effect,
        })
    offices = db.conn.execute("SELECT office_key FROM government_offices ORDER BY office_key").fetchall()
    for row in offices:
        effect = office_effect(db, str(row["office_key"]))
        if effect.get("vacant"):
            items.append({
                "id": f"office-vacant:{row['office_key']}",
                "kind": "空缺",
                "title": str(effect.get("name") or row["office_key"]),
                "summary": f"{effect.get('name')}尚无合适任事人物，效率 {effect.get('efficiency')}。",
                "action": {"entry": "朝议", "label": "议人事"},
                "audit": effect,
            })
    return items


def _secret_items(db, state: object, turn: int) -> List[Dict[str, Any]]:
    del turn
    orders = db.list_secret_orders()
    current_turn = int(getattr(state, "turn", 0))
    items = []
    for order in orders[:8]:
        due = int(order.get("due_turn") or 0)
        due_text = "无硬限" if due <= 0 else ("已到核议" if due <= current_turn else f"第 {due} 回合核议")
        items.append({
            "id": f"secret:{order['id']}",
            "kind": "密令",
            "title": str(order["title"]),
            "summary": f"{order['minister_name']}承办「{order['title']}」，状态 {order['status']}，{due_text}。",
            "action": {"entry": "朝议", "label": "私下密谈"},
            "audit": order,
        })
    return items


def _world_items(db, state: object, source_report: str) -> List[Dict[str, Any]]:
    report_turn = max(0, int(getattr(state, "turn", 1) or 1) - 1)
    chronicle_rows = db.conn.execute(
        """
        SELECT * FROM historical_chronicle
        WHERE turn<=?
        ORDER BY turn DESC, id DESC
        LIMIT 4
        """,
        (report_turn,),
    ).fetchall()
    chronicle_items = [
        {
            "id": f"chronicle:{int(row['id'])}",
            "kind": "史册裁定",
            "title": str(row["title"]),
            "summary": str(row["summary"] or f"{row['title']} · {row['status']}"),
            "action": {"entry": "史册", "label": "查史册"},
            "audit": _row_dict(row),
        }
        for row in chronicle_rows
    ]
    timeline = []
    try:
        from ming_sim.historical_events import historical_timeline_preview

        timeline = historical_timeline_preview(db, state, months=3)
    except Exception:
        timeline = []
    items = [
        {
            "id": f"timeline:{item['id']}",
            "kind": "史势窗口",
            "title": str(item["title"]),
            "summary": f"{item['window']} · {item['status']}",
            "action": {"entry": "史册", "label": "查史势"},
            "audit": item,
        }
        for item in timeline[:4]
    ]
    items = chronicle_items + items
    context = db.conn.execute("SELECT * FROM world_simulation_contexts WHERE turn=?", (report_turn,)).fetchone()
    if context is not None:
        weather = _decode(context["weather_json"], {})
        mood = _decode(context["public_mood_json"], {})
        items.insert(0, {
            "id": f"world-context:{report_turn}", "kind": "世界环境", "title": f"{context['season']}季·{weather.get('kind', '天候未明')}",
            "summary": f"民情{mood.get('trend', '观望')}；本月环境由可复现种子派生。",
            "action": {"entry": "史册", "label": "查世界审计"},
            "audit": {"seed": context["seed"], "weather": weather, "public_mood": mood, "regional_conditions": _decode(context["regional_conditions_json"], {})},
        })
    intel_rows = db.conn.execute("SELECT * FROM external_intelligence_reports WHERE turn=? ORDER BY id DESC", (report_turn,)).fetchall()
    for intel in intel_rows:
        visibility = str(intel["visibility"])
        label = {"rumor": "传闻", "assessment": "研判", "confirmed": "确认"}.get(visibility, visibility)
        items.append({
            "id": f"intel:{int(intel['id'])}", "kind": f"外部{label}", "title": str(intel["title"]),
            "summary": str(intel["summary"]), "action": {"entry": "外交", "label": "查看外势"},
            "audit": {"visibility": visibility, "usable_as_fact": bool(intel["usable_as_fact"]), "evidence_refs": _decode(intel["evidence_json"], [])},
        })
    if source_report:
        items.insert(0, {
            "id": "source-report",
            "kind": "月报原文",
            "title": "上月军政报",
            "summary": _compact(source_report, 96),
            "action": {"entry": "史册", "label": "读原文"},
            "audit": {"report": source_report},
        })
    return items


def _reputation_items(db, turn: int) -> List[Dict[str, Any]]:
    rows = db.conn.execute(
        "SELECT * FROM reputation_logs WHERE turn=? ORDER BY id DESC LIMIT 8",
        (turn,),
    ).fetchall()
    return [
        {
            "id": f"reputation:{int(row['id'])}",
            "kind": str(row["metric"]),
            "title": str(row["metric"]),
            "summary": f"{row['summary']}（{row['metric']} {int(row['delta']):+d}）。",
            "action": {"entry": "朝议", "label": "问口碑"},
            "audit": _row_dict(row),
        }
        for row in rows
    ]


def _pending_items(db, turn: int) -> List[Dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT * FROM pending_adjudications
        WHERE status='pending_review' AND turn<=?
        ORDER BY turn DESC, id DESC
        LIMIT 12
        """,
        (turn,),
    ).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        pack = _decode(row["pack_json"], {})
        if not isinstance(pack, dict):
            pack = {}
        kind = str(row["kind"])
        subject = str(row["subject_id"] or "")
        reason = str(row["reason"] or "裁决输出未通过规则校验")
        items.append({
            "id": f"pending-adjudication:{int(row['id'])}",
            "kind": "需廷议核定",
            "title": f"{kind}:{subject}" if subject else kind,
            "summary": f"{kind} 裁决暂停：{reason}。",
            "action": {"entry": "朝议", "label": "廷议核定"},
            "audit": {
                **_row_dict(row),
                "pack": pack,
                "rejected_proposal": _decode(row["rejected_proposal_json"], {}),
            },
        })
    return items


def _adjudication_items(db, turn: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    sources = [
        (
            "army_logs",
            "军情裁决",
            "SELECT id, army_id AS subject_id, field, new_value, reason FROM army_logs WHERE turn=? AND (reason LIKE '%AI裁判%' OR new_value LIKE '%AI裁判%') ORDER BY id DESC LIMIT 8",
        ),
        (
            "diplomacy_logs",
            "外交裁决",
            "SELECT id, power_a || ':' || power_b AS subject_id, field, new_value, reason FROM diplomacy_logs WHERE turn=? AND (reason LIKE '%AI裁判%' OR new_value LIKE '%AI裁判%') ORDER BY id DESC LIMIT 8",
        ),
        (
            "region_investment_logs",
            "内政裁决",
            "SELECT id, region_id AS subject_id, status AS field, reason AS new_value, reason FROM region_investment_logs WHERE turn=? AND reason LIKE '%AI裁判%' ORDER BY id DESC LIMIT 8",
        ),
        (
            "historical_chronicle",
            "天下裁决",
            "SELECT id, event_id AS subject_id, status AS field, summary AS new_value, summary AS reason FROM historical_chronicle WHERE turn=? AND summary LIKE '%AI裁判%' ORDER BY id DESC LIMIT 8",
        ),
    ]
    for table, kind, sql in sources:
        try:
            rows = db.conn.execute(sql, (turn,)).fetchall()
        except Exception:
            rows = []
        for row in rows:
            subject = str(row["subject_id"] or "")
            summary = str(row["new_value"] or row["reason"] or "")
            items.append({
                "id": f"adjudication:{table}:{int(row['id'])}",
                "kind": kind,
                "title": subject or kind,
                "summary": _compact(summary, 140),
                "action": {"entry": "朝议", "label": "查裁决"},
                "audit": {"source_table": table, **_row_dict(row)},
            })
    pending_count = db.conn.execute(
        "SELECT COUNT(*) FROM pending_adjudications WHERE turn=? AND status='pending_review'",
        (turn,),
    ).fetchone()[0]
    if int(pending_count or 0) > 0:
        items.insert(0, {
            "id": f"adjudication:pending:{turn}",
            "kind": "待核议",
            "title": "待核议裁决",
            "summary": f"本月有 {int(pending_count)} 项模型裁决被规则暂停，需廷议核定。",
            "action": {"entry": "朝议", "label": "廷议核定"},
            "audit": {"pending_count": int(pending_count)},
        })
    return items[:12]


def _compact(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[:limit].rstrip() + "…"


def _summary(label: str, items: Iterable[Dict[str, Any]], empty: str) -> str:
    count = len(list(items))
    return empty if count == 0 else f"{label}共 {count} 项，先列要害，细项可展开查证。"


def build_monthly_report(db, state: object) -> Dict[str, Any]:
    """返回每回合开始展示的结构化军政总计。"""
    current_turn = int(getattr(state, "turn", 1) or 1)
    # 颁令批次在本回合核销时即保存回奏；尚未进入下月时应优先展示这份刚生成的
    # 回奏（尤其是重大天下反应的待决），进入下月后才自然回看上月。
    current_row = db.conn.execute("SELECT 1 FROM turn_reports WHERE turn=?", (current_turn,)).fetchone()
    report_turn = current_turn if current_row is not None else max(0, current_turn - 1)
    row = db.conn.execute(
        "SELECT year, period, report FROM turn_reports WHERE turn=?",
        (report_turn,),
    ).fetchone()
    year = int(row["year"]) if row is not None else int(getattr(state, "year", 208))
    period = int(row["period"]) if row is not None else int(getattr(state, "period", 1))
    source_report = str(row["report"] or "") if row is not None else ""

    military_items = _battle_items(db, report_turn) + _army_pressure_items(db, report_turn)
    internal_items = _internal_items(db, report_turn)
    regional_items = _regional_items(db, report_turn)
    geopolitical_items = _geopolitical_items(db, report_turn)
    diplomacy_items = _diplomacy_items(db, report_turn)
    personnel_items = _personnel_items(db, report_turn)
    memorial_rows = db.conn.execute("SELECT * FROM minister_memorials WHERE turn=? ORDER BY id", (report_turn,)).fetchall()
    personnel_items.extend({
        "id": f"memorial:{int(item['id'])}", "kind": str(item["memorial_kind"]), "title": str(item["title"]),
        "summary": f"{item['minister_name']}：{item['summary']}", "action": {"entry": "朝议", "label": "纳入方略"},
        "audit": {"risk": item["risk_note"], "evidence_refs": _decode(item["evidence_json"], []), "suggested_action": _decode(item["suggested_action_json"], {})},
    } for item in memorial_rows)
    secret_items = _secret_items(db, state, report_turn)
    world_items = _world_items(db, state, source_report)
    reputation_items = _reputation_items(db, report_turn)
    pending_items = _pending_items(db, report_turn)
    adjudication_items = _adjudication_items(db, report_turn)
    reaction_rows = db.conn.execute(
        "SELECT * FROM reaction_events WHERE turn=? ORDER BY id",
        (report_turn,),
    ).fetchall()
    reaction_items = [
        {
            "id": f"reaction:{int(row['id'])}",
            "kind": "重大天下反应" if str(row["reaction_level"]) == "major" else "天下反应",
            "title": str(row["actor"] or "天下反应"),
            "summary": str(row["outcome_summary"] or ""),
            "status": str(row["status"]), "level": str(row["reaction_level"]),
            "action": {"entry": "朝议", "label": "查看反应依据"},
            "audit": {
                **_row_dict(row),
                "rule_facts_snapshot": _decode(row["rule_facts_snapshot"], {}),
                "ai_proposal": _decode(row["ai_proposal"], {}),
                "validation_result": _decode(row["validation_result"], {}),
            },
        }
        for row in reaction_rows
    ]
    reputation_score = db.reputation_summary(limit=8)["score"]

    sections = [
        _section("military", _summary("军令战事", military_items, "上月无明确战役，仍需留意补给、疲劳与驻防。"), military_items),
        _section("internal", _summary("郡县经营", internal_items, "上月未见郡县投资推进，可从粮仓、城防、民心中择要问策。"), internal_items),
        _section("regional", _summary("区域局势", regional_items, "上月区域平稳，无显著灾害或事件。"), regional_items),
        _section("geopolitical", _summary("天下态势", geopolitical_items, "上月无跨势力地缘反应。"), geopolitical_items),
        _section("diplomacy", _summary("使臣盟约", diplomacy_items, "上月无新外交回报，可继续审视孙刘、荆州与借粮议题。"), diplomacy_items),
        _section("personnel", _summary("人事任命", personnel_items, "上月无新任事记录，空缺与效率仍可在廷议中追问。"), personnel_items),
        _section("secret", _summary("密令暗流", secret_items, "暂无进行中密令。"), secret_items),
        _section("world", _summary("天下动向", world_items, "暂无新的天下条目。"), world_items),
        _section("reputation", f"仁义口碑 {reputation_score}，以近期可见民心与名望回声为准。", reputation_items),
    ]
    if reaction_items:
        sections.insert(-1, _section("reactions", _summary("人物与天下反应", reaction_items, "暂无新的天下反应。"), reaction_items))
    if pending_items:
        sections.insert(0, _section("pending", _summary("待核议裁决", pending_items, "暂无被规则暂停的裁决。"), pending_items))
    if adjudication_items:
        insert_at = 1 if pending_items else 0
        sections.insert(insert_at, _section("adjudication", _summary("模型裁决", adjudication_items, "暂无模型裁决记录。"), adjudication_items))

    return {
        "turn": report_turn,
        "year": year,
        "period": period,
        "title": _period_title(year, period),
        "source_report": source_report,
        "sections": sections,
    }
