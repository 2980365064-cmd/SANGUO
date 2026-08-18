"""P1 接收验收：所有新增纵深系统必须在方略批次中结算。"""

import json

from ming_sim.db import GameDB
from ming_sim.models import GameState
from ming_sim.phased_execution import PhasedExecutor
from ming_sim.long_term import adjust_character_loyalty, long_term_summary, refresh_long_term_state
from ming_sim.random_events import (
    _create_random_event,
    ensure_templates_seeded,
    generate_random_events,
)


def _board() -> tuple[GameDB, GameState]:
    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(
        year=208,
        period=8,
        turn=1,
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
    )
    db.save_state(state)
    return db, state


def test_random_event_choice_changes_nothing_until_issued_batch_executes():
    db, state = _board()
    try:
        ensure_templates_seeded(db)
        template = db.conn.execute(
            "SELECT id, category, title, description, options FROM random_event_templates WHERE title='蝗灾袭扰'"
        ).fetchone()
        template_data = dict(template)
        template_data["options"] = json.loads(template_data["options"])
        event = _create_random_event(state, db, template_data)
        before = dict(state.metrics)

        draft_id = db.create_directive_draft(
            turn=state.turn, year=state.year, period=state.period,
            source_type="manual", directive_type="other", title="处理蝗灾", target=f"随机事件#{event['id']}",
            resources_json='{"sub_type":"random_event_resolution","random_event_id":%d,"choice":1}' % event["id"],
        )
        batch_id = db.create_directive_batch(state.turn, state.year, state.period, "八月赈灾方略", [draft_id])

        assert dict(state.metrics) == before
        assert db.conn.execute("SELECT status FROM random_events WHERE id=?", (event["id"],)).fetchone()[0] == "active"

        result = PhasedExecutor(state, db, batch_id)._execute_civilian_phase()

        assert result.success
        assert state.metrics["粮秣"] == before["粮秣"] - 20
        assert state.metrics["民望"] == before["民望"] + 10
        assert db.conn.execute("SELECT status FROM random_events WHERE id=?", (event["id"],)).fetchone()[0] == "resolved"
        assert db.conn.execute("SELECT execution_status FROM directive_batch_items WHERE batch_id=?", (batch_id,)).fetchone()[0] == "success"
    finally:
        db.close()


def test_random_event_generation_obeys_monthly_cap_across_repeated_calls():
    """第二阶段：generate_random_events 不再独立生成事件，返回空列表。"""
    db, state = _board()
    try:
        ensure_templates_seeded(db)

        first = generate_random_events(state, db, max_per_turn=2)
        second = generate_random_events(state, db, max_per_turn=2)

        assert first == []
        assert second == []
        assert db.conn.execute("SELECT COUNT(*) FROM random_events WHERE turn=?", (state.turn,)).fetchone()[0] == 0
    finally:
        db.close()


def test_batch_decision_checkpoint_persists_and_resume_skips_completed_work():
    db, state = _board()
    try:
        draft_id = db.create_directive_draft(
            turn=state.turn, year=state.year, period=state.period,
            source_type="manual", directive_type="military", title="进攻江陵", target="进攻江陵",
            resources_json='{"ambush_chance": 0.8}',
        )
        batch_id = db.create_directive_batch(state.turn, state.year, state.period, "试探江陵", [draft_id])
        paused = PhasedExecutor(state, db, batch_id).execute()
        checkpoint = db.get_directive_batch_checkpoint(batch_id)
        assert paused.message == "需要玩家裁断"
        assert checkpoint["status"] == "pending"
        assert checkpoint["draft_id"] == draft_id

        db.resolve_directive_batch_checkpoint(batch_id, "继续进攻")
        resumed = PhasedExecutor(state, db, batch_id).execute()
        assert resumed.message == "批次执行完成"
        assert db.get_directive_batch_checkpoint(batch_id)["status"] == "completed"
        assert db.conn.execute("SELECT execution_status FROM directive_batch_items WHERE batch_id=?", (batch_id,)).fetchone()[0] == "success"
    finally:
        db.close()


def test_long_term_groups_are_progressive_and_loyalty_is_audited():
    db, state = _board()
    try:
        refresh_long_term_state(db, state)
        opening = {item["faction_key"]: item["status"] for item in long_term_summary(db, state)["factions"]}
        assert opening == {"veterans": "active", "jingzhou": "active", "local": "active", "yizhou": "locked"}

        before = db.conn.execute("SELECT loyalty FROM characters WHERE name='张飞'").fetchone()[0]
        after = adjust_character_loyalty(
            db, state, "张飞", -6, "擅离军令", source_kind="test", source_id="case-1"
        )
        assert after == before - 6
        log = db.conn.execute(
            "SELECT reason, source_kind FROM character_loyalty_logs WHERE character_name='张飞'"
        ).fetchone()
        assert tuple(log) == ("擅离军令", "test")

        db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='chengdu'")
        db.conn.commit()
        refresh_long_term_state(db, state)
        yizhou = next(item for item in long_term_summary(db, state)["factions"] if item["faction_key"] == "yizhou")
        assert yizhou["status"] == "active"
    finally:
        db.close()
