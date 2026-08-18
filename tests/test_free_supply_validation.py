"""自由补给裁决边界校验测试。

覆盖：
- delta 边界裁剪（supply_delta, morale_delta, fatigue_delta）
- 事实一致性检查（粮仓可达性、携粮量、断粮状态）
- 禁止文本拦截
- feasibility=impossible 回退
- 无粮仓无携粮时 supply_delta 不得为正
"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.supply import (
    build_supply_adjudication_pack,
    _validate_free_supply,
    run_supply_ai_judge,
    FREE_SUPPLY_BOUNDS,
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


def _build_pack(db, army_id="liubei_main", requested_amount=0):
    return build_supply_adjudication_pack(db, _state(1), army_id, requested_amount=requested_amount)


# ========== 基础边界裁剪 ==========


def test_supply_delta_clipped_to_upper_bound(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "大量补给",
        "supply_delta": 100,
        "morale_delta": 0,
        "fatigue_delta": 0,
        "feasibility": "high",
        "narrative": "粮草充足。",
        "reasoning": [],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["supply_delta"] == FREE_SUPPLY_BOUNDS["supply_delta"][1]


def test_supply_delta_clipped_to_lower_bound(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "补给中断",
        "supply_delta": -100,
        "morale_delta": 0,
        "fatigue_delta": 0,
        "feasibility": "medium",
        "narrative": "补给线被截。",
        "reasoning": [],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["supply_delta"] == FREE_SUPPLY_BOUNDS["supply_delta"][0]


def test_morale_delta_clipped(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "士气高涨",
        "supply_delta": 0,
        "morale_delta": 50,
        "fatigue_delta": 0,
        "feasibility": "medium",
        "narrative": "粮草到，士气升。",
        "reasoning": [],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["morale_delta"] == FREE_SUPPLY_BOUNDS["morale_delta"][1]


def test_fatigue_delta_clipped(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "疲劳缓解",
        "supply_delta": 0,
        "morale_delta": 0,
        "fatigue_delta": -50,
        "feasibility": "medium",
        "narrative": "休整充分。",
        "reasoning": [],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["fatigue_delta"] == FREE_SUPPLY_BOUNDS["fatigue_delta"][0]


def test_deltas_within_bounds_accepted(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "正常补给",
        "supply_delta": 10,
        "morale_delta": 5,
        "fatigue_delta": -3,
        "feasibility": "high",
        "narrative": "本月补给顺利。",
        "reasoning": ["粮仓可达", "携粮充足"],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["supply_delta"] == 10
    assert result["morale_delta"] == 5
    assert result["fatigue_delta"] == -3


# ========== feasibility=impossible 回退 ==========


def test_impossible_falls_back_to_status_quo(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "特殊补给",
        "supply_delta": 20,
        "feasibility": "impossible",
        "narrative": "方案不可行。",
        "reasoning": ["条件不满足"],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["supply_delta"] == 0
    assert result["morale_delta"] == 0
    assert result["fatigue_delta"] == 0
    assert result["feasibility"] == "impossible"


# ========== 禁止文本 ==========


def test_forbidden_text_in_narrative_rejected(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "补给",
        "supply_delta": 0,
        "feasibility": "medium",
        "narrative": "援军带来大量补给。",
        "reasoning": [],
    }
    with pytest.raises(ValueError, match="援军"):
        _validate_free_supply(pack, proposal)


def test_forbidden_text_in_reasoning_rejected(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "补给",
        "supply_delta": 0,
        "feasibility": "medium",
        "narrative": "正常补给。",
        "reasoning": ["因为援军到达"],
    }
    with pytest.raises(ValueError, match="援军"):
        _validate_free_supply(pack, proposal)


def test_forbidden_spawn_supply_rejected(board):
    pack = _build_pack(board)
    proposal = {
        "supply_action": "补给",
        "supply_delta": 10,
        "feasibility": "medium",
        "narrative": "天降粮草，补给满。",
        "reasoning": [],
    }
    with pytest.raises(ValueError):
        _validate_free_supply(pack, proposal)


# ========== 事实一致性 ==========


def test_claims_granary_reachable_but_none_exists(board):
    pack = _build_pack(board)
    # 确保该军队无粮仓可达
    # 修改 pack facts 来模拟
    pack["facts"]["reachable_granary"] = None
    proposal = {
        "supply_action": "粮仓补给",
        "supply_delta": 10,
        "feasibility": "medium",
        "narrative": "从粮仓补给。",
        "reasoning": ["粮仓可达", "可就近补给"],
    }
    with pytest.raises(ValueError, match="粮仓可达"):
        _validate_free_supply(pack, proposal)


def test_claims_supply_sufficient_but_low(board):
    pack = _build_pack(board)
    pack["facts"]["army"]["supply"] = 5
    pack["facts"]["carried_supply_cost"] = 20
    proposal = {
        "supply_action": "消耗携粮",
        "supply_delta": 0,
        "feasibility": "medium",
        "narrative": "携粮充足。",
        "reasoning": ["携粮充足", "足以支撑"],
    }
    with pytest.raises(ValueError, match="携粮充足"):
        _validate_free_supply(pack, proposal)


def test_claims_starvation_but_has_supply_and_granary(board):
    pack = _build_pack(board)
    pack["facts"]["army"]["supply"] = 30
    pack["facts"]["army"]["starvation_turns"] = 0
    pack["facts"]["reachable_granary"] = {"id": "jiangxia", "name": "江夏"}
    proposal = {
        "supply_action": "断粮",
        "supply_delta": -10,
        "feasibility": "medium",
        "narrative": "军队断粮。",
        "reasoning": ["断粮", "补给线中断"],
    }
    with pytest.raises(ValueError, match="断粮"):
        _validate_free_supply(pack, proposal)


# ========== 条件约束 ==========


def test_no_granary_no_supply_positive_delta_clipped_to_zero(board):
    pack = _build_pack(board)
    pack["facts"]["reachable_granary"] = None
    pack["facts"]["army"]["supply"] = 0
    proposal = {
        "supply_action": "紧急补给",
        "supply_delta": 15,
        "morale_delta": 0,
        "fatigue_delta": 0,
        "feasibility": "medium",
        "narrative": "紧急调配。",
        "reasoning": [],
    }
    result = _validate_free_supply(pack, proposal)
    assert result["supply_delta"] == 0


# ========== 集成：run_supply_ai_judge ==========


def test_run_supply_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    proposal = {
        "supply_action": "正常补给",
        "supply_delta": 5,
        "morale_delta": 2,
        "fatigue_delta": -1,
        "feasibility": "high",
        "narrative": "补给顺利。",
        "reasoning": [],
    }
    result = run_supply_ai_judge(board, state, pack, proposal)
    assert result["supply_action"] == "正常补给"
    assert result["supply_delta"] == 5
