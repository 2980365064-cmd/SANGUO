"""Action intents, ongoing plans, envoy missions, and reputation logs.

This layer turns player/council ideas into durable world debts. LLM text may
draft or explain an idea, but monthly settlement reads these tables.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List


ACTION_TYPES = {
    "军令", "密令", "使臣外交", "国策", "地区治理", "任免赏罚",
    "补给调度", "迁民安抚", "情报任务", "长期方略",
}


def _json_loads(value: object, fallback: object) -> object:
    try:
        return json.loads(str(value or json.dumps(fallback, ensure_ascii=False)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


class _ActionPlansMixin:
    def _character_power_status(self, name: str) -> tuple[str, str]:
        row = self.conn.execute(
            "SELECT power_id, status FROM characters WHERE name=?", (str(name),)
        ).fetchone()
        if row is None:
            return "", ""
        return str(row["power_id"] or ""), str(row["status"] or "")

    def _extract_assignee(self, text: str) -> str:
        explicit = re.search(r"(?:让|令|命|派|遣)([^，。；、\s]{2,4})", text)
        if explicit:
            candidate = explicit.group(1)
            for name in ("诸葛亮", "关羽", "张飞", "赵云", "糜竺", "孙乾", "简雍", "刘备", "曹操"):
                if name in candidate:
                    return name
        for name in ("诸葛亮", "关羽", "张飞", "赵云", "糜竺", "孙乾", "简雍", "刘备", "曹操"):
            if name in text:
                return name
        return ""

    def _extract_duration(self, text: str) -> int:
        numerals = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}
        match = re.search(r"([一二两三四五六]|\d+)\s*个?月", text)
        if not match:
            return 1
        raw = match.group(1)
        return max(1, min(12, int(raw) if raw.isdigit() else numerals.get(raw, 1)))

    def _classify_action_type(self, text: str, duration: int) -> str:
        if duration > 1:
            return "长期方略"
        if any(word in text for word in ("使臣", "遣使", "谈", "盟", "借粮", "议和")):
            return "使臣外交"
        if any(word in text for word in ("密查", "暗查", "刺探", "离间", "策反")):
            return "情报任务"
        if any(word in text for word in ("平定", "叛军", "迁民", "安抚", "护送")):
            return "地区治理"
        return "长期方略"

    def build_action_draft(self, text: str, source: str = "自由命令") -> Dict[str, Any]:
        text = (text or "").strip()
        assignee = self._extract_assignee(text)
        duration = self._extract_duration(text)
        action_type = self._classify_action_type(text, duration)
        reasons: List[str] = []
        executable = bool(text)
        if not text:
            executable = False
            reasons.append("命令内容不能为空。")
        if assignee:
            power_id, status = self._character_power_status(assignee)
            if power_id != "liu_bei" or status != "active":
                executable = False
                reasons.append(f"{assignee}不属刘备军府或当前不可承办。")
        elif action_type in {"长期方略", "地区治理", "情报任务"}:
            executable = False
            reasons.append("缺少明确执行者。")
        constraints = "；".join(
            item for item in ("不得滥杀百姓", "不得伤民", "不得背盟", "不得暴露刘备名义")
            if item in text
        )
        risks = []
        if "叛军" in text or "平定" in text:
            risks += ["强攻伤民", "粮道受扰", "地方豪强暗助"]
        if "借粮" in text or "盟" in text:
            risks += ["承诺过重", "互信受损"]
        return {
            "executable": executable,
            "action_type": action_type,
            "title": text[:40],
            "assignee": assignee,
            "target": "江夏" if "江夏" in text else "",
            "duration_months": duration if action_type == "长期方略" else 1,
            "resources": {"军资": 0, "粮秣": 0},
            "constraints": constraints,
            "risks": risks,
            "reasons": reasons,
            "rewrite_suggestion": "" if executable else "请改派刘备军府 active 人物，并说明目标、边界与期限。",
            "source": source,
        }

    def _action_intent_payload(self, row) -> Dict[str, Any]:
        item = self._row_dict(row)
        item["draft"] = _json_loads(item.get("draft_json"), {})
        item.pop("draft_json", None)
        return item

    def create_action_intent(self, state: object, *, source: str, text: str) -> Dict[str, Any]:
        draft = self.build_action_draft(text, source=source)
        cursor = self.conn.execute(
            """
            INSERT INTO action_intents
            (turn, year, period, source, text, draft_json, status)
            VALUES (?, ?, ?, ?, ?, ?, 'draft')
            """,
            (
                int(getattr(state, "turn", 0)),
                int(getattr(state, "year", 0)),
                int(getattr(state, "period", 0)),
                str(source or "自由命令"),
                str(text or "").strip(),
                json.dumps(draft, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.conn.commit()
        return self.get_action_intent(int(cursor.lastrowid))

    def get_action_intent(self, intent_id: int) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM action_intents WHERE id=?", (int(intent_id),)).fetchone()
        if row is None:
            raise ValueError(f"方略草案不存在：{intent_id}")
        return self._action_intent_payload(row)

    def list_action_intents(self, status: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM action_intents"
        params: tuple[object, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY id DESC"
        return [self._action_intent_payload(row) for row in self.conn.execute(sql, params).fetchall()]

    def _ongoing_plan_payload(self, row) -> Dict[str, Any]:
        item = self._row_dict(row)
        for field, fallback in (("resources", {}), ("constraints", []), ("risks", [])):
            item[field] = _json_loads(item.get(f"{field}_json"), fallback)
            item.pop(f"{field}_json", None)
        item["logs"] = self.list_ongoing_plan_logs(int(item["id"]))
        return item

    def create_ongoing_plan_from_draft(self, state: object, intent: Dict[str, Any]) -> Dict[str, Any]:
        draft = dict(intent.get("draft") or {})
        if not draft.get("executable"):
            raise ValueError("草案当前不可执行，不能入账。")
        duration = max(1, int(draft.get("duration_months") or 1))
        cursor = self.conn.execute(
            """
            INSERT INTO ongoing_plans
            (origin_turn, year, period, source, source_id, title, action_type, assignee,
             target, duration_months, progress, resources_json, constraints_json, risks_json,
             status, last_result, next_check_turn)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'active', '', ?)
            """,
            (
                int(getattr(state, "turn", 0)),
                int(getattr(state, "year", 0)),
                int(getattr(state, "period", 0)),
                str(intent.get("source") or "自由命令"),
                str(intent.get("id") or ""),
                str(draft.get("title") or intent.get("text") or "")[:80],
                str(draft.get("action_type") or "长期方略"),
                str(draft.get("assignee") or ""),
                str(draft.get("target") or ""),
                duration,
                json.dumps(draft.get("resources") or {}, ensure_ascii=False, sort_keys=True),
                json.dumps([draft.get("constraints")] if draft.get("constraints") else [], ensure_ascii=False),
                json.dumps(draft.get("risks") or [], ensure_ascii=False),
                int(getattr(state, "turn", 0)),
            ),
        )
        self.conn.execute("UPDATE action_intents SET status='confirmed', updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(intent["id"]),))
        self.conn.commit()
        return self.get_ongoing_plan(int(cursor.lastrowid))

    def confirm_action_intent(self, state: object, intent_id: int) -> Dict[str, Any]:
        intent = self.get_action_intent(intent_id)
        draft = intent["draft"]
        if not draft.get("executable"):
            raise ValueError("草案当前不可执行，不能确认。")
        if str(draft.get("action_type")) == "长期方略" or int(draft.get("duration_months") or 1) > 1:
            plan = self.create_ongoing_plan_from_draft(state, intent)
            return {"kind": "ongoing_plan", "plan_id": int(plan["id"]), "plan": plan}
        self.conn.execute("UPDATE action_intents SET status='confirmed', updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(intent_id),))
        self.conn.commit()
        return {"kind": "action_intent", "intent": self.get_action_intent(intent_id)}

    def get_ongoing_plan(self, plan_id: int) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM ongoing_plans WHERE id=?", (int(plan_id),)).fetchone()
        if row is None:
            raise ValueError(f"持续方略不存在：{plan_id}")
        return self._ongoing_plan_payload(row)

    def list_ongoing_plans(self, status: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM ongoing_plans"
        params: tuple[object, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY status, id DESC"
        return [self._ongoing_plan_payload(row) for row in self.conn.execute(sql, params).fetchall()]

    def update_ongoing_plan(self, plan_id: int, **changes: object) -> Dict[str, Any]:
        allowed = {"status", "assignee", "last_result", "next_check_turn", "progress"}
        pairs = [(key, value) for key, value in changes.items() if key in allowed]
        if not pairs:
            return self.get_ongoing_plan(plan_id)
        clause = ", ".join(f"{key}=?" for key, _ in pairs)
        params = [value for _, value in pairs] + [int(plan_id)]
        self.conn.execute(f"UPDATE ongoing_plans SET {clause}, updated_at=CURRENT_TIMESTAMP WHERE id=?", params)
        self.conn.commit()
        return self.get_ongoing_plan(plan_id)

    def list_ongoing_plan_logs(self, plan_id: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM ongoing_plan_logs WHERE plan_id=? ORDER BY turn, id", (int(plan_id),)
        ).fetchall()
        return [self._row_dict(row) for row in rows]

    def advance_ongoing_plans(self, state: object) -> List[Dict[str, Any]]:
        turn = int(getattr(state, "turn", 0))
        rows = self.conn.execute(
            """
            SELECT * FROM ongoing_plans
            WHERE status='active' AND next_check_turn<=?
            ORDER BY id
            """,
            (turn,),
        ).fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            plan = self._ongoing_plan_payload(row)
            power_id, assignee_status = self._character_power_status(str(plan["assignee"]))
            if power_id != "liu_bei" or assignee_status != "active":
                new_status = "blocked"
                narrative = "执行者不在刘备军府 active 状态，方略受阻，需主公裁断。"
                progress = int(plan["progress"])
            else:
                step = max(1, math.ceil(100 / max(1, int(plan["duration_months"]))))
                progress = _clamp(int(plan["progress"]) + step)
                new_status = "done" if progress >= 100 else "active"
                narrative = (
                    f"{plan['assignee']}继续推进「{plan['title']}」，"
                    f"进度至{progress}%。"
                )
                if new_status == "done":
                    narrative += "方略已可结案，相关影响进入月末核销。"
            self.conn.execute(
                """
                UPDATE ongoing_plans
                SET progress=?, status=?, last_result=?, next_check_turn=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    progress,
                    new_status,
                    narrative,
                    turn + 1,
                    int(plan["id"]),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO ongoing_plan_logs
                (plan_id, turn, year, period, status, progress, narrative)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(plan["id"]),
                    turn,
                    int(getattr(state, "year", 0)),
                    int(getattr(state, "period", 0)),
                    new_status,
                    progress,
                    narrative,
                ),
            )
            if new_status == "done":
                self.add_reputation_log(
                    state,
                    source_kind="ongoing_plan",
                    source_id=str(plan["id"]),
                    metric="仁义",
                    delta=2 if "不得滥杀百姓" in json.dumps(plan["constraints"], ensure_ascii=False) else 0,
                    summary=f"{plan['title']}完成，军府方略有了可核销结果。",
                    commit=False,
                )
            results.append({"plan_id": int(plan["id"]), "status": new_status, "progress": progress, "narrative": narrative})
        self.conn.commit()
        return results

    def add_reputation_log(
        self, state: object, *, source_kind: str, source_id: str, metric: str, delta: int, summary: str, commit: bool = True
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO reputation_logs
            (turn, year, period, source_kind, source_id, metric, delta, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(getattr(state, "turn", 0)),
                int(getattr(state, "year", 0)),
                int(getattr(state, "period", 0)),
                str(source_kind),
                str(source_id),
                str(metric or "仁义"),
                int(delta),
                str(summary),
            ),
        )
        if commit:
            self.conn.commit()
        return int(cursor.lastrowid)

    def reputation_summary(self, limit: int = 8) -> Dict[str, Any]:
        rows = self.conn.execute(
            "SELECT * FROM reputation_logs ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        recent = [self._row_dict(row) for row in rows]
        delta = sum(int(item["delta"] or 0) for item in recent if str(item["metric"]) in {"仁义", "民望"})
        return {"score": _clamp(50 + delta), "recent": recent}

    def create_envoy_mission(self, state: object, *, target_power: str, envoy: str, goal: str, boundaries: str = "") -> Dict[str, Any]:
        power_id, status = self._character_power_status(envoy)
        if power_id != "liu_bei" or status != "active":
            raise ValueError(f"{envoy}不属刘备军府或当前不可遣使。")
        if self.conn.execute("SELECT 1 FROM powers WHERE id=?", (str(target_power),)).fetchone() is None:
            raise ValueError(f"目标势力不存在：{target_power}")
        cursor = self.conn.execute(
            """
            INSERT INTO envoy_missions
            (turn, year, period, target_power, envoy, goal, boundaries, status, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'preparing', '')
            """,
            (
                int(getattr(state, "turn", 0)),
                int(getattr(state, "year", 0)),
                int(getattr(state, "period", 0)),
                str(target_power),
                str(envoy),
                str(goal),
                str(boundaries),
            ),
        )
        self.conn.commit()
        return self.get_envoy_mission(int(cursor.lastrowid))

    def get_envoy_mission(self, mission_id: int) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM envoy_missions WHERE id=?", (int(mission_id),)).fetchone()
        if row is None:
            raise ValueError(f"使臣任务不存在：{mission_id}")
        return self._row_dict(row)

    def list_envoy_missions(self, status: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM envoy_missions"
        params: tuple[object, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY id DESC"
        return [self._row_dict(row) for row in self.conn.execute(sql, params).fetchall()]

    # ─── 使臣任务自动推进 ──────────────────────────────────────

    # 使臣状态机：preparing → traveling → negotiating → returning → completed/failed
    ENVOY_PHASE_TURNS = {
        "preparing": 1,     # 准备 1 回合
        "traveling": 2,     # 旅途 2 回合
        "negotiating": 2,   # 谈判 2 回合
        "returning": 1,     # 返程 1 回合
    }

    def advance_envoy_missions(self, state: object) -> List[Dict[str, Any]]:
        """月末推进所有进行中的使臣任务。

        返回本回合有状态变更的任务列表。
        """
        current_turn = int(getattr(state, "turn", 0))
        results: List[Dict[str, Any]] = []

        active = self.list_envoy_missions()
        for mission in active:
            status = mission.get("status", "")
            if status in ("completed", "failed"):
                continue

            # 检查使臣是否仍然可用
            envoy = mission.get("envoy", "")
            if status != "preparing":  # preparing 阶段不检查（刚任命）
                try:
                    power_id, char_status = self._character_power_status(envoy)
                    if char_status != "active":
                        self.conn.execute(
                            "UPDATE envoy_missions SET status='failed', result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (f"使臣{envoy}已不可用（{char_status}）", mission["id"]),
                        )
                        self.conn.commit()
                        results.append({"id": mission["id"], "status": "failed", "reason": f"{envoy}已{char_status}"})
                        continue
                except Exception:
                    pass

            # 读取 progress（JSON 存储在 result 字段中，用于中间状态跟踪）
            import json as _json
            progress_raw = mission.get("result", "") or "{}"
            try:
                progress = _json.loads(progress_raw) if progress_raw.startswith("{") else {}
            except _json.JSONDecodeError:
                progress = {}

            phase_turns = progress.get("phase_turns", 0) + 1
            required = self.ENVOY_PHASE_TURNS.get(status, 1)

            if status == "preparing":
                if phase_turns >= required:
                    self._update_envoy_status(mission["id"], "traveling", "")
                    results.append({"id": mission["id"], "status": "traveling", "envoy": envoy})
                else:
                    progress["phase_turns"] = phase_turns
                    self._update_envoy_progress(mission["id"], progress)

            elif status == "traveling":
                if phase_turns >= required:
                    self._update_envoy_status(mission["id"], "negotiating", "")
                    results.append({"id": mission["id"], "status": "negotiating", "envoy": envoy})
                else:
                    progress["phase_turns"] = phase_turns
                    self._update_envoy_progress(mission["id"], progress)

            elif status == "negotiating":
                if phase_turns >= required:
                    # 谈判完成：生成结果
                    outcome = self._resolve_envoy_negotiation(mission, state)
                    self._update_envoy_status(mission["id"], "returning", outcome)
                    results.append({"id": mission["id"], "status": "returning", "envoy": envoy, "outcome": outcome})
                else:
                    progress["phase_turns"] = phase_turns
                    self._update_envoy_progress(mission["id"], progress)

            elif status == "returning":
                if phase_turns >= required:
                    # 使臣归来
                    final_result = progress.get("outcome", mission.get("result", ""))
                    self._update_envoy_status(mission["id"], "completed", final_result)
                    results.append({"id": mission["id"], "status": "completed", "envoy": envoy, "result": final_result})
                else:
                    progress["phase_turns"] = phase_turns
                    self._update_envoy_progress(mission["id"], progress)

        return results

    def _update_envoy_status(self, mission_id: int, new_status: str, result: str) -> None:
        self.conn.execute(
            "UPDATE envoy_missions SET status=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_status, result, int(mission_id)),
        )
        self.conn.commit()

    def _update_envoy_progress(self, mission_id: int, progress: Dict[str, Any]) -> None:
        import json as _json
        self.conn.execute(
            "UPDATE envoy_missions SET result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (_json.dumps(progress, ensure_ascii=False), int(mission_id)),
        )
        self.conn.commit()

    def _resolve_envoy_negotiation(self, mission: Dict[str, Any], state: object) -> str:
        """简化版谈判结果生成。

        基于使臣能力、目标势力关系、外交目标计算一个结构化结果。
        完整 AI 裁决将在后续版本接入。
        """
        envoy = mission.get("envoy", "")
        target = mission.get("target_power", "")
        goal = mission.get("goal", "")

        # 获取使臣外交能力
        envoy_ability = 50  # 默认值
        row = self.conn.execute(
            "SELECT abilities FROM characters WHERE name=?", (envoy,)
        ).fetchone()
        if row:
            import json as _json
            try:
                abilities = _json.loads(row[0]) if row[0] else {}
                envoy_ability = int(abilities.get("diplomacy", abilities.get("politics", 50)))
            except (ValueError, TypeError):
                pass

        # 获取当前外交关系
        rel_row = self.conn.execute(
            "SELECT public_relation, trust FROM diplomatic_relations WHERE (power_a=? AND power_b=?) OR (power_a=? AND power_b=?)",
            ("liu_bei", target, target, "liu_bei"),
        ).fetchone()
        base_relation = int(rel_row[0]) if rel_row else 0
        base_trust = int(rel_row[1]) if rel_row else 50

        # 简化判定：使臣能力 * 0.4 + 关系基础 * 0.3 + 信任 * 0.3
        score = envoy_ability * 0.4 + max(0, (base_relation + 100) / 2) * 0.3 + base_trust * 0.3

        if score >= 70:
            outcome = f"出使成功：{envoy}与{target}达成良好共识，外交关系改善。目标：{goal}"
            # 改善外交关系
            if rel_row:
                self.conn.execute(
                    "UPDATE diplomatic_relations SET public_relation = MIN(100, public_relation + 10), trust = MIN(100, trust + 5) WHERE (power_a=? AND power_b=?) OR (power_a=? AND power_b=?)",
                    ("liu_bei", target, target, "liu_bei"),
                )
                self.conn.commit()
        elif score >= 40:
            outcome = f"出使部分成功：{envoy}与{target}进行了有限接触，关系略有改善。目标：{goal}"
            if rel_row:
                self.conn.execute(
                    "UPDATE diplomatic_relations SET public_relation = MIN(100, public_relation + 5) WHERE (power_a=? AND power_b=?) OR (power_a=? AND power_b=?)",
                    ("liu_bei", target, target, "liu_bei"),
                )
                self.conn.commit()
        else:
            outcome = f"出使受阻：{envoy}在{target}未能达成预期目标。关系未改善。目标：{goal}"

        return outcome

    def month_agenda(self, state: object) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for plan in self.list_ongoing_plans("blocked") + self.list_ongoing_plans("pending_review"):
            items.append({
                "id": f"ongoing_plan:{plan['id']}",
                "kind": "长期方略受阻" if plan["status"] == "blocked" else "长期方略待裁",
                "title": str(plan["title"]),
                "summary": str(plan.get("last_result") or "持续方略需要主公裁断。"),
                "ref_id": int(plan["id"]),
                "entry": "朝议",
                "urgency": 80 if plan["status"] == "blocked" else 65,
            })
        due_orders = self.conn.execute(
            """
            SELECT id, title, minister_name FROM secret_orders
            WHERE status IN ('active', 'pending_review') AND due_turn>0 AND due_turn<=?
            ORDER BY id DESC
            """,
            (int(getattr(state, "turn", 0)),),
        ).fetchall()
        for row in due_orders:
            items.append({
                "id": f"secret_order:{row['id']}",
                "kind": "密令待回奏",
                "title": str(row["title"]),
                "summary": f"{row['minister_name']}承办的密令已到核议窗口。",
                "ref_id": int(row["id"]),
                "entry": "朝议",
                "urgency": 70,
            })
        if not items:
            items.append({
                "id": "general:council",
                "kind": "本月军政",
                "title": "召群臣问策",
                "summary": "本月暂无受阻旧案，可先围绕战线、外交与仁义口碑发起廷议。",
                "ref_id": 0,
                "entry": "朝议",
                "urgency": 35,
            })
        return items
