from types import SimpleNamespace

import pytest

import ming_sim.adjudication as adjudication_module
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.adjudication import attach_adjudication_runtime
from ming_sim.diplomacy import accept_treaty, breach_treaty, propose_treaty


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state():
    return SimpleNamespace(
        turn=1,
        year=208,
        period=7,
        metrics={"军资": 40, "粮秣": 40, "民望": 72, "名分": 78, "军心": 70, "士族支持": 35},
    )


def test_opening_relations_store_six_independent_dimensions(board):
    relation = board.get_diplomatic_relation("liu_bei", "sun_quan")
    assert relation["public_relation"] > 0
    assert relation["trust"] > 0
    assert isinstance(relation["obligations"], list)
    assert set(relation["territorial_claims"]) == {"liu_bei", "sun_quan"}
    assert isinstance(relation["marriage_hostages"], dict)
    assert isinstance(relation["military_coordination"], int)

    treaty = next(
        item for item in board.list_diplomacy_treaties("active")
        if item["treaty_key"] == "sun_liu_anti_cao_208"
    )
    assert set(treaty["terms"]) >= {
        "obligations", "territorial_claims", "marriage_hostages", "military_coordination"
    }


def test_diplomacy_attribute_changes_acceptance_chance(board):
    common = {
        "treaty_key": "test_envoy",
        "treaty_type": "互市",
        "obligations": [{"type": "开放互市"}],
        "territorial_claims": {},
        "marriage_hostages": {},
        "military_coordination": 10,
    }
    low = propose_treaty(board, "liu_bei", "sun_quan", {**common, "envoy": "张飞"})
    high = propose_treaty(board, "liu_bei", "sun_quan", {**common, "treaty_key": "test_envoy_2", "envoy": "诸葛亮"})
    assert high["acceptance_chance"] > low["acceptance_chance"]
    assert board.conn.execute(
        "SELECT 1 FROM character_attribute_logs WHERE character_name='诸葛亮' AND context='negotiation'"
    ).fetchone()


def test_high_diplomacy_cannot_override_conflicting_jingzhou_claim(board):
    result = propose_treaty(
        board,
        "liu_bei",
        "sun_quan",
        {
            "treaty_key": "demand_jingnan",
            "treaty_type": "割让",
            "envoy": "诸葛亮",
            "obligations": [],
            "territorial_claims": {"cede": ["jingnan"], "from": "sun_quan"},
            "marriage_hostages": {},
            "military_coordination": 0,
        },
    )
    assert result["status"] == "blocked"
    assert any("荆州" in item or "领土主张" in item for item in result["hard_blockers"])


def test_marriage_claims_obligations_and_coordination_remain_separate_clauses(board):
    proposal = propose_treaty(
        board,
        "liu_bei",
        "sun_quan",
        {
            "treaty_key": "sun_shangxiang_marriage",
            "treaty_type": "政治联姻",
            "envoy": "诸葛亮",
            "obligations": [{"type": "互不攻伐"}],
            "territorial_claims": {"settlement": {"jiangxia": "liu_bei"}},
            "marriage_hostages": {
                "type": "marriage", "persons": ["刘备", "孙尚香"], "status": "active"
            },
            "military_coordination": 65,
        },
    )
    accepted = accept_treaty(board, proposal["treaty_id"])
    assert accepted["status"] == "active"
    relation = board.get_diplomatic_relation("liu_bei", "sun_quan")
    assert relation["obligations"] == [{"type": "互不攻伐"}]
    assert relation["territorial_claims"]["settlement"]["jiangxia"] == "liu_bei"
    assert relation["marriage_hostages"]["persons"] == ["刘备", "孙尚香"]
    assert relation["military_coordination"] == 65
    assert board.conn.execute(
        "SELECT status FROM family_relations WHERE person_a='刘备' AND person_b='孙尚香' "
        "AND relation_type='political_marriage'"
    ).fetchone()[0] == "active"


def test_breach_automatically_settles_trust_legitimacy_gentry_marriage_and_war(board):
    proposal = propose_treaty(
        board,
        "liu_bei",
        "sun_quan",
        {
            "treaty_key": "breach_marriage",
            "treaty_type": "政治联姻",
            "envoy": "诸葛亮",
            "obligations": [{"type": "互不攻伐"}, {"type": "共同抗曹"}],
            "territorial_claims": {"settlement": {"jiangxia": "liu_bei"}},
            "marriage_hostages": {
                "type": "marriage", "persons": ["刘备", "孙尚香"], "status": "active"
            },
            "military_coordination": 70,
        },
    )
    accept_treaty(board, proposal["treaty_id"])
    before = board.get_diplomatic_relation("liu_bei", "sun_quan")
    state = _state()

    result = breach_treaty(
        board,
        state,
        proposal["treaty_id"],
        actor="liu_bei",
        action={"type": "attack", "target_node": "jiangling"},
    )

    after = board.get_diplomatic_relation("liu_bei", "sun_quan")
    assert result["status"] == "breached"
    assert after["trust"] == max(0, before["trust"] - 30)
    assert after["marriage_hostages"]["status"] == "broken"
    assert board.conn.execute(
        "SELECT status FROM family_relations WHERE person_a='刘备' AND person_b='孙尚香' "
        "AND relation_type='political_marriage'"
    ).fetchone()[0] == "broken"
    assert after["status"] == "war"
    assert state.metrics["名分"] == 68
    assert state.metrics["士族支持"] == 27
    assert result["war_triggered"] is True
    assert board.conn.execute(
        "SELECT COUNT(*) FROM diplomacy_logs WHERE treaty_id=?", (proposal["treaty_id"],)
    ).fetchone()[0] >= 4


def test_diplomacy_model_feedback_is_logged_without_activating_treaty(board, monkeypatch):
    state = _state()
    attach_adjudication_runtime(state, object(), None)

    def fake_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        assert kind == "diplomacy"
        return {
            "outcome": "counter_offer",
            "reason": "孙权愿共抗曹，但要先明荆州归属。",
            "recommended_followup": "召使臣改条款",
            "changes": [],
        }

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", fake_judge)
    proposal = propose_treaty(
        board,
        "liu_bei",
        "sun_quan",
        {
            "treaty_key": "model_counter_offer",
            "treaty_type": "盟约",
            "envoy": "诸葛亮",
            "obligations": [{"type": "共同抗曹"}],
            "territorial_claims": {},
            "marriage_hostages": {},
            "military_coordination": 45,
        },
        state=state,
    )

    assert proposal["status"] == "proposed"
    assert proposal["adjudication"]["status"] == "validated"
    assert board.conn.execute(
        "SELECT status FROM diplomacy_treaties WHERE id=?", (proposal["treaty_id"],)
    ).fetchone()[0] == "proposed"
    log = board.conn.execute(
        "SELECT field, new_value, reason FROM diplomacy_logs WHERE treaty_id=? ORDER BY id DESC LIMIT 1",
        (proposal["treaty_id"],),
    ).fetchone()
    assert log["field"] == "ai_judge"
    assert "counter_offer" in log["new_value"]
    assert "AI裁判依据" in log["reason"]


def test_diplomacy_model_illegal_activation_goes_pending_review(board, monkeypatch):
    state = _state()
    attach_adjudication_runtime(state, object(), None)

    def bad_judge(db, state, llm_config, agno_db, kind, subject_id, *, player_intent="", **kwargs):
        return {"outcome": "accept_terms", "narrative": "条约生效并割让江夏。", "changes": []}

    monkeypatch.setattr(adjudication_module, "run_adjudication_with_tools", bad_judge)
    proposal = propose_treaty(
        board,
        "liu_bei",
        "sun_quan",
        {
            "treaty_key": "model_illegal_activation",
            "treaty_type": "盟约",
            "envoy": "诸葛亮",
            "obligations": [{"type": "共同抗曹"}],
            "territorial_claims": {},
            "marriage_hostages": {},
            "military_coordination": 45,
        },
        state=state,
    )

    assert proposal["status"] == "proposed"
    assert proposal["adjudication"]["status"] == "pending_review"
    assert board.conn.execute(
        "SELECT COUNT(*) FROM pending_adjudications WHERE kind='diplomacy'"
    ).fetchone()[0] == 1
