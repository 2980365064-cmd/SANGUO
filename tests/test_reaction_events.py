from ming_sim.db import GameDB
from ming_sim.models import GameState
from ming_sim.reactions import run_reaction_layer


def test_reactions_are_seeded_auditable_and_idempotent():
    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        draft = {"id": 1, "directive_type": "diplomatic", "title": "遣使孙权", "assignee": "诸葛亮", "target": "孙权"}
        first = run_reaction_layer(db, state, batch_id=7, drafts=[draft], intensity="standard")
        again = run_reaction_layer(db, state, batch_id=7, drafts=[draft], intensity="standard")
        assert first["created"] == 1
        assert again["created"] == 0
        row = db.conn.execute("SELECT seed, reaction_level, status, rule_facts_snapshot FROM reaction_events").fetchone()
        assert row["seed"]
        assert row["reaction_level"] in {"minor", "medium"}
        assert row["status"] in {"resolved", "suggested"}
        assert "孙权" in row["rule_facts_snapshot"]
    finally:
        db.close()


def test_contested_title_claim_becomes_major_pending_reaction_without_world_write():
    from ming_sim.identity import apply_identity_promotion

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        # 硬规则已记下僭越宣称；反应层只能请求裁断，不可再改写世界事实。
        apply_identity_promotion(db, state, "promote_hanzhong")
        draft = {
            "id": 2, "directive_type": "internal", "title": "进位汉中王", "target": "称号宣称",
            "resources_json": '{"sub_type":"identity_promotion","identity_action":"promote_hanzhong"}',
        }
        result = run_reaction_layer(db, state, batch_id=8, drafts=[draft], intensity="standard")
        row = db.conn.execute("SELECT reaction_level, status, validation_result FROM reaction_events WHERE batch_id=8").fetchone()
        pending = db.conn.execute("SELECT kind, subject_id, status FROM pending_adjudications").fetchone()
        assert result["pending_count"] == 1
        assert row["reaction_level"] == "major"
        assert row["status"] == "pending_decision"
        assert "pending_adjudication_id" in row["validation_result"]
        assert pending["kind"] == "reaction_event"
        assert pending["status"] == "pending_review"
    finally:
        db.close()


def test_minor_low_loyalty_reaction_applies_only_one_auditable_loyalty_risk():
    from ming_sim.reactions import apply_minor_reaction_effects

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        db.conn.execute("UPDATE characters SET loyalty=40 WHERE name='关羽'")
        db.conn.commit()
        effects = apply_minor_reaction_effects(db, state, {
            "directive_type": "military", "subject_context": {"character": {"name": "关羽", "loyalty": 40}},
        }, reaction_id=91)
        assert effects == [{"kind": "loyalty", "character": "关羽", "delta": -1}]
        assert db.conn.execute("SELECT loyalty FROM characters WHERE name='关羽'").fetchone()[0] == 39
        assert db.conn.execute("SELECT COUNT(*) FROM character_loyalty_logs WHERE source_id='reaction:91'").fetchone()[0] == 1
    finally:
        db.close()


def test_major_claim_choices_apply_exact_rule_effects_once():
    from ming_sim.identity import apply_identity_promotion
    from ming_sim.long_term import refresh_long_term_state
    from ming_sim.reactions import resolve_major_reaction

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        refresh_long_term_state(db, state)
        apply_identity_promotion(db, state, "promote_hanzhong")
        run_reaction_layer(db, state, batch_id=13, drafts=[{
            "id": 7, "directive_type": "internal", "title": "进位汉中王",
            "resources_json": '{"sub_type":"identity_promotion","identity_action":"promote_hanzhong"}',
        }], intensity="standard")
        reaction_id = db.conn.execute("SELECT id FROM reaction_events WHERE batch_id=13").fetchone()[0]
        pressure_before = db.conn.execute("SELECT external_pressure FROM political_claims").fetchone()[0]
        veterans_before = db.conn.execute("SELECT support FROM political_faction_states WHERE faction_key='veterans'").fetchone()[0]
        result = resolve_major_reaction(db, state, int(reaction_id), "安定朝议")
        assert result["applied_effects"]
        assert db.conn.execute("SELECT external_pressure FROM political_claims").fetchone()[0] == max(0, pressure_before - 3)
        assert db.conn.execute("SELECT support FROM political_faction_states WHERE faction_key='veterans'").fetchone()[0] == veterans_before + 2
        assert db.conn.execute("SELECT COUNT(*) FROM reputation_logs WHERE source_kind='reaction_decision'").fetchone()[0] == 1
        try:
            resolve_major_reaction(db, state, int(reaction_id), "安定朝议")
            assert False, "重复裁断必须被拒绝"
        except ValueError:
            pass
    finally:
        db.close()


def test_reaction_validator_rejects_forbidden_world_effect():
    from ming_sim.reactions import validate_reaction_proposal

    verdict = validate_reaction_proposal({
        "actor": "荆州士人", "reaction_kind": "diplomatic", "level": "minor", "motive": "试探",
        "narrative": "不可采纳", "allowed_effect_kind": "territory_change", "suggested_action": "", "audit_basis": {},
    })
    assert verdict["allowed"] is False
    assert "不允许" in verdict["reason"]

    verdict = validate_reaction_proposal({
        "actor": "荆州士人", "reaction_kind": "diplomatic", "level": "minor", "motive": "试探",
        "narrative": "不可采纳", "allowed_effect_kind": "none", "suggested_action": "", "audit_basis": {},
        "changes": [{"kind": "territory_change"}],
    })
    assert verdict["allowed"] is False
    assert "越权字段" in verdict["reason"]


def test_major_reaction_must_be_resolved_before_time_can_advance():
    from ming_sim.identity import apply_identity_promotion
    from ming_sim.reactions import has_pending_major_reactions, resolve_major_reaction

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        apply_identity_promotion(db, state, "promote_hanzhong")
        run_reaction_layer(db, state, batch_id=9, drafts=[{
            "id": 3, "directive_type": "internal", "title": "进位汉中王",
            "resources_json": '{"sub_type":"identity_promotion","identity_action":"promote_hanzhong"}',
        }], intensity="standard")
        reaction_id = db.conn.execute("SELECT id FROM reaction_events WHERE batch_id=9").fetchone()[0]
        assert has_pending_major_reactions(db) is True
        resolved = resolve_major_reaction(db, state, int(reaction_id), "安定朝议")
        assert resolved["status"] == "resolved"
        assert has_pending_major_reactions(db) is False
    finally:
        db.close()


def test_current_turn_reaction_is_visible_before_entering_next_month():
    from ming_sim.monthly_report import build_monthly_report

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        run_reaction_layer(db, state, batch_id=10, drafts=[
            {"id": 4, "directive_type": "diplomatic", "title": "遣使孙权", "target": "孙权"},
        ], intensity="standard")
        db.save_turn_report(state, "本回合回奏")
        report = build_monthly_report(db, state)
        reactions = next(section for section in report["sections"] if section["id"] == "reactions")
        assert report["turn"] == 3
        assert reactions["items"][0]["title"] == "孙权"
    finally:
        db.close()


def test_invalid_ai_reaction_creates_audit_only_not_suggestion(monkeypatch):
    import ming_sim.reactions as reactions

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        monkeypatch.setattr(reactions, "_llm_reaction_proposal", lambda *_args: ({"changes": []}, "llm"))
        reactions.run_reaction_layer(db, state, batch_id=11, drafts=[
            {"id": 5, "directive_type": "diplomatic", "title": "遣使孙权", "target": "孙权"},
        ], intensity="standard", llm_config=object())
        row = db.conn.execute("SELECT status FROM reaction_events WHERE batch_id=11").fetchone()
        assert row["status"] == "rejected"
        assert db.conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0] == 0
    finally:
        db.close()


def test_reaction_context_contains_actor_traits_factions_and_knowledge_scope():
    from ming_sim.long_term import refresh_long_term_state

    db = GameDB(":memory:")
    db.seed_static_data()
    state = GameState(year=208, period=8, turn=3, metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40})
    try:
        refresh_long_term_state(db, state)
        db.conn.execute("UPDATE characters SET loyalty=31 WHERE name='关羽'")
        db.conn.execute("UPDATE political_faction_states SET status='active' WHERE faction_key='veterans'")
        db.conn.commit()
        run_reaction_layer(db, state, batch_id=12, drafts=[{
            "id": 6, "directive_type": "military", "title": "密令整军", "target": "江陵",
            "resources_json": '{"sub_type":"secret_order","is_secret":true}',
        }], intensity="standard")
        row = db.conn.execute("SELECT rule_facts_snapshot FROM reaction_events WHERE batch_id=12").fetchone()
        import json
        facts = json.loads(row["rule_facts_snapshot"])
        context = facts["subject_context"]
        assert context["knowledge_scope"] == "密令知情范围"
        assert "character" in context
        assert "recent_loyalty" in context
        assert context["active_factions"]
    finally:
        db.close()
