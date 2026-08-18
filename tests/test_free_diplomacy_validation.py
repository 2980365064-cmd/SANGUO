"""自由外交裁决边界校验测试。

覆盖：
- 边界裁剪（relation_delta, trust_delta, coordination_delta 范围）
- 事实一致性检查（AI 声称共同敌人但无战争 → 拒绝）
- 禁止字段拦截
- 基准外交路径（保留既有行为）
- 自由外交路径（AI 评估玩家自由外交意图）
- impossible 方案回退
- 回归既有测试
"""

import json
import pytest
from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.diplomacy import (
    build_diplomacy_adjudication_pack,
    _validate_free_diplomacy,
    run_diplomacy_ai_judge,
    propose_treaty,
)


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    yield db
    db.close()


def _state():
    return SimpleNamespace(
        turn=1, year=208, period=7,
        metrics={"军资": 40, "粮秣": 40, "民望": 72, "名分": 78, "军心": 70, "士族支持": 35},
    )


def _build_pack(db, proposer="liu_bei", target="sun_quan", terms=None):
    state = _state()
    if terms is None:
        terms = {
            "treaty_key": "test_free_diplo",
            "treaty_type": "盟约",
            "envoy": "诸葛亮",
            "obligations": [{"type": "共同抗曹"}],
            "territorial_claims": {},
            "marriage_hostages": {},
            "military_coordination": 50,
        }
    return build_diplomacy_adjudication_pack(db, state, proposer, target, terms)


# ========== 基础边界校验 ==========


def test_validate_free_diplomacy_basic_proposal_is_accepted(board):
    """基本自由外交提案在边界内时被接受。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 10,
        "trust_delta": 5,
        "coordination_delta": 8,
        "feasibility": "high",
        "reasoning": ["双方有共同敌人曹操", "诸葛亮外交能力强"],
        "narrative": "诸葛亮出使江东，孙权欣然应允，双方歃血为盟。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["diplomacy_action"] == "结盟"
    assert result["relation_delta"] == 10
    assert result["trust_delta"] == 5


def test_validate_free_diplomacy_relation_delta_clipped_to_bounds(board):
    """relation_delta 超出 [-30, +30] 时被裁剪。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 50,  # 超出 +30
        "trust_delta": 0,
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["双方关系极好"],
        "narrative": "结盟成功。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["relation_delta"] == 30  # 裁剪到 +30


def test_validate_free_diplomacy_trust_delta_clipped(board):
    """trust_delta 超出 [-20, +20] 时被裁剪。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 0,
        "trust_delta": 30,  # 超出 +20
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["互信深厚"],
        "narrative": "结盟成功。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["trust_delta"] == 20


def test_validate_free_diplomacy_coordination_delta_clipped(board):
    """coordination_delta 超出 [-20, +20] 时被裁剪。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "军事协作",
        "relation_delta": 0,
        "trust_delta": 0,
        "coordination_delta": 25,  # 超出 +20
        "feasibility": "medium",
        "reasoning": ["双方有军事合作意愿"],
        "narrative": "军事协作达成。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["coordination_delta"] == 20


def test_validate_free_diplomacy_negative_deltas_clipped(board):
    """负向 delta 超出下界时被裁剪。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "威慑",
        "relation_delta": -50,  # 超出 -30
        "trust_delta": -30,    # 超出 -20
        "coordination_delta": -25,  # 超出 -20
        "feasibility": "medium",
        "reasoning": ["刘备展示军力"],
        "narrative": "威慑对方。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["relation_delta"] == -30
    assert result["trust_delta"] == -20
    assert result["coordination_delta"] == -20


# ========== 可行性回退 ==========


def test_validate_free_diplomacy_impossible_falls_back_to_standard(board):
    """feasibility=impossible 时退回标准外交（所有 delta=0）。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "联姻",
        "relation_delta": 20,
        "trust_delta": 15,
        "coordination_delta": 10,
        "feasibility": "impossible",
        "reasoning": ["双方没有适婚人物"],
        "narrative": "联姻不可行。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["relation_delta"] == 0
    assert result["trust_delta"] == 0
    assert result["coordination_delta"] == 0
    assert result["diplomacy_action"] == "标准外交"


# ========== 事实一致性检查 ==========


def test_validate_free_diplomacy_claims_common_enemy_but_no_war_is_rejected(board):
    """AI 声称'共同敌人'但目标与所谓敌人没有战争时拒绝。"""
    pack = _build_pack(board, proposer="liu_bei", target="liu_zhang")
    # liu_zhang 与 cao_cao 没有战争关系（status=neutral）
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 15,
        "trust_delta": 10,
        "coordination_delta": 5,
        "feasibility": "high",
        "reasoning": ["刘璋与曹操有仇，有共同敌人"],  # 声称共同敌人
        "narrative": "结盟成功。",
    }
    with pytest.raises(ValueError, match="声称.*共同敌人.*但盘面事实不支持"):
        _validate_free_diplomacy(pack, proposal)


def test_validate_free_diplomacy_claims_common_enemy_and_war_exists_accepted(board):
    """AI 声称'共同敌人'且确实存在战争时通过。"""
    # liu_bei 与 sun_quan 的共同敌人是 cao_cao，cao_cao 与 sun_quan 是 war
    pack = _build_pack(board, proposer="liu_bei", target="sun_quan")
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 15,
        "trust_delta": 10,
        "coordination_delta": 5,
        "feasibility": "high",
        "reasoning": ["孙权与曹操正在交战，有共同敌人"],
        "narrative": "结盟成功。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["relation_delta"] == 15


def test_validate_free_diplomacy_claims_military_superiority_but_weaker_is_rejected(board):
    """AI 声称'军力优势'但提案方实际军力更弱时拒绝。"""
    # liu_bei 军力远弱于 cao_cao
    pack = _build_pack(board, proposer="liu_bei", target="cao_cao")
    proposal = {
        "diplomacy_action": "威慑",
        "relation_delta": 10,
        "trust_delta": 5,
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["刘备军力远超曹操，可以威慑"],  # 声称军力优势
        "narrative": "威慑成功。",
    }
    with pytest.raises(ValueError, match="声称.*军力优势.*但盘面事实不支持"):
        _validate_free_diplomacy(pack, proposal)


# ========== 禁止字段/文本 ==========


def test_validate_free_diplomacy_forbidden_text_in_narrative_is_rejected(board):
    """narrative 中包含禁止文本时被拒绝。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 10,
        "trust_delta": 5,
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["双方关系好"],
        "narrative": "结盟成功并割让荆州给刘备。",  # "割让" 是禁止文本
    }
    with pytest.raises(ValueError, match="不得写未获规则允许的领土变化"):
        _validate_free_diplomacy(pack, proposal)


def test_validate_free_diplomacy_forbidden_text_in_reasoning_is_rejected(board):
    """reasoning 中包含禁止文本时被拒绝。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 10,
        "trust_delta": 5,
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["结盟后条约生效"],  # "条约生效" 是禁止文本
        "narrative": "结盟成功。",
    }
    with pytest.raises(ValueError, match="不得用叙事直接使条约生效"):
        _validate_free_diplomacy(pack, proposal)


def test_validate_free_diplomacy_forbidden_spawn_army_is_rejected(board):
    """reasoning 中包含'援军'时被拒绝。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 10,
        "trust_delta": 5,
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["盟国派来援军"],
        "narrative": "结盟成功。",
    }
    with pytest.raises(ValueError, match="不得凭空生成援军"):
        _validate_free_diplomacy(pack, proposal)


# ========== 统一自由路径 ==========


def test_legacy_proposal_now_uses_free_path(board):
    """传统格式的提案现在也走自由路径，返回自由路径格式的结果。"""
    pack = _build_pack(board)
    proposal = {
        "outcome": "counter_offer",
        "reason": "孙权愿共抗曹，但要先明荆州归属。",
        "changes": [],
    }
    # 统一走自由路径，结果包含自由路径字段
    result = run_diplomacy_ai_judge(board, _state(), pack, proposal)
    assert "diplomacy_action" in result
    assert "relation_delta" in result


def test_validate_free_diplomacy_proposal_with_action_name_uses_free_path(board):
    """包含 diplomacy_action 的提案走自由路径。"""
    pack = _build_pack(board)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 10,
        "trust_delta": 5,
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["双方有共同敌人"],
        "narrative": "结盟成功。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert "diplomacy_action" in result
    assert result["relation_delta"] == 10


# ========== Pack 扩展 ==========


def test_diplomacy_pack_includes_power_balance(board):
    """裁决包包含双方军力对比数据。"""
    pack = _build_pack(board)
    facts = pack["facts"]
    assert "power_balance" in facts
    balance = facts["power_balance"]
    assert "proposer_force" in balance
    assert "target_force" in balance
    assert "ratio" in balance


def test_diplomacy_pack_includes_strategic_context(board):
    """裁决包包含战略态势数据（共同敌人等）。"""
    pack = _build_pack(board)
    facts = pack["facts"]
    assert "strategic_context" in facts
    context = facts["strategic_context"]
    assert "common_enemies" in context
    # liu_bei 和 sun_quan 的共同敌人是 cao_cao（与两者都是 war）
    assert "cao_cao" in context["common_enemies"]


def test_diplomacy_pack_includes_active_treaties(board):
    """裁决包包含当前活跃条约。"""
    pack = _build_pack(board)
    facts = pack["facts"]
    assert "active_treaties" in facts
    treaties = facts["active_treaties"]
    assert isinstance(treaties, list)
    # liu_bei 和 sun_quan 之间有 sun_liu_anti_cao_208 条约
    assert any(t.get("treaty_key") == "sun_liu_anti_cao_208" for t in treaties)


# ========== 边界：无特性匹配时的 accept rate 修正 ==========


def test_validate_free_diplomacy_without_envoy_has_lower_trust_cap(board):
    """无使臣时 trust_delta 上限为 +10（有使臣时 +20）。"""
    terms = {
        "treaty_key": "test_no_envoy",
        "treaty_type": "盟约",
        "obligations": [],
        "territorial_claims": {},
        "marriage_hostages": {},
        "military_coordination": 0,
    }
    pack = _build_pack(board, terms=terms)
    proposal = {
        "diplomacy_action": "结盟",
        "relation_delta": 10,
        "trust_delta": 15,  # 无使臣，上限 +10
        "coordination_delta": 0,
        "feasibility": "high",
        "reasoning": ["双方关系好"],
        "narrative": "结盟成功。",
    }
    result = _validate_free_diplomacy(pack, proposal)
    assert result["trust_delta"] == 10  # 裁剪到 +10
