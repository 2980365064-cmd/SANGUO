"""可复现的月度活世界上下文 — Facade 层。

本模块是所有外部调用的唯一入口。内部实现已拆分至 ws_* 子模块。
外部代码不应直接 import ws_* 模块。

子模块：
  - ws_utils: 纯函数工具（JSON 解析 / 数值截断 / 状态判断）
  - ws_common: 公共基础（种子 / 季节 / 关系操作）
  - ws_context: 世界上下文 + 战斗环境
  - ws_memorials: 奏议记忆集成
  - ws_regional: 区域状态 + 事件生成
  - ws_incident_chain: 事件效果 + 政策议题
  - ws_power_internal: 外势内部动态
  - ws_intelligence: 情报网络
  - ws_geopolitics: 地缘反应链
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# ws_utils — 纯函数工具
# ---------------------------------------------------------------------------
from ming_sim.ws_utils import decode_json as _decode  # noqa: F401
from ming_sim.ws_utils import safe_list as _safe_list  # noqa: F401
from ming_sim.ws_utils import status_terminal as _status_terminal  # noqa: F401
from ming_sim.ws_utils import clamp as _clamp_base  # noqa: F401
from ming_sim.ws_utils import get_turn as _get_turn  # noqa: F401
from ming_sim.ws_utils import get_year as _get_year  # noqa: F401
from ming_sim.ws_utils import get_period as _get_period  # noqa: F401
from ming_sim.ws_utils import to_json as _to_json  # noqa: F401
from ming_sim.ws_utils import is_already_processed as _is_already_processed  # noqa: F401

# ---------------------------------------------------------------------------
# ws_common — 公共基础
# ---------------------------------------------------------------------------
from ming_sim.ws_common import seed_for as _seed_for  # noqa: F401
from ming_sim.ws_common import season as _season  # noqa: F401
from ming_sim.ws_common import get_or_create_relation as _get_or_create_relation  # noqa: F401
from ming_sim.ws_common import get_relation as _get_relation  # noqa: F401
from ming_sim.ws_common import iter_active_powers as _iter_active_powers  # noqa: F401
from ming_sim.ws_common import log_power_change as _log_power_change  # noqa: F401
from ming_sim.ws_common import log_diplomacy_change as _log_diplomacy_change  # noqa: F401
from ming_sim.ws_common import log_region_change as _log_region_change  # noqa: F401

# ---------------------------------------------------------------------------
# ws_context — 世界上下文 + 战斗环境
# ---------------------------------------------------------------------------
from ming_sim.ws_context import get_or_create_world_context  # noqa: F401
from ming_sim.ws_context import battle_environment  # noqa: F401

# ---------------------------------------------------------------------------
# ws_memorials — 奏议记忆集成
# ---------------------------------------------------------------------------
from ming_sim.ws_memorials import build_monthly_memorials  # noqa: F401
from ming_sim.ws_memorials import can_write_memory_from_source  # noqa: F401
from ming_sim.ws_memorials import _compute_speaker_score  # noqa: F401

# ---------------------------------------------------------------------------
# ws_regional — 区域状态 + 事件生成
# ---------------------------------------------------------------------------
from ming_sim.ws_regional import _STATE_CLAMP  # noqa: F401
from ming_sim.ws_regional import _ROAD_RECOVERY_PER_TURN  # noqa: F401
from ming_sim.ws_regional import _GENERIC_DECAY_PER_TURN  # noqa: F401
from ming_sim.ws_regional import ALLOWED_INCIDENT_TYPES  # noqa: F401
from ming_sim.ws_regional import _ORDINARY_EFFECT_CAPS  # noqa: F401
from ming_sim.ws_regional import _DRAMATIC_EFFECT_CAPS  # noqa: F401
from ming_sim.ws_regional import _clamp  # noqa: F401
from ming_sim.ws_regional import ensure_regional_world_states  # noqa: F401
from ming_sim.ws_regional import region_world_state  # noqa: F401
from ming_sim.ws_regional import generate_regional_incidents  # noqa: F401
from ming_sim.ws_regional import _apply_effects_to_region  # noqa: F401

# ---------------------------------------------------------------------------
# ws_incident_chain — 事件效果 + 政策议题
# ---------------------------------------------------------------------------
from ming_sim.ws_incident_chain import apply_local_incident_effects  # noqa: F401
from ming_sim.ws_incident_chain import build_incident_policy_issue  # noqa: F401

# ---------------------------------------------------------------------------
# ws_power_internal — 外势内部动态
# ---------------------------------------------------------------------------
from ming_sim.ws_power_internal import _POWER_INTERNAL_DYNAMIC_TYPES  # noqa: F401
from ming_sim.ws_power_internal import _DYNAMIC_EFFECT_CAPS  # noqa: F401
from ming_sim.ws_power_internal import _build_power_internal_candidates  # noqa: F401
from ming_sim.ws_power_internal import ensure_power_internal_dynamics  # noqa: F401
from ming_sim.ws_power_internal import apply_power_internal_dynamic_effects  # noqa: F401

# ---------------------------------------------------------------------------
# ws_intelligence — 情报网络
# ---------------------------------------------------------------------------
from ming_sim.ws_intelligence import record_external_intelligence  # noqa: F401
from ming_sim.ws_intelligence import validate_simulation_evidence  # noqa: F401
from ming_sim.ws_intelligence import build_intelligence_reports_for_turn  # noqa: F401
from ming_sim.ws_intelligence import resolve_intelligence_verification  # noqa: F401
from ming_sim.ws_intelligence import build_incident_intelligence_reports  # noqa: F401
# 观察路径函数（内部 + 统一 API）
from ming_sim.ws_intelligence import _is_bordering_liu_bei  # noqa: F401
from ming_sim.ws_intelligence import _is_power_bordering_liu_bei  # noqa: F401
from ming_sim.ws_intelligence import _has_active_envoy  # noqa: F401
from ming_sim.ws_intelligence import _can_merchant_network  # noqa: F401
from ming_sim.ws_intelligence import _determine_source_and_visibility  # noqa: F401
from ming_sim.ws_intelligence import is_bordering  # noqa: F401
from ming_sim.ws_intelligence import has_active_envoy_unified  # noqa: F401
from ming_sim.ws_intelligence import can_merchant_network_unified  # noqa: F401
from ming_sim.ws_intelligence import determine_observation_source  # noqa: F401

# ---------------------------------------------------------------------------
# ws_geopolitics — 地缘反应链
# ---------------------------------------------------------------------------
from ming_sim.ws_geopolitics import generate_incident_diplomatic_reactions  # noqa: F401
from ming_sim.ws_geopolitics import collect_significant_battle_outcomes  # noqa: F401
from ming_sim.ws_geopolitics import collect_significant_siege_outcomes  # noqa: F401
from ming_sim.ws_geopolitics import collect_treaty_breach_outcomes  # noqa: F401
from ming_sim.ws_geopolitics import generate_geopolitical_reactions  # noqa: F401
from ming_sim.ws_geopolitics import resolve_delayed_reactions  # noqa: F401
# 反应规则层（从 ws_reaction_rules 导入）
from ming_sim.ws_reaction_rules import _eligible_third_parties  # noqa: F401
from ming_sim.ws_reaction_rules import _determine_reaction_type  # noqa: F401
from ming_sim.ws_reaction_rules import _battle_or_siege_reaction  # noqa: F401
from ming_sim.ws_reaction_rules import _treaty_breach_reaction  # noqa: F401
# 反应效果层（从 ws_reaction_effects 导入）
from ming_sim.ws_geopolitics import apply_geopolitical_reaction_effects  # noqa: F401
from ming_sim.ws_geopolitics import select_player_visible_world_dynamics  # noqa: F401
from ming_sim.ws_reaction_effects import _is_power_observable  # noqa: F401
from ming_sim.ws_reaction_effects import _is_bordering_liu_bei_via  # noqa: F401
from ming_sim.ws_reaction_effects import _has_active_envoy_for  # noqa: F401
from ming_sim.ws_reaction_effects import _can_merchant_network_between  # noqa: F401
from ming_sim.ws_reaction_effects import _reaction_source_and_visibility  # noqa: F401
from ming_sim.ws_reaction_effects import _compute_soft_effects  # noqa: F401
from ming_sim.ws_reaction_effects import _compute_action_hints  # noqa: F401
from ming_sim.ws_reaction_effects import build_geopolitical_intelligence_reports  # noqa: F401
