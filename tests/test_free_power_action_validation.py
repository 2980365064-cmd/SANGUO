"""自由势力行动裁决边界校验测试。"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.power_ai import (
    build_power_action_adjudication_pack,
    _validate_free_power_action,
    run_power_action_ai_judge,
    FREE_POWER_ACTION_BOUNDS,
    ACTION_TYPES,
)


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    yield db
    db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def _build_pack(db, power_id="cao_cao"):
    return build_power_action_adjudication_pack(db, _state(1), power_id)


def _make_proposal(**overrides):
    base = {
        "power_action": "resupply",
        "action_type": "resupply",
        "priority": "normal",
        "risk_level": "low",
        "feasibility": "high",
        "narrative": "曹军补充给养。",
        "reasoning": [],
        "risk_note": "",
    }
    base.update(overrides)
    return base


# ========== 枚举校验 ==========


def test_invalid_priority_defaults_to_normal(board):
    pack = _build_pack(board)
    result = _validate_free_power_action(pack, _make_proposal(priority="ultra"))
    assert result["priority"] == "normal"


def test_invalid_risk_level_defaults_to_medium(board):
    pack = _build_pack(board)
    result = _validate_free_power_action(pack, _make_proposal(risk_level="extreme"))
    assert result["risk_level"] == "medium"


def test_invalid_action_type_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="行动类型"):
        _validate_free_power_action(pack, _make_proposal(action_type="summon_dragon"))


# ========== feasibility=impossible ==========


def test_impossible_falls_back(board):
    pack = _build_pack(board)
    result = _validate_free_power_action(pack, _make_proposal(feasibility="impossible"))
    assert result["action_type"] == "no_action"
    assert result["priority"] == "low"


# ========== 禁止文本 ==========


def test_forbidden_text_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="援军"):
        _validate_free_power_action(pack, _make_proposal(narrative="援军到达。"))


# ========== 事实一致性 ==========


def test_claims_military_superiority_but_weak(board):
    pack = _build_pack(board)
    pack["facts"]["power"]["military_strength"] = 20
    with pytest.raises(ValueError, match="军力优势"):
        _validate_free_power_action(pack, _make_proposal(reasoning=["军力优势"]))


def test_claims_well_supplied_but_low(board):
    pack = _build_pack(board)
    pack["facts"]["power"]["supply"] = 10
    with pytest.raises(ValueError, match="补给充足"):
        _validate_free_power_action(pack, _make_proposal(reasoning=["补给充足"]))


def test_claims_isolated_but_has_ally(board):
    pack = _build_pack(board)
    pack["facts"]["relations"] = [{"status": "allied", "power_a": "cao_cao", "power_b": "sun_quan"}]
    with pytest.raises(ValueError, match="外交孤立"):
        _validate_free_power_action(pack, _make_proposal(reasoning=["外交孤立"]))


# ========== 禁止字段 ==========


def test_forbidden_field_region_control_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="非法字段"):
        _validate_free_power_action(pack, _make_proposal(region_control={"jiangxia": "cao_cao"}))


# ========== 集成 ==========


def test_run_power_action_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    result = run_power_action_ai_judge(board, state, pack, _make_proposal())
    assert result["action_type"] == "resupply"
