import sqlite3

import pytest

import ming_sim.sanguo_rules as sanguo_rules

from ming_sim.context import character_context
from ming_sim.models import Character
from ming_sim.sanguo_rules import (
    ArmyOrderError,
    apply_route_entry,
    calculate_siege_progress,
    issue_army_order,
    load_strategic_routes,
)


def test_strategic_route_catalog_matches_approved_map():
    catalog = load_strategic_routes()
    assert len(catalog.nodes) == 49
    assert len(catalog.edges) == 79
    assert {edge.kind for edge in catalog.edges} == {"普通路", "江河", "山道", "关隘"}
    assert {
        "jiuyuan", "nanpi", "qiaoxian", "wancheng",
        "zitong", "shangyong", "yelang", "qielan",
        "zhangye", "wu", "zhuojun", "youbeiping", "taishan", "pengcheng",
    }.issubset({node.id for node in catalog.nodes})


def test_route_catalog_rejects_duplicate_node_names(monkeypatch):
    raw = {
        "nodes": [
            {"id": "a", "name": "同名", "province": "甲州"},
            {"id": "b", "name": "同名", "province": "乙州"},
        ],
        "edges": [],
    }
    monkeypatch.setattr(sanguo_rules, "load_json_asset", lambda _name: raw)
    with pytest.raises(SystemExit, match="节点名称重复"):
        load_strategic_routes()


def test_route_catalog_rejects_duplicate_undirected_edges(monkeypatch):
    raw = {
        "nodes": [
            {"id": "a", "name": "甲", "province": "甲州"},
            {"id": "b", "name": "乙", "province": "乙州"},
        ],
        "edges": [
            {"source": "a", "target": "b", "kind": "普通路"},
            {"source": "b", "target": "a", "kind": "普通路"},
        ],
    }
    monkeypatch.setattr(sanguo_rules, "load_json_asset", lambda _name: raw)
    with pytest.raises(SystemExit, match="路线重复"):
        load_strategic_routes()


def test_dangerous_route_requires_supply_and_applies_three_turn_penalty():
    with pytest.raises(ArmyOrderError, match="粮秣低于20"):
        apply_route_entry("山道", supply=19, hazard_turns=0)

    result = apply_route_entry("江河", supply=55, hazard_turns=1)
    assert result == {"supply": 35, "hazard_turns": 3, "combat_multiplier": 0.5, "mobility_multiplier": 0.5}


def test_one_army_can_only_receive_one_primary_order_per_turn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE army_orders (army_id TEXT, turn INTEGER, order_type TEXT, payload TEXT, UNIQUE(army_id, turn))"
    )
    issue_army_order(conn, army_id="liubei_main", turn=1, order_type="移动", payload={"to": "江夏"})
    with pytest.raises(ArmyOrderError, match="本回合已执行主军令"):
        issue_army_order(conn, army_id="liubei_main", turn=1, order_type="补给", payload={})


def test_standard_siege_resolves_in_about_three_turns():
    progress = 0
    for _ in range(3):
        progress = calculate_siege_progress(progress, attacker_score=100, defender_score=100)
    assert progress == 100


def test_character_context_injects_all_sanguo_attributes():
    character = Character(
        name="刘备",
        office="左将军",
        office_type="君主",
        faction="元从旧部",
        aliases=["玄德"],
        personal_skills=["仁德"],
        loyalty=100,
        ability=83,
        integrity=96,
        courage=88,
        style="半文半白",
        power_id="liu_bei",
        martial=72,
        leadership=80,
        intelligence=83,
        politics=81,
        diplomacy=89,
        charisma=96,
        ambition=45,
        closeness_to_liu_bei=100,
        core_tier="S",
    )
    context = character_context(character)
    for fragment in (
        "武力72", "统率80", "智略83", "政治81", "外交89", "魅力96",
        "忠诚100", "节义96", "野心45", "胆略88", "亲密度100", "核心等级S",
    ):
        assert fragment in context
