from types import SimpleNamespace

from ming_sim.battle import resolve_battle
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.monthly_report import build_monthly_report
from ming_sim.world_simulation import (
    build_monthly_memorials,
    get_or_create_world_context,
    record_external_intelligence,
)


def _state(turn=1):
    return SimpleNamespace(
        turn=turn, year=208, period=8,
        metrics={"军资": 60, "民望": 55, "名分": 65, "士族支持": 45, "军心": 60, "粮秣": 60},
    )


def _board():
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    return db


def test_world_context_is_persisted_and_reproducible():
    db = _board()
    try:
        state = _state()
        first = get_or_create_world_context(db, state)
        second = get_or_create_world_context(db, state)
        assert first == second
        assert first["seed"]
        assert first["weather"]["kind"]
        assert first["power_budgets"]["cao_cao"] >= 1
        assert db.conn.execute("SELECT COUNT(*) FROM world_simulation_contexts WHERE turn=1").fetchone()[0] == 1
    finally:
        db.close()


def test_memorials_require_rule_evidence_and_are_traceable():
    db = _board()
    try:
        state = _state()
        db.conn.execute("UPDATE armies SET supply=15 WHERE id='liubei_main'")
        created = build_monthly_memorials(db, state)
        assert created
        row = db.conn.execute("SELECT * FROM minister_memorials WHERE turn=1").fetchone()
        assert row is not None
        assert row["evidence_json"] != "[]"
        assert row["status"] == "open"
    finally:
        db.close()


def test_external_intelligence_keeps_unconfirmed_reports_out_of_rule_facts():
    db = _board()
    try:
        report = record_external_intelligence(
            db, _state(), power_id="cao_cao", visibility="rumor",
            title="北军或有调动", summary="商旅称襄阳道军马增多。", evidence_refs=["power_ai_actions:1"],
        )
        assert report["visibility"] == "rumor"
        assert report["usable_as_fact"] is False
        assert db.conn.execute("SELECT usable_as_fact FROM external_intelligence_reports").fetchone()[0] == 0
    finally:
        db.close()


def test_battle_records_seeded_environment_layer():
    db = _board()
    try:
        state = _state()
        get_or_create_world_context(db, state)
        result = resolve_battle(
            db, state,
            {"attacker_ids": ["guanyu_fleet"], "defender_ids": ["cao_vanguard"], "node_id": "city:xiangyang"},
            {"tactic": "正面交锋", "actor": "关羽"},
        )
        assert result["environment"]["weather"]["kind"]
        assert "environment_probability_delta" in result
        assert result["audit"]["environment"] == result["environment"]
    finally:
        db.close()


def test_monthly_report_exposes_memorial_and_layered_external_intelligence():
    db = _board()
    try:
        state = _state(turn=2)
        prior = _state(turn=1)
        get_or_create_world_context(db, prior)
        db.conn.execute("UPDATE armies SET supply=15 WHERE id='liubei_main'")
        build_monthly_memorials(db, prior)
        record_external_intelligence(db, prior, power_id="cao_cao", visibility="assessment", title="北军动向", summary="斥候研判北军整备。", evidence_refs=["power_ai_actions:1"])
        report = build_monthly_report(db, state)
        personnel = next(section for section in report["sections"] if section["id"] == "personnel")
        world = next(section for section in report["sections"] if section["id"] == "world")
        assert any(item["id"].startswith("memorial:") for item in personnel["items"])
        intel = next(item for item in world["items"] if item["id"].startswith("intel:"))
        assert intel["audit"]["visibility"] == "assessment"
        assert intel["audit"]["usable_as_fact"] is False
    finally:
        db.close()
