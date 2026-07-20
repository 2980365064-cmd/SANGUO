from types import SimpleNamespace

import pytest

import ming_sim.adjudication as adjudication_module
from ming_sim.adjudication import attach_adjudication_runtime, run_adjudication
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.historical_events import (
    evaluate_historical_event,
    historical_timeline_preview,
    resolve_world_events_for_turn,
    resolve_historical_event,
)
from ming_sim.monthly_report import build_monthly_report
from ming_sim.issues import bind_content, gather_candidate_events


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(year=208, month=8, turn=1):
    return SimpleNamespace(
        year=year,
        period=month,
        turn=turn,
        metrics={"军资": 60, "粮秣": 60, "民望": 50, "名分": 65, "军心": 65, "士族支持": 40},
    )


def test_content_has_exactly_fifteen_approved_historical_cards(board):
    assert len(board.content.events) == 15
    assert [event.id for event in board.content.events] == [
        "xinye_aftermath", "sun_liu_alliance", "red_cliffs", "jingnan_campaign",
        "sun_lady_marriage", "enter_yizhou", "chengdu_surrender", "xiangshui_division",
        "hanzhong_campaign", "king_of_hanzhong", "jingzhou_collapse", "cao_pi_usurpation",
        "chengdu_enthronement", "eastern_campaign_yiling", "baidi_entrustment",
    ]
    assert all(event.is_historical for event in board.content.events)
    assert all(event.roles and event.variants for event in board.content.events)


def test_lifecycle_moves_from_scheduled_to_eligible(board):
    before = evaluate_historical_event(board, _state(208, 7), "sun_liu_alliance")
    assert before["status"] == "scheduled"
    open_window = evaluate_historical_event(board, _state(208, 9), "sun_liu_alliance")
    assert open_window["status"] == "eligible"
    assert open_window["participants"]["刘备使者"] == "诸葛亮"


def test_dead_primary_uses_living_alternate_and_marks_adapted(board):
    board.conn.execute("UPDATE characters SET status='dead' WHERE name='诸葛亮'")
    result = evaluate_historical_event(board, _state(208, 9), "sun_liu_alliance")
    assert result["status"] == "adapted"
    assert result["participants"]["刘备使者"] == "孙乾"
    assert "诸葛亮" in result["reason"]


def test_no_living_candidate_supersedes_event_and_records_chronicle(board):
    board.conn.execute(
        "UPDATE characters SET status='dead' WHERE name IN ('诸葛亮','孙乾','糜竺')"
    )
    result = evaluate_historical_event(board, _state(208, 9), "sun_liu_alliance")
    assert result["status"] == "superseded"
    chronicle = board.conn.execute(
        "SELECT status, summary FROM historical_chronicle WHERE event_id='sun_liu_alliance'"
    ).fetchone()
    assert chronicle["status"] == "superseded"
    assert "无合理候补" in chronicle["summary"]


def test_past_window_expires_once_and_does_not_repeat(board):
    first = evaluate_historical_event(board, _state(209, 2), "red_cliffs")
    second = evaluate_historical_event(board, _state(209, 3, turn=2), "red_cliffs")
    assert first["status"] == "expired"
    assert second["status"] == "expired"
    assert board.conn.execute(
        "SELECT COUNT(*) FROM historical_chronicle WHERE event_id='red_cliffs'"
    ).fetchone()[0] == 1


def test_resolve_variant_applies_world_effect_and_cannot_repeat(board):
    state = _state(208, 9)
    evaluate_historical_event(board, state, "sun_liu_alliance")
    before = state.metrics["名分"]
    result = resolve_historical_event(board, state, "sun_liu_alliance", "alliance_formed")
    assert result["status"] == "resolved"
    assert result["variant_id"] == "alliance_formed"
    assert state.metrics["名分"] > before
    again = resolve_historical_event(board, state, "sun_liu_alliance", "alliance_formed")
    assert again["status"] == "resolved"
    assert state.metrics["名分"] == result["metrics_after"]["名分"]


def test_twelve_month_preview_never_leaks_outcomes_deaths_or_tactics(board):
    preview = historical_timeline_preview(board, _state(208, 8), months=12)
    assert preview
    assert {"id", "title", "window", "status"} == set(preview[0])
    serialized = str(preview)
    for forbidden in ("胜利", "失败", "死亡", "病逝", "火攻", "白衣渡江"):
        assert forbidden not in serialized


def test_issue_candidate_pool_only_receives_rule_eligible_or_adapted_cards(board):
    bind_content(board.content)
    state = _state(208, 9)
    candidates = {event.id for event in gather_candidate_events(state, board)}
    assert "sun_liu_alliance" in candidates
    board.conn.execute(
        "UPDATE characters SET status='dead' WHERE name IN ('诸葛亮','孙乾','糜竺')"
    )
    candidates = {event.id for event in gather_candidate_events(state, board)}
    assert "sun_liu_alliance" not in candidates


def test_world_event_dispatcher_accepts_legal_variant_choice(board, monkeypatch):
    state = _state(208, 9)
    evaluate_historical_event(board, state, "sun_liu_alliance")

    def fake_judge(_llm_config, _agno_db, pack, *, tag):
        assert pack["kind"] == "world_event"
        assert pack["subject_id"] == "sun_liu_alliance"
        return {
            "outcome": "resolve_event_variant",
            "variant_id": "limited_cooperation",
            "reason": "鲁肃可成其议，但互信尚浅。",
            "risk_note": "后续荆州归属仍留争端。",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
    result = run_adjudication(
        board,
        state,
        "world_event",
        "sun_liu_alliance",
        llm_config=object(),
        agno_db=None,
    )

    assert result["status"] == "validated"
    assert result["validated"]["variant_id"] == "limited_cooperation"


def test_resolve_world_events_applies_validated_variant_and_monthly_report_shows_it(board, monkeypatch):
    state = _state(208, 9)
    attach_adjudication_runtime(state, object(), None)
    before = state.metrics["名分"]

    def fake_judge(_llm_config, _agno_db, pack, *, tag):
        if pack["subject_id"] != "sun_liu_alliance":
            return {"outcome": "wait_for_window", "changes": []}
        return {
            "outcome": "resolve_event_variant",
            "variant_id": "alliance_formed",
            "reason": "曹操南迫，孙刘合则两利。",
            "risk_note": "联盟虽成，荆州仍需另议。",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
    results = resolve_world_events_for_turn(board, state)

    assert any(item["event_id"] == "sun_liu_alliance" and item["status"] == "resolved" for item in results)
    row = board.conn.execute(
        "SELECT status, variant_id, reason FROM historical_event_states WHERE event_id='sun_liu_alliance'"
    ).fetchone()
    assert row["status"] == "resolved"
    assert row["variant_id"] == "alliance_formed"
    assert "AI裁判依据" in row["reason"]
    assert state.metrics["名分"] > before

    report = build_monthly_report(board, SimpleNamespace(year=208, period=10, turn=2, metrics=state.metrics))
    world = next(section for section in report["sections"] if section["id"] == "world")
    assert any("AI裁判依据" in item["summary"] for item in world["items"])


def test_resolve_world_events_without_llm_only_updates_lifecycle(board):
    state = _state(208, 9)
    results = resolve_world_events_for_turn(board, state)

    assert any(item["event_id"] == "sun_liu_alliance" and item["status"] == "eligible" for item in results)
    row = board.conn.execute(
        "SELECT status, variant_id FROM historical_event_states WHERE event_id='sun_liu_alliance'"
    ).fetchone()
    assert row["status"] == "eligible"
    assert row["variant_id"] == ""


def test_world_event_rejects_unknown_variant_and_forbidden_ending_change(board, monkeypatch):
    state = _state(208, 9)
    attach_adjudication_runtime(state, object(), None)

    def bad_judge(_llm_config, _agno_db, pack, *, tag):
        if pack["subject_id"] != "sun_liu_alliance":
            return {"outcome": "review_world_state", "changes": []}
        return {
            "outcome": "resolve_event_variant",
            "variant_id": "invented_miracle",
            "ending_status": "unified_victory",
            "reason": "孙刘结盟后天下立刻归一。",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_llm", bad_judge)
    results = resolve_world_events_for_turn(board, state)

    assert any(item.get("status") == "pending_review" for item in results)
    row = board.conn.execute(
        "SELECT status, variant_id FROM historical_event_states WHERE event_id='sun_liu_alliance'"
    ).fetchone()
    assert row["status"] == "eligible"
    assert row["variant_id"] == ""
    assert board.conn.execute(
        "SELECT COUNT(*) FROM pending_adjudications WHERE kind='world_event' AND subject_id='sun_liu_alliance'"
    ).fetchone()[0] == 1


def test_resolve_world_events_does_not_repeat_terminal_event(board, monkeypatch):
    state = _state(208, 9)
    evaluate_historical_event(board, state, "sun_liu_alliance")
    resolve_historical_event(board, state, "sun_liu_alliance", "alliance_formed")
    called_subjects = []
    attach_adjudication_runtime(state, object(), None)

    def fake_judge(_llm_config, _agno_db, pack, *, tag):
        called_subjects.append(pack["subject_id"])
        return {"outcome": "review_world_state", "changes": []}

    monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
    results = resolve_world_events_for_turn(board, state)

    assert not any(item["event_id"] == "sun_liu_alliance" and item.get("adjudication_status") == "validated" for item in results)
    assert "sun_liu_alliance" not in called_subjects
    assert board.conn.execute(
        "SELECT variant_id FROM historical_event_states WHERE event_id='sun_liu_alliance'"
    ).fetchone()[0] == "alliance_formed"
