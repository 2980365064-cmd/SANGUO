"""从审核路线与军队表生成三国 208 开局势力、地区、军队 JSON。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


POWER_DATA = [
    ("cao_cao", "曹操", "北方霸主", "曹操", "敌对", 95, 82, 95, 84, 82, "南下夺取荆州、压服孙刘并统一天下"),
    ("sun_quan", "孙权", "江东政权", "孙权", "潜在盟友", 82, 72, 78, 80, 86, "保全江东、控制长江并争夺荆州"),
    ("liu_bei", "刘备", "玩家政权", "刘备", "自身", 48, 78, 32, 86, 40, "联吴抗曹、取得立足之地并兴复汉室"),
    ("liu_qi", "刘琦", "荆州余部", "刘琦", "友好", 38, 65, 24, 48, 45, "守住江夏并延续刘表旧部"),
    ("liu_zhang", "刘璋", "益州政权", "刘璋", "中立", 62, 58, 55, 62, 78, "保全益州、抵御汉中与北方威胁"),
    ("zhang_lu", "张鲁", "汉中政权", "张鲁", "中立", 46, 62, 40, 70, 68, "守住汉中与阳平关、维系道众"),
    ("ma_han", "马腾／韩遂", "西凉联盟", "马腾", "中立", 54, 55, 50, 58, 55, "维持凉州部众并牵制曹操关中势力"),
    ("shi_xie", "士燮", "交州政权", "士燮", "观望", 30, 68, 28, 72, 66, "安抚交州、避免卷入中原大战"),
    ("gongsun_kang", "公孙康", "辽东政权", "公孙康", "观望", 34, 60, 35, 65, 60, "固守辽东并在曹氏与北方边地间周旋"),
]

CONTROLLER_BY_PROVINCE = {
    "司隶": "cao_cao", "冀州": "cao_cao", "兖州": "cao_cao", "豫州": "cao_cao",
    "徐州": "cao_cao", "青州": "cao_cao", "并州": "cao_cao",
    "凉州": "ma_han", "扬州": "sun_quan", "幽州": "gongsun_kang", "交州": "shi_xie",
}
CONTROLLER_BY_NODE = {
    "xiangyang": "cao_cao", "jiangling": "cao_cao", "jingnan": "cao_cao",
    "jiangxia": "liu_qi", "chengdu": "liu_zhang", "jiangzhou": "liu_zhang",
    "yongan": "liu_zhang", "hanzhong": "zhang_lu",
}

STATION_NODES = {
    "夏口": "jiangxia", "江陵": "jiangling", "襄阳": "xiangyang", "合肥/庐江": "hefei",
    "邺": "ye", "柴桑": "chaisang", "建业": "jianye", "成都": "chengdu",
    "江州/巴郡": "jiangzhou", "永安/白帝": "yongan", "汉中": "hanzhong",
    "武威": "wuwei", "天水": "tianshui", "江夏": "jiangxia", "辽东": "liaodong",
    "蓟": "ji", "交趾": "jiaozhi", "南海": "nanhai",
}
ARMY_POWERS = {
    "刘备": "liu_bei", "曹操": "cao_cao", "孙权": "sun_quan", "刘璋": "liu_zhang",
    "张鲁": "zhang_lu", "马韩": "ma_han", "刘琦": "liu_qi", "公孙康": "gongsun_kang", "士燮": "shi_xie",
}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def build_powers() -> dict[str, object]:
    return {
        "powers": [
            {
                "id": pid, "name": name, "kind": kind, "leader": leader, "stance": stance,
                "leverage": leverage, "satisfaction": satisfaction, "military_strength": military,
                "cohesion": cohesion, "supply": supply, "agenda": agenda,
                "status": "建安十三年赤壁前夕在局势力。", "last_action": "整军观势",
                "aliases": [name.replace("／", "/")],
            }
            for pid, name, kind, leader, stance, leverage, satisfaction, military, cohesion, supply, agenda in POWER_DATA
        ]
    }


def build_regions(routes_path: Path) -> dict[str, object]:
    nodes = json.loads(routes_path.read_text(encoding="utf-8"))["nodes"]
    regions: list[dict[str, object]] = []
    major = {"changan", "luoyang", "ye", "xuchang", "xiangyang", "jiangling", "jianye", "chengdu"}
    frontier = {"tongguan", "jiangxia", "hefei", "yongan", "hanzhong", "tianshui", "shangdang", "ji"}
    for index, node in enumerate(nodes):
        node_id = str(node["id"])
        province = str(node["province"])
        owner = CONTROLLER_BY_NODE.get(node_id, CONTROLLER_BY_PROVINCE.get(province))
        if owner is None:
            raise SystemExit(f"节点 {node_id} 未配置208归属")
        population = 260 if node_id in major else 150 if node_id not in frontier else 110
        farmland = population * 4
        grain_output = round(population * (2.7 if province in {"益州", "荆州", "扬州"} else 2.2))
        granary = round(grain_output * (0.9 if node_id in major else 0.65))
        gentry_support = {"liu_qi": 62, "liu_zhang": 58, "sun_quan": 64, "cao_cao": 60}.get(owner, 55)
        security = 70 if node_id in major else 60
        fortification = 78 if node_id in frontier else 62 if node_id in major else 48
        transport = 72 if province in {"司隶", "兖州", "豫州", "扬州"} else 52
        revolt_risk = max(8, 45 - security // 2)
        tax = max(2, round(population / 45))
        commerce = max(2, round(population / 35))
        fiscal = {
            "population": population,
            "farmland": farmland,
            "grain_output": grain_output,
            "granary": granary,
            "tax": tax,
            "commerce": commerce,
            "gentry_support": gentry_support,
            "security": security,
            "fortification": fortification,
            "transport": transport,
            "revolt_risk": revolt_risk,
            "grain_stock": granary,
            "guan_min_tian": farmland,
            "huang_tian": 0,
            "wang_tian": 0,
            "salt_tax": 0,
            "commerce_tax": commerce,
            "corruption": 100 - gentry_support,
            "tian_fu_li": 100,
            "liao_xiang_li": 0,
        }
        regions.append(
            {
                "id": node_id, "name": str(node["name"]), "kind": province,
                "population": population, "public_support": 56, "unrest": revolt_risk,
                "natural_disaster": "无重大灾害", "human_disaster": "战乱压力" if node_id in frontier else "局势尚稳",
                "registered_land": farmland, "hidden_land": round(farmland * 0.16),
                "tax_per_turn": tax, "gentry_resistance": 100 - gentry_support,
                "military_pressure": 65 if node_id in frontier else 35,
                "status": f"{node['name']}为{province}战略节点。", "controlled_by": owner, "fiscal": fiscal,
            }
        )
    return {"meta": {"scenario_id": "sanguo_liubei_208", "node_count": len(regions)}, "regions": regions}


def _composition(text: str, manpower: int) -> dict[str, int]:
    if "水军" in text or "江防" in text:
        return {"水军": round(manpower * 0.7), "步卒": manpower - round(manpower * 0.7)}
    if "骑" in text:
        return {"骑兵": round(manpower * 0.6), "步卒": manpower - round(manpower * 0.6)}
    return {"步卒": round(manpower * 0.7), "弓弩": manpower - round(manpower * 0.7)}


def build_armies(army_table: Path) -> dict[str, object]:
    armies: list[dict[str, object]] = []
    for line in army_table.read_text(encoding="utf-8").splitlines():
        cells = _cells(line) if line.startswith("|") else []
        if len(cells) != 10 or cells[0] in {"势力", "---"} or not re.fullmatch(r"[\d,]+", cells[4]):
            continue
        army_id, name = [part.strip() for part in cells[1].split("／", 1)]
        manpower = int(cells[4].replace(",", ""))
        supply_turns = int(cells[5])
        specialties = [part.strip() for part in re.split(r"[、；;，]", cells[9]) if part.strip()]
        owner = ARMY_POWERS[cells[0]]
        mobility = 78 if any(key in cells[9] for key in ("机动", "快速", "骑战", "追击")) else 66 if "水" in cells[9] else 55
        armies.append(
            {
                "id": army_id, "name": name, "station": cells[3], "station_node": STATION_NODES[cells[3]],
                "theater": cells[3], "commander": cells[2], "controller": cells[0],
                "troop_type": specialties[0], "troop_composition": _composition(cells[9], manpower),
                "manpower": manpower, "maintenance_per_turn": max(1, round(manpower / 5000)),
                "supply_turns": supply_turns, "supply": supply_turns * 20,
                "morale": int(cells[8]), "training": int(cells[6]), "equipment": int(cells[7]),
                "arrears": 0, "mobility": mobility, "loyalty": int(cells[8]),
                "fatigue": 0, "experience": max(20, int(cells[6]) - 10),
                "discipline": int(cells[6]), "hazard_turns": 0, "specialties": specialties,
                "status": cells[9], "owner_power": owner,
                "arms": (
                    [
                        {"troop_type": "骑兵", "weapon": "三眼铳", "qty": 4000},
                        {"troop_type": "步卒", "weapon": "火铳", "qty": 15000},
                    ]
                    if army_id == "cao_main" else []
                ),
            }
        )
    if len(armies) != 25:
        raise SystemExit(f"军队数量应为25，实际{len(armies)}")
    if sum(a["manpower"] for a in armies if a["owner_power"] == "liu_bei") != 22_000:
        raise SystemExit("刘备三军兵力不是22000")
    if sum(a["manpower"] for a in armies if a["owner_power"] == "cao_cao") != 128_000:
        raise SystemExit("曹操可调度军兵力不是128000")
    return {"meta": {"scenario_id": "sanguo_liubei_208", "army_count": 25}, "armies": armies}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=Path, required=True)
    parser.add_argument("--armies", type=Path, required=True)
    parser.add_argument("--content-dir", type=Path, required=True)
    args = parser.parse_args()
    outputs = {
        "powers.json": build_powers(),
        "regions.json": build_regions(args.routes),
        "armies.json": build_armies(args.armies),
    }
    for filename, payload in outputs.items():
        (args.content_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
