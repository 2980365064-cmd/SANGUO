"""臣子奏议生成与记忆写入守卫。

从 world_simulation.py 提取：
- build_monthly_memorials: 基于区域事件、军队压力、活跃 issue、外势情报生成臣子奏议
- _compute_speaker_score: 为 (议题, 大臣) 对计算 speaker_score
- can_write_memory_from_source: 检查来源是否足够可信以写入记忆
"""
from __future__ import annotations

from typing import Any, Dict

from ming_sim.world_random import draw_int, draw_weighted
from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list, status_terminal as _status_terminal
from ming_sim.ws_utils import get_turn, to_json
from ming_sim.ws_common import seed_for as _seed_for


def build_monthly_memorials(db, state: object) -> list[Dict[str, Any]]:
    """基于区域事件、军队压力、活跃 issue、外势情报生成臣子奏议。

    每月最多 3 条，同一人物最多 1 条。发言人有 speaker_score 评分。
    """
    turn = get_turn(state)
    if db.conn.execute("SELECT 1 FROM minister_memorials WHERE turn=? LIMIT 1", (turn,)).fetchone():
        return []

    # === 候选议题 ===
    candidates: list[Dict[str, Any]] = []

    # 1. 本月区域事件（重大 + 普通）
    for inc in db.conn.execute(
        "SELECT id, region_id, incident_type, tier, title, summary FROM regional_incidents WHERE turn=?",
        (turn,),
    ).fetchall():
        region = db.conn.execute(
            "SELECT name FROM regions WHERE id=?", (str(inc["region_id"]),)
        ).fetchone()
        rname = str(region["name"]) if region else str(inc["region_id"])
        candidates.append({
            "kind": "区域局势",
            "title": f"请处置：{inc['title']}",
            "summary": f"{rname}发生{inc['incident_type']}，等级{'重大' if inc['tier'] == 'dramatic' else '一般'}。",
            "subject": f"regional_incident:{inc['id']}",
            "risk": "未及时处置将使区域状态持续恶化。",
            "evidence": [f"regional_incidents:{inc['id']}"],
            "regional_incident_ids": [int(inc["id"])],
            "topic_type": "regional_incident",
        })

    # 2. 军队补给/疲劳
    for army in db.conn.execute(
        "SELECT id, name, commander, supply, morale, fatigue, station_node "
        "FROM armies WHERE owner_power='liu_bei' AND active=1 ORDER BY supply, fatigue DESC"
    ).fetchall():
        if int(army["supply"] or 0) < 35:
            candidates.append({
                "kind": "建言", "title": f"请议{army['name']}补给",
                "summary": f"{army['name']}携粮仅{army['supply']}，不宜无备而进。",
                "subject": str(army["id"]), "risk": "补给不足将削弱行军与接战。",
                "evidence": [f"armies:{army['id']}:supply={army['supply']}"],
                "regional_incident_ids": [],
                "topic_type": "army_supply",
            })
        elif int(army["fatigue"] or 0) >= 65:
            candidates.append({
                "kind": "忧虑", "title": f"请缓{army['name']}疲军",
                "summary": f"{army['name']}疲劳{army['fatigue']}，宜整训再图。",
                "subject": str(army["id"]), "risk": "疲军强行接战将增加伤亡。",
                "evidence": [f"armies:{army['id']}:fatigue={army['fatigue']}"],
                "regional_incident_ids": [],
                "topic_type": "army_fatigue",
            })

    # 3. 活跃 issue
    for issue in db.conn.execute(
        "SELECT id, title, severity, region_hint FROM issues WHERE status IN ('active','open') "
        "ORDER BY severity DESC, id LIMIT 2"
    ).fetchall():
        candidates.append({
            "kind": "奏议", "title": f"请处置：{issue['title']}",
            "summary": f"此事紧急度{issue['severity']}，请定承办与期限。",
            "subject": f"issue:{issue['id']}", "risk": "久置将使局势继续恶化。",
            "evidence": [f"issues:{issue['id']}:severity={issue['severity']}"],
            "regional_incident_ids": [],
            "topic_type": "issue",
        })

    # 4. 确认外势情报
    for intel in db.conn.execute(
        "SELECT id, power_id, title, summary FROM external_intelligence_reports "
        "WHERE turn=? AND visibility='confirmed' LIMIT 2", (turn,)
    ).fetchall():
        candidates.append({
            "kind": "情报", "title": f"外势确认：{intel['title']}",
            "summary": f"关于{intel['power_id']}的研判已确认。",
            "subject": f"intel:{intel['id']}", "risk": "外势动向影响战略选择。",
            "evidence": [f"external_intelligence_reports:{intel['id']}"],
            "regional_incident_ids": [],
            "topic_type": "intel",
        })

    # 5. 记忆驱动候选：近 5 回合负面记忆触发"旧事重提"
    if hasattr(db, "get_recent_event_memories"):
        try:
            recent_memories = db.get_recent_event_memories(turn, window=5, limit=10)
            neg_memories = [
                m for m in recent_memories
                if str(m.get("sentiment") or "") == "negative" and int(m.get("importance") or 0) >= 3
            ]
            for mem in neg_memories[:1]:  # 最多 1 条
                candidates.append({
                    "kind": "旧事", "title": f"请察旧事：{mem.get('title', '旧事')}",
                    "summary": f"近有旧事重提，不可不察。",
                    "subject": f"memory:{mem['id']}", "risk": "旧事不察恐生嫌隙。",
                    "evidence": [f"event_memories:{mem['id']}"],
                    "regional_incident_ids": [],
                    "topic_type": "memory_grievance",
                })
        except Exception:
            pass

    # 6. 忠诚变动候选：近 3 回合 |delta|>=5 的忠诚变动
    for log_row in db.conn.execute(
        "SELECT id, character_name, delta, reason FROM character_loyalty_logs "
        "WHERE turn >= ? AND ABS(delta) >= 5 ORDER BY turn DESC LIMIT 1",
        (turn - 2,),
    ).fetchall():
        candidates.append({
            "kind": "忧虑", "title": f"请察{log_row['character_name']}忠诚",
            "summary": f"{log_row['character_name']}近有忠诚变动（{log_row['delta']:+d}），{log_row['reason'] or '宜加留意'}。",
            "subject": f"loyalty:{log_row['character_name']}", "risk": "忠诚动摇恐生变故。",
            "evidence": [f"character_loyalty_logs:{log_row['id']}"],
            "regional_incident_ids": [],
            "topic_type": "loyalty_risk",
        })

    # 7. 派系低支持候选：support < 40 的派系代言人
    for faction_row in db.conn.execute(
        "SELECT faction_key, label, support, agenda FROM political_faction_states "
        "WHERE status='active' AND support < 40 LIMIT 1"
    ).fetchall():
        candidates.append({
            "kind": "进言", "title": f"{faction_row['label']}有不满之声",
            "summary": f"{faction_row['label']}支持度仅{faction_row['support']}，宜加安抚。",
            "subject": f"faction:{faction_row['faction_key']}", "risk": "派系不满可能影响朝局稳定。",
            "evidence": [f"political_faction_states:{faction_row['faction_key']}"],
            "regional_incident_ids": [],
            "topic_type": "faction_grievance",
        })

    if not candidates:
        return []

    # === 获取大臣列表（含派系支持度） ===
    ministers = db.conn.execute(
        "SELECT c.name, c.office, c.office_type, c.faction, c.politics, c.intelligence, "
        "c.ambition, c.integrity, c.courage, c.loyalty, c.closeness_to_liu_bei, c.location, "
        "COALESCE(pfs.support, 50) as faction_support, COALESCE(pfs.agenda, '') as faction_agenda "
        "FROM characters c "
        "LEFT JOIN political_faction_states pfs ON c.faction = pfs.label "
        "WHERE c.power_id='liu_bei' AND c.status='active' AND c.name!='刘备' "
        "LIMIT 20"
    ).fetchall()
    if not ministers:
        return []

    # === 评分：每个 (candidate, minister) 对计算 speaker_score ===
    scored_pairs: list[tuple[float, dict, dict, dict]] = []
    for candidate in candidates:
        for minister_row in ministers:
            minister = dict(minister_row)
            score, breakdown = _compute_speaker_score(db, state, candidate, minister)
            scored_pairs.append((score, candidate, minister, breakdown))

    # 按分数排序，选 top 3，每人最多 1 条
    scored_pairs.sort(key=lambda x: -x[0])
    used_ministers: set[str] = set()
    created: list[Dict[str, Any]] = []

    for score, candidate, minister, breakdown in scored_pairs:
        if len(created) >= 3:
            break
        mname = str(minister["name"])
        if mname in used_ministers:
            continue
        used_ministers.add(mname)

        evidence_with_score = list(candidate["evidence"])
        evidence_with_score.append(f"speaker_score:{score:.0f}")

        cursor = db.conn.execute(
            """INSERT INTO minister_memorials
            (turn, minister_name, memorial_kind, title, summary, subject_ref, risk_note,
             evidence_json, suggested_action_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (
                turn, mname, candidate["kind"],
                candidate["title"], candidate["summary"], candidate["subject"],
                candidate["risk"],
                to_json({
                    "facts": candidate["evidence"],
                    "memory_ids": candidate.get("_memory_ids", []),
                    "speaker_score_breakdown": breakdown,
                    "regional_incident_ids": candidate.get("regional_incident_ids", []),
                }),
                to_json({"action": "draft", "subject": candidate["subject"]}),
            ),
        )
        created.append({
            "id": int(cursor.lastrowid), "minister": mname,
            "speaker_score": score, **candidate,
        })

    db.conn.commit()
    return created


def _compute_speaker_score(
    db, state, candidate: dict, minister: dict,
) -> tuple[float, dict]:
    """为 (议题, 大臣) 计算 speaker_score。返回 (总分, 评分明细)。

    评分维度：
      - 职责匹配（0..35）
      - 性格匹配（0..20）
      - 派系利益（-15..20）
      - 与刘备亲疏/忠诚（-10..15）
      - 相关记忆情绪（-15..15）
      - 可见情报/所在区域匹配（0..15）
    """
    breakdown: dict[str, float] = {}

    # 职责匹配
    office_type = str(minister.get("office_type") or "")
    topic_type = candidate.get("topic_type", "")
    office_match = 0.0
    if topic_type == "army_supply" and office_type in {" military", "军务"}:
        office_match = 30
    elif topic_type == "army_fatigue" and office_type in {"military", "军务"}:
        office_match = 25
    elif topic_type == "regional_incident" and office_type in {"civil", "民政"}:
        office_match = 30
    elif topic_type == "issue" and office_type in {"court", "朝政"}:
        office_match = 25
    elif topic_type == "intel" and office_type in {"diplomacy", "外交"}:
        office_match = 35
    elif office_type:
        office_match = 10  # 有官职但不对口
    breakdown["职责匹配"] = office_match

    # 性格匹配（基于 ambition/integrity/courage）
    ambition = int(minister.get("ambition") or 50)
    integrity = int(minister.get("integrity") or 50)
    courage = int(minister.get("courage") or 50)
    personality = 0.0
    if topic_type in {"army_supply", "army_fatigue", "regional_incident"}:
        # 务实型：高 integrity + 中等 ambition
        personality = (integrity - 30) / 5 + (courage - 40) / 10
    elif topic_type == "issue":
        # 政略型：高 ambition + 高 intelligence
        intelligence = int(minister.get("intelligence") or 50)
        personality = (ambition - 40) / 5 + (intelligence - 40) / 10
    elif topic_type == "intel":
        personality = (integrity - 30) / 8
    personality = max(0, min(20, personality))
    breakdown["性格匹配"] = personality

    # 派系利益（基于真实 faction_support + agenda）
    faction = str(minister.get("faction") or "")
    faction_support = int(minister.get("faction_support") or 50)
    faction_agenda = str(minister.get("faction_agenda") or "")
    topic_title = str(candidate.get("title") or "")
    faction_score = 0.0
    # 派系支持度低（<40）时，该派系大臣更积极发言（加分）
    if faction_support < 40:
        faction_score = 15 + (40 - faction_support) / 4  # 最高 25
    elif faction_support > 70:
        faction_score = -5  # 满意，少说话
    # agenda 与话题匹配加分
    if faction_agenda and topic_type:
        if topic_type in faction_agenda:
            faction_score += 5
        elif any(kw in faction_agenda for kw in topic_title.split("：")[-1:] if kw):
            faction_score += 3
    faction_score = max(-15, min(20, faction_score))
    breakdown["派系利益"] = faction_score

    # 亲疏/忠诚
    loyalty = int(minister.get("loyalty") or 50)
    closeness = int(minister.get("closeness_to_liu_bei") or 50)
    loyalty_score = (loyalty - 50) / 10 + (closeness - 50) / 10
    loyalty_score = max(-10, min(15, loyalty_score))
    breakdown["亲疏忠诚"] = loyalty_score

    # 记忆情绪（接入 event_memory）
    memory_score = 0.0
    minister_name = str(minister.get("name") or "")
    office_type_str = str(minister.get("office_type") or "")
    memories = []
    if minister_name and hasattr(db, "get_relevant_event_memories"):
        try:
            memories = db.get_relevant_event_memories(
                character_name=minister_name,
                faction=faction,
                office_type=office_type_str,
                turn=turn,
                limit=5,
            )
        except Exception:
            memories = []
    if memories:
        pos = sum(1 for m in memories if str(m.get("sentiment") or "") == "positive")
        neg = sum(1 for m in memories if str(m.get("sentiment") or "") == "negative")
        total = len(memories)
        memory_score = ((pos - neg) / total) * 15.0 if total > 0 else 0.0
    breakdown["记忆情绪"] = memory_score
    # 将记忆 ID 暂存到 candidate 供后续填充 evidence_json
    candidate["_memory_ids"] = [int(m["id"]) for m in memories]

    # 区域/情报匹配
    location_score = 0.0
    location = str(minister.get("location") or "")
    if topic_type == "regional_incident" and location:
        # 如果大臣所在区域就是事件区域，加分
        subject = candidate.get("subject", "")
        if location in subject:
            location_score = 15
    elif topic_type == "intel":
        location_score = 5
    location_score = max(0, min(15, location_score))
    breakdown["区域情报"] = location_score

    total = office_match + personality + faction_score + loyalty_score + memory_score + location_score
    return total, breakdown


def can_write_memory_from_source(db, *, source_kind: str, source_id: str) -> bool:
    """检查来源是否足够可信以写入记忆。

    传闻不得写成"人物已知事实"。只有已确认的事实才能写入记忆。
    - external_intelligence_reports: 仅 verification_status='confirmed' 可写入
    - power_ai_actions: 仅 status='executed' 可写入
    - 其他来源（regional_incidents, issues 等）默认可写入
    """
    if source_kind == "external_intelligence_reports":
        row = db.conn.execute(
            "SELECT verification_status FROM external_intelligence_reports WHERE id=?",
            (source_id,),
        ).fetchone()
        if row is None:
            return False
        return str(row["verification_status"]) == "confirmed"
    elif source_kind == "power_ai_actions":
        row = db.conn.execute(
            "SELECT status FROM power_ai_actions WHERE id=?",
            (source_id,),
        ).fetchone()
        if row is None:
            return False
        return str(row["status"]) == "executed"
    elif source_kind in (
        "regional_incidents", "issues", "character_loyalty_logs",
        "political_faction_states", "power_internal_dynamics",
        "directive", "battle", "government", "reaction",
        "geopolitical_reactions",
    ):
        return True
    else:
        return False
