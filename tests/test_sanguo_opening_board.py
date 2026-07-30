from ming_sim.content import GameContent
from ming_sim.db import GameDB


POWER_IDS = {
    "cao_cao", "sun_quan", "liu_bei", "liu_qi", "liu_zhang",
    "zhang_lu", "ma_han", "shi_xie", "gongsun_kang",
}


def test_opening_board_has_approved_power_region_and_army_counts():
    content = GameContent.load()
    # 路线节点使用 city:* 前缀，去掉前缀后应为 regions 的子集
    route_city_ids = {node.city_id for node in content.routes.nodes}
    route_commandery_ids = {node.commandery_id for node in content.routes.nodes}

    assert set(content.powers) == POWER_IDS
    # 数据驱动：regions 数量以 content 为准，不硬编码
    assert len(content.regions) > 0
    # 路线节点的郡 ID 应为 regions 的子集
    assert route_commandery_ids <= set(content.regions)
    assert len(content.armies) == 25
    assert not [region for region in content.regions.values() if region.controlled_by == "liu_bei"]
    assert content.regions["jiangxia"].controlled_by == "liu_qi"


def test_opening_armies_match_approved_strength_and_resolve_commanders_and_stations():
    content = GameContent.load()
    # station_node 使用 city:* 前缀；去掉前缀后应在 routes 或 regions 中
    valid_city_ids = {node.city_id for node in content.routes.nodes}
    valid_commandery_ids = set(content.regions)
    armies = list(content.armies.values())

    assert sum(army.manpower for army in armies if army.owner_power == "liu_bei") == 22_000
    assert sum(army.manpower for army in armies if army.owner_power == "cao_cao") == 128_000
    assert all(army.commander in content.characters for army in armies)
    # station_node 必须是有效的 city:* 节点
    assert all(army.station_node in valid_city_ids for army in armies)

    liu_bei_main = content.armies["liubei_main"]
    assert liu_bei_main.station == "夏口"
    assert liu_bei_main.station_node == "city:jiangxia"
    assert liu_bei_main.supply_turns == 2
    assert liu_bei_main.supply == 40
    assert content.armies["liuzhang_yongan"].commander == "刘巴"


def test_region_fiscal_contains_sanguo_county_fields():
    content = GameContent.load()
    required = {
        "population", "farmland", "grain_output", "granary", "tax", "commerce",
        "gentry_support", "security", "fortification", "transport", "revolt_risk",
    }
    for region in content.regions.values():
        assert required <= set(region.fiscal), region.id


def test_liubei_has_structured_xiakou_garrison_right_without_owning_jiangxia(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        db.seed_static_data()
        right = db.conn.execute(
            """
            SELECT proposer, target, treaty_type, terms, status
            FROM diplomacy_treaties WHERE treaty_type='驻军权'
            """
        ).fetchone()
        assert right is not None
        assert right["proposer"] == "liu_qi"
        assert right["target"] == "liu_bei"
        assert '"node_id": "city:jiangxia"' in right["terms"]
        assert right["status"] == "active"
        assert db.conn.execute(
            "SELECT controlled_by FROM regions WHERE id='jiangxia'"
        ).fetchone()["controlled_by"] == "liu_qi"
    finally:
        db.close()
