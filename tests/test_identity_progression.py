from ming_sim.db import GameDB
from ming_sim.identity import apply_identity_promotion, identity_summary
from ming_sim.models import GameState


def _state(year: int, period: int, turn: int = 1) -> GameState:
    return GameState(
        year=year,
        period=period,
        turn=turn,
        metrics={"军资": 60, "粮秣": 60, "民望": 70, "名分": 90, "军心": 70, "士族支持": 60},
    )


def _board():
    db = GameDB(":memory:")
    db.seed_static_data()
    return db


def _ready_for_hanzhong(db):
    db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id IN ('chengdu', 'jiangzhou')")
    db.add_reputation_log(
        _state(219, 7), source_kind="test", source_id="identity",
        metric="仁义", delta=15, summary="守约护民，天下称颂",
    )
    db.conn.commit()


def test_hanzhong_is_always_claimable_but_exposes_legitimacy_pressure():
    db = _board()
    try:
        _ready_for_hanzhong(db)
        early = identity_summary(db, _state(219, 6))
        assert early["next_stage"] == "汉中王"
        assert early["eligible"] is True
        assert early["available_action"] == "promote_hanzhong"
        assert early["legitimacy"] == "名实相符"

        ready = identity_summary(db, _state(219, 7))
        assert ready["eligible"] is True
        assert ready["available_action"] == "promote_hanzhong"
    finally:
        db.close()


def test_promotion_records_fact_and_pressure_even_when_claim_is_contested():
    db = _board()
    try:
        _ready_for_hanzhong(db)
        state = _state(219, 7)
        applied = apply_identity_promotion(db, state, "promote_hanzhong")
        assert applied["stage"] == "汉中王"
        assert db.kv_get("identity_hanzhong_granted") == "1"
        assert "汉中王" in db.conn.execute("SELECT office FROM characters WHERE name='刘备'").fetchone()[0]

        emperor = identity_summary(db, _state(221, 3))
        assert emperor["next_stage"] == "称帝后"
        assert emperor["eligible"] is False
        assert emperor["available_action"] == "proclaim_emperor"
    finally:
        db.close()


def test_contested_claim_applies_auditable_penalty_instead_of_blocking():
    db = _board()
    try:
        state = _state(208, 8)
        before = dict(state.metrics)
        result = apply_identity_promotion(db, state, "promote_hanzhong")
        assert result["stage"] == "汉中王"
        claim = db.conn.execute("SELECT legitimacy, external_pressure FROM political_claims").fetchone()
        assert claim["legitimacy"] == "僭越"
        assert int(claim["external_pressure"]) > 0
        assert state.metrics["名分"] < before["名分"]
        assert db.conn.execute("SELECT COUNT(*) FROM reputation_logs WHERE source_kind='political_claim'").fetchone()[0] == 1
    finally:
        db.close()
