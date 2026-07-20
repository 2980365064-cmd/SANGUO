"""把审核后的 81 人首批名单扩展为 140 人完整首发名单。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHARACTERS_PATH = ROOT / "content" / "characters.json"
FAMILIES_PATH = ROOT / "content" / "families.json"


# name, power, location, debut, status, office, office_type, faction, traits,
# six abilities, five personality values, core tier, short positioning
ROWS = [
    ("阎圃","zhang_lu","hanzhong",208,"active","张鲁功曹","政务","汉中道众",["外交","治政"],(28,48,84,82,86,72),(86,82,38,58,38),"2","汉中政务与劝降中枢"),
    ("杨任","zhang_lu","hanzhong",208,"active","汉中守将","军政","汉中道众",["守城","山地"],(78,76,62,42,42,60),(90,82,42,82,20),"2","汉中山地守将"),
    ("昌奇","zhang_lu","hanzhong",208,"active","关隘副将","军政","汉中道众",["守城"],(66,68,54,40,38,52),(82,70,48,68,18),"3","阳平关候补守将"),
    ("公孙恭","gongsun_kang","liaodong",208,"active","辽东宗室","宗室","辽东集团",["守成","外交"],(30,48,66,70,72,62),(84,66,58,48,12),"2","辽东继承与对外联络"),
    ("柳毅","gongsun_kang","ji",208,"active","辽东守将","军政","辽东集团",["守城","骑战"],(72,74,60,48,46,58),(86,72,48,74,10),"3","辽东南线守将"),
    ("韩忠","gongsun_kang","liaodong",208,"active","辽东长史","政务","辽东集团",["治政"],(34,46,68,76,62,58),(82,70,42,52,10),"3","辽东地方治理"),
    ("士武","shi_xie","jiaozhi",208,"active","交州军政官","军政","交州集团",["军纪","山地"],(64,68,60,66,58,64),(88,76,42,66,24),"3","交州军政与边地守备"),
    ("士徽","shi_xie","jiaozhi",210,"offstage","交州宗室","宗室","交州集团",["突击"],(70,66,54,48,50,62),(78,58,76,72,18),"2","交州继承与野心线"),
    ("桓治","shi_xie","jiaozhi",208,"active","交州从事","政务","交州集团",["治政","外交"],(24,38,72,80,76,64),(86,78,34,48,22),"3","交州文治与外交"),
    ("文聘","liu_qi","jiangxia",208,"active","江夏守将","军政","荆州旧部",["守城","军纪"],(82,84,72,62,58,70),(92,86,40,78,42),"2","江夏独立守备统帅"),
    ("王威","liu_qi","jiangxia",208,"active","荆州旧将","军政","荆州旧部",["守城"],(70,68,58,52,50,60),(88,82,38,70,40),"3","刘琦麾下候补将领"),
    ("伊籍","liu_qi","xiangyang",209,"offstage","荆州从事","外交","荆州士人",["外交","治政"],(22,38,78,82,88,76),(86,84,34,54,62),"3","荆州士人联络与外交"),
    ("廖化","liu_qi","xiangyang",209,"offstage","荆州部将","军政","荆州旧部",["突击","山地"],(78,76,66,52,48,66),(90,88,40,82,48),"2","蜀汉长线将领"),
    ("周仓","liu_qi","jiangxia",209,"offstage","关羽部将","军政","荆州旧部",["护卫","水战"],(86,72,52,38,40,68),(96,92,24,88,82),"2","关羽护卫与水军副将"),
    ("关平","liu_bei","jiangxia",208,"active","关羽副将","军政","元从旧部",["突击","水战"],(84,78,60,46,48,72),(96,90,36,82,90),"2","关羽军副将"),
    ("马谡","liu_qi","xiangyang",214,"offstage","荆州士人","军师","荆州士人",["神机"],(32,62,86,72,68,70),(84,70,62,68,54),"2","谋略出众但临阵风险较高"),
    ("王平","cao_cao","hanzhong",215,"offstage","曹军部曲将","军政","曹魏军将",["山地","军纪"],(72,82,78,60,54,68),(82,86,34,76,28),"2","汉中山地与营垒将领"),
    ("孟达","liu_zhang","chengdu",211,"offstage","益州部将","军政","益州本土士族",["攻城","外交"],(72,76,76,64,70,68),(68,56,78,72,32),"2","上庸经营与反复风险"),
    ("霍峻","liu_bei","jiangxia",208,"active","偏将","军政","元从旧部",["守城","军纪"],(72,82,70,58,52,66),(94,90,28,80,72),"2","孤城坚守名将"),
    ("邓芝","liu_zhang","chengdu",214,"offstage","益州从事","外交","益州本土士族",["外交","治政"],(26,42,82,80,92,76),(90,88,30,62,44),"3","吴蜀外交与政务"),
    ("董允","liu_zhang","chengdu",214,"offstage","益州士人","政务","益州本土士族",["治政","守成"],(20,36,78,90,76,72),(94,94,24,54,38),"3","宫府直谏与内政"),
    ("杨仪","liu_qi","xiangyang",209,"offstage","荆州士人","政务","荆州士人",["治政","财政"],(22,42,84,86,66,58),(78,60,74,48,36),"2","军政文书与后勤"),
    ("向朗","liu_qi","xiangyang",209,"offstage","荆州从事","政务","荆州士人",["治政"],(26,44,76,84,70,68),(88,84,34,52,50),"3","荆州与益州政务衔接"),
    ("诸葛均","liu_qi","xiangyang",210,"offstage","荆州士人","在野","荆州士人",["治政"],(18,30,72,74,68,66),(82,80,28,42,70),"3","诸葛氏家族支线"),
    ("马忠","liu_zhang","chengdu",214,"offstage","益州郡吏","军政","益州本土士族",["山地","军纪"],(70,78,72,66,56,66),(90,84,34,72,40),"3","南中与山地治理将领"),
    ("张嶷","liu_zhang","jiangzhou",214,"offstage","巴郡士人","军政","益州本土士族",["山地","治政"],(76,80,74,68,54,70),(92,88,32,78,38),"3","山地平乱与地方治理"),
    ("吴班","liu_zhang","chengdu",214,"offstage","益州将门","军政","益州本土士族",["突击","军纪"],(80,78,62,50,50,66),(86,78,48,78,34),"3","益州将门与东征将领"),
    ("曹洪","cao_cao","ye",208,"active","宗亲大将","军政","曹魏宗亲",["骑战","统合"],(84,82,62,48,54,70),(96,74,52,82,12),"2","曹氏宗亲机动将领"),
    ("曹彰","cao_cao","ye",208,"active","曹操之子","宗室","曹魏宗亲",["突击","骑战"],(92,84,56,42,46,76),(92,72,66,90,10),"2","宗室勇将与继承竞争"),
    ("曹植","cao_cao","ye",208,"active","曹操之子","宗室","曹魏宗亲",["外交"],(20,34,82,76,78,90),(84,76,72,46,16),"2","文名与继承竞争"),
    ("曹真","cao_cao","ye",208,"active","虎豹骑将领","军政","曹魏宗亲",["骑战","军纪"],(84,86,72,58,54,72),(94,82,46,82,10),"2","曹魏宗亲后继统帅"),
    ("曹休","cao_cao","hefei",208,"active","宗亲偏将","军政","曹魏宗亲",["骑战","守城"],(82,82,68,56,52,68),(94,78,48,78,10),"2","曹魏东线宗亲将领"),
    ("夏侯尚","cao_cao","ye",208,"active","宗亲偏将","军政","曹魏宗亲",["突击"],(78,78,70,56,54,68),(92,76,50,76,10),"3","曹魏后继宗亲将领"),
    ("李典","cao_cao","hefei",208,"active","合肥守将","军政","曹魏军将",["守城","军纪"],(78,82,78,64,56,72),(94,86,34,70,16),"2","合肥守备与协同"),
    ("庞德","ma_han","wuwei",211,"offstage","西凉将领","军政","西凉集团",["突击","骑战"],(94,86,68,42,46,72),(92,90,38,92,30),"2","西凉勇将与襄樊死战"),
    ("华歆","cao_cao","xuchang",208,"active","尚书","政务","曹魏文臣",["外交","守成"],(18,34,82,88,86,72),(88,58,62,42,22),"3","朝廷政务与禅代推动"),
    ("陈群","cao_cao","xuchang",208,"active","司空西曹掾","政务","曹魏文臣",["治政","守成"],(18,38,84,94,80,76),(94,82,40,46,20),"2","法制与士族官僚"),
    ("刘晔","cao_cao","xuchang",208,"active","曹操谋臣","军师","曹魏文臣",["神机","攻城"],(28,54,90,80,74,70),(88,70,48,62,24),"2","军略与器械谋划"),
    ("蒋济","cao_cao","hefei",208,"active","扬州别驾","政务","曹魏文臣",["治政","守城"],(28,52,82,84,72,68),(90,78,42,58,18),"3","淮南政务与守备"),
    ("毛玠","cao_cao","xuchang",208,"active","东曹掾","政务","曹魏文臣",["治政","军纪"],(24,44,78,88,68,64),(94,90,30,52,18),"3","选官与军政纪律"),
    ("钟繇","cao_cao","changan",208,"active","司隶校尉","政务","曹魏文臣",["治政","外交"],(22,48,82,92,82,78),(94,88,32,54,24),"2","关中治理与名士网络"),
    ("王朗","cao_cao","xuchang",208,"active","谏议大夫","外交","曹魏文臣",["外交","守成"],(18,32,78,86,88,76),(90,76,48,38,18),"3","朝廷辩论与外交"),
    ("郝昭","cao_cao","changan",215,"offstage","关中部将","军政","曹魏军将",["守城","军纪"],(76,84,72,48,44,66),(94,88,30,80,12),"2","陈仓坚守型将领"),
    ("孙皎","sun_quan","jianye",208,"active","江东宗室将领","军政","江东宗室",["水战","统合"],(78,80,68,58,62,74),(94,78,52,78,18),"2","江东宗室水军将领"),
    ("孙瑜","sun_quan","jianye",208,"active","江东宗室将领","军政","江东宗室",["水战","守成"],(72,76,70,62,66,72),(92,80,42,68,18),"3","宗室协防与安民"),
    ("徐盛","sun_quan","jianye",208,"active","江东偏将","军政","江东军将",["水战","守城"],(86,84,70,50,52,72),(94,84,38,84,18),"2","江防与疑城拒敌"),
    ("丁奉","sun_quan","jianye",215,"offstage","江东部将","军政","江东军将",["突击","水战"],(88,82,66,46,48,70),(92,82,42,88,16),"3","后期水军突击将领"),
    ("朱然","sun_quan","jianye",208,"active","江东将领","军政","江东军将",["守城","水战"],(82,84,70,54,56,70),(94,82,44,80,20),"2","江陵守备与水军"),
    ("朱桓","sun_quan","kuaiji",208,"active","余姚长","军政","江东军将",["守城","军纪"],(84,86,74,66,58,72),(90,78,50,82,18),"2","江东地方守备名将"),
    ("全琮","sun_quan","kuaiji",210,"offstage","江东士人","军政","江东军将",["水战","外交"],(76,78,70,62,66,72),(90,76,54,72,18),"3","江东将门与联姻线"),
    ("顾雍","sun_quan","jianye",208,"active","吴郡丞","政务","江东文臣",["治政","守成"],(18,36,82,94,82,76),(96,90,28,42,28),"2","江东士族政务中枢"),
    ("步骘","sun_quan","nanhai",210,"offstage","交州刺史候选","政务","江东文臣",["治政","外交"],(24,44,82,88,84,72),(92,84,36,52,24),"2","岭南经营与外交"),
    ("吕范","sun_quan","jianye",208,"active","江东长史","政务","江东文臣",["财政","外交"],(30,50,78,84,82,72),(94,82,38,58,22),"3","财赋与宗室事务"),
    ("张纮","sun_quan","jianye",208,"active","江东谋臣","政务","江东文臣",["外交","治政"],(18,34,86,90,90,78),(94,88,30,46,30),"2","江东战略与文书"),
    ("蒋钦","sun_quan","chaisang",208,"active","江东水军将领","军政","江东军将",["水战","军纪"],(84,80,66,50,52,68),(92,80,42,82,20),"3","水军与江面巡防"),
    ("刘循","liu_zhang","chengdu",208,"active","刘璋之子","宗室","益州本土士族",["守城"],(58,64,58,54,58,66),(90,76,44,66,24),"2","益州继承与雒城防线"),
    ("冷苞","liu_zhang","chengdu",211,"offstage","益州将领","军政","益州本土士族",["山地","守城"],(74,74,60,42,40,58),(88,76,46,74,20),"3","入蜀战役守将"),
    ("邓贤","liu_zhang","chengdu",211,"offstage","益州将领","军政","益州本土士族",["山地"],(70,70,58,42,40,56),(86,72,48,70,18),"3","入蜀战役山地守军"),
    ("雷铜","liu_zhang","jiangzhou",211,"offstage","巴郡将领","军政","益州本土士族",["突击","山地"],(78,74,58,42,42,62),(82,68,54,78,22),"3","巴蜀山地机动将领"),
]


ROLE_IDS = {"君主":"ruler","宗室":"clan","军政":"military","军师":"strategist","外交":"envoy","政务":"civil","在野":"scholar"}


def character_from_row(row):
    name, power, location, debut, status, office, office_type, faction, traits, six, personality, tier, summary = row
    martial, leadership, intelligence, politics, diplomacy, charisma = six
    loyalty, integrity, ambition, courage, closeness = personality
    return {
        "name": name, "office": office, "office_type": office_type, "faction": faction,
        "aliases": [name], "personal_skills": traits, "loyalty": loyalty,
        "ability": round(sum(six) / 6), "integrity": integrity, "ambition": ambition,
        "courage": courage, "closeness_to_liu_bei": closeness, "martial": martial,
        "leadership": leadership, "intelligence": intelligence, "politics": politics,
        "diplomacy": diplomacy, "charisma": charisma, "stewardship": politics,
        "intrigue": intelligence, "learning": intelligence, "power_id": power,
        "location": location, "status": status, "debut_year": debut,
        "debut_month": 1 if debut else 0, "core_tier": tier, "style": "半文半白",
        "summary": f"{office}。演义定位：{summary}。",
        "portrait_id": f"tier_{power}_{ROLE_IDS[office_type]}_adult",
    }


def main():
    payload = json.loads(CHARACTERS_PATH.read_text(encoding="utf-8"))
    addition_names = {row[0] for row in ROWS}
    opening = [item for item in payload["characters"] if item["name"] not in addition_names]
    opening_names = {item["name"] for item in opening}
    additions = [character_from_row(row) for row in ROWS]
    if len(opening) != 81 or len(ROWS) != 59 or opening_names & {item["name"] for item in additions}:
        raise SystemExit("第二批人物数量或姓名重复不合法")
    for item in opening:
        if not item.get("portrait_id"):
            role = ROLE_IDS.get(item.get("office_type"), "civil")
            item["portrait_id"] = f"tier_{item['power_id']}_{role}_adult"
    payload["characters"] = opening + additions
    faction_names = {item["name"] for item in payload["factions"]}
    for faction in sorted({item["faction"] for item in additions} - faction_names):
        payload["factions"].append({
            "name": faction, "satisfaction": 55, "leverage": 50,
            "agenda": "依人物归属、名分与当前局势维护本集团利益。",
        })
    CHARACTERS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    families = json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))
    families["relations"] = [
        item for item in families["relations"] if item["relation_type"] != "sibling"
    ]
    extra = [
        ("曹操", "曹丕", "child", "曹魏继承主线"),
        ("曹操", "曹彰", "child", "宗室军事竞争"),
        ("曹操", "曹植", "child", "宗室名望竞争"),
        ("关羽", "关平", "child", "荆州军政继承"),
    ]
    existing = {(item["person_a"], item["person_b"], item["relation_type"]) for item in families["relations"]}
    for person_a, person_b, relation_type, effect in extra:
        if (person_a, person_b, relation_type) not in existing:
            families["relations"].append({
                "person_a": person_a, "person_b": person_b, "relation_type": relation_type,
                "status": "active", "start_year": 0, "end_year": 0,
                "political_effect": effect, "succession_risk": "medium",
                "source": "三国演义人物关系",
            })
    FAMILIES_PATH.write_text(json.dumps(families, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
