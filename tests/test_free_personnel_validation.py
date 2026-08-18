"""自由人事裁决边界校验测试。"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.government import (
    build_personnel_adjudication_pack,
    _validate_free_personnel,
    run_personnel_ai_judge,
    FREE_PERSONNEL_BOUNDS,
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


def _build_pack(db, office_key="chief_strategist", candidate="诸葛亮"):
    return build_personnel_adjudication_pack(db, _state(1), office_key, candidate)


def _make_proposal(**overrides):
    base = {
        "personnel_action": "appoint_candidate",
        "candidate": "诸葛亮",
        "efficiency_delta": 10,
        "feasibility": "high",
        "narrative": "任命得当，效率提升。",
        "reasoning": [],
        "risk_note": "",
    }
    base.update(overrides)
    return base


# ========== 边界裁剪 ==========


def test_efficiency_delta_clipped_upper(board):
    pack = _build_pack(board)
    result = _validate_free_personnel(pack, _make_proposal(efficiency_delta=100))
    assert result["efficiency_delta"] == FREE_PERSONNEL_BOUNDS["efficiency_delta"][1]


def test_efficiency_delta_clipped_lower(board):
    pack = _build_pack(board)
    result = _validate_free_personnel(pack, _make_proposal(efficiency_delta=-50))
    assert result["efficiency_delta"] == FREE_PERSONNEL_BOUNDS["efficiency_delta"][0]


# ========== feasibility=impossible ==========


def test_impossible_falls_back(board):
    pack = _build_pack(board)
    result = _validate_free_personnel(pack, _make_proposal(feasibility="impossible"))
    assert result["efficiency_delta"] == 0
    assert result["candidate"] == ""


# ========== 禁止文本 ==========


def test_forbidden_text_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="死亡"):
        _validate_free_personnel(pack, _make_proposal(narrative="前任死亡后补位。"))


# ========== 事实一致性 ==========


def test_claims_capable_but_low_ability(board):
    pack = _build_pack(board)
    pack["facts"]["candidate"]["ability_value"] = 40
    with pytest.raises(ValueError, match="能力出众"):
        _validate_free_personnel(pack, _make_proposal(reasoning=["候选人能力出众"]))


def test_claims_loyal_but_low_loyalty(board):
    pack = _build_pack(board)
    pack["facts"]["candidate"]["loyalty"] = 30
    with pytest.raises(ValueError, match="忠诚可靠"):
        _validate_free_personnel(pack, _make_proposal(reasoning=["忠诚可靠"]))


def test_appoint_non_liubei_rejected(board):
    pack = _build_pack(board)
    pack["facts"]["candidate"]["power_id"] = "cao_cao"
    with pytest.raises(ValueError, match="不属于刘备"):
        _validate_free_personnel(pack, _make_proposal(personnel_action="appoint_candidate"))


# ========== 集成 ==========


def test_run_personnel_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    result = run_personnel_ai_judge(board, state, pack, _make_proposal(efficiency_delta=5))
    assert result["efficiency_delta"] == 5
