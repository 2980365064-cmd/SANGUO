"""自由世界事件裁决边界校验测试。"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.historical_events import (
    build_world_event_adjudication_pack,
    _validate_free_world_event,
    run_world_event_ai_judge,
    FREE_WORLD_EVENT_BOUNDS,
)


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    yield db
    db.close()


def _state(turn=1):
    return SimpleNamespace(
        turn=turn, year=208, period=turn,
        metrics={"军资": 40, "粮秣": 40, "民望": 72, "名分": 78, "军心": 70, "士族支持": 35},
    )


def _build_pack(db, event_id="sun_liu_alliance"):
    return build_world_event_adjudication_pack(db, _state(1), event_id=event_id)


def _make_proposal(**overrides):
    base = {
        "event_action": "keep_scheduled",
        "urgency_delta": 0,
        "feasibility": "medium",
        "narrative": "事件按计划推进。",
        "reasoning": [],
        "risk_note": "",
        "variant_id": "",
    }
    base.update(overrides)
    return base


# ========== 边界裁剪 ==========


def test_urgency_delta_clipped_upper(board):
    pack = _build_pack(board)
    result = _validate_free_world_event(pack, _make_proposal(urgency_delta=50))
    assert result["urgency_delta"] == FREE_WORLD_EVENT_BOUNDS["urgency_delta"][1]


def test_urgency_delta_clipped_lower(board):
    pack = _build_pack(board)
    result = _validate_free_world_event(pack, _make_proposal(urgency_delta=-50))
    assert result["urgency_delta"] == FREE_WORLD_EVENT_BOUNDS["urgency_delta"][0]


# ========== feasibility=impossible ==========


def test_impossible_falls_back(board):
    pack = _build_pack(board)
    result = _validate_free_world_event(pack, _make_proposal(feasibility="impossible"))
    assert result["urgency_delta"] == 0
    assert result["feasibility"] == "impossible"


# ========== 禁止字段 ==========


def test_forbidden_field_effects_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="非法字段"):
        _validate_free_world_event(pack, _make_proposal(effects={"power_collapse": "sun_quan"}))


def test_forbidden_field_ending_status_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="非法字段"):
        _validate_free_world_event(pack, _make_proposal(ending_status="victory"))


# ========== 禁止文本 ==========


def test_forbidden_annihilation_in_narrative(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="灭国"):
        _validate_free_world_event(pack, _make_proposal(narrative="曹操灭国。"))


def test_forbidden_death_in_reasoning(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="身死"):
        _validate_free_world_event(pack, _make_proposal(reasoning=["刘备身死"]))


# ========== 事实一致性 ==========


def test_claims_window_open_but_not_eligible(board):
    pack = _build_pack(board)
    # 修改事件状态为非 eligible
    selected = pack["facts"]["selected_event"]
    if isinstance(selected, dict) and "state" in selected:
        selected["state"]["status"] = "resolved"
    with pytest.raises(ValueError, match="窗口已开"):
        _validate_free_world_event(pack, _make_proposal(reasoning=["事件窗口已开"]))


# ========== 集成 ==========


def test_run_world_event_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    result = run_world_event_ai_judge(board, state, pack, _make_proposal())
    assert result["event_action"] == "keep_scheduled"
