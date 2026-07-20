"""替换仍由通用引擎加载的旧静态目录，内容统一为刘备线。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "content"


def write_json(name: str, payload) -> None:
    (ROOT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    write_json("buildings.json", {
        "meta": {"scenario_id": "sanguo_liubei_208", "note": "三国郡级设施；主要投资由 national_focus 系统结算。"},
        "buildings": [
            {"id":"xiakou_granary","region_id":"jiangxia","name":"夏口军仓","category":"军事","level":1,"condition":65,"maintenance":0,"risk":25,"output_metric":"","output_amount":0,"status":"借驻军仓，储备有限"},
            {"id":"chaisang_dock","region_id":"chaisang","name":"柴桑水寨","category":"军事","level":2,"condition":82,"maintenance":0,"risk":15,"output_metric":"","output_amount":0,"status":"江东水军枢纽"},
            {"id":"chengdu_granary","region_id":"chengdu","name":"成都府仓","category":"民生","level":2,"condition":78,"maintenance":0,"risk":18,"output_metric":"","output_amount":0,"status":"益州核心粮仓"},
        ],
    })
    write_json("classes.json", {
        "_comment": "三国郡级社会群体，仅供低影响治理叙事。",
        "classes": [
            {"name":"流民与军户","region_id":"jiangxia","population":12000,"satisfaction":68,"leverage":35,"agenda":"求安置、军粮与免受强征。"},
            {"name":"荆州士人","region_id":"xiangyang","population":8000,"satisfaction":52,"leverage":70,"agenda":"维护地方秩序与仕进网络。"},
            {"name":"益州豪族","region_id":"chengdu","population":10000,"satisfaction":62,"leverage":75,"agenda":"维护乡里田产与地方官职。"},
        ],
    })
    write_json("fiscal_config.json", {
        "_comment": "旧通用财政表已停用；三国资源由六指标、地区 fiscal 与国策投资结算。",
        "schema_version": 3,
        "items": [],
    })
    write_json("opening_legacies.json", {
        "meta": {"note": "刘备 208 开局结构性困境。"},
        "legacies": [{
            "key":"no_fixed_domain","name":"寄军夏口·无一郡之土",
            "modifiers":{"民望":-2,"名分":-1},
            "narrative_hint":"刘备暂借夏口驻军，兵少粮薄，无正式控制郡县。",
            "clear_gate":{"region.jiangxia.controlled_by":"==liu_bei"},
            "clear_narrative":"刘备取得稳定立足之地，流亡军局告终。",
        }],
    })
    department = {
        "key":"military_council","name":"军府参谋署","category":"政治","题材":"政治",
        "authority_scope":"汇总军令、外交、粮道与战区情报","power":55,"responsibility":70,"corruption_risk":10,
        "预计月数":3,"起步进度":25,"stage_text":"参谋署草创，人手与军报格式尚未齐备。",
        "resolve_condition":"军报、粮道与战区文书形成固定流程。","fail_condition":"人手离散或军令互相冲突，进度归零。",
        "effect_on_resolve":{"departments":[{"action":"create","key":"military_council"}]},"effect_on_fail":{},
        "modifiers":{},"effect_summary":"军令汇总更清晰。","requires":[],
    }
    write_json("preset_departments.json", {"meta":{"note":"三国通用军府机构。"},"departments":[department]})
    technology = {
        "key":"river_signal_code","name":"江面旗号规程","category":"军事","题材":"军事",
        "预计月数":2,"起步进度":30,"stage_text":"各部旗鼓号令尚未统一。",
        "resolve_condition":"水军旗号与夜间识别规程完成操演。","fail_condition":"操演混乱或无水军承办，进度归零。",
        "effect_on_resolve":{"technologies":[{"action":"create","key":"river_signal_code"}]},"effect_on_fail":{},
        "modifiers":{},"effect_summary":"水军协同更稳定。","requires":[],"default_unlocked":True,
    }
    write_json("preset_technologies.json", {"meta":{"note":"兼容通用事项引擎的三国军政技术。"},"technologies":[technology]})
    write_json("directive_templates.json", [
        {"id":"army_order","label":"军令","category":"军务","settlement_hint":"每军每月一道主军令，只能沿战略边行动。","compiled_text":"军令：命{army}执行{action}，目标{target}。{note}","fields":[{"key":"army","label":"军队","type":"select","option_source":"armies","required":True},{"key":"action","label":"行动","type":"select","required":True,"options":["移动","驻守","围城","突袭","补给","撤退"]},{"key":"target","label":"目标节点","type":"select","option_source":"regions","required":False},{"key":"note","label":"备注","type":"textarea","required":False}]},
        {"id":"personnel_change","label":"人物任免","category":"人事","settlement_hint":"任命权归刘备，职位空缺只影响效率。","compiled_text":"任命：{person}出任{office}，理由：{reason}。","fields":[{"key":"person","label":"人物","type":"select","option_source":"people","required":True},{"key":"office","label":"官职","type":"text","required":True},{"key":"reason","label":"理由","type":"text","required":False}]},
        {"id":"diplomatic_proposal","label":"外交提案","category":"外交","settlement_hint":"盟约必须保存独立条款并由规则校验。","compiled_text":"外交：向{target}提出{terms}。","fields":[{"key":"target","label":"对象势力","type":"text","required":True},{"key":"terms","label":"条款","type":"textarea","required":True}]},
    ])

    office_types = ["君主","军政","军师","外交","政务","宗室","在野"]
    grants = {name:{"court_tools":[],"agno_skills":[],"chips":[]} for name in office_types}
    definitions = {
        name:{"tools":[],"authority_scope":f"{name}职责范围","power":70 if name in {"君主","军政"} else 55,"responsibility":70,"corruption_risk":15}
        for name in office_types
    }
    write_json("skills.json", {"__office_grant_version":3,"office_default_skills":grants,"office_definitions":definitions})
    write_json("skill_tools.json", {
        "check_treasury_prefix":"查军资粮秣：",
        "check_military":"{event_title}军情复核：军队警讯为{army_warning}。",
        "front_line_plan":"前线部署须核对路线、粮秣、关隘与各军本月军令：{army_detail}。",
        "strategic_review":"复核{event_title}：先看兵力、粮道、盟约与历史事件窗口。",
        "inner_court_inquiry":"家族与近侍查访只能提供低影响线索，不得直接落高影响事实。",
        "secret_investigation":"密查{subject}与{event_title}，只取可验证线索并记录风险。",
        "factory_network_probe":"地方耳目回报{event_title}，须再由情报与规则盘面核实。",
        "intimidate_obstruction":"威慑{target}可能加快执行，但会结算名分、民望与互信代价。",
        "convene_court_debate":"召集群议{event_title}，比较军资、粮秣、名分与外交代价。",
        "estimate_project_workshop":"估算{event_title}所需军资、粮秣、人物与回合数。",
        "estimate_project_default":"{event_title}须先核资源与承办人，不得空立。",
        "draft_edict":"命{executor}承办{event_title}，依“{policy}”执行，限期具实回报。",
        "directive_generic":"命{actor}承办{event_title}：{action}。",
        "directive_funds":"命{actor}为{purpose}调度资源{amount}，逐项记录。",
        "directive_troops":"命{actor}依路线与单军单令规则调度{target}：{action}。",
        "directive_investigation":"命{actor}以{method}查核{target}，只取实据。",
    })
    write_json("weapons.json", {
        "version":3,"note":"三国军队装备类别；实际战力仍以 armies.equipment 与特性结算。","default_tier":"常规兵械",
        "tiers":{
            "常规兵械":{"cost":1,"equip_per_unit":0.4,"keywords":["刀","矛","弓","弩","盾"]},
            "重装兵械":{"cost":2,"equip_per_unit":0.8,"keywords":["甲","具装"]},
            "舟船":{"cost":3,"equip_per_unit":1.0,"keywords":["船","舟","舰"]},
        },
        "weapons":[
            {"id":"spear","name":"长矛","tier":"常规兵械","cost":1,"equip_per_unit":0.4,"requires_tech":"","opening_stock":0},
            {"id":"bow_crossbow","name":"弓弩","tier":"常规兵械","cost":1,"equip_per_unit":0.4,"requires_tech":"","opening_stock":0},
            {"id":"shield_blade","name":"刀盾","tier":"常规兵械","cost":1,"equip_per_unit":0.4,"requires_tech":"","opening_stock":0},
            {"id":"armor","name":"甲胄","tier":"重装兵械","cost":2,"equip_per_unit":0.8,"requires_tech":"","opening_stock":0},
            {"id":"warship","name":"战船","tier":"舟船","cost":3,"equip_per_unit":1.0,"requires_tech":"","opening_stock":0},
        ],
    })
    write_json("troop_cost.json", {
        "version":7,"note":"208 开局四类战略兵种，仅用于通用军需接口。","unit":"军资/千人/月","default_tier":"步卒",
        "tiers":[
            {"tier":"步卒","category":"步兵","per_kilo":0.10,"keywords":["步卒","步兵","守军"],"equipment":["长矛","刀盾"],"upgrades":[],"requires_tech":""},
            {"tier":"弓弩","category":"远程","per_kilo":0.12,"keywords":["弓弩","弓兵","弩兵"],"equipment":["弓弩"],"upgrades":[],"requires_tech":""},
            {"tier":"骑兵","category":"骑兵","per_kilo":0.18,"keywords":["骑兵","骑军","铁骑"],"equipment":["战马","甲胄"],"upgrades":[],"requires_tech":""},
            {"tier":"水军","category":"水军","per_kilo":0.16,"keywords":["水军","水师","舟师"],"equipment":["战船","弓弩"],"upgrades":[],"requires_tech":""},
        ],
    })
    armies = json.loads((ROOT / "armies.json").read_text(encoding="utf-8"))
    for army in armies["armies"]:
        army["arms"] = []
    write_json("armies.json", armies)
    (ROOT / "opening_gazette.md").write_text(
        "# 建安十三年七月军报\n\n曹军南下，荆襄新附；刘备暂驻夏口，无正式郡土。孙权据江东，联盟尚待鲁肃、诸葛亮等人奔走。三军合二万二千，粮秣仅堪短期周转，赤壁风云已近。\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
