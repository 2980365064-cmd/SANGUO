"""自由围城裁决边界校验测试。

覆盖：
- progress_delta / casualty_pct 边界裁剪
- 事实一致性检查（守军士气、城防、民心、破城进度）
- 禁止文本拦截
- feasibility=impossible 回退
"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.siege import (
    build_siege_adjudication_pack,
    _validate_free_siege,
    run_siege_ai_judge,
    FREE_SIEGE_BOUNDS,
)


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    # 创建一个围城记录供测试使用
    db.conn.execute("""
        INSERT INTO sieges (target_node, attacker_army_id, defender_power, status, progress, started_turn, last_turn, details)
        VALUES ('ji', 'liubei_main', 'cao_cao', 'active', 30, 1, 1, '{}')
    """)
    db.conn.commit()
    yield db
    db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def _build_pack(db, siege_id=1):
    return build_siege_adjudication_pack(db, _state(1), siege_id)


def _make_proposal(**overrides):
    base = {
        "siege_action": "加紧攻城",
        "progress_delta": 10,
        "casualty_pct": 5,
        "feasibility": "high",
        "narrative": "围城进展顺利。",
        "reasoning": [],
        "risk_note": "",
    }
    base.update(overrides)
    return base


# ========== 边界裁剪 ==========


def test_progress_delta_clipped_upper(board):
    pack = _build_pack(board)
    result = _validate_free_siege(pack, _make_proposal(progress_delta=100))
    assert result["progress_delta"] == FREE_SIEGE_BOUNDS["progress_delta"][1]


def test_progress_delta_clipped_lower(board):
    pack = _build_pack(board)
    result = _validate_free_siege(pack, _make_proposal(progress_delta=-100))
    assert result["progress_delta"] == FREE_SIEGE_BOUNDS["progress_delta"][0]


def test_casualty_pct_clipped_upper(board):
    pack = _build_pack(board)
    result = _validate_free_siege(pack, _make_proposal(casualty_pct=80))
    assert result["casualty_pct"] == FREE_SIEGE_BOUNDS["casualty_pct"][1]


def test_casualty_pct_clipped_lower(board):
    pack = _build_pack(board)
    result = _validate_free_siege(pack, _make_proposal(casualty_pct=-10))
    assert result["casualty_pct"] == FREE_SIEGE_BOUNDS["casualty_pct"][0]


def test_deltas_within_bounds(board):
    pack = _build_pack(board)
    result = _validate_free_siege(pack, _make_proposal(progress_delta=8, casualty_pct=10))
    assert result["progress_delta"] == 8
    assert result["casualty_pct"] == 10


# ========== feasibility=impossible ==========


def test_impossible_falls_back(board):
    pack = _build_pack(board)
    result = _validate_free_siege(pack, _make_proposal(
        feasibility="impossible", progress_delta=15, casualty_pct=20,
    ))
    assert result["progress_delta"] == 0
    assert result["casualty_pct"] == 0
    assert result["feasibility"] == "impossible"


# ========== 禁止文本 ==========


def test_forbidden_massacre_in_narrative(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="屠城"):
        _validate_free_siege(pack, _make_proposal(narrative="破城屠城，三日不封刀。"))


def test_forbidden_death_in_reasoning(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="死亡"):
        _validate_free_siege(pack, _make_proposal(reasoning=["守将死亡"]))


def test_forbidden_reinforcements(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="援军"):
        _validate_free_siege(pack, _make_proposal(reasoning=["援军到达"]))


# ========== 事实一致性 ==========


def test_claims_low_morale_but_defenders_strong(board):
    pack = _build_pack(board)
    # 修改守军士气为高
    for d in pack["facts"]["defenders"]:
        d["morale"] = 80
    with pytest.raises(ValueError, match="士气低落"):
        _validate_free_siege(pack, _make_proposal(reasoning=["守军士气低落"]))


def test_claims_weak_fortification_but_strong(board):
    pack = _build_pack(board)
    pack["facts"]["target_region"]["fortification"] = 80
    with pytest.raises(ValueError, match="城防薄弱"):
        _validate_free_siege(pack, _make_proposal(reasoning=["城防薄弱"]))


def test_claims_about_to_fall_but_low_progress(board):
    pack = _build_pack(board)
    pack["audit"]["projected_progress"] = 50
    with pytest.raises(ValueError, match="即将破城"):
        _validate_free_siege(pack, _make_proposal(reasoning=["即将破城"]))


# ========== 集成 ==========


def test_run_siege_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    result = run_siege_ai_judge(board, state, pack, _make_proposal(progress_delta=5, casualty_pct=3))
    assert result["siege_action"] == "加紧攻城"
    assert result["progress_delta"] == 5
