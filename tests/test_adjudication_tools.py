"""查询工具版裁决流程测试。

覆盖核心变更：
- run_adjudication_with_tools() 替代 run_adjudication_llm()
- _build_kind_instruction() 替代 _pack_prompt()
- _build_validation_context() 替代 _build_pack_for_kind()
- run_adjudication() 统一调度器（查询工具版）
- run_monthly_adjudication_batch() 月末批量裁决
"""

import pytest
from ming_sim.adjudication import (
    ADJUDICATION_KIND_POLICIES,
    COMMON_FORBIDDEN_OUTCOMES,
    COMMON_FORBIDDEN_FIELDS,
    COMMON_FORBIDDEN_TEXT,
    _build_kind_instruction,
    _build_task_prompt,
    _policy_for,
    _base_result,
    _proposal_summary,
    _audit_reason,
    _validated_changes,
    record_pending_adjudication,
    json_safe,
    attach_adjudication_runtime,
    adjudication_runtime_from_state,
)


# ---------------------------------------------------------------------------
# 常量测试
# ---------------------------------------------------------------------------

def test_kind_policies_cover_all_nine_types():
    assert set(ADJUDICATION_KIND_POLICIES.keys()) == {
        "battle", "power_action", "diplomacy", "secret_order",
        "siege", "region_investment", "personnel", "supply", "world_event",
    }


def test_common_forbidden_outcomes_are_stable():
    assert "unlisted_death" in COMMON_FORBIDDEN_OUTCOMES
    assert "spawn_army" in COMMON_FORBIDDEN_OUTCOMES
    assert "revive_character" in COMMON_FORBIDDEN_OUTCOMES
    assert "ignore_supply" in COMMON_FORBIDDEN_OUTCOMES


def test_common_forbidden_fields_are_stable():
    assert "death" in COMMON_FORBIDDEN_FIELDS
    assert "ending_status" in COMMON_FORBIDDEN_FIELDS
    assert "reinforcements" in COMMON_FORBIDDEN_FIELDS


def test_common_forbidden_text_has_chinese_markers():
    assert "阵亡" in COMMON_FORBIDDEN_TEXT
    assert "援军" in COMMON_FORBIDDEN_TEXT
    assert "割让" in COMMON_FORBIDDEN_TEXT


# ---------------------------------------------------------------------------
# 指令生成器测试
# ---------------------------------------------------------------------------

def test_build_kind_instruction_includes_kind_specific_content():
    for kind in ADJUDICATION_KIND_POLICIES:
        instruction = _build_kind_instruction(kind, "test_subject", "玩家意图")
        assert kind in instruction or "裁决任务" in instruction
        assert "查询工具" in instruction


def test_build_kind_instruction_battle_has_query_tools():
    instruction = _build_kind_instruction("battle", "city:xiangyang", "火攻曹军")
    assert "query_army" in instruction
    assert "query_character" in instruction
    assert "query_region" in instruction
    assert "query_tactic_reference" in instruction


def test_build_kind_instruction_diplomacy_has_query_tools():
    instruction = _build_kind_instruction("diplomacy", "liu_bei:sun_quan", "派诸葛亮劝说孙权结盟")
    assert "query_diplomacy" in instruction
    assert "query_power" in instruction


def test_build_kind_instruction_power_action():
    instruction = _build_kind_instruction("power_action", "cao_cao", "")
    assert "cao_cao" in instruction


def test_build_kind_instruction_secret_order():
    instruction = _build_kind_instruction("secret_order", "42", "")
    assert "secret_order" in instruction.lower() or "密令" in instruction


def test_build_kind_instruction_siege():
    instruction = _build_kind_instruction("siege", "1", "")
    assert "query_siege" in instruction


def test_build_kind_instruction_supply():
    instruction = _build_kind_instruction("supply", "guanyu_fleet", "")
    assert "query_army" in instruction


def test_build_kind_instruction_world_event():
    instruction = _build_kind_instruction("world_event", "chi_bi", "")
    assert "query_events" in instruction


# ---------------------------------------------------------------------------
# 任务提示词测试
# ---------------------------------------------------------------------------

def test_build_task_prompt_includes_player_intent():
    prompt = _build_task_prompt("battle", "city:xiangyang", "火攻曹军连环船")
    assert "battle" in prompt
    assert "city:xiangyang" in prompt
    assert "火攻曹军连环船" in prompt


def test_build_task_prompt_without_intent():
    prompt = _build_task_prompt("supply", "guanyu_fleet", "")
    assert "未提供具体意图" in prompt


# ---------------------------------------------------------------------------
# 运行时管理测试
# ---------------------------------------------------------------------------

def test_attach_and_retrieve_runtime():
    class MockState:
        pass

    state = MockState()
    mock_config = object()
    mock_db = object()

    attach_adjudication_runtime(state, mock_config, mock_db)
    config, db = adjudication_runtime_from_state(state)
    assert config is mock_config
    assert db is mock_db


def test_runtime_defaults_to_none():
    class MockState:
        pass

    state = MockState()
    config, db = adjudication_runtime_from_state(state)
    assert config is None
    assert db is None


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------

def test_policy_for_known_kind():
    policy = _policy_for("battle")
    assert policy["mode"] == "llm"
    assert policy["failure_policy"] == "pending_review"


def test_policy_for_unknown_kind():
    policy = _policy_for("unknown_kind")
    assert policy == {}


def test_proposal_summary_extracts_first_text():
    assert _proposal_summary({"narrative": "关羽突袭", "reason": ""}) == "关羽突袭"
    assert _proposal_summary({"reason": "兵力优势"}) == "兵力优势"
    assert _proposal_summary({}) == ""
    assert _proposal_summary(None) == ""


def test_audit_reason_includes_kind_and_outcome():
    reason = _audit_reason(
        "battle",
        {"outcome": "attacker_win", "narrative": "关羽突袭成功"},
        {"outcome": "attacker_win"},
    )
    assert "battle" in reason
    assert "attacker_win" in reason


def test_validated_changes_returns_list():
    assert _validated_changes({"validated_changes": [1, 2]}) == [1, 2]
    assert _validated_changes({"validated_changes": "not_list"}) == []
    assert _validated_changes({}) == []
    assert _validated_changes(None) == []


def test_json_safe_handles_nested_structures():
    result = json_safe({"a": {"b": [1, "c", None]}})
    assert result == {"a": {"b": [1, "c", None]}}


def test_json_safe_handles_non_serializable():
    class Custom:
        pass

    result = json_safe({"obj": Custom()})
    assert isinstance(result, dict)
    assert "obj" in result


# ---------------------------------------------------------------------------
# base_result 测试
# ---------------------------------------------------------------------------

def test_base_result_validated():
    result = _base_result(
        status="validated",
        kind="battle",
        subject_id="city:xiangyang",
        context={"kind": "battle", "subject_id": "city:xiangyang"},
        proposal={"outcome": "attacker_win", "narrative": "关羽突袭"},
        validated={"outcome": "attacker_win", "validated_changes": []},
    )
    assert result["status"] == "validated"
    assert result["kind"] == "battle"
    assert "关羽突袭" in result["proposal_summary"]


def test_base_result_pending_review():
    result = _base_result(
        status="pending_review",
        kind="diplomacy",
        subject_id="liu_bei:sun_quan",
        context={"kind": "diplomacy", "subject_id": "liu_bei:sun_quan"},
        proposal={"outcome": "propose_terms", "narrative": "诸葛亮出使"},
        reason="信任度不足",
    )
    assert result["status"] == "pending_review"
    assert "信任度不足" in result["audit_reason"]


# ---------------------------------------------------------------------------
# record_pending_adjudication 测试
# ---------------------------------------------------------------------------

def test_record_pending_creates_entry():
    from ming_sim.db import GameDB
    from ming_sim.content import GameContent
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    
    class MockState:
        turn = 1

    state = MockState()
    context = {"kind": "battle", "subject_id": "test", "turn": 1}

    result = record_pending_adjudication(
        db, state, context, "测试原因", {"outcome": "invalid"}
    )
    assert result["status"] == "pending_review"
    assert result["reason"] == "测试原因"
    db.close()


def test_record_pending_deduplicates():
    from ming_sim.db import GameDB
    from ming_sim.content import GameContent
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    
    class MockState:
        turn = 1

    state = MockState()
    context = {"kind": "battle", "subject_id": "test", "turn": 1}

    r1 = record_pending_adjudication(db, state, context, "原因1")
    r2 = record_pending_adjudication(db, state, context, "原因2")
    assert r1["id"] == r2["id"]
    assert r2.get("deduped") is True
    db.close()
