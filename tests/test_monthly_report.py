import json
from types import SimpleNamespace

import pytest

import ming_sim.battle as battle_module
from ming_sim.battle import resolve_battle
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.government import appoint_office
from ming_sim.monthly_report import build_monthly_report
from ming_sim.national_focus import start_region_investment


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn=1):
    return SimpleNamespace(
        turn=turn,
        year=208,
        period=turn,
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
    )


def _section(report, section_id):
    return next(item for item in report["sections"] if item["id"] == section_id)


def test_monthly_report_aggregates_world_events_into_named_sections(board, monkeypatch):
    # 固定存档种子以确保 draw_int 结果可复现
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "monthly_report_test_seed" + "0" * 39)
    settled = _state(1)
    board.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    resolve_battle(
        board,
        settled,
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {"tactic": "正面交锋", "actor": "关羽"},
    )
    board.create_envoy_mission(
        settled,
        target_power="sun_quan",
        envoy="诸葛亮",
        goal="续盟并借粮",
        boundaries="不得割让江夏",
    )
    start_region_investment(board, settled, "jiangxia", "屯田粮仓")
    appoint_office(board, settled, "chief_strategist", "诸葛亮")
    board.create_secret_order(settled, "赵云", "暗护百姓", "护送江夏流民，不得扰民。", ["护民"])
    board.add_reputation_log(settled, source_kind="test", source_id="kindness", metric="仁义", delta=4, summary="护送流民，江夏百姓称颂。")
    board.save_turn_report(settled, "《月末军政报》\n关羽水战得胜，诸葛亮赴江东议粮。")

    report = build_monthly_report(board, _state(2))

    assert report["title"] == "建安十三年正月军政总计"
    assert [item["id"] for item in report["sections"]] == [
        "military", "internal", "regional", "geopolitical", "diplomacy", "personnel", "secret", "world", "reputation",
    ]
    assert "关羽水战得胜" in report["source_report"]

    military = _section(report, "military")
    assert any(item["kind"] == "战役" for item in military["items"])
    battle_item = next(item for item in military["items"] if item["kind"] == "战役")
    # draw_int 确定性抽取，掷骰在 [1, 100] 范围
    assert 1 <= battle_item["audit"]["random_roll"] <= 100
    assert "army_breakdown" in battle_item["audit"]
    assert "random_roll" not in battle_item["summary"]

    diplomacy = _section(report, "diplomacy")
    assert any("续盟并借粮" in item["summary"] for item in diplomacy["items"])
    assert any(item["action"]["entry"] == "外交" for item in diplomacy["items"])

    internal = _section(report, "internal")
    assert any("屯田粮仓" in item["summary"] for item in internal["items"])

    personnel = _section(report, "personnel")
    assert any("诸葛亮" in item["summary"] and "首席军师" in item["summary"] for item in personnel["items"])

    secret = _section(report, "secret")
    assert any("暗护百姓" in item["summary"] for item in secret["items"])

    reputation = _section(report, "reputation")
    assert reputation["summary"].startswith("仁义口碑")
    assert any("护送流民" in item["summary"] for item in reputation["items"])


def test_monthly_report_keeps_battle_detail_inside_expandable_audit(board, monkeypatch):
    # 固定存档种子以确保 draw_int 结果可复现
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "battle_detail_test_seed" + "0" * 40)
    resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {"tactic": "正面交锋", "actor": "关羽"},
    )

    report = build_monthly_report(board, _state(2))
    battle_item = next(item for item in _section(report, "military")["items"] if item["kind"] == "战役")

    visible = json.dumps({k: battle_item[k] for k in ("title", "summary", "kind")}, ensure_ascii=False)
    audit = json.dumps(battle_item["audit"], ensure_ascii=False)

    assert "random_roll" not in visible
    assert "army_breakdown" not in visible
    assert "random_roll" in audit
    assert "army_breakdown" in audit
