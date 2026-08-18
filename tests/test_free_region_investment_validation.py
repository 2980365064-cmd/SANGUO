"""自由区域投资裁决边界校验测试。"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.national_focus import (
    build_region_investment_adjudication_pack,
    _validate_free_region_investment,
    run_region_investment_ai_judge,
    FREE_INVESTMENT_BOUNDS,
    INVESTMENT_CATEGORIES,
)


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
    db.conn.commit()
    yield db
    db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def _build_pack(db, region_id="jiangxia", category="屯田粮仓"):
    return build_region_investment_adjudication_pack(db, _state(1), region_id, category)


def _make_proposal(**overrides):
    base = {
        "investment_action": "推进投资",
        "investment_category": "屯田粮仓",
        "progress_delta": 5,
        "resource_cost_modifier": 1.0,
        "feasibility": "high",
        "narrative": "投资进展顺利。",
        "reasoning": [],
        "risk_note": "",
    }
    base.update(overrides)
    return base


# ========== 边界裁剪 ==========


def test_progress_delta_clipped_upper(board):
    pack = _build_pack(board)
    result = _validate_free_region_investment(pack, _make_proposal(progress_delta=100))
    assert result["progress_delta"] == FREE_INVESTMENT_BOUNDS["progress_delta"][1]


def test_progress_delta_clipped_lower(board):
    pack = _build_pack(board)
    result = _validate_free_region_investment(pack, _make_proposal(progress_delta=-50))
    assert result["progress_delta"] == FREE_INVESTMENT_BOUNDS["progress_delta"][0]


def test_resource_cost_modifier_clipped(board):
    pack = _build_pack(board)
    result = _validate_free_region_investment(pack, _make_proposal(resource_cost_modifier=5.0))
    assert result["resource_cost_modifier"] == FREE_INVESTMENT_BOUNDS["resource_cost_modifier"][1]


def test_invalid_category_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="投资类别"):
        _validate_free_region_investment(pack, _make_proposal(investment_category="魔法建筑"))


# ========== feasibility=impossible ==========


def test_impossible_falls_back(board):
    pack = _build_pack(board)
    result = _validate_free_region_investment(pack, _make_proposal(
        feasibility="impossible", progress_delta=10,
    ))
    assert result["progress_delta"] == 0
    assert result["feasibility"] == "impossible"


# ========== 禁止文本 ==========


def test_forbidden_text_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="援军"):
        _validate_free_region_investment(pack, _make_proposal(narrative="援军帮助建设。"))


# ========== 事实一致性 ==========


def test_claims_high_support_but_low(board):
    pack = _build_pack(board)
    pack["facts"]["region"]["public_support"] = 30
    with pytest.raises(ValueError, match="民心高涨"):
        _validate_free_region_investment(pack, _make_proposal(reasoning=["民心高涨"]))


def test_claims_rich_but_poor(board):
    pack = _build_pack(board)
    pack["facts"]["metrics"]["军资"] = 10
    with pytest.raises(ValueError, match="资源充裕"):
        _validate_free_region_investment(pack, _make_proposal(reasoning=["资源充裕"]))


def test_not_controlled_positive_delta_clipped(board):
    pack = _build_pack(board)
    pack["facts"]["region"]["controlled_by"] = "cao_cao"
    result = _validate_free_region_investment(pack, _make_proposal(progress_delta=10))
    assert result["progress_delta"] == 0


# ========== 集成 ==========


def test_run_region_investment_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    result = run_region_investment_ai_judge(board, state, pack, _make_proposal(progress_delta=3))
    assert result["progress_delta"] == 3
