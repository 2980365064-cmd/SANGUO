"""剧本编辑助手的工具集：直接增删改剧本目录里的 JSON 文件。L5。

镜像 tools.py 的结构：嵌套函数（docstring=LLM schema，返回人话状态串），闭包持 scenario_dir。
工具本身就是改动（read-modify-write 盘上 JSON），不返回哨兵；调用方一轮跑完回读整份剧本刷预览。

校验两级：每工具只做字段级 sanity（类型/枚举/personal_skills 非 null），失败返回中文错误串、不写盘，
让 agent 自纠；跨文件引用一致性延到激活时的全 loader 校验（_validate_scenario_dir）。
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

_FILES = {
    "characters": "characters.json",
    "events": "events.json",
    "seed_events": "seed_events.json",
}
_EVENT_TYPES = ("situation", "node", "ending")
_EDIT_TOOL_NAMES = {
    "upsert_character", "delete_character",
    "upsert_faction", "delete_faction",
    "upsert_event", "delete_event",
}


def _path(scenario_dir: str, file_key: str) -> str:
    return os.path.join(scenario_dir, _FILES[file_key])


def _load(scenario_dir: str, file_key: str):
    """读 JSON，缺文件容错：characters→{factions:[],characters:[]}，events/seed→[]。"""
    path = _path(scenario_dir, file_key)
    if not os.path.isfile(path):
        return {"factions": [], "characters": []} if file_key == "characters" else []
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump(scenario_dir: str, file_key: str, data) -> None:
    """原子写：写 .tmp 再 os.replace，避免半写坏档。"""
    path = _path(scenario_dir, file_key)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _coerce_int(value, default: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError


def _parse_json_list(raw: str, field: str) -> List[str]:
    """把 JSON 数组字符串解析成 str list；空/None→[]；非数组报错。"""
    if raw is None or str(raw).strip() in ("", "[]", "null"):
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # 容错：当作顿号/逗号分隔
        return [x.strip() for x in str(raw).replace("，", ",").replace("、", ",").split(",") if x.strip()]
    if not isinstance(parsed, list):
        raise ValueError(f"{field} 必须是 JSON 数组，如 [\"甲\",\"乙\"]")
    return [str(x) for x in parsed]


def _parse_gate(raw: str, field: str) -> Optional[dict]:
    """门槛 DSL：JSON 对象字符串。空→None（不写该字段）。非对象报错。"""
    if raw is None or str(raw).strip() in ("", "{}", "null"):
        return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ValueError(f"{field} 不是合法 JSON：{raw!r}")
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} 必须是 JSON 对象（门槛条件树）")
    return parsed


def build_scenario_editor_tools(scenario_dir: str) -> list:
    """构造剧本编辑工具列表，闭包持 scenario_dir。"""

    def upsert_character(
        name: str, office: str, office_type: str, faction: str,
        loyalty: int, ability: int, integrity: int, courage: int,
        style: str = "", power_id: str = "ming",
        personal_skills_json: str = "[]", aliases_json: str = "[]",
        diplomacy=None, martial=None, stewardship=None, intrigue=None, learning=None,
        location: str = "", birth_year=None, status: str = "", summary: str = "",
        rank: str = "", debut_year=None, debut_month=None,
        historical_death_year=None, historical_death_month=None,
    ) -> str:
        """新增或修改一名人物（按姓名定位，已存在则覆盖）。loyalty/ability/integrity/courage 为
        0–100 整数。faction 须是已存在的派系名（不存在请先 upsert_faction）。power_id 明臣填 ming。
        personal_skills_json/aliases_json 是 JSON 数组字符串如 ["制度名分"]，没有填 []，绝不能 null。
        diplomacy/martial/stewardship/intrigue/learning 为 0–100 整数，省略则回落 ability。
        rank 品秩/位号（如后宫「皇后/贵妃/妃」，外朝可留空）。
        debut_year/debut_month 登场年月（公历，0 或省略=开局即在场；填了则到该年月才登场）。
        historical_death_year/historical_death_month 史实卒年月（0 或省略=不自动离场；填了则到该年月自动离场）。"""
        nm = (name or "").strip()
        if not nm:
            return "人物写入失败：姓名为空。"
        off = (office or "").strip()
        otype = (office_type or "").strip()
        fac = (faction or "").strip()
        if not off or not otype or not fac:
            return "人物写入失败：office / office_type / faction 均不可为空。"
        try:
            loy = _coerce_int(loyalty); abi = _coerce_int(ability)
            inte = _coerce_int(integrity); cou = _coerce_int(courage)
            if None in (loy, abi, inte, cou):
                return "人物写入失败：loyalty/ability/integrity/courage 必须是整数。"
            skills = _parse_json_list(personal_skills_json, "personal_skills_json")
            aliases = _parse_json_list(aliases_json, "aliases_json")
        except ValueError as e:
            return f"人物写入失败：{e}"
        rec = {
            "name": nm, "office": off, "office_type": otype, "faction": fac,
            "loyalty": loy, "ability": abi, "integrity": inte, "courage": cou,
            "style": (style or "").strip() or "持重", "power_id": (power_id or "ming").strip(),
            "personal_skills": skills, "aliases": aliases,
        }
        try:
            for k, v in (("diplomacy", diplomacy), ("martial", martial), ("stewardship", stewardship),
                         ("intrigue", intrigue), ("learning", learning), ("birth_year", birth_year),
                         ("debut_year", debut_year), ("debut_month", debut_month),
                         ("historical_death_year", historical_death_year),
                         ("historical_death_month", historical_death_month)):
                iv = _coerce_int(v)
                if iv is not None:
                    rec[k] = iv
        except ValueError:
            return "人物写入失败：五维/生年/登场年月/卒年月须为整数。"
        if (location or "").strip():
            rec["location"] = location.strip()
        if (status or "").strip():
            rec["status"] = status.strip()
        if (summary or "").strip():
            rec["summary"] = summary.strip()
        if (rank or "").strip():
            rec["rank"] = rank.strip()

        data = _load(scenario_dir, "characters")
        chars = data.setdefault("characters", [])
        for i, c in enumerate(chars):
            if str(c.get("name")) == nm:
                chars[i] = rec
                _dump(scenario_dir, "characters", data)
                return f"已更新人物「{nm}」（{off}）。"
        chars.append(rec)
        _dump(scenario_dir, "characters", data)
        return f"已新增人物「{nm}」（{off}）。"

    def delete_character(name: str) -> str:
        """删除一名人物（按姓名）。"""
        nm = (name or "").strip()
        data = _load(scenario_dir, "characters")
        chars = data.get("characters", [])
        new = [c for c in chars if str(c.get("name")) != nm]
        if len(new) == len(chars):
            return f"未找到人物「{nm}」，无改动。"
        data["characters"] = new
        _dump(scenario_dir, "characters", data)
        return f"已删除人物「{nm}」。"

    def upsert_faction(name: str, satisfaction: int = 50, leverage: int = 50, agenda: str = "") -> str:
        """新增或修改一个派系（按派系名）。satisfaction/leverage 为 0–100 整数，agenda 为诉求。"""
        nm = (name or "").strip()
        if not nm:
            return "派系写入失败：派系名为空。"
        try:
            sat = _coerce_int(satisfaction, 50); lev = _coerce_int(leverage, 50)
        except ValueError:
            return "派系写入失败：satisfaction/leverage 必须是整数。"
        rec = {"name": nm, "satisfaction": sat, "leverage": lev, "agenda": (agenda or "").strip() or "维持现状"}
        data = _load(scenario_dir, "characters")
        facs = data.setdefault("factions", [])
        for i, f in enumerate(facs):
            if str(f.get("name")) == nm:
                facs[i] = rec
                _dump(scenario_dir, "characters", data)
                return f"已更新派系「{nm}」。"
        facs.append(rec)
        _dump(scenario_dir, "characters", data)
        return f"已新增派系「{nm}」。"

    def delete_faction(name: str) -> str:
        """删除一个派系（按派系名）。注意：若仍有人物引用该派系，激活时会校验不过，记得改那些人物的 faction。"""
        nm = (name or "").strip()
        data = _load(scenario_dir, "characters")
        facs = data.get("factions", [])
        new = [f for f in facs if str(f.get("name")) != nm]
        if len(new) == len(facs):
            return f"未找到派系「{nm}」，无改动。"
        data["factions"] = new
        _dump(scenario_dir, "characters", data)
        refs = [c.get("name") for c in data.get("characters", []) if str(c.get("faction")) == nm]
        warn = f"（注意：{('、'.join(map(str, refs)))} 仍引用此派系，请改其 faction）" if refs else ""
        return f"已删除派系「{nm}」。{warn}"

    def upsert_event(
        file: str, id: str, title: str, kind: str, summary: str,
        urgency: int, severity: int, credibility: int, event_type: str,
        interests_json: str = "[]", audiences_json: str = "[]",
        resolve_condition: str = "", fail_condition: str = "",
        trigger_year=None, trigger_month=None,
        trigger_gate: str = "", require: str = "",
        auto_trigger=None, region_hint: str = "", tags_json: str = "[]",
        precondition: str = "",
        is_historical=None, trigger_end_year=None, trigger_end_month=None,
        bar_value=None, bar_good_meaning: str = "", bar_bad_meaning: str = "",
        stage_text: str = "", inertia=None,
        ongoing_effects_json: str = "", effect_on_resolve_json: str = "", effect_on_fail_json: str = "",
    ) -> str:
        """新增或修改一个事件（按 id 定位）。file 为 "events"（历史事件，用 trigger_year/month）或
        "seed_events"（随机事件，用 trigger_gate）。urgency/severity/credibility 为 0–100 整数。
        event_type 只能是 situation/node/ending。interests_json/audiences_json/tags_json 是 JSON 数组字符串。
        trigger_gate/require 是门槛 DSL 的 JSON 对象字符串（可留空）。
        precondition 是触发前提的人话说明，喂推演由 LLM 判定（当叙事背景，并据盘面判结果烈度/走向，可列结果分档）；
        它不走程序求值——决定「能不能触发」的程序闸是 require（历史事件）/trigger_gate（随机事件）。
        is_historical：是否史实锚定情势（true/false，省略=按 trigger_year>0 自动推断）。
        trigger_end_year/trigger_end_month：候选窗口结束年月（0=不设上限）。
        bar_value 是 situation 转 issue 时进度条初值 0–100；bar_good_meaning/bar_bad_meaning 是进度条满端/见底端的含义（不是当前状态）。
        stage_text 是立项后的阶段叙事文案（空=用 summary）。inertia 是每月惯性漂移量（0=不漂）。
        ongoing_effects_json/effect_on_resolve_json/effect_on_fail_json：过程/达成/崩坏时的结构化效果，
        JSON 对象字符串，形如 {"metrics":{"国库":-10},"economy":[{"account":"国库","delta":-10,"category":"...","reason":"..."}]}；
        effect_on_resolve 还可带 "buildings":[{"action":"create","region_id":"guangxi","name":"广西官银矿","category":"财政","output_metric":"国库","output_amount":200,"status":"..."}] 在达成时新建建筑（持续月产）。"""
        fk = (file or "").strip()
        if fk not in ("events", "seed_events"):
            return "事件写入失败：file 须为 events 或 seed_events。"
        eid = (id or "").strip()
        ttl = (title or "").strip()
        if not eid or not ttl:
            return "事件写入失败：id 与 title 不可为空。"
        etype = (event_type or "").strip()
        if etype not in _EVENT_TYPES:
            return f"事件写入失败：event_type 须为 {'/'.join(_EVENT_TYPES)} 之一（收到 {etype!r}）。"
        try:
            urg = _coerce_int(urgency); sev = _coerce_int(severity); cred = _coerce_int(credibility)
            if None in (urg, sev, cred):
                return "事件写入失败：urgency/severity/credibility 必须是整数。"
            interests = _parse_json_list(interests_json, "interests_json")
            audiences = _parse_json_list(audiences_json, "audiences_json")
            tags = _parse_json_list(tags_json, "tags_json")
            gate = _parse_gate(trigger_gate, "trigger_gate")
            req = _parse_gate(require, "require")
            ty = _coerce_int(trigger_year); tm = _coerce_int(trigger_month)
            tey = _coerce_int(trigger_end_year); tem = _coerce_int(trigger_end_month)
            bv = _coerce_int(bar_value); inert = _coerce_int(inertia)
            ongoing = _parse_gate(ongoing_effects_json, "ongoing_effects_json")
            on_resolve = _parse_gate(effect_on_resolve_json, "effect_on_resolve_json")
            on_fail = _parse_gate(effect_on_fail_json, "effect_on_fail_json")
        except ValueError as e:
            return f"事件写入失败：{e}"
        if not interests:
            interests = ["朝廷"]
        if not audiences:
            audiences = []
        rec = {
            "id": eid, "title": ttl, "kind": (kind or "").strip() or "朝政",
            "summary": (summary or "").strip(), "urgency": urg, "severity": sev,
            "credibility": cred, "event_type": etype,
            "interests": interests, "audiences": audiences,
        }
        if (resolve_condition or "").strip():
            rec["resolve_condition"] = resolve_condition.strip()
        if (fail_condition or "").strip():
            rec["fail_condition"] = fail_condition.strip()
        if (region_hint or "").strip():
            rec["region_hint"] = region_hint.strip()
        if (precondition or "").strip():
            rec["precondition"] = precondition.strip()
        if tags:
            rec["tags"] = tags
        if ty:
            rec["trigger_year"] = ty
        if tm:
            rec["trigger_month"] = tm
        if tey:
            rec["trigger_end_year"] = tey
        if tem:
            rec["trigger_end_month"] = tem
        if gate is not None:
            rec["trigger_gate"] = gate
        if req is not None:
            rec["require"] = req
        if auto_trigger is not None:
            rec["auto_trigger"] = bool(auto_trigger) if not isinstance(auto_trigger, str) else auto_trigger.strip().lower() in ("1", "true", "是", "yes")
        if is_historical is not None:
            rec["is_historical"] = bool(is_historical) if not isinstance(is_historical, str) else is_historical.strip().lower() in ("1", "true", "是", "yes")
        if bv:
            rec["bar_value"] = bv
        if (bar_good_meaning or "").strip():
            rec["bar_good_meaning"] = bar_good_meaning.strip()
        if (bar_bad_meaning or "").strip():
            rec["bar_bad_meaning"] = bar_bad_meaning.strip()
        if (stage_text or "").strip():
            rec["stage_text"] = stage_text.strip()
        if inert:
            rec["inertia"] = inert
        if ongoing is not None:
            rec["ongoing_effects"] = ongoing
        if on_resolve is not None:
            rec["effect_on_resolve"] = on_resolve
        if on_fail is not None:
            rec["effect_on_fail"] = on_fail

        data = _load(scenario_dir, fk)
        if not isinstance(data, list):
            data = []
        for i, ev in enumerate(data):
            if str(ev.get("id")) == eid:
                data[i] = rec
                _dump(scenario_dir, fk, data)
                return f"已更新{('随机' if fk == 'seed_events' else '历史')}事件「{ttl}」（{eid}）。"
        data.append(rec)
        _dump(scenario_dir, fk, data)
        return f"已新增{('随机' if fk == 'seed_events' else '历史')}事件「{ttl}」（{eid}）。"

    def delete_event(file: str, id: str) -> str:
        """删除一个事件。file 为 events 或 seed_events，id 为事件标识。"""
        fk = (file or "").strip()
        if fk not in ("events", "seed_events"):
            return "删除失败：file 须为 events 或 seed_events。"
        eid = (id or "").strip()
        data = _load(scenario_dir, fk)
        if not isinstance(data, list):
            data = []
        new = [ev for ev in data if str(ev.get("id")) != eid]
        if len(new) == len(data):
            return f"未找到事件「{eid}」，无改动。"
        _dump(scenario_dir, fk, new)
        return f"已删除事件「{eid}」。"

    def list_current(section: str = "all") -> str:
        """查看当前剧本里已有什么。section 为 all/factions/characters/events/seed_events/summary。
        返回紧凑文本索引（名字/id/标题+计数），用于在改动前确认现状。"""
        sec = (section or "all").strip()
        chars_data = _load(scenario_dir, "characters")
        facs = chars_data.get("factions", [])
        chars = chars_data.get("characters", [])
        events = _load(scenario_dir, "events") or []
        seeds = _load(scenario_dir, "seed_events") or []
        if sec == "summary":
            return f"派系 {len(facs)}、人物 {len(chars)}、历史事件 {len(events)}、随机事件 {len(seeds)}。"
        parts = []
        if sec in ("all", "factions"):
            parts.append("派系：" + ("、".join(str(f.get("name")) for f in facs) or "（无）"))
        if sec in ("all", "characters"):
            parts.append("人物：" + ("、".join(f"{c.get('name')}({c.get('faction')})" for c in chars) or "（无）"))
        if sec in ("all", "events"):
            parts.append("历史事件：" + ("；".join(f"{e.get('id')}:{e.get('title')}" for e in events) or "（无）"))
        if sec in ("all", "seed_events"):
            parts.append("随机事件：" + ("；".join(f"{e.get('id')}:{e.get('title')}" for e in seeds) or "（无）"))
        return "\n".join(parts)

    def validate_now() -> str:
        """对当前整套剧本跑游戏的加载校验，确认能否被游戏正常加载。改完想确认时调用。"""
        # 延迟导入避免环：scenario_active(L1) + content loaders(L2)。
        from ming_sim import scenario_active
        from ming_sim.content import load_character_content, load_event_content
        with scenario_active.override(scenario_dir):
            try:
                if os.path.isfile(_path(scenario_dir, "characters")):
                    load_character_content()
                if os.path.isfile(_path(scenario_dir, "events")):
                    load_event_content("events.json")
                if os.path.isfile(_path(scenario_dir, "seed_events")):
                    load_event_content("seed_events.json")
            except SystemExit as exc:
                return f"校验未过：{exc}"
        return "校验通过：当前剧本可被游戏正常加载。"

    return [
        upsert_character, delete_character,
        upsert_faction, delete_faction,
        upsert_event, delete_event,
        list_current, validate_now,
    ]
