"""分阶段推演执行系统 - P0 核心

将颁令批次按阶段执行：内政 → 军事 → 外交 → 民生 → 核销
支持 SSE 流式输出和检查点裁断。

各阶段使用已有的 GameDB 方法实际修改世界状态，
对于尚无直接方法的操作，记录到执行日志但不崩溃。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ming_sim.db import GameDB
from ming_sim.models import GameState


# ─── 阶段中文名称映射 ─────────────────────────────────────────

PHASE_LABELS: Dict[str, str] = {
    "internal": "内政执行",
    "military": "军事行动",
    "diplomatic": "外交动向",
    "civilian": "民生与事件",
    "settlement": "月度核销",
}


class ExecutionPhase(str, Enum):
    """执行阶段"""
    INTERNAL = "internal"
    MILITARY = "military"
    DIPLOMATIC = "diplomatic"
    CIVILIAN = "civilian"
    SETTLEMENT = "settlement"


@dataclass
class ExecutionEvent:
    """执行事件（用于 SSE 流式输出）"""
    type: str  # phase_start, phase_complete, draft_executed, decision_point, batch_complete, error
    phase: Optional[str] = None
    phase_label: Optional[str] = None
    draft_id: Optional[int] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"type": self.type}
        if self.phase:
            result["phase"] = self.phase
        if self.phase_label:
            result["phase_label"] = self.phase_label
        if self.draft_id is not None:
            result["draft_id"] = self.draft_id
        if self.message:
            result["message"] = self.message
        if self.data:
            result["data"] = self.data
        return result


@dataclass
class PhaseResult:
    """阶段执行结果"""
    phase: ExecutionPhase
    success: bool
    executed_drafts: List[int] = field(default_factory=list)
    failed_drafts: List[int] = field(default_factory=list)
    requires_decision: bool = False
    decision_draft_id: Optional[int] = None
    decision_options: Optional[List[Dict[str, Any]]] = None
    message: str = ""


@dataclass
class ExecutionResult:
    """批次执行结果"""
    batch_id: int
    success: bool
    phase_results: List[PhaseResult] = field(default_factory=list)
    total_executed: int = 0
    total_failed: int = 0
    message: str = ""


class PhasedExecutor:
    """分阶段执行器

    将 batch 中的草案按 directive_type 分组，依次执行五个阶段。
    每个草案执行后通过 update_batch_item_execution 记录结果，
    通过 on_event 回调发射 SSE 事件。
    """

    def __init__(
        self,
        state: GameState,
        db: GameDB,
        batch_id: int,
        on_event: Optional[Callable[[ExecutionEvent], None]] = None,
        llm_config: Any = None,
    ):
        self.state = state
        self.db = db
        self.batch_id = batch_id
        self.on_event = on_event or (lambda _e: None)
        self.llm_config = llm_config
        self._execution_log: List[str] = []  # 累积执行日志
        self._checkpoint = self.db.get_directive_batch_checkpoint(batch_id)

    # ─── 工具方法 ──────────────────────────────────────────

    def _emit(self, event: ExecutionEvent) -> None:
        self.on_event(event)

    def _emit_phase_start(self, phase: ExecutionPhase) -> None:
        self._emit(ExecutionEvent(
            type="phase_start",
            phase=phase.value,
            phase_label=PHASE_LABELS.get(phase.value, phase.value),
            message=f"开始{PHASE_LABELS.get(phase.value, phase.value)}",
        ))

    def _emit_phase_complete(self, phase: ExecutionPhase, result: PhaseResult) -> None:
        self._emit(ExecutionEvent(
            type="phase_complete",
            phase=phase.value,
            phase_label=PHASE_LABELS.get(phase.value, phase.value),
            message=f"{PHASE_LABELS.get(phase.value, phase.value)}完成：成功 {len(result.executed_drafts)}，失败 {len(result.failed_drafts)}",
            data={
                "executed": len(result.executed_drafts),
                "failed": len(result.failed_drafts),
                "requires_decision": result.requires_decision,
            },
        ))

    def _emit_draft_success(self, phase: ExecutionPhase, draft_id: int, message: str, data: Optional[Dict] = None) -> None:
        self._emit(ExecutionEvent(
            type="draft_executed",
            phase=phase.value,
            draft_id=draft_id,
            message=message,
            data=data,
        ))
        self._execution_log.append(message)
        self.db.update_batch_item_execution(self.batch_id, draft_id, "success", json.dumps(data or {}, ensure_ascii=False))

    def _emit_draft_fail(self, phase: ExecutionPhase, draft_id: int, message: str) -> None:
        self._emit(ExecutionEvent(
            type="error",
            phase=phase.value,
            draft_id=draft_id,
            message=message,
        ))
        self._execution_log.append(f"[失败] {message}")
        self.db.update_batch_item_execution(self.batch_id, draft_id, "failed", json.dumps({"error": message}, ensure_ascii=False))

    def _get_drafts_by_type(self, directive_type: str) -> List[Dict[str, Any]]:
        """获取批次中指定类型的草案"""
        batch = self.db.get_directive_batch(self.batch_id)
        if not batch or "items" not in batch:
            return []
        drafts: List[Dict[str, Any]] = []
        for item in batch["items"]:
            if str(item.get("execution_status") or "") == "success":
                continue
            draft = self.db.get_directive_draft(item["draft_id"])
            if draft and draft["directive_type"] == directive_type:
                drafts.append(draft)
        return drafts

    def _checkpoint_choice(self, draft_id: int) -> str:
        checkpoint = self._checkpoint or {}
        if int(checkpoint.get("draft_id") or 0) != int(draft_id):
            return ""
        return str(checkpoint.get("choice") or "") if checkpoint.get("status") == "ready" else ""

    def _parse_json(self, raw: str, default: Any = None) -> Any:
        try:
            return json.loads(raw) if raw else (default if default is not None else {})
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else {}

    # ─── 阶段 1：内政 ──────────────────────────────────────

    def _execute_internal_phase(self) -> PhaseResult:
        self._emit_phase_start(ExecutionPhase.INTERNAL)
        drafts = self._get_drafts_by_type("internal")
        executed: List[int] = []
        failed: List[int] = []

        for draft in drafts:
            try:
                msg = self._execute_internal_draft(draft)
                executed.append(draft["id"])
                self._emit_draft_success(ExecutionPhase.INTERNAL, draft["id"], msg)
            except Exception as e:
                failed.append(draft["id"])
                self._emit_draft_fail(ExecutionPhase.INTERNAL, draft["id"], str(e))

        result = PhaseResult(
            phase=ExecutionPhase.INTERNAL,
            success=len(failed) == 0,
            executed_drafts=executed,
            failed_drafts=failed,
            message="内政执行完成",
        )
        self._emit_phase_complete(ExecutionPhase.INTERNAL, result)
        return result

    def _execute_internal_draft(self, draft: Dict[str, Any]) -> str:
        """执行单个内政草案，返回描述消息"""
        target = draft.get("target", "")
        assignee = draft.get("assignee", "")
        resources = self._parse_json(draft.get("resources_json", "{}"), {})
        title = draft.get("title", "")
        sub_type = resources.get("sub_type", "")

        # ─── 任免（优先判断） ───
        is_appointment = (
            sub_type == "appointment"
            or "任免" in target + title
            or "任命" in target + title
            or "调任" in target + title
        )
        if assignee and is_appointment:
            return self._execute_appointment(assignee, target, title, resources)

        # ─── 屯田 ───
        if "屯田" in target or "农田" in target or "屯田" in title:
            grain_bonus = int(resources.get("grain", 100))
            self.state.metrics["粮秣"] = self.state.metrics.get("粮秣", 0) + grain_bonus
            self.db.save_state(self.state)
            return f"屯田推行，粮秣增加 {grain_bonus}"

        # ─── 安民 ───
        if "安民" in target or "民心" in target or "安民" in title:
            pop_bonus = int(resources.get("popularity", 10))
            self.state.metrics["民望"] = self.state.metrics.get("民望", 0) + pop_bonus
            self.db.save_state(self.state)
            return f"安民施策，民望增加 {pop_bonus}"

        # ─── 征发 ───
        if "征发" in target or "征兵" in target or "征发" in title:
            mil_bonus = int(resources.get("military_supply", 200))
            pop_penalty = int(resources.get("popularity_penalty", 5))
            self.state.metrics["军资"] = self.state.metrics.get("军资", 0) + mil_bonus
            self.state.metrics["民望"] = self.state.metrics.get("民望", 0) - pop_penalty
            self.db.save_state(self.state)
            return f"征发完成，军资增加 {mil_bonus}，民望降低 {pop_penalty}"

        # ─── 通用内政 ───
        return f"内政策略执行完成：{title}"

    def _execute_appointment(
        self, assignee: str, target: str, title: str, resources: Dict[str, Any]
    ) -> str:
        """执行任免操作

        优先尝试政府十槽官制（government_offices），
        若 target 不是有效 office_key 则退回古典官制（characters.office）。
        """
        from ming_sim.government import GOVERNMENT_OFFICE_KEYS  # 十槽 key 列表

        office = target or title
        # 尝试十槽官制
        if office in GOVERNMENT_OFFICE_KEYS:
            try:
                from ming_sim.government import appoint_office
                appoint_office(self.db, self.state, office, assignee, resources.get("target_id", ""))
                return f"任命 {assignee} 为{office}（政府十槽）"
            except Exception as e:
                # 降级到古典官制
                pass

        # 古典官制
        try:
            office_type = resources.get("office_type", "")
            self.db.set_character_office(assignee, office, office_type=office_type, source="军府方略")
            return f"调任 {assignee} 为 {office}"
        except Exception as e:
            return f"任免记录：{assignee} → {office}（{e}）"

    # ─── 阶段 2：军事 ──────────────────────────────────────

    def _execute_military_phase(self) -> PhaseResult:
        self._emit_phase_start(ExecutionPhase.MILITARY)
        drafts = self._get_drafts_by_type("military")
        executed: List[int] = []
        failed: List[int] = []
        requires_decision = False
        decision_draft_id = None
        decision_options = None

        for draft in drafts:
            try:
                result = self._execute_military_draft(draft)
                if result.get("requires_decision"):
                    requires_decision = True
                    decision_draft_id = draft["id"]
                    decision_options = result.get("options")
                    self._emit(ExecutionEvent(
                        type="decision_point",
                        phase=ExecutionPhase.MILITARY.value,
                        draft_id=draft["id"],
                        message=result.get("message", "需要裁断"),
                        data={"options": decision_options},
                    ))
                    break
                executed.append(draft["id"])
                self._emit_draft_success(ExecutionPhase.MILITARY, draft["id"], result.get("message", ""))
            except Exception as e:
                failed.append(draft["id"])
                self._emit_draft_fail(ExecutionPhase.MILITARY, draft["id"], str(e))

        result = PhaseResult(
            phase=ExecutionPhase.MILITARY,
            success=len(failed) == 0,
            executed_drafts=executed,
            failed_drafts=failed,
            requires_decision=requires_decision,
            decision_draft_id=decision_draft_id,
            decision_options=decision_options,
            message="需要玩家裁断" if requires_decision else "军事行动完成",
        )
        self._emit_phase_complete(ExecutionPhase.MILITARY, result)
        return result

    def _execute_military_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个军事草案"""
        assignee = draft.get("assignee", "")
        target = draft.get("target", "")
        title = draft.get("title", "")
        resources = self._parse_json(draft.get("resources_json", "{}"), {})
        sub_type = resources.get("sub_type", "")

        # ─── 战役相关操作 ───
        if sub_type == "campaign" or any(k in target + title for k in ("战役", "出征", "大军")):
            return self._execute_campaign_draft(draft, resources)

        # ─── 行军 / 移动 ───
        if any(k in target + title for k in ("行军", "移动", "开拔")):
            # 通过 issue_army_order 记录军令
            army_id = assignee  # 简化：assignee 为 army_id 或将军名
            try:
                order_id = self.db.issue_army_order(
                    self.state,
                    army_id=army_id,
                    order_type="move",
                    payload={"destination": target, "reason": title},
                )
                return {"requires_decision": False, "message": f"{assignee} 已下达行军令，目标 {target}（军令 #{order_id}）"}
            except Exception:
                # 如果 army_id 不合法，降级为仅记录
                return {"requires_decision": False, "message": f"{assignee} 准备行军至 {target}（军令记录降级）"}

        # 攻城 / 攻击
        if any(k in target + title for k in ("攻城", "攻击", "进攻")):
            ambush = float(resources.get("ambush_chance", 0))
            if ambush > 0.5:
                choice = self._checkpoint_choice(int(draft["id"]))
                if choice:
                    return {"requires_decision": False, "message": f"伏击处已按主公裁断“{choice}”执行"}
                return {
                    "requires_decision": True,
                    "options": [
                        {"label": "撤退", "description": "保存实力，撤退到安全区域"},
                        {"label": "继续进攻", "description": "冒险继续进攻，可能损失惨重"},
                    ],
                    "message": f"{assignee} 在 {target} 遭遇伏击，需要裁断",
                }
            try:
                order_id = self.db.issue_army_order(
                    self.state,
                    army_id=assignee,
                    order_type="siege",
                    payload={"target": target, "reason": title},
                )
                return {"requires_decision": False, "message": f"{assignee} 开始围攻 {target}（军令 #{order_id}）"}
            except Exception:
                return {"requires_decision": False, "message": f"{assignee} 准备攻打 {target}"}

        # 驻守 / 防御
        if any(k in target + title for k in ("驻守", "防御", "守备")):
            try:
                order_id = self.db.issue_army_order(
                    self.state,
                    army_id=assignee,
                    order_type="guard",
                    payload={"location": target, "reason": title},
                )
                return {"requires_decision": False, "message": f"{assignee} 已受命驻守 {target}（军令 #{order_id}）"}
            except Exception:
                return {"requires_decision": False, "message": f"{assignee} 准备驻守 {target}"}

        # 默认
        return {"requires_decision": False, "message": f"军事策略执行完成：{title}"}

    def _execute_campaign_draft(self, draft: Dict[str, Any], resources: Dict[str, Any]) -> Dict[str, Any]:
        """执行战役相关军事草案"""
        assignee = draft.get("assignee", "")
        target = draft.get("target", "")
        title = draft.get("title", "")
        campaign_action = resources.get("campaign_action", "create")

        if campaign_action == "create":
            try:
                army_ids = resources.get("army_ids", [])
                if assignee and assignee not in army_ids:
                    army_ids.append(assignee)
                campaign = self.db.create_campaign(
                    self.state,
                    name=title or f"{assignee}出征{target}",
                    objective=resources.get("objective", title),
                    theater_node=target,
                    commander=assignee,
                    army_ids=army_ids,
                    planned_duration=int(resources.get("duration", 3)),
                )
                return {
                    "requires_decision": False,
                    "message": f"战役 \"{campaign['name']}\" 已建立（#{campaign['id']}），统帅 {assignee}，战区 {target}",
                }
            except Exception as e:
                return {"requires_decision": False, "message": f"战役创建记录：{title}（{e}）"}

        if campaign_action == "reinforce":
            campaign_id = resources.get("campaign_id")
            if campaign_id:
                try:
                    army_ids = resources.get("reinforcement_armies", [])
                    self.db.add_campaign_reinforcements(int(campaign_id), army_ids)
                    return {"requires_decision": False, "message": f"战役 #{campaign_id} 增援已登记"}
                except Exception as e:
                    return {"requires_decision": False, "message": f"增援登记失败：{e}"}

        if campaign_action == "retreat":
            campaign_id = resources.get("campaign_id")
            if campaign_id:
                try:
                    self.db.order_campaign_retreat(int(campaign_id))
                    return {"requires_decision": False, "message": f"战役 #{campaign_id} 已下令撤军"}
                except Exception as e:
                    return {"requires_decision": False, "message": f"撤军命令失败：{e}"}

        if campaign_action == "adjust":
            campaign_id = resources.get("campaign_id")
            new_objective = resources.get("new_objective", "")
            if campaign_id and new_objective:
                try:
                    self.db.update_campaign(int(campaign_id), objective=new_objective)
                    return {"requires_decision": False, "message": f"战役 #{campaign_id} 目标调整为：{new_objective}"}
                except Exception as e:
                    return {"requires_decision": False, "message": f"目标调整失败：{e}"}

        return {"requires_decision": False, "message": f"战役相关操作已记录：{title}"}

    # ─── 阶段 3：外交 ──────────────────────────────────────

    def _execute_diplomatic_phase(self) -> PhaseResult:
        self._emit_phase_start(ExecutionPhase.DIPLOMATIC)
        drafts = self._get_drafts_by_type("diplomatic")
        executed: List[int] = []
        failed: List[int] = []

        for draft in drafts:
            try:
                msg = self._execute_diplomatic_draft(draft)
                executed.append(draft["id"])
                self._emit_draft_success(ExecutionPhase.DIPLOMATIC, draft["id"], msg)
            except Exception as e:
                failed.append(draft["id"])
                self._emit_draft_fail(ExecutionPhase.DIPLOMATIC, draft["id"], str(e))

        result = PhaseResult(
            phase=ExecutionPhase.DIPLOMATIC,
            success=len(failed) == 0,
            executed_drafts=executed,
            failed_drafts=failed,
            message="外交动向完成",
        )
        self._emit_phase_complete(ExecutionPhase.DIPLOMATIC, result)
        return result

    def _execute_diplomatic_draft(self, draft: Dict[str, Any]) -> str:
        """执行单个外交草案"""
        assignee = draft.get("assignee", "")
        target = draft.get("target", "")
        title = draft.get("title", "")
        narrative = draft.get("narrative_text", "")

        # 派遣使臣
        if any(k in title + target for k in ("使臣", "出使", "遣使", "外交")):
            try:
                mission = self.db.create_envoy_mission(
                    self.state,
                    target_power=target,
                    envoy=assignee,
                    goal=narrative or title,
                )
                mission_id = mission.get("id", "?") if isinstance(mission, dict) else "?"
                return f"已派遣 {assignee} 出使 {target}（使命 #{mission_id}）"
            except Exception as e:
                return f"使臣派遣记录：{assignee} → {target}（{e}）"

        # 结盟
        if any(k in target + title for k in ("结盟", "联盟", "同盟")):
            return f"与 {target} 结盟意向已记录（条约系统将在 P1 实现）"

        # 求和
        if any(k in target + title for k in ("求和", "和谈", "议和")):
            return f"向 {target} 提出和谈意向，{assignee} 为使者（和谈系统将在 P1 实现）"

        return f"外交策略执行完成：{title}"

    # ─── 阶段 4：民生 ──────────────────────────────────────

    def _execute_civilian_phase(self) -> PhaseResult:
        self._emit_phase_start(ExecutionPhase.CIVILIAN)
        drafts = self._get_drafts_by_type("other") + self._get_drafts_by_type("secret")
        executed: List[int] = []
        failed: List[int] = []

        for draft in drafts:
            try:
                msg = self._execute_civilian_draft(draft)
                executed.append(draft["id"])
                self._emit_draft_success(ExecutionPhase.CIVILIAN, draft["id"], msg)
            except Exception as e:
                failed.append(draft["id"])
                self._emit_draft_fail(ExecutionPhase.CIVILIAN, draft["id"], str(e))

        result = PhaseResult(
            phase=ExecutionPhase.CIVILIAN,
            success=len(failed) == 0,
            executed_drafts=executed,
            failed_drafts=failed,
            message="民生与事件完成",
        )
        self._emit_phase_complete(ExecutionPhase.CIVILIAN, result)
        return result

    def _execute_civilian_draft(self, draft: Dict[str, Any]) -> str:
        """执行单个民生/密令草案"""
        assignee = draft.get("assignee", "")
        target = draft.get("target", "")
        title = draft.get("title", "")
        directive_type = draft.get("directive_type", "")
        resources = self._parse_json(draft.get("resources_json", "{}"), {})

        # 事件页只能把选择写入草案；实际结算必须随颁令批次发生。
        if resources.get("sub_type") == "identity_promotion":
            action = str(resources.get("identity_action") or "")
            from ming_sim.identity import apply_identity_promotion
            result = apply_identity_promotion(self.db, self.state, action)
            return f"{title}已依方略施行，身份进至{result['stage']}。"

        if resources.get("sub_type") == "random_event_resolution":
            event_id = resources.get("random_event_id")
            choice = resources.get("choice")
            if not event_id or choice in (None, ""):
                raise ValueError("事件处理方略缺少事件编号或处理方案")
            from ming_sim.random_events import resolve_random_event

            result = resolve_random_event(self.db, self.state, int(event_id), str(choice))
            if result.get("error"):
                raise ValueError(str(result["error"]))
            return f"事件“{title}”已按方略处理：{result.get('choice', '已核定')}"

        # 密令
        if directive_type == "secret":
            if assignee:
                try:
                    order_id = self.db.create_secret_order(
                        self.state,
                        minister_name=assignee,
                        title=title,
                        content=draft.get("narrative_text", ""),
                        tags=[directive_type],
                    )
                    return f"密令已下达给 {assignee}：{title}（密令 #{order_id}）"
                except Exception as e:
                    return f"密令记录：{assignee} → {title}（{e}）"
            return f"密令记录：{title}（未指定承办人）"

        # 税收
        if "税收" in target + title:
            tax_bonus = int(resources.get("tax", 100))
            self.state.metrics["军资"] = self.state.metrics.get("军资", 0) + tax_bonus
            self.db.save_state(self.state)
            return f"税收调整完成，军资增加 {tax_bonus}"

        # 贸易
        if "贸易" in target + title:
            trade_bonus = int(resources.get("trade", 150))
            self.state.metrics["军资"] = self.state.metrics.get("军资", 0) + trade_bonus
            self.db.save_state(self.state)
            return f"贸易完成，军资增加 {trade_bonus}"

        # 事件处理
        if "事件" in target + title:
            return f"事件处理已记录：{title}（事件系统将在 P1 实现）"

        # 其他
        return f"民生策略执行完成：{title}"

    # ─── 阶段 5：核销 ──────────────────────────────────────

    def _execute_settlement_phase(self) -> PhaseResult:
        self._emit_phase_start(ExecutionPhase.SETTLEMENT)

        try:
            self._perform_settlement()
            result = PhaseResult(
                phase=ExecutionPhase.SETTLEMENT,
                success=True,
                message="月度核销完成",
            )
            self._emit_phase_complete(ExecutionPhase.SETTLEMENT, result)
            return result
        except Exception as e:
            result = PhaseResult(
                phase=ExecutionPhase.SETTLEMENT,
                success=False,
                message=f"核销失败：{e}",
            )
            self._emit(ExecutionEvent(
                type="error",
                phase=ExecutionPhase.SETTLEMENT.value,
                message=f"核销失败：{e}",
            ))
            return result

    def _perform_settlement(self) -> None:
        """执行月度核销

        复用已有 GameDB 方法：
        1. advance_ongoing_plans — 推进进行中的方略
        2. save_turn_report — 保存月度回奏
        3. save_state — 持久化当前状态（含 metrics 变更）
        """
        # 1. 推进 ongoing_plans
        try:
            plan_results = self.db.advance_ongoing_plans(self.state)
            if plan_results:
                self._execution_log.append(f"推进 {len(plan_results)} 条持续方略")
        except Exception as e:
            self._execution_log.append(f"推进持续方略时出错：{e}")

        # 2. 生成回奏摘要
        batch = self.db.get_directive_batch(self.batch_id) or {}
        drafts = [self.db.get_directive_draft(item["draft_id"]) for item in batch.get("items", [])]
        from ming_sim.reactions import run_reaction_layer
        reactions = run_reaction_layer(
            self.db, self.state, batch_id=self.batch_id, drafts=[item for item in drafts if item],
            llm_config=self.llm_config,
        )
        self._execution_log.extend(reactions["summaries"])
        report_text = self._build_settlement_report()

        # 3. 保存回奏
        try:
            self.db.save_turn_report(self.state, report_text)
        except Exception as e:
            self._execution_log.append(f"保存回奏时出错：{e}")

        # 4. 保存状态（含 metrics 变更）
        self.db.save_state(self.state)

        # 注意：不在此处调用 next_period()
        # 回合推进由前端 POST /api/turn/next 显式触发

    def _build_settlement_report(self) -> str:
        """生成本月执行回奏文本"""
        lines = [
            f"建安{self.state.year}年第{self.state.turn}回合执行摘要",
            f"{'=' * 40}",
        ]
        for log_entry in self._execution_log:
            lines.append(f"  · {log_entry}")
        lines.append("")
        lines.append("当前国势：")
        for key, value in self.state.metrics.items():
            lines.append(f"  {key}：{value:.0f}")
        return "\n".join(lines)

    # ─── 主执行入口 ─────────────────────────────────────────

    def execute(self) -> ExecutionResult:
        """执行完整批次（五阶段）"""
        phase_results: List[PhaseResult] = []
        total_executed = 0
        total_failed = 0

        # 阶段 1：内政
        result = self._execute_internal_phase()
        phase_results.append(result)
        total_executed += len(result.executed_drafts)
        total_failed += len(result.failed_drafts)

        if result.requires_decision:
            return self._halt_for_decision(phase_results, total_executed, total_failed)

        # 阶段 2：军事
        result = self._execute_military_phase()
        phase_results.append(result)
        total_executed += len(result.executed_drafts)
        total_failed += len(result.failed_drafts)

        if result.requires_decision:
            return self._halt_for_decision(phase_results, total_executed, total_failed)

        # 阶段 3：外交
        result = self._execute_diplomatic_phase()
        phase_results.append(result)
        total_executed += len(result.executed_drafts)
        total_failed += len(result.failed_drafts)

        # 阶段 4：民生
        result = self._execute_civilian_phase()
        phase_results.append(result)
        total_executed += len(result.executed_drafts)
        total_failed += len(result.failed_drafts)

        # 阶段 5：核销
        result = self._execute_settlement_phase()
        phase_results.append(result)

        # 完成
        self._emit(ExecutionEvent(
            type="batch_complete",
            message=f"批次执行完成：成功 {total_executed}，失败 {total_failed}",
            data={
                "batch_id": self.batch_id,
                "total_executed": total_executed,
                "total_failed": total_failed,
            },
        ))

        # 更新批次状态
        self.db.update_directive_batch(
            self.batch_id,
            status="completed" if total_failed == 0 else "failed",
            completed_at=str(self.state.turn),
        )
        if self._checkpoint:
            self.db.complete_directive_batch_checkpoint(self.batch_id)

        return ExecutionResult(
            batch_id=self.batch_id,
            success=total_failed == 0,
            phase_results=phase_results,
            total_executed=total_executed,
            total_failed=total_failed,
            message="批次执行完成",
        )

    def _halt_for_decision(
        self,
        phase_results: List[PhaseResult],
        total_executed: int,
        total_failed: int,
    ) -> ExecutionResult:
        """因需要玩家裁断而暂停"""
        # 更新批次状态为 executing（暂停中）
        self.db.update_directive_batch(self.batch_id, status="executing")
        decision = next((item for item in reversed(phase_results) if item.requires_decision), None)
        if decision is not None:
            self._checkpoint = self.db.save_directive_batch_checkpoint(
                self.batch_id, phase=decision.phase.value, draft_id=int(decision.decision_draft_id or 0),
                options=list(decision.decision_options or []), status="pending",
            )

        return ExecutionResult(
            batch_id=self.batch_id,
            success=False,
            phase_results=phase_results,
            total_executed=total_executed,
            total_failed=total_failed,
            message="需要玩家裁断",
        )
