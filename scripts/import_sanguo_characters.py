"""把两份审核通过的 Markdown 人物表机械转录为 content/characters.json。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


POWER_IDS = {
    "刘备": "liu_bei",
    "曹操": "cao_cao",
    "孙权": "sun_quan",
    "刘璋": "liu_zhang",
    "张鲁": "zhang_lu",
    "马腾": "ma_han",
    "韩玄": "cao_cao",
    "刘表": "liu_qi",
    "刘琦": "liu_qi",
    "公孙康": "gongsun_kang",
    "士燮": "shi_xie",
    "汉室": "cao_cao",
    "中立": "sun_quan",
}

LOCATION_IDS = {
    "夏口": "jiangxia",
    "荆州": "xiangyang",
    "成都": "chengdu",
    "长沙/荆南": "jingnan",
    "江陵": "jiangling",
    "邺": "ye",
    "长安": "changan",
    "襄阳": "xiangyang",
    "许昌/颍川": "xuchang",
    "宛城": "xuchang",
    "柳城": "liaodong",
    "河内": "luoyang",
    "合肥/庐江": "hefei",
    "建业": "jianye",
    "柴桑": "chaisang",
    "吴郡": "kuaiji",
    "海昏": "chaisang",
    "江州/巴郡": "jiangzhou",
    "永安/白帝": "yongan",
    "汉中": "hanzhong",
    "武威": "wuwei",
    "天水": "tianshui",
    "江夏": "jiangxia",
    "辽东": "liaodong",
    "交趾": "jiaozhi",
    "南海": "nanhai",
    "江东": "jianye",
}

LIUBEI_OLD_GUARD = {
    "刘备", "关羽", "张飞", "赵云", "孙乾", "简雍", "糜竺", "糜芳", "刘封", "陈到", "刘禅",
}
LIUBEI_JINGZHOU = {"诸葛亮", "庞统", "黄忠", "魏延", "马良", "蒋琬", "费祎"}
LIUBEI_YIZHOU = {"法正", "李严"}
CAO_RELATIVES = {"曹操", "曹丕", "曹仁", "夏侯惇", "夏侯渊"}
CAO_CIVIL = {"荀彧", "荀攸", "郭嘉", "贾诩", "程昱", "司马懿", "满宠"}
SUN_RELATIVES = {"孙权", "孙尚香"}
SUN_CIVIL = {"鲁肃", "诸葛瑾", "张昭"}
APPROVED_TRAITS = {
    "仁德", "武圣", "突击", "护卫", "神机", "水战", "水战熟练", "火攻", "守城", "攻城",
    "山地", "骑战", "西凉威望", "治政", "财政", "外交", "反间", "军纪", "统合", "守成",
}


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_abilities(path: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        cells = table_cells(line) if line.startswith("|") else []
        if len(cells) != 10 or cells[0] in {"人物", "---"} or not cells[2]:
            continue
        if not all(re.fullmatch(r"\d+", value) for value in cells[3:9]):
            continue
        debut = 0 if cells[2] in {"开局", "已故"} else int(cells[2])
        result.append(
            {
                "name": cells[0],
                "opening_affiliation": cells[1],
                "debut_year": debut,
                "martial": int(cells[3]),
                "leadership": int(cells[4]),
                "intelligence": int(cells[5]),
                "politics": int(cells[6]),
                "diplomacy": int(cells[7]),
                "charisma": int(cells[8]),
                "traits_text": cells[9],
                "section": section,
            }
        )
    return result


def parse_states(path: Path) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = table_cells(line) if line.startswith("|") else []
        if len(cells) != 10 or cells[0] in {"name", "---"}:
            continue
        if not all(re.fullmatch(r"\d+", value) for value in cells[1:6]):
            continue
        states[cells[0]] = {
            "loyalty": int(cells[1]),
            "integrity": int(cells[2]),
            "ambition": int(cells[3]),
            "courage": int(cells[4]),
            "closeness_to_liu_bei": int(cells[5]),
            "location_text": cells[6],
            "status": cells[7],
            "office": cells[8],
            "core_tier": cells[9],
        }
    return states


def faction_for(name: str, affiliation: str) -> str:
    if name in LIUBEI_OLD_GUARD:
        return "元从旧部"
    if name in LIUBEI_JINGZHOU:
        return "荆州士人"
    if name in LIUBEI_YIZHOU:
        return "益州本土士族"
    if affiliation == "刘备":
        return "军中将领"
    if affiliation == "曹操":
        if name in CAO_RELATIVES:
            return "曹魏宗亲"
        return "曹魏文臣" if name in CAO_CIVIL else "曹魏军将"
    if affiliation == "孙权":
        if name in SUN_RELATIVES:
            return "江东宗室"
        return "江东文臣" if name in SUN_CIVIL else "江东军将"
    return {
        "刘璋": "益州本土士族",
        "张鲁": "汉中道众",
        "马腾": "西凉集团",
        "韩玄": "荆南旧部",
        "刘表": "荆州旧部",
        "刘琦": "荆州旧部",
        "公孙康": "辽东集团",
        "士燮": "交州集团",
        "汉室": "汉室宫廷",
        "中立": "方外人物",
    }[affiliation]


def office_type_for(office: str) -> str:
    if any(word in office for word in ("军主", "之主", "太守", "益州牧", "天子", "诸侯")):
        return "君主"
    if any(word in office for word in ("统帅", "将领", "偏将", "守将", "宿将", "牙门将", "部将", "中军")):
        return "军政"
    if any(word in office for word in ("军师", "谋士", "谋臣")):
        return "军师"
    if any(word in office for word in ("使者", "说客", "外交")):
        return "外交"
    if any(word in office for word in ("皇后", "宗室", "世子", "继承人", "少主", "养子")):
        return "宗室"
    if office in {"已故", "异人", "隐居士人"}:
        return "在野"
    return "政务"


def mechanical_traits_for(source_traits: list[str], ability: dict[str, object]) -> list[str]:
    joined = "、".join(source_traits)
    selected = {trait for trait in source_traits if trait in APPROVED_TRAITS}
    keyword_traits = {
        "水军": "水战", "江防": "水战", "火攻": "火攻", "守备": "守城", "守城": "守城",
        "奇谋": "神机", "谋士": "神机", "骑": "骑战", "山地": "山地", "攻城": "攻城",
        "财政": "财政", "商贸": "财政", "治政": "治政", "内政": "治政", "外交": "外交",
        "使者": "外交", "辩才": "外交", "军纪": "军纪", "护卫": "护卫", "统合": "统合",
        "突击": "突击", "先登": "突击", "勇战": "突击", "夜袭": "突击", "斩将": "突击",
        "反间": "反间", "离间": "反间", "守成": "守成",
    }
    for keyword, trait in keyword_traits.items():
        if keyword in joined:
            selected.add(trait)
    if not selected:
        ranked = [
            (int(ability["politics"]), "治政"),
            (int(ability["diplomacy"]), "外交"),
            (int(ability["martial"]), "突击"),
            (int(ability["intelligence"]), "神机"),
            (int(ability["leadership"]), "守成"),
        ]
        selected.add(max(ranked)[1])
    return sorted(selected)


def build(abilities: list[dict[str, object]], states: dict[str, dict[str, object]]) -> dict[str, object]:
    ability_names = {str(item["name"]) for item in abilities}
    if ability_names != set(states):
        raise SystemExit(f"能力表与状态表人物不一致：能力独有={ability_names-set(states)}；状态独有={set(states)-ability_names}")
    if len(abilities) != 81:
        raise SystemExit(f"人物数量应为81，实际{len(abilities)}")

    characters: list[dict[str, object]] = []
    for index, ability in enumerate(abilities, 1):
        name = str(ability["name"])
        state = states[name]
        source_traits = [part.strip() for part in re.split(r"[、；;]", str(ability["traits_text"])) if part.strip()]
        if state["status"] == "dead":
            source_traits = [trait for trait in source_traits if trait not in {"已故", "不可登场"}]
        traits = mechanical_traits_for(source_traits, ability)
        six = [int(ability[key]) for key in ("martial", "leadership", "intelligence", "politics", "diplomacy", "charisma")]
        core_tier = str(state["core_tier"])
        location_text = str(state["location_text"])
        affiliation = str(ability["opening_affiliation"])
        character = {
            "name": name,
            "office": str(state["office"]),
            "office_type": office_type_for(str(state["office"])),
            "faction": faction_for(name, affiliation),
            "aliases": [name],
            "personal_skills": traits,
            "loyalty": int(state["loyalty"]),
            "ability": round(sum(six) / len(six)),
            "integrity": int(state["integrity"]),
            "ambition": int(state["ambition"]),
            "courage": int(state["courage"]),
            "closeness_to_liu_bei": int(state["closeness_to_liu_bei"]),
            "martial": int(ability["martial"]),
            "leadership": int(ability["leadership"]),
            "intelligence": int(ability["intelligence"]),
            "politics": int(ability["politics"]),
            "diplomacy": int(ability["diplomacy"]),
            "charisma": int(ability["charisma"]),
            "stewardship": int(ability["politics"]),
            "intrigue": int(ability["intelligence"]),
            "learning": int(ability["intelligence"]),
            "power_id": POWER_IDS[affiliation],
            "location": LOCATION_IDS[location_text],
            "status": str(state["status"]),
            "debut_year": int(ability["debut_year"]),
            "debut_month": 0,
            "core_tier": core_tier,
            "style": "半文半白",
            "summary": f"{state['office']}。演义定位：{'、'.join(source_traits) if source_traits else '历史记忆'}。",
            "portrait_id": f"sanguo/core_{index:03d}" if core_tier in {"S", "1", "2"} else "",
        }
        characters.append(character)

    faction_names = sorted({str(item["faction"]) for item in characters} | {"宗室"})
    factions = [
        {
            "name": name,
            "satisfaction": 45 if name == "宗室" else 55,
            "leverage": 65 if name == "宗室" else 50,
            "agenda": "维护刘氏宗亲、继承与封赏秩序。" if name == "宗室" else "依人物归属、名分与当前局势维护本集团利益。",
        }
        for name in faction_names
    ]
    return {"factions": factions, "characters": characters}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--abilities", type=Path, required=True)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(parse_abilities(args.abilities), parse_states(args.states))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
