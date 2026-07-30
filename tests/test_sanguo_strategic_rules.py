import sqlite3

import pytest

import ming_sim.sanguo_rules as sanguo_rules

from ming_sim.context import character_context
from ming_sim.content import load_administrative_units
from ming_sim.models import Character
from ming_sim.sanguo_rules import (
    ArmyOrderError,
    CityStrategicCatalog,
    CityStrategicEdge,
    CityStrategicNode,
    apply_route_entry,
    calculate_siege_progress,
    find_strategic_route,
    issue_army_order,
    load_city_strategic_catalog,
    require_city_node,
)


def test_city_strategic_catalog_matches_approved_map():
    admin = load_administrative_units()
    catalog = load_city_strategic_catalog(admin)
    assert len(catalog.nodes) == 72
    assert len(catalog.edges) == 177
    assert all(n.city_id.startswith("city:") for n in catalog.nodes)
    assert catalog.topology_version == "city-network-v1"
    # 所有边端点都在节点集合中
    for edge in catalog.edges:
        assert edge.source in catalog.city_ids
        assert edge.target in catalog.city_ids


def test_city_catalog_rejects_node_not_in_cities():
    admin = load_administrative_units()
    # 添加一个不在行政城池中的节点
    strategic = dict(admin["strategic"])
    strategic["nodes"] = list(strategic["nodes"]) + [
        {"city_id": "city:fake_node", "x": 0, "y": 0},
    ]
    admin_bad = dict(admin)
    admin_bad["strategic"] = strategic
    with pytest.raises(SystemExit, match="不在行政城池名册中"):
        load_city_strategic_catalog(admin_bad)


def test_city_catalog_rejects_duplicate_undirected_edges():
    admin = load_administrative_units()
    strategic = dict(admin["strategic"])
    edges = list(strategic["edges"])
    # 复制第一条边制造重复
    edges.append(dict(edges[0]))
    strategic["edges"] = edges
    admin_bad = dict(admin)
    admin_bad["strategic"] = strategic
    with pytest.raises(SystemExit, match="路线重复"):
        load_city_strategic_catalog(admin_bad)


def test_require_city_node_validates_prefix():
    assert require_city_node("city:jiangxia") == "city:jiangxia"
    with pytest.raises(ArmyOrderError, match="必须是城池节点"):
        require_city_node("jiangxia")
    with pytest.raises(ArmyOrderError, match="必须是城池节点"):
        require_city_node("")


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
