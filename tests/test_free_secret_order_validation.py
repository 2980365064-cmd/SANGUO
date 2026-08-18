"""自由密令裁决边界校验测试。"""

import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.db.secret_orders import (
    build_secret_order_adjudication_pack,
    _validate_free_secret_order,
    run_secret_order_ai_judge,
    FREE_SECRET_ORDER_BOUNDS,
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


def _build_pack(db, viewer="赵云"):
    state = _state(1)
    order_id = db.create_secret_order(state, viewer, "查探敌营", "只许查证。", ["敌情"])
    return build_secret_order_adjudication_pack(db, state, order_id, viewer=viewer)


def _make_proposal(**overrides):
    base = {
        "secret_action": "推进密令",
        "progress_delta": 10,
        "feasibility": "high",
        "narrative": "密令进展顺利。",
        "reasoning": [],
        "risk_note": "",
        "progress_note": "已派出斥候。",
    }
    base.update(overrides)
    return base


# ========== 边界裁剪 ==========


def test_progress_delta_clipped_upper(board):
    pack = _build_pack(board)
    result = _validate_free_secret_order(pack, _make_proposal(progress_delta=100))
    assert result["progress_delta"] == FREE_SECRET_ORDER_BOUNDS["progress_delta"][1]


def test_progress_delta_clipped_lower(board):
    pack = _build_pack(board)
    result = _validate_free_secret_order(pack, _make_proposal(progress_delta=-100))
    assert result["progress_delta"] == FREE_SECRET_ORDER_BOUNDS["progress_delta"][0]


# ========== feasibility=impossible ==========


def test_impossible_falls_back(board):
    pack = _build_pack(board)
    result = _validate_free_secret_order(pack, _make_proposal(feasibility="impossible"))
    assert result["progress_delta"] == 0


# ========== 禁止文本 ==========


def test_forbidden_defection_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="策反"):
        _validate_free_secret_order(pack, _make_proposal(narrative="策反成功。"))


def test_forbidden_assassination_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="暗杀"):
        _validate_free_secret_order(pack, _make_proposal(narrative="暗杀成功。"))


def test_common_forbidden_text_rejected(board):
    pack = _build_pack(board)
    with pytest.raises(ValueError, match="死亡"):
        _validate_free_secret_order(pack, _make_proposal(narrative="目标死亡。"))


# ========== 事实一致性 ==========


def test_claims_capable_minister_but_low_intelligence(board):
    pack = _build_pack(board)
    pack["facts"]["minister"] = {"intelligence": 40}
    with pytest.raises(ValueError, match="能力出色"):
        _validate_free_secret_order(pack, _make_proposal(reasoning=["承办人能力出色"]))


def test_claims_near_complete_but_not_due(board):
    pack = _build_pack(board)
    pack["audit"]["due"] = False
    with pytest.raises(ValueError, match="即将完成"):
        _validate_free_secret_order(pack, _make_proposal(reasoning=["密令即将完成"]))


def test_close_done_before_due_rejected(board):
    pack = _build_pack(board)
    pack["audit"]["due"] = False
    with pytest.raises(ValueError, match="未到期"):
        _validate_free_secret_order(pack, _make_proposal(status="close_done"))


# ========== 集成 ==========


def test_run_secret_order_ai_judge_uses_free_path(board):
    pack = _build_pack(board)
    state = _state(1)
    result = run_secret_order_ai_judge(board, state, pack, _make_proposal(progress_delta=5))
    assert result["progress_delta"] == 5
