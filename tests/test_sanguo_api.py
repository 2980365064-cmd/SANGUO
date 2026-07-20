from types import SimpleNamespace

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import GameState
from web_app import WebGame


@pytest.fixture
def game():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    state = GameState(
        year=208, period=8, turn=1, stage="流亡军",
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
    )
    session = SimpleNamespace(
        db=db, content=content, state=state, previous_summary="", last_decree="", last_report="",
        victory=lambda: {"status": "ongoing", "summary": "天下未定"},
        list_structured_directives=lambda: [], pending_count=lambda: 0, pending_decisions=lambda: [],
    )
    instance = WebGame.__new__(WebGame)
    instance.session = session
    instance.favorites = {"刘备", "诸葛亮"}
    try:
        yield instance
    finally:
        db.close()


def _serialized(payload):
    import json
    return json.dumps(payload, ensure_ascii=False)


def test_state_contract_contains_only_sanguo_runtime_systems(game):
    payload = game.state_payload()
    assert payload["scenario_id"] == "sanguo_liubei_208"
    assert payload["government"]["stage"] == "流亡军"
    assert set(payload["metrics"]) == {"军资", "粮秣", "民望", "名分", "军心", "士族支持"}
    assert len(payload["map"]["nodes"]) == 49
    assert len(payload["map"]["routes"]) == 0
    assert {
        "jiuyuan", "nanpi", "qiaoxian", "wancheng",
        "zitong", "shangyong", "yelang", "qielan",
        "zhangye", "wu", "zhuojun", "youbeiping", "taishan", "pengcheng",
    }.issubset({node["id"] for node in payload["map"]["nodes"]})
    assert len(payload["armies"]) == 25
    assert "army_orders" in payload and "sieges" in payload and "battles" in payload
    assert "diplomacy" in payload and "national_focus" in payload
    assert "timeline" in payload and "characters" in payload and "families" in payload

    serialized = _serialized(payload)
    for stale in ("崇祯", "大明", "后金", "皇太极", "辽饷", "选妃", "国库", "内库", "皇威"):
        assert stale not in serialized
    for stale_key in ("treasury", "budget", "consorts", "departments", "technologies", "preset_trees", "arms_stock"):
        assert stale_key not in payload


def test_character_contract_exposes_six_abilities_but_hides_personality_by_intel(game):
    characters = {item["name"]: item for item in game.state_payload()["characters"]}
    liu_bei = characters["刘备"]
    assert set(liu_bei["abilities"]["values"]) == {"武力", "统率", "智略", "政治", "外交", "魅力"}
    assert set(liu_bei["personality"]["values"]) == {"忠诚", "节义", "野心", "胆略", "对刘备亲密度"}
    assert not ({"loyalty", "integrity", "ambition", "courage", "closeness_to_liu_bei"} & set(liu_bei))
    cao_cao = characters["曹操"]
    assert cao_cao["personality"]["visibility"] != "exact"


def test_high_impact_army_write_is_revalidated_server_side(game):
    order_id = game.submit_army_order(
        "liubei_main", "移动", {"to": "xiangyang"}
    )
    assert order_id > 0
    with pytest.raises(ValueError, match="不相邻|不接壤|当前不在|本回合已"):
        game.submit_army_order("guanyu_fleet", "移动", {"to": "ji"})


def test_battle_preview_rejects_fabricated_non_adjacent_or_wrong_armies(game):
    with pytest.raises(ValueError, match="不相邻|不接壤|不存在|不在战役节点"):
        game.preview_battle({
            "attacker_ids": ["liubei_main"],
            "defender_ids": ["zhanglu_hanzhong"],
            "node_id": "ji",
        })


def test_region_detail_exposes_manageable_county_fields_without_bloating_main_state(game):
    game.db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    detail = game.region_detail_payload("jiangxia")

    assert detail["id"] == "jiangxia"
    assert detail["can_invest"] is True
    assert {"grain_stock", "fortification", "commerce_tax", "transport"} <= set(detail["fiscal"])
    assert isinstance(detail["stationed_armies"], list)
    assert "regions" not in game.state_payload()


def test_government_office_api_payload_and_appointment_replace_current_holder(game):
    offices = game.government_office_payload()
    chief = next(item for item in offices if item["office_key"] == "chief_strategist")
    assert chief["name"] == "首席军师"
    assert "effect" in chief

    appointed = game.appoint_government_office("chief_strategist", "张飞")
    replaced = game.appoint_government_office("chief_strategist", "诸葛亮")

    assert replaced["character_name"] == "诸葛亮"
    assert replaced["efficiency"] > appointed["efficiency"]
    assert game.db.conn.execute(
        "SELECT character_name FROM government_offices WHERE office_key='chief_strategist'"
    ).fetchone()[0] == "诸葛亮"
