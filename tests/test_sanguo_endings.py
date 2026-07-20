from ming_sim.content import GameContent
from ming_sim.context import (
    ENDING_HISTORICAL_BAIDI,
    ENDING_LIU_BEI_DEAD,
    ENDING_ONGOING,
    ENDING_REGIME_COLLAPSED,
    ENDING_REWRITTEN_223,
    ENDING_UNIFIED_VICTORY,
    ENDING_YIZHOU_CORE_FALLEN,
    victory_status,
)
from ming_sim.db import GameDB
from ming_sim.models import GameState


def _board():
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    return db


def _state(year=208, month=8, turn=1):
    return GameState(
        year=year, period=month, turn=turn,
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 45},
    )


def _assert_review(outcome):
    assert set(outcome["scores"]) == {"统一", "名分", "民生", "将相", "外交", "军功"}
    assert all(0 <= value <= 100 for value in outcome["scores"].values())
    assert len(outcome["review"]) >= 80


def test_liu_bei_early_death_ends_immediately_with_review():
    db = _board()
    try:
        db.set_character_status(_state(), "刘备", "dead", "战役中阵亡")
        outcome = victory_status(db, _state())
        assert outcome["status"] == ENDING_LIU_BEI_DEAD
        _assert_review(outcome)
    finally:
        db.close()


def test_chengdu_loss_is_three_turn_recoverable_crisis_but_all_core_lost_is_immediate():
    db = _board()
    try:
        state = _state(214, 5, 10)
        db.conn.execute(
            "UPDATE regions SET controlled_by='liu_bei' WHERE id IN ('chengdu','jiangzhou','yongan')"
        )
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        db.conn.execute("UPDATE regions SET controlled_by='cao_cao' WHERE id='chengdu'")
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        assert state.chengdu_crisis_turns == 1
        state.turn = 11
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        assert state.chengdu_crisis_turns == 2
        db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='chengdu'")
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        assert state.chengdu_crisis_turns == 0

        db.conn.execute("UPDATE regions SET controlled_by='cao_cao' WHERE id='chengdu'")
        state.turn = 12
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        state.turn = 13
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        state.turn = 14
        assert victory_status(db, state)["status"] == ENDING_YIZHOU_CORE_FALLEN

        db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id IN ('chengdu','jiangzhou','yongan')")
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        db.conn.execute(
            "UPDATE regions SET controlled_by='cao_cao' WHERE id IN ('chengdu','jiangzhou','yongan')"
        )
        state.turn = 15
        outcome = victory_status(db, state)
        assert outcome["status"] == ENDING_YIZHOU_CORE_FALLEN
        _assert_review(outcome)
    finally:
        db.close()


def test_regime_collapse_requires_no_region_low_army_for_three_distinct_turns():
    db = _board()
    try:
        db.conn.execute("UPDATE regions SET controlled_by='cao_cao' WHERE controlled_by='liu_bei'")
        db.conn.execute("UPDATE armies SET active=0 WHERE owner_power='liu_bei'")
        db.conn.execute(
            "UPDATE armies SET active=1, manpower=2500 WHERE id='liubei_main'"
        )
        state = _state(211, 1, 20)
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        state.turn = 21
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        state.turn = 22
        assert victory_status(db, state)["status"] == ENDING_REGIME_COLLAPSED
    finally:
        db.close()


def test_unification_requires_all_regions_and_no_other_active_army():
    db = _board()
    try:
        state = _state(218, 6, 120)
        db.conn.execute("UPDATE regions SET controlled_by='liu_bei'")
        assert victory_status(db, state)["status"] == ENDING_ONGOING
        db.conn.execute("UPDATE armies SET active=0 WHERE owner_power!='liu_bei'")
        outcome = victory_status(db, state)
        assert outcome["status"] == ENDING_UNIFIED_VICTORY
        assert outcome["scores"]["统一"] == 100
        _assert_review(outcome)
    finally:
        db.close()


def test_april_223_distinguishes_historical_baidi_from_living_rewrite():
    db = _board()
    try:
        historical = _state(223, 4, 177)
        db.set_character_status(historical, "刘备", "dead", "历史卒于 223年4月，白帝托孤")
        outcome = victory_status(db, historical)
        assert outcome["status"] == ENDING_HISTORICAL_BAIDI
        _assert_review(outcome)

        other = _board()
        try:
            living = victory_status(other, _state(223, 4, 177))
            assert living["status"] == ENDING_REWRITTEN_223
            _assert_review(living)
        finally:
            other.close()
    finally:
        db.close()


def test_ending_prompt_is_fully_sanguo_and_demands_six_dimension_review():
    prompt = GameContent.load().ending_summary_prompt
    assert all(name in prompt for name in ("统一", "名分", "民生", "将相", "外交", "军功"))
    for stale in ("崇祯", "京师陷落", "煤山", "明史", "国库/内库"):
        assert stale not in prompt
