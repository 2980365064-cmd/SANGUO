"""统一裁决协议（查询工具版）。

AI 通过 QueryToolKit 主动查询游戏真实数据，基于玩家意图做出判断。
彻底废弃原有的固定裁决包（build_adjudication_pack）方案。

核心变更：
- run_adjudication_llm() → run_adjudication_with_tools()
- build_adjudication_pack() → 废弃
- _pack_prompt() → _build_kind_instruction()
- _build_pack_for_kind() → _build_validation_context()

AI 不再是被动地读取固定数据包，而是通过工具主动查询所需数据。
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

from agno.agent import Agent
from agno.db.sqlite import SqliteDb

from ming_sim.agents import parse_agent_json, run_agent_text
from ming_sim.llm_config import for_role as _llm_for_role
from ming_sim.llm_model import create_chat_model
from ming_sim.models import LLMConfig
from ming_sim.exceptions import LLMContractError, LLMUnavailable


PROTOCOL_VERSION = 1  # 协议版本 1，用于裁决上下文校验

# ---------------------------------------------------------------------------
# 公共常量：所有裁决类型共享的禁止规则
# ---------------------------------------------------------------------------

COMMON_FORBIDDEN_OUTCOMES = [
    "unlisted_death",
    "spawn_army",
    "free_reinforcements",
    "unvalidated_territory_change",
    "unvalidated_treaty_effect",
    "ignore_supply",
    "revive_character",
]

COMMON_FORBIDDEN_FIELDS = {
    "death",
    "ending_status",
    "kill_character",
    "character_death",
    "army_spawn",
    "spawn_army",
    "manpower_delta",
    "reinforcements",
    "free_reinforcements",
    "region_control",
    "controlled_by",
    "territory_delta",
    "treaty_active",
    "ignore_supply",
    "revive_character",
}

COMMON_FORBIDDEN_TEXT = {
    "阵亡": "不得写未获规则允许的人物死亡",
    "死亡": "不得写未获规则允许的人物死亡",
    "处死": "不得写未获规则允许的人物死亡",
    "援军": "不得凭空生成援军",
    "增援": "不得凭空生成援军",
    "复活": "不得复活人物",
    "割让": "不得写未获规则允许的领土变化",
    "易主": "不得写未获规则允许的领土变化",
    "条约生效": "不得用叙事直接使条约生效",
    "忽略补给": "不得无视补给",
}


def check_forbidden_fields(proposal: Mapping[str, Any], *, extra: Iterable[str] = ()) -> None:
    """检查提案中是否包含禁止字段。

    供各模块的自由校验器调用，确保 AI 提案不直接篡改世界状态。
    """
    forbidden = COMMON_FORBIDDEN_FIELDS | set(extra)
    present = sorted(field for field in forbidden if field in proposal)
    if present:
        raise ValueError(f"AI 裁决包含非法字段：{','.join(present)}")

# ---------------------------------------------------------------------------
# 内部工具：裁决上下文构建器（供各模块 validator 使用，不再作为 AI 输入）
# ---------------------------------------------------------------------------

def build_adjudication_pack(
    *,
    kind: str,
    turn: int,
    subject_id: str,
    facts: Mapping[str, Any],
    rules: Mapping[str, Any],
    allowed_outcomes: Sequence[str],
    forbidden_outcomes: Sequence[str] | None = None,
    ai_options: Sequence[Mapping[str, Any]] | None = None,
    randomness_bounds: Mapping[str, Any] | None = None,
    apply_contract: Mapping[str, Any] | None = None,
    audit: Mapping[str, Any] | None = None,
    source_tables: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """构建裁决上下文（校验用）。

    注意：这个函数现在仅供各模块的 validator 使用，构建校验所需的上下文数据。
    AI 不再被动接收这个数据包，而是通过 QueryToolKit 主动查询数据。
    """
    forbidden = list(dict.fromkeys(list(forbidden_outcomes or []) + COMMON_FORBIDDEN_OUTCOMES))
    policy = ADJUDICATION_KIND_POLICIES.get(str(kind), {})
    return {
        "protocol_version": PROTOCOL_VERSION,
        "kind": str(kind),
        "turn": int(turn),
        "subject_id": str(subject_id),
        "randomness_level": str(policy.get("randomness_level") or "narrative"),
        "randomness_bounds": json_safe(dict(randomness_bounds or {})),
        "apply_contract": json_safe(dict(apply_contract or {"mode": "log_only"})),
        "facts": json_safe(dict(facts)),
        "rules": json_safe(dict(rules)),
        "allowed_outcomes": [str(item) for item in allowed_outcomes],
        "forbidden_outcomes": forbidden,
        "ai_options": json_safe(list(ai_options or [])),
        "ai_proposal": {},
        "validated_changes": [],
        "audit": {
            "source_tables": [str(item) for item in (source_tables or [])],
            **json_safe(dict(audit or {})),
        },
    }


# ---------------------------------------------------------------------------
# 各裁决类型的元数据
# ---------------------------------------------------------------------------

ADJUDICATION_KIND_POLICIES: Dict[str, Dict[str, Any]] = {
    "battle": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "decision",
    },
    "power_action": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "decision",
    },
    "diplomacy": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "apply_limited",
    },
    "secret_order": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "narrative",
    },
    "siege": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "modifier",
    },
    "region_investment": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "modifier",
    },
    "personnel": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "narrative",
    },
    "supply": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "modifier",
    },
    "world_event": {
        "auto_apply": False, "failure_policy": "pending_review",
        "mode": "llm", "randomness_level": "apply_limited",
    },
}

# 每种裁决类型的允许 outcome 列表（由系统状态动态决定，这里提供基线）
KIND_ALLOWED_OUTCOMES: Dict[str, List[str]] = {
    "battle": ["attacker_win", "defender_win", "stalemate", "retreat"],
    "power_action": [],  # 动态：由 available_power_actions 决定
    "diplomacy": ["propose_terms", "accept_terms", "counter_offer", "reject_terms", "breach_or_pressure"],
    "secret_order": ["continue_secret_order", "add_progress_note", "submit_for_review", "close_done", "close_failed"],
    "siege": ["continue_siege", "withdraw_siege", "conquer_city"],
    "region_investment": ["view_region", "start_investment", "advance_investment", "stall_investment"],
    "personnel": ["review_office", "keep_current", "appoint_candidate"],
    "supply": ["granary_supply", "consume_carried_supply", "starvation", "execute_supply_order"],
    "world_event": ["review_world_state", "keep_scheduled", "resolve_event_variant", "supersede_event",
                    "wait_for_window", "mark_eligible", "record_chronicle"],
}


# ---------------------------------------------------------------------------
# JSON 安全序列化
# ---------------------------------------------------------------------------

def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# AI 指令生成器（替代 _pack_prompt）
# ---------------------------------------------------------------------------

def _build_kind_instruction(kind: str, subject_id: str, player_intent: str) -> str:
    """按裁决类型生成 AI 指令。

    AI 通过查询工具主动获取数据，不再被动接收固定裁决包。
    """
    base = (
        "你是 SANGUO 的战术裁决员。你的职责是评估玩家提出的方案的可行性。\n"
        "你必须通过查询工具获取真实盘面数据，基于事实做出判断。\n\n"
        "## 核心约束\n"
        "1. 只能使用查询工具返回的真实数据，不能编造不存在的条件\n"
        "2. 必须符合东汉末年历史合理性\n"
        "3. 不得创造死亡、领土变化、增援、条约生效等世界事实\n"
        "4. 叙事文本必须符合历史背景，简洁有力\n\n"
        "## 禁止词汇\n"
        "narrative 和 reasoning 中不得包含：阵亡、死亡、处死、援军、增援、复活、割让、易主、条约生效、忽略补给\n\n"
    )

    kind_specific = {
        "battle": (
            "## 战斗裁决任务\n"
            f"评估以下战斗方案：{player_intent or '（未提供玩家意图）'}\n"
            f"战斗地点节点：{subject_id}\n\n"
            "## 需要查询的数据\n"
            "- query_army(): 攻守双方军队的兵力、训练、装备、士气、补给、疲劳\n"
            "- query_character(): 统帅的智力、勇气、统率、特性\n"
            "- query_region(): 战场地形\n"
            "- query_world_context(): 季节、天气\n"
            "- query_regional_state(): 区域状态（疫病、灾害等）\n"
            "- query_tactic_reference(): 基准战术列表和边界常量\n\n"
            "## 评估维度\n"
            "- 方案各环节是否满足盘面条件（地形、天气、人物属性等）\n"
            "- 历史合理性（东汉末年是否有类似战例）\n"
            "- 成功概率和可能的意外\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"attacker_win/defender_win/stalemate/retreat\",\n"
            "  \"tactic_name\": \"战术名称（从玩家描述中提炼）\",\n"
            "  \"actor\": \"执行统帅\",\n"
            "  \"delta\": 修正值(int, -5 到 +15),\n"
            "  \"feasibility\": \"high/medium/low/impossible\",\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"评估依据1\", \"评估依据2\"],\n"
            "  \"risks\": [\"可能风险1\"],\n"
            "  \"risk_note\": \"风险提示\",\n"
            "  \"recommended_followup\": \"后续建议\"\n"
            "}\n"
            "```\n"
            "如果 feasibility=impossible，delta 必须为 0，outcome 必须为 stalemate。\n"
        ),
        "power_action": (
            "## 势力行动裁决任务\n"
            f"评估 NPC 势力（{subject_id}）本月应采取的行动。\n\n"
            "## 需要查询的数据\n"
            "- query_power(): 本势力军力、补给、态势\n"
            "- query_diplomacy(): 与其他势力的关系\n"
            "- query_world_context(): 季节、天气、民情\n"
            "- query_regional_state(): 周边区域状态\n\n"
            "## 评估维度\n"
            "- 当前势力处境（军力、补给、外交形势）\n"
            "- 最紧迫的威胁或机遇\n"
            "- 行动的历史合理性\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"行动类型\",\n"
            "  \"action\": {\"action_type\": \"...\", \"target\": \"...\", \"priority\": \"high/normal\"},\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"依据\"],\n"
            "  \"risk_note\": \"风险提示\"\n"
            "}\n"
            "```\n"
        ),
        "diplomacy": (
            "## 外交裁决任务\n"
            f"评估以下外交方案：{player_intent or '（未提供玩家意图）'}\n\n"
            "## 需要查询的数据\n"
            "- query_diplomacy(): 双方关系、信任度、条约\n"
            "- query_power(): 双方军力对比\n"
            "- query_character(): 使臣属性（外交、魅力）\n"
            "- query_world_context(): 天下大势\n\n"
            "## 评估维度\n"
            "- 双方实力对比和战略形势\n"
            "- 当前关系和信任度\n"
            "- 使臣能力是否匹配\n"
            "- 条款的历史合理性\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"propose_terms/accept_terms/counter_offer/reject_terms\",\n"
            "  \"relation_delta\": 关系修正(int, -30 到 +30),\n"
            "  \"trust_delta\": 信任修正(int, -20 到 +20),\n"
            "  \"coordination_delta\": 协同修正(int, -20 到 +20),\n"
            "  \"feasibility\": \"high/medium/low/impossible\",\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"评估依据\"],\n"
            "  \"risks\": [\"可能风险\"]\n"
            "}\n"
            "```\n"
        ),
        "secret_order": (
            "## 密令裁决任务\n"
            f"评估密令 {subject_id} 的进展。\n\n"
            "## 需要查询的数据\n"
            "- query_secret_orders(): 密令详情\n"
            "- query_character(): 承办大臣属性\n"
            "- query_region(): 相关区域状态\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"continue_secret_order/add_progress_note/submit_for_review/close_done/close_failed\",\n"
            "  \"narrative\": \"100字以内进展描述\",\n"
            "  \"reasoning\": [\"依据\"],\n"
            "  \"progress_note\": \"进展备注\"\n"
            "}\n"
            "```\n"
        ),
        "siege": (
            "## 围城裁决任务\n"
            f"评估围城 {subject_id} 的本月进展。\n\n"
            "## 需要查询的数据\n"
            "- query_siege(): 围城状态、进度、攻守双方\n"
            "- query_army(): 攻守军队详情\n"
            "- query_region(): 目标区域民心、动乱\n"
            "- query_city(): 城池城防、仓储\n\n"
            "## 评估维度\n"
            "- 攻守兵力对比\n"
            "- 城防强度和守军士气\n"
            "- 区域民心对围城的影响\n"
            "- 是否有援军可能\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"continue_siege/withdraw_siege/conquer_city\",\n"
            "  \"progress_delta\": 进度修正(int),\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"依据\"],\n"
            "  \"risks\": [\"风险\"]\n"
            "}\n"
            "```\n"
        ),
        "region_investment": (
            "## 区域投资裁决任务\n"
            f"评估区域 {subject_id} 的投资方向。\n\n"
            "## 需要查询的数据\n"
            "- query_region(): 区域人口、民心、田赋\n"
            "- query_metrics(): 当前军资\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"start_investment/advance_investment/view_region\",\n"
            "  \"investment_category\": \"屯田/城防/军备/水军/道路/市易\",\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"依据\"]\n"
            "}\n"
            "```\n"
        ),
        "personnel": (
            "## 人事裁决任务\n"
            f"评估官职 {subject_id} 的人选。\n\n"
            "## 需要查询的数据\n"
            "- query_character(): 候选人属性\n"
            "- query_metrics(): 相关指标\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"appoint_candidate/keep_current/review_office\",\n"
            "  \"candidate\": \"候选人姓名\",\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"依据\"]\n"
            "}\n"
            "```\n"
        ),
        "supply": (
            "## 补给裁决任务\n"
            f"评估军队 {subject_id} 的补给方案。\n\n"
            "## 需要查询的数据\n"
            "- query_army(): 军队状态、补给、携粮\n"
            "- query_region(): 可达粮仓\n"
            "- query_metrics(): 粮秣\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"granary_supply/consume_carried_supply/starvation\",\n"
            "  \"supply_delta\": 补给修正(int),\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"依据\"]\n"
            "}\n"
            "```\n"
        ),
        "world_event": (
            "## 天下事件裁决任务\n"
            f"评估历史事件 {subject_id} 的处置。\n\n"
            "## 需要查询的数据\n"
            "- query_events(): 事件详情和状态\n"
            "- query_power(): 相关势力状态\n"
            "- query_world_context(): 天下大势\n\n"
            "## 输出格式\n"
            "```json\n"
            "{\n"
            "  \"outcome\": \"resolve_event_variant/keep_scheduled/record_chronicle\",\n"
            "  \"variant_id\": \"变体ID（如适用）\",\n"
            "  \"narrative\": \"100字以内叙事\",\n"
            "  \"reasoning\": [\"依据\"]\n"
            "}\n"
            "```\n"
        ),
    }

    specific = kind_specific.get(kind, f"## 裁决任务\n评估 {kind}（{subject_id}）。\n")
    return f"{base}\n{specific}"


def _build_task_prompt(kind: str, subject_id: str, player_intent: str) -> str:
    """构建任务提示词（不含指令，只描述具体任务）。"""
    intent_text = player_intent.strip() if player_intent else "（未提供具体意图）"
    return (
        f"## 当前任务\n"
        f"- 裁决类型: {kind}\n"
        f"- 裁决对象: {subject_id}\n"
        f"- 玩家意图: {intent_text}\n\n"
        f"请先通过查询工具获取所需数据，然后评估方案可行性，输出 JSON。\n"
    )


# ---------------------------------------------------------------------------
# 裁决入口（替代 run_adjudication_llm）
# ---------------------------------------------------------------------------

def run_adjudication_with_tools(
    db,
    state: object,
    llm_config: LLMConfig,
    agno_db: SqliteDb | None,
    kind: str,
    subject_id: str,
    *,
    player_intent: str = "",
    validation_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """使用查询工具运行 AI 裁决。

    AI 通过 QueryToolKit 主动查询游戏数据，基于玩家意图做出判断。
    不再使用固定裁决包。

    P3 优化：传入 validation_context 预加载到缓存，减少 AI 重复查询 DB。
    """
    from ming_sim.query_tools import BatchQueryCache, QueryToolKit

    del agno_db  # 一次性裁决不需要历史，避免污染长期对话记忆。

    model_config = _llm_for_role(llm_config, "simulator")

    # P3: 创建带缓存的 toolkit，预加载校验上下文
    cache = BatchQueryCache()
    toolkit = QueryToolKit(db, state, cache=cache)
    if validation_context:
        toolkit.preload_context(validation_context)

    agent = Agent(
        name="SANGUO受控裁判",
        id=f"adjudication-{kind}-{subject_id}",
        model=create_chat_model(
            model_config,
            temperature=0.75,
            top_p=0.85,
            max_tokens=min(1800, max(800, model_config.max_tokens)),
            force_json_output=True,
        ),
        tools=toolkit.get_tools(),
        instructions=[
            "你是 SANGUO 的受控裁判。通过查询工具获取真实盘面数据，评估玩家方案的可行性。",
            "所有判断必须基于查询工具返回的真实数据，不能编造不存在的条件。",
            "你只能输出严格 JSON。不得创造死亡、领土变化、增援、条约等世界事实。",
            "叙事必须符合东汉末年历史背景。",
        ],
        add_history_to_context=False,
        markdown=False,
    )

    task_prompt = _build_task_prompt(kind, subject_id, player_intent)
    tag = f"统一裁决/{kind}/{subject_id}"
    raw = run_agent_text(agent, task_prompt, tag)
    proposal = parse_agent_json(raw, tag)
    if not isinstance(proposal, dict):
        raise ValueError("裁判模型输出顶层必须是 JSON object。")
    return proposal


# ---------------------------------------------------------------------------
# 校验上下文构建（为各类型 validator 提供所需数据）
# ---------------------------------------------------------------------------

def _build_validation_context(
    db, state: object, kind: str, subject_id: str,
    *, player_intent: str = "",
    kwargs: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """构建校验上下文，供各类 validator 使用。

    只包含 validator 校验所需的最小数据，不包含给 LLM 的完整数据包。
    """
    kws = dict(kwargs or {})

    if kind == "battle":
        from ming_sim.battle import build_battle_adjudication_pack
        battle_input = kws.get("battle_input")
        if not isinstance(battle_input, Mapping):
            raise ValueError("battle 裁决需要 battle_input。")
        return build_battle_adjudication_pack(db, state, dict(battle_input))

    if kind == "power_action":
        from ming_sim.power_ai import build_power_action_adjudication_pack
        return build_power_action_adjudication_pack(db, state, subject_id)

    if kind == "diplomacy":
        from ming_sim.diplomacy import build_diplomacy_adjudication_pack
        proposer = str(kws.get("proposer") or "")
        target = str(kws.get("target") or subject_id)
        terms = kws.get("terms") if isinstance(kws.get("terms"), Mapping) else {}
        return build_diplomacy_adjudication_pack(db, state, proposer, target, dict(terms))

    if kind == "secret_order":
        from ming_sim.db.secret_orders import build_secret_order_adjudication_pack
        return build_secret_order_adjudication_pack(
            db, state, int(subject_id), viewer=str(kws.get("viewer") or "")
        )

    if kind == "siege":
        from ming_sim.siege import build_siege_adjudication_pack
        return build_siege_adjudication_pack(db, state, int(subject_id))

    if kind == "region_investment":
        from ming_sim.national_focus import build_region_investment_adjudication_pack
        return build_region_investment_adjudication_pack(
            db, state, subject_id, str(kws.get("category") or "")
        )

    if kind == "personnel":
        from ming_sim.government import build_personnel_adjudication_pack
        return build_personnel_adjudication_pack(
            db, state, subject_id,
            candidate_name=str(kws.get("candidate_name") or ""),
            target_id=str(kws.get("target_id") or ""),
        )

    if kind == "supply":
        from ming_sim.supply import build_supply_adjudication_pack
        return build_supply_adjudication_pack(
            db, state, subject_id,
            requested_amount=int(kws.get("requested_amount") or 0),
        )

    if kind == "world_event":
        from ming_sim.historical_events import build_world_event_adjudication_pack
        return build_world_event_adjudication_pack(db, state, event_id=subject_id)

    raise ValueError(f"未知裁决分类：{kind}")


# ---------------------------------------------------------------------------
# 分类校验调度（替代 _validate_proposal_for_kind）
# ---------------------------------------------------------------------------

def _validate_proposal_for_kind(
    db, state: object, kind: str,
    context: Dict[str, Any], proposal: Dict[str, Any],
) -> Dict[str, Any]:
    """按裁决类型校验 AI 提案。"""
    if kind == "battle":
        from ming_sim.battle import validate_battle_ai_choice
        tactic = validate_battle_ai_choice(db, context, proposal)
        return {
            "ai_proposal": json_safe(dict(proposal)),
            "validated_changes": [],
            "tactic": json_safe(tactic),
            "outcome": str(proposal.get("outcome") or ""),
        }
    if kind == "power_action":
        from ming_sim.power_ai import run_power_action_ai_judge
        return run_power_action_ai_judge(db, state, context, proposal)
    if kind == "diplomacy":
        from ming_sim.diplomacy import run_diplomacy_ai_judge
        return run_diplomacy_ai_judge(db, state, context, proposal)
    if kind == "secret_order":
        from ming_sim.db.secret_orders import run_secret_order_ai_judge
        return run_secret_order_ai_judge(db, state, context, proposal)
    if kind == "siege":
        from ming_sim.siege import run_siege_ai_judge
        return run_siege_ai_judge(db, state, context, proposal)
    if kind == "region_investment":
        from ming_sim.national_focus import run_region_investment_ai_judge
        return run_region_investment_ai_judge(db, state, context, proposal)
    if kind == "personnel":
        from ming_sim.government import run_personnel_ai_judge
        return run_personnel_ai_judge(db, state, context, proposal)
    if kind == "supply":
        from ming_sim.supply import run_supply_ai_judge
        return run_supply_ai_judge(db, state, context, proposal)
    if kind == "world_event":
        from ming_sim.historical_events import run_world_event_ai_judge
        return run_world_event_ai_judge(db, state, context, proposal)
    raise ValueError(f"未知裁决分类：{kind}")


# ---------------------------------------------------------------------------
# 运行时管理
# ---------------------------------------------------------------------------

def attach_adjudication_runtime(state: object, llm_config: LLMConfig | None, agno_db: SqliteDb | None) -> None:
    """把本次月末结算的裁判运行环境挂到 state；不落库，只在进程内有效。"""
    setattr(state, "_adjudication_llm_config", llm_config)
    setattr(state, "_adjudication_agno_db", agno_db)


def adjudication_runtime_from_state(state: object) -> tuple[LLMConfig | None, SqliteDb | None]:
    return (
        getattr(state, "_adjudication_llm_config", None),
        getattr(state, "_adjudication_agno_db", None),
    )


def _policy_for(kind: str) -> Dict[str, Any]:
    return dict(ADJUDICATION_KIND_POLICIES.get(str(kind), {}))


# ---------------------------------------------------------------------------
# 结果构造
# ---------------------------------------------------------------------------

def _proposal_summary(proposal: Mapping[str, Any] | None) -> str:
    if not isinstance(proposal, Mapping):
        return ""
    for key in ("reason", "summary", "narrative", "risk_note", "recommended_followup"):
        text = str(proposal.get(key) or "").strip()
        if text:
            return text
    outcome = str(proposal.get("outcome") or "").strip()
    return outcome


def _audit_reason(kind: str, proposal: Mapping[str, Any] | None, validated: Mapping[str, Any] | None = None) -> str:
    summary = _proposal_summary(proposal)
    outcome = str((validated or {}).get("outcome") or (proposal or {}).get("outcome") or "").strip()
    parts = [f"{kind} 模型裁判已通过验证"]
    if outcome:
        parts.append(f"结果：{outcome}")
    if summary:
        parts.append(summary)
    return "；".join(parts)


def _validated_changes(validated: Mapping[str, Any] | None) -> List[Any]:
    if not isinstance(validated, Mapping):
        return []
    changes = validated.get("validated_changes")
    return list(changes) if isinstance(changes, list) else []


def _base_result(
    *,
    status: str,
    kind: str,
    subject_id: str,
    context: Mapping[str, Any],
    proposal: Mapping[str, Any] | None = None,
    validated: Mapping[str, Any] | None = None,
    reason: str = "",
) -> Dict[str, Any]:
    policy = _policy_for(kind)
    proposal_text = _proposal_summary(proposal)
    return {
        "status": status,
        "kind": kind,
        "subject_id": str(subject_id),
        "randomness_level": str(policy.get("randomness_level") or context.get("randomness_level") or "narrative"),
        "proposal_summary": proposal_text,
        "validated_changes": json_safe(_validated_changes(validated)),
        "applied_changes": [],
        "audit_reason": reason or (_audit_reason(kind, proposal, validated) if proposal else ""),
    }


# ---------------------------------------------------------------------------
# 通用提案校验（被各类型的 run_xxx_ai_judge 调用）
# ---------------------------------------------------------------------------

def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _combined_text(proposal: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ("narrative", "reason", "risk_note", "recommended_followup", "summary"):
        if key in proposal:
            parts.append(str(proposal.get(key) or ""))
    return "\n".join(parts)


def validate_ai_proposal(
    context: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    allowed_change_kinds: Sequence[str],
    extra_validator: Callable[[Mapping[str, Any], Mapping[str, Any]], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """把 AI 候选校验成可落库的受控提案。"""
    allowed_changes = {str(item) for item in allowed_change_kinds}
    forbidden_keys = sorted((COMMON_FORBIDDEN_FIELDS - allowed_changes) & set(_walk_keys(proposal)))
    if forbidden_keys:
        raise ValueError(f"AI 裁决包含非法字段：{','.join(forbidden_keys)}")
    text = _combined_text(proposal)
    for marker, message in COMMON_FORBIDDEN_TEXT.items():
        if marker in text:
            raise ValueError(message)
    outcome = str(proposal.get("outcome") or "")
    allowed_outcomes = {str(item) for item in context.get("allowed_outcomes", [])}
    if outcome and outcome not in allowed_outcomes:
        raise ValueError(f"AI 裁决结果不在允许范围：{outcome}")
    changes = proposal.get("changes") or []
    if not isinstance(changes, list):
        raise ValueError("AI 裁决 changes 必须是数组。")
    for change in changes:
        if not isinstance(change, Mapping):
            raise ValueError("AI 裁决 change 必须是对象。")
    extra = extra_validator(context, proposal) if extra_validator else {}
    return {
        "ai_proposal": json_safe(dict(proposal)),
        "validated_changes": json_safe(changes),
        "outcome": outcome,
        "extra": json_safe(extra),
    }


# ---------------------------------------------------------------------------
# 待审登记
# ---------------------------------------------------------------------------

def record_pending_adjudication(
    db,
    state: object,
    context: Mapping[str, Any],
    reason: str,
    rejected_proposal: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """登记待廷议核定的越界/失败裁决。"""
    turn = int(getattr(state, "turn", context.get("turn", 0)) or 0)
    kind = str(context.get("kind") or "")
    subject_id = str(context.get("subject_id") or "")
    existing = db.conn.execute(
        """
        SELECT id, reason FROM pending_adjudications
        WHERE turn=? AND kind=? AND subject_id=? AND status='pending_review'
        ORDER BY id ASC LIMIT 1
        """,
        (turn, kind, subject_id),
    ).fetchone()
    if existing is not None:
        return {
            "id": int(existing["id"]),
            "turn": turn,
            "kind": kind,
            "subject_id": subject_id,
            "status": "pending_review",
            "reason": str(existing["reason"] or reason),
            "deduped": True,
        }
    cursor = db.conn.execute(
        """
        INSERT INTO pending_adjudications
        (turn, kind, subject_id, pack_json, rejected_proposal_json, reason, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending_review')
        """,
        (
            turn,
            kind,
            subject_id,
            json.dumps(json_safe(dict(context)), ensure_ascii=False),
            json.dumps(json_safe(dict(rejected_proposal or {})), ensure_ascii=False),
            str(reason),
        ),
    )
    db.conn.commit()
    return {
        "id": int(cursor.lastrowid),
        "turn": turn,
        "kind": kind,
        "subject_id": subject_id,
        "status": "pending_review",
        "reason": str(reason),
    }


# ---------------------------------------------------------------------------
# 统一裁决调度器（核心入口）
# ---------------------------------------------------------------------------

def run_adjudication(
    db,
    state: object,
    kind: str,
    subject_id: str,
    *,
    llm_config: LLMConfig | None,
    agno_db: SqliteDb | None,
    mode: str = "llm",
    player_intent: str = "",
    proposal: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """统一裁决调度器（查询工具版）。

    核心流程：
    1. 构建校验上下文（供 validator 使用）
    2. 如果 LLM 可用：使用查询工具让 AI 查询数据并生成提案
    3. 校验 AI 提案是否在边界内
    4. 通过 → 返回 validated / 越界 → 返回 pending_review
    """
    clean_kind = str(kind)
    if clean_kind not in ADJUDICATION_KIND_POLICIES:
        raise ValueError(f"未知裁决分类：{clean_kind}")
    policy = ADJUDICATION_KIND_POLICIES[clean_kind]

    # 构建校验上下文
    context = _build_validation_context(
        db, state, clean_kind, str(subject_id),
        player_intent=player_intent, kwargs=kwargs,
    )

    # 检查是否启用模型裁判
    if str(policy.get("mode") or "llm") != "llm":
        reason = f"{clean_kind} 当前策略为 {policy.get('mode')}，不自动调用模型裁判。"
        result = _base_result(
            status="skipped", kind=clean_kind, subject_id=str(subject_id),
            context=context, reason=reason,
        )
        result["reason"] = reason
        return result

    if mode != "llm" or llm_config is None:
        result = _base_result(
            status="skipped", kind=clean_kind, subject_id=str(subject_id),
            context=context, reason="未启用模型裁判。",
        )
        result["reason"] = "未启用模型裁判。"
        return result

    # AI 生成提案（使用查询工具）
    try:
        candidate = dict(proposal) if isinstance(proposal, Mapping) else run_adjudication_with_tools(
            db, state, llm_config, agno_db,
            clean_kind, str(subject_id),
            player_intent=player_intent,
            validation_context=context,  # P3: 预加载校验上下文到缓存
        )
    except (LLMUnavailable, LLMContractError, ValueError) as error:
        pending = record_pending_adjudication(db, state, context, str(error), {})
        result = _base_result(
            status="pending_review", kind=clean_kind, subject_id=str(subject_id),
            context=context, reason=f"模型输出不可用：{error}",
        )
        result["pending_adjudication"] = pending
        return result

    # 校验 AI 提案
    try:
        validated = _validate_proposal_for_kind(db, state, clean_kind, context, candidate)
    except ValueError as error:
        pending = record_pending_adjudication(db, state, context, str(error), candidate)
        result = _base_result(
            status="pending_review", kind=clean_kind, subject_id=str(subject_id),
            context=context, proposal=candidate, reason=f"模型提案越界：{error}",
        )
        result["pending_adjudication"] = pending
        return result

    if validated.get("status") == "pending_review":
        pending = dict(validated.get("pending_adjudication") or {})
        result = _base_result(
            status="pending_review", kind=clean_kind, subject_id=str(subject_id),
            context=context, proposal=candidate, validated=validated,
            reason=str(pending.get("reason") or "模型提案需廷议核定"),
        )
        result["pending_adjudication"] = pending
        result["validated"] = json_safe(validated)
        return result

    result = _base_result(
        status="validated", kind=clean_kind, subject_id=str(subject_id),
        context=context, proposal=candidate, validated=validated,
    )
    result["proposal"] = json_safe(candidate)
    result["validated"] = json_safe(validated)
    return result


# ---------------------------------------------------------------------------
# 月末批量裁决
# ---------------------------------------------------------------------------

def _monthly_batch_subjects(db, state: object) -> List[tuple[str, str, Dict[str, Any]]]:
    """收集本月适合让模型参与的裁决对象；只读查询，不直接改变世界。"""
    subjects: List[tuple[str, str, Dict[str, Any]]] = []
    turn = int(getattr(state, "turn", 0) or 0)

    for row in db.conn.execute("SELECT id FROM powers WHERE id<>'liu_bei' ORDER BY id").fetchall():
        subjects.append(("power_action", str(row["id"]), {}))

    diplomacy_rows = db.conn.execute(
        """
        SELECT proposer, target, terms FROM diplomacy_treaties
        WHERE status='proposed'
        ORDER BY id
        """
    ).fetchall()
    for row in diplomacy_rows:
        try:
            terms = json.loads(str(row["terms"] or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            terms = {}
        if not isinstance(terms, dict):
            terms = {}
        proposer = str(row["proposer"])
        target = str(row["target"])
        subjects.append(("diplomacy", f"{proposer}:{target}", {"proposer": proposer, "target": target, "terms": terms}))

    for row in db.conn.execute(
        "SELECT id, minister_name FROM secret_orders WHERE status IN ('active', 'pending_review') ORDER BY id"
    ).fetchall():
        subjects.append(("secret_order", str(row["id"]), {"viewer": str(row["minister_name"] or "")}))

    for row in db.conn.execute("SELECT id FROM sieges WHERE status='active' ORDER BY id").fetchall():
        subjects.append(("siege", str(row["id"]), {}))

    for row in db.conn.execute(
        "SELECT region_id, category FROM region_investments WHERE status='active' ORDER BY region_id"
    ).fetchall():
        subjects.append(("region_investment", str(row["region_id"]), {"category": str(row["category"] or "")}))

    office_rows = db.conn.execute("SELECT office_key, character_name, target_id FROM government_offices ORDER BY office_key").fetchall()
    used_offices = {str(row["office_key"]) for row in office_rows}
    for row in office_rows:
        subjects.append((
            "personnel",
            str(row["office_key"]),
            {"candidate_name": str(row["character_name"] or ""), "target_id": str(row["target_id"] or "")},
        ))
    for office_key in sorted(getattr(getattr(db, "content", None), "sanguo_offices", {}) or {}):
        if str(office_key) not in used_offices:
            subjects.append(("personnel", str(office_key), {}))

    for row in db.conn.execute("SELECT id FROM armies WHERE active=1 ORDER BY id").fetchall():
        subjects.append(("supply", str(row["id"]), {}))

    try:
        content_events = getattr(getattr(db, "content", None), "events", {})
        if isinstance(content_events, Mapping):
            event_items = sorted(content_events.items())
        else:
            event_items = [(str(getattr(event, "id", "") or (event.get("id") if isinstance(event, Mapping) else "")), event) for event in (content_events or [])]
        for event_id, event in event_items:
            is_historical = bool(
                getattr(event, "is_historical", False)
                if not isinstance(event, Mapping)
                else event.get("is_historical")
            )
            if not is_historical:
                continue
            state_row = db.conn.execute(
                "SELECT status FROM historical_event_states WHERE event_id=?", (str(event_id),)
            ).fetchone()
            status = str(state_row["status"]) if state_row is not None else "scheduled"
            if status in {"resolved", "superseded", "expired"}:
                continue
            subjects.append(("world_event", str(event_id), {}))
    except Exception:
        pass

    return subjects


def _has_existing_adjudication_trace(db, turn: int, kind: str, subject_id: str) -> bool:
    checks = {
        "power_action": (
            "SELECT 1 FROM power_ai_actions WHERE turn=? AND power_id=? LIMIT 1",
            (turn, subject_id),
        ),
        "supply": (
            "SELECT 1 FROM army_logs WHERE turn=? AND army_id=? AND field='ai_judge' LIMIT 1",
            (turn, subject_id),
        ),
        "secret_order": (
            "SELECT 1 FROM secret_orders WHERE id=? AND sim_note LIKE '%AI裁判%' LIMIT 1",
            (subject_id,),
        ),
        "siege": (
            "SELECT 1 FROM sieges WHERE id=? AND details LIKE '%ai_judge%' LIMIT 1",
            (subject_id,),
        ),
        "region_investment": (
            "SELECT 1 FROM region_investment_logs WHERE turn=? AND region_id=? AND reason LIKE '%AI裁判%' LIMIT 1",
            (turn, subject_id),
        ),
        "world_event": (
            "SELECT 1 FROM historical_chronicle WHERE turn=? AND event_id=? AND summary LIKE '%AI裁判%' LIMIT 1",
            (turn, subject_id),
        ),
    }
    if kind == "diplomacy":
        parts = subject_id.split(":", 1)
        if len(parts) != 2:
            return False
        sql = (
            "SELECT 1 FROM diplomacy_logs WHERE turn=? AND "
            "((power_a=? AND power_b=?) OR (power_a=? AND power_b=?)) "
            "AND reason LIKE '%AI裁判%' LIMIT 1"
        )
        args = (turn, parts[0], parts[1], parts[1], parts[0])
    else:
        item = checks.get(kind)
        if item is None:
            return False
        sql, args = item
    try:
        return db.conn.execute(sql, args).fetchone() is not None
    except Exception:
        return False


def _collect_batch_tasks(
    db, state: object,
) -> List[tuple[str, str, Dict[str, Any]]]:
    """收集所有待裁决项，过滤已处理和 pending 的。串行执行。"""
    tasks: List[tuple[str, str, Dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    turn = int(getattr(state, "turn", 0) or 0)

    for kind, subject_id, kwargs in _monthly_batch_subjects(db, state):
        key = (kind, subject_id)
        if key in seen:
            continue
        seen.add(key)

        if _has_existing_adjudication_trace(db, turn, kind, subject_id):
            continue

        pending = db.conn.execute(
            "SELECT 1 FROM pending_adjudications WHERE turn=? AND kind=? AND subject_id=? AND status='pending_review' LIMIT 1",
            (turn, kind, subject_id),
        ).fetchone()
        if pending is not None:
            continue

        tasks.append((kind, subject_id, kwargs))

    return tasks


def _run_single_adjudication_worker(
    db_path: str,
    state: object,
    kind: str,
    subject_id: str,
    kwargs: Dict[str, Any],
    llm_config: LLMConfig,
    agno_db: Any,
    batch_cache: Any | None = None,
) -> Dict[str, Any]:
    """单个裁决的工作线程函数。每个线程使用独立 DB 连接。"""
    import sqlite3
    from ming_sim.db import GameDB
    from ming_sim.content import GameContent

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    content = GameContent.load()
    thread_db = GameDB(conn, content=content)

    try:
        t0 = time.monotonic()
        result = run_adjudication(
            thread_db, state, kind, subject_id,
            llm_config=llm_config, agno_db=agno_db,
            **kwargs,
        )
        elapsed = round(time.monotonic() - t0, 2)
        result["_timing"] = {"total_seconds": elapsed}
        return result
    except (ValueError, Exception) as error:
        elapsed = round(time.monotonic() - t0, 2) if 't0' in dir() else 0
        return {
            "status": "unavailable",
            "kind": kind,
            "subject_id": subject_id,
            "reason": str(error),
            "randomness_level": str(_policy_for(kind).get("randomness_level") or ""),
            "proposal_summary": "",
            "validated_changes": [],
            "applied_changes": [],
            "audit_reason": str(error),
            "_timing": {"total_seconds": elapsed},
        }
    finally:
        conn.close()


def run_monthly_adjudication_batch(
    db, state: object, *, max_workers: int = 0,
) -> Dict[str, Any]:
    """月末统一模型随机性批处理（查询工具版）。

    AI 通过 QueryToolKit 主动查询数据，基于玩家意图做出裁决。
    支持并行执行：默认使用 ADJUDICATION_MAX_WORKERS 环境变量（默认 4）。
    设置 max_workers=1 可强制串行（用于测试或调试）。
    """
    llm_config, agno_db = adjudication_runtime_from_state(state)
    if llm_config is None:
        return {"status": "skipped", "reason": "未启用模型裁判。", "results": [], "summary": {"total": 0}}

    # 确定并发数
    if max_workers <= 0:
        max_workers = int(os.environ.get("ADJUDICATION_MAX_WORKERS", "4"))
    max_workers = max(1, min(max_workers, 8))  # 限制在 1-8 之间

    # 收集阶段（串行）
    tasks = _collect_batch_tasks(db, state)
    if not tasks:
        return {
            "status": "completed",
            "results": [],
            "summary": {"total": 0, "validated": 0, "pending_review": 0, "skipped": 0, "unavailable": 0},
        }

    batch_t0 = time.monotonic()

    # 获取 DB 文件路径
    db_row = db.conn.execute("PRAGMA database_list").fetchone()
    db_path = dict(db_row).get("file", "")

    results: List[Dict[str, Any]] = []

    if max_workers == 1 or not db_path:
        # 串行模式（测试/内存数据库/显式指定）
        for kind, subject_id, kwargs in tasks:
            try:
                t0 = time.monotonic()
                result = run_adjudication(
                    db, state, kind, subject_id,
                    llm_config=llm_config, agno_db=agno_db,
                    **kwargs,
                )
                result["_timing"] = {"total_seconds": round(time.monotonic() - t0, 2)}
                results.append(result)
            except ValueError as error:
                results.append({
                    "status": "unavailable",
                    "kind": kind,
                    "subject_id": subject_id,
                    "reason": str(error),
                    "randomness_level": str(_policy_for(kind).get("randomness_level") or ""),
                    "proposal_summary": "",
                    "validated_changes": [],
                    "applied_changes": [],
                    "audit_reason": str(error),
                })
    else:
        # 并行模式
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="adjud") as pool:
            futures = {
                pool.submit(
                    _run_single_adjudication_worker,
                    db_path, state, kind, subject_id, kwargs,
                    llm_config, agno_db,
                ): (kind, subject_id)
                for kind, subject_id, kwargs in tasks
            }

            for fut in as_completed(futures):
                kind, subject_id = futures[fut]
                try:
                    result = fut.result()
                    results.append(result)
                except Exception as error:
                    results.append({
                        "status": "unavailable",
                        "kind": kind,
                        "subject_id": subject_id,
                        "reason": str(error),
                    })

    batch_elapsed = round(time.monotonic() - batch_t0, 2)

    summary = {
        "total": len(results),
        "validated": sum(1 for item in results if item.get("status") == "validated"),
        "pending_review": sum(1 for item in results if item.get("status") == "pending_review"),
        "skipped": sum(1 for item in results if item.get("status") == "skipped"),
        "unavailable": sum(1 for item in results if item.get("status") == "unavailable"),
        "_batch_timing_seconds": batch_elapsed,
        "_max_workers": max_workers,
    }
    return {"status": "completed", "results": json_safe(results), "summary": summary}
