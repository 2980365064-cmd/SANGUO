"""上下文生成与文本匹配：历史锚点、胜负判定、地区/军队/事件模糊匹配、
人物/事件上下文串、给 LLM 的 state_context。L4。

通过 bind_content() 注入 GameContent（过渡期）。
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from ming_sim.constants import ECONOMY_ACCOUNTS, TURN_UNIT
from ming_sim.assets import format_money, format_money_delta
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.exceptions import LLMContractError
from ming_sim.models import Army, Character, Event, GameState, Region

_content: Optional[GameContent] = None


def bind_content(content: GameContent) -> None:
    global _content
    _content = content


def _ctx() -> GameContent:
    if _content is None:
        raise RuntimeError("context.bind_content() 未调用：GameContent 未注入。")
    return _content


def historical_anchor_for_month(year: int, month: int) -> Dict[str, object]:
    """给 LLM 的无剧透历史压力标题；真正前提与变体由历史事件卡结算。"""
    anchors = {
        (208, 9): "孙刘联盟的外交窗口正在开启。",
        (208, 11): "赤壁战区的决战压力正在上升。",
        (211, 1): "益州政略进入可作出长期抉择的窗口。",
        (214, 1): "成都归属将改变刘备集团的政权性质。",
        (215, 1): "孙刘围绕荆州归属的冲突进入公开化窗口。",
        (217, 1): "汉中门户的军事压力正在上升。",
        (219, 7): "汉中王名号与准国家建制的政治窗口正在开启。",
        (219, 10): "荆州前线、孙刘互信与襄樊战局同时进入高风险窗口。",
        (220, 10): "汉廷名义的变化将重构天下政权的合法性竞争。",
        (221, 4): "成都继统建国的政治窗口正在开启。",
        (221, 7): "东线战略、荆州与孙刘关系进入重大抉择窗口。",
        (223, 4): "刘备历史线进入最终收束窗口。",
    }
    note = anchors.get((year, month), "")
    return {
        "date": f"{year}年{month}月",
        "note": note or f"本{TURN_UNIT}无硬性历史锚点，但势力仍需按其利益自行推进。",
        "must_respect": bool(note),
    }


ENDING_ONGOING = "ongoing"
ENDING_LIU_BEI_DEAD = "liu_bei_dead"
ENDING_YIZHOU_CORE_FALLEN = "yizhou_core_fallen"
ENDING_REGIME_COLLAPSED = "regime_collapsed"
ENDING_HISTORICAL_BAIDI = "historical_baidi"
ENDING_UNIFIED_VICTORY = "unified_victory"
ENDING_REWRITTEN_223 = "rewritten_223"
ENDING_THREE_KINGDOMS = "three_kingdoms_balance"
ENDING_YIZHOU_GUARDIAN = "yizhou_guardian"

# 五态结局的定调文案（前端弹窗标题/CLI 打印用）。ongoing 不入此表。
ENDING_LABELS: Dict[str, str] = {
    ENDING_LIU_BEI_DEAD: "主公身死",
    ENDING_YIZHOU_CORE_FALLEN: "益州核心失守",
    ENDING_REGIME_COLLAPSED: "军政瓦解",
    ENDING_HISTORICAL_BAIDI: "白帝托孤",
    ENDING_UNIFIED_VICTORY: "兴复汉室",
    ENDING_THREE_KINGDOMS: "三足均衡",
    ENDING_YIZHOU_GUARDIAN: "偏安守成",
    ENDING_REWRITTEN_223: "章武改写",
}


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def _ending_scores(db: GameDB, state: GameState) -> Dict[str, int]:
    total_regions = int(db.conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0] or 0)
    owned_regions = int(db.conn.execute(
        "SELECT COUNT(*) FROM regions WHERE controlled_by='liu_bei'"
    ).fetchone()[0] or 0)
    territorial = owned_regions / max(1, total_regions)
    public_row = db.conn.execute(
        "SELECT AVG(public_support) FROM regions WHERE controlled_by='liu_bei'"
    ).fetchone()[0]
    public_support = float(public_row if public_row is not None else state.metrics.get("民望", 50))
    active_court = db.conn.execute(
        """
        SELECT AVG((ability+loyalty+integrity+politics+leadership)/5.0)
        FROM characters WHERE power_id='liu_bei' AND status='active'
        """
    ).fetchone()[0]
    relation_rows = db.conn.execute(
        "SELECT public_relation, trust, military_coordination FROM diplomatic_relations WHERE power_a='liu_bei' OR power_b='liu_bei'"
    ).fetchall()
    diplomacy = 50.0
    if relation_rows:
        diplomacy = sum(
            ((int(row["public_relation"]) + 100) / 2 + int(row["trust"]) + int(row["military_coordination"])) / 3
            for row in relation_rows
        ) / len(relation_rows)
    liu_manpower = int(db.conn.execute(
        "SELECT COALESCE(SUM(manpower),0) FROM armies WHERE owner_power='liu_bei' AND active=1"
    ).fetchone()[0] or 0)
    all_manpower = int(db.conn.execute(
        "SELECT COALESCE(SUM(manpower),0) FROM armies WHERE active=1"
    ).fetchone()[0] or 0)
    battle_rows = db.conn.execute("SELECT result FROM battles").fetchall()
    wins = 0
    for row in battle_rows:
        try:
            result = json.loads(str(row["result"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if result.get("winner") == "attacker":
            attacker_ids = result.get("attacker_ids") or []
            if any(str(item).startswith(("liu", "guan", "zhangfei")) for item in attacker_ids):
                wins += 1
    win_rate = wins / len(battle_rows) if battle_rows else 0.5
    return {
        "统一": _clamp_score(territorial * 100),
        "名分": _clamp_score(float(state.metrics.get("名分", 50))),
        "民生": _clamp_score((public_support + float(state.metrics.get("民望", 50))) / 2),
        "将相": _clamp_score(float(active_court if active_court is not None else 20)),
        "外交": _clamp_score(diplomacy),
        "军功": _clamp_score(territorial * 45 + (liu_manpower / max(1, all_manpower)) * 30 + win_rate * 25),
    }


def _ending_timeline(db: GameDB) -> List[Dict[str, object]]:
    timeline: List[Dict[str, object]] = []
    for row in db.conn.execute(
        "SELECT turn, year, period, report FROM turn_reports ORDER BY turn"
    ).fetchall():
        timeline.append({"turn": int(row["turn"]), "year": int(row["year"]), "period": int(row["period"]), "kind": "月报", "summary": str(row["report"])})
    for row in db.conn.execute(
        "SELECT turn, year, period, title, status, summary FROM historical_chronicle ORDER BY turn, id"
    ).fetchall():
        timeline.append({"turn": int(row["turn"]), "year": int(row["year"]), "period": int(row["period"]), "kind": str(row["status"]), "title": str(row["title"]), "summary": str(row["summary"])})
    return sorted(timeline, key=lambda item: (int(item["turn"]), str(item["kind"])))


def _outcome(db: GameDB, state: GameState, status: str, summary: str, evidence: List[Dict[str, object]] | None = None) -> Dict[str, object]:
    scores = _ending_scores(db, state)
    average = round(sum(scores.values()) / len(scores))
    grade = "兴复之功" if average >= 85 else "建基之业" if average >= 65 else "守成未就" if average >= 45 else "大业中衰"
    review = (
        f"{summary}国史总评为「{grade}」。"
        f"其统一{scores['统一']}、名分{scores['名分']}、民生{scores['民生']}、将相{scores['将相']}、"
        f"外交{scores['外交']}、军功{scores['军功']}。论其成败，既须观克复郡国之广狭，"
        "亦当观汉室名义能否系人心、将相能否同德、军民能否久任战事。"
    )
    return {"status": status, "route": status, "summary": summary, "scores": scores, "grade": grade, "review": review, "evidence": evidence or [], "timeline": _ending_timeline(db)}


def _tick_counter(db: GameDB, state: GameState, field: str, condition: bool) -> int:
    if not condition:
        setattr(state, field, 0)
        return 0
    key = f"ending_counter_{field}_last_turn"
    try:
        last_turn = int(db.kv_get(key) or -1)
    except (TypeError, ValueError):
        last_turn = -1
    if last_turn != int(state.turn):
        setattr(state, field, int(getattr(state, field, 0)) + 1)
        db.kv_set(key, str(int(state.turn)))
    return int(getattr(state, field, 0))


def victory_status(db: GameDB, state: GameState) -> Dict[str, object]:
    """刘备线结局唯一硬判定入口；LLM 只负责对已定结果撰写史评。"""
    liu_bei = db.conn.execute(
        "SELECT status, status_reason FROM characters WHERE name='刘备'"
    ).fetchone()
    liu_dead = liu_bei is None or str(liu_bei["status"]) == "dead"
    historical_death = liu_dead and int(state.year) == 223 and int(state.period) >= 4 and (
        "历史卒" in str(liu_bei["status_reason"] if liu_bei else "")
        or "白帝" in str(liu_bei["status_reason"] if liu_bei else "")
    )
    if historical_death:
        return _outcome(db, state, ENDING_HISTORICAL_BAIDI, "章武三年四月，刘备于白帝安排后事，此线以历史托孤收束。")
    if liu_dead:
        return _outcome(db, state, ENDING_LIU_BEI_DEAD, "刘备于大业未成时身死，主公视角随之终结。")

    owned_regions = int(db.conn.execute(
        "SELECT COUNT(*) FROM regions WHERE controlled_by='liu_bei'"
    ).fetchone()[0] or 0)
    liu_manpower = int(db.conn.execute(
        "SELECT COALESCE(SUM(manpower),0) FROM armies WHERE owner_power='liu_bei' AND active=1"
    ).fetchone()[0] or 0)

    chengdu_owner = db.conn.execute(
        "SELECT controlled_by FROM regions WHERE id='chengdu'"
    ).fetchone()
    chengdu_held = chengdu_owner is not None and str(chengdu_owner["controlled_by"]) == "liu_bei"
    if chengdu_held:
        db.kv_set("chengdu_ever_liu_bei", "1")
    chengdu_was_held = db.kv_get("chengdu_ever_liu_bei") == "1"
    crisis_active = int(state.year) >= 214 and chengdu_was_held and not chengdu_held
    crisis_turns = _tick_counter(db, state, "chengdu_crisis_turns", crisis_active)
    if crisis_active:
        fallback_held = int(db.conn.execute(
            "SELECT COUNT(*) FROM regions WHERE id IN ('jiangzhou','yongan') AND controlled_by='liu_bei'"
        ).fetchone()[0] or 0)
        if fallback_held == 0 or crisis_turns >= 3:
            return _outcome(db, state, ENDING_YIZHOU_CORE_FALLEN, "成都危局未能挽回，江州与永安退路亦不足支撑益州核心。")

    collapse_turns = _tick_counter(
        db, state, "collapse_turns", owned_regions == 0 and liu_manpower < 3000
    )
    if collapse_turns >= 3:
        return _outcome(db, state, ENDING_REGIME_COLLAPSED, "刘备集团已无可控郡县，主力亦不足三千，军政体系连续三月无法恢复。")

    total_regions = int(db.conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0] or 0)
    other_regions = total_regions - owned_regions
    other_armies = int(db.conn.execute(
        "SELECT COUNT(*) FROM armies WHERE owner_power!='liu_bei' AND active=1 AND manpower>0"
    ).fetchone()[0] or 0)
    if total_regions > 0 and other_regions == 0 and other_armies == 0:
        return _outcome(db, state, ENDING_UNIFIED_VICTORY, "天下郡国尽归刘备，其他势力已无领土与现役军，兴复汉室的统一条件达成。", [{"kind": "领土", "detail": "全部地区归属刘备"}, {"kind": "军势", "detail": "无其他势力现役军"}])

    if int(state.year) > 223 or (int(state.year) == 223 and int(state.period) >= 4):
        controlled = {str(row["id"]) for row in db.conn.execute("SELECT id FROM regions WHERE controlled_by='liu_bei'").fetchall()}
        major_powers = int(db.conn.execute("SELECT COUNT(*) FROM powers WHERE id!='liu_bei' AND status NOT IN ('defeated','destroyed','collapsed','inactive')").fetchone()[0] or 0)
        stable = int(state.metrics.get("民望", 0)) >= 45 and int(state.metrics.get("军心", 0)) >= 45
        jingzhou_held = bool(controlled.intersection({"xiangyang", "jiangling", "jiangxia", "jingnan"}))
        yizhou_held = {"chengdu", "jiangzhou", "yongan"}.issubset(controlled)
        if yizhou_held and jingzhou_held and major_powers >= 2 and stable:
            return _outcome(db, state, ENDING_THREE_KINGDOMS, "益荆两地相维，魏吴等强权仍存，天下形成可守可进的三足均衡。", [{"kind":"领土","detail":"益州核心与荆州核心均在掌握"},{"kind":"天下","detail":f"仍有{major_powers}方主要外部势力"},{"kind":"国势","detail":"民望、军心稳定"}])
        if yizhou_held and not jingzhou_held and stable:
            return _outcome(db, state, ENDING_YIZHOU_GUARDIAN, "益州根本稳固而荆州不复，刘备集团选择偏安守成，保存汉家一隅。", [{"kind":"领土","detail":"成都、江州、永安稳定"},{"kind":"国势","detail":"民望、军心稳定"}])

        return _outcome(db, state, ENDING_REWRITTEN_223, "223年四月，刘备仍存而天下未统，此局以存活且未完成统一的改写历史收束。")
    db.conn.commit()
    return {"status": ENDING_ONGOING, "summary": "天下未定，刘备大业仍在推进。"}


# 地区/军队名称匹配实现在 matching.py；此处提供绑定 GameContent 的便捷封装。
from ming_sim.matching import army_aliases, compact_name, region_aliases  # noqa: E402,F401
from ming_sim.matching import match_army_id_from_text as _match_army
from ming_sim.matching import match_region_id_from_text as _match_region


def match_region_id_from_text(text: str) -> Optional[str]:
    return _match_region(text, _ctx().regions)


def match_army_id_from_text(text: str) -> Optional[str]:
    return _match_army(text, _ctx().armies)


def state_context(state: GameState) -> str:
    parts = []
    for key, value in state.metrics.items():
        if key in ECONOMY_ACCOUNTS:
            parts.append(f"{key}{format_money(value)}")
        else:
            parts.append(f"{key}{value}")
    return "，".join(parts)


def parse_json_dict(raw: str) -> Dict[str, int]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise LLMContractError(f"数据库中的数值变化 JSON 已损坏：{raw[:200]}") from error
    if not isinstance(data, dict):
        raise LLMContractError(f"数据库中的数值变化不是 object：{raw[:200]}")
    parsed: Dict[str, int] = {}
    for key, value in data.items():
        try:
            parsed[str(key)] = int(value)
        except (TypeError, ValueError) as error:
            raise LLMContractError(f"数据库中的数值变化字段不是整数：{key}={value}") from error
    return parsed


def format_metric_delta(delta: Dict[str, int]) -> str:
    if not delta:
        return "核心数值无明显变化"
    parts = []
    for key, value in delta.items():
        if key in ECONOMY_ACCOUNTS:
            parts.append(f"{key}{format_money_delta(value)}")
        else:
            sign = "+" if value > 0 else ""
            parts.append(f"{key}{sign}{value}")
    return "数值变化：" + "；".join(parts)


def character_context(character: Character) -> str:
    parts = [
        f"{character.name}，{character.office}，职位类型：{character.office_type}，派系：{character.faction}，"
        f"别名：{', '.join(character.aliases) or '无'}，"
        f"人物标签：{', '.join(character.personal_skills)}，"
        f"六维：武力{character.martial}/统率{character.leadership}/智略{character.intelligence}/"
        f"政治{character.politics}/外交{character.diplomacy}/魅力{character.charisma}，"
        f"动态人格：忠诚{character.loyalty}/节义{character.integrity}/野心{character.ambition}/"
        f"胆略{character.courage}/亲密度{character.closeness_to_liu_bei}，"
        f"核心等级{character.core_tier}，"
        f"风格：{character.style}",
    ]
    if character.summary:
        parts.append(f"人物简介：{character.summary}")
    if character.location:
        parts.append(f"当前所在：{character.location}")
    if character.status and character.status != "active":
        parts.append(f"当前状态：{character.status}")
    if character.power_id and character.power_id != "liu_bei":
        parts.append(f"所属势力：{character.power_id}")
    return "，".join(parts)


def character_context_with_db(character: Character, db: GameDB) -> str:
    parts = [character_context(character)]
    rows = db.conn.execute(
        """
        SELECT attribute, context, delta, reason, turn
        FROM character_attribute_logs
        WHERE character_name = ?
        ORDER BY id DESC LIMIT 5
        """,
        (character.name,),
    ).fetchall()
    if rows:
        recent = "；".join(
            f"T{row['turn']} {row['attribute']} {float(row['delta']):+g}（{row['context']}）"
            for row in rows
        )
        parts.append(f"最近属性影响：{recent}")
    closeness = int(character.closeness_to_liu_bei)
    relation = "亲密" if closeness >= 80 else "信任" if closeness >= 60 else "一般" if closeness >= 40 else "疏远"
    parts.append(f"与刘备关系：{relation}（亲密度{closeness}）")
    if character.status == "dead":
        action_range = "无；仅可作为历史记忆引用"
    elif character.status == "offstage":
        action_range = "不可直接召见或任命；仅可通过合理登场事件接触"
    elif character.power_id == "liu_bei":
        action_range = "可召见、议政、任命、领军或承办合理任务；高影响事实仍须规则核定"
    else:
        action_range = "可外交接触、侦察、劝降或作为事件对象；不可越权替刘备直接行动"
    parts.append(f"可行动范围：{action_range}")
    return "，".join(parts)


def event_context(event: Event) -> str:
    return (
        f"{event.title}。类型：{event.kind}。奏报：{event.summary} "
        f"紧急{event.urgency}，严重{event.severity}，可信{event.credibility}。"
        f"牵涉利益：{', '.join(event.interests)}。"
    )


def first_character() -> Character:
    try:
        return next(iter(_ctx().characters.values()))
    except StopIteration as error:
        raise SystemExit("characters.json 至少需要一个人物。") from error


def first_character_name() -> str:
    return first_character().name


def character_from_name(name: object) -> Character:
    value = str(name or "")
    character = _ctx().characters.get(value)
    if character is None:
        raise LLMContractError(f"人物未建档：{value}")
    return character


def match_minister_from_text(text: str, current: Optional[Character] = None) -> Optional[Character]:
    cleaned = text.strip()
    if not cleaned:
        return None
    matches = []
    for character in _ctx().characters.values():
        if current is not None and character.name == current.name:
            continue
        if (
            character.name in cleaned
            or character.office in cleaned
            or character.office_type in cleaned
            or character.faction in cleaned
            or any(alias in cleaned for alias in character.aliases)
        ):
            matches.append(character)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        exact = [character for character in matches if character.name in cleaned]
        if len(exact) == 1:
            return exact[0]
    return None
