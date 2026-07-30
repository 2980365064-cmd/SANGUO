"""三国战略盘面持久化：路线、军令及后续战役状态的数据库接口。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List

from ming_sim.sanguo_rules import ArmyOrderError, PRIMARY_ORDERS, validate_route_move
from ming_sim.siege import validate_siege_target
from ming_sim.battle import preview_battle, validate_battle_plan


class _StrategyMixin:
    @staticmethod
    def _relation_pair(power_a: str, power_b: str) -> tuple[str, str]:
        if power_a == power_b:
            raise ValueError("外交关系必须发生在两个不同势力之间。")
        return tuple(sorted((str(power_a), str(power_b))))

    def get_diplomatic_relation(self, power_a: str, power_b: str) -> Dict[str, Any]:
        first, second = self._relation_pair(power_a, power_b)
        row = self.conn.execute(
            "SELECT * FROM diplomatic_relations WHERE power_a=? AND power_b=?",
            (first, second),
        ).fetchone()
        if row is None:
            raise ValueError(f"外交关系未建档：{power_a}—{power_b}")
        item = self._row_dict(row)
        for field, fallback in (
            ("obligations", []),
            ("territorial_claims", {}),
            ("marriage_hostages", {}),
        ):
            try:
                item[field] = json.loads(str(item.get(field) or json.dumps(fallback)))
            except (TypeError, ValueError, json.JSONDecodeError):
                item[field] = fallback
        return item

    def list_diplomacy_treaties(self, status: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM diplomacy_treaties"
        params: tuple[object, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = self._row_dict(row)
            try:
                item["terms"] = json.loads(str(item.get("terms") or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                item["terms"] = {}
            out.append(item)
        return out

    def list_sieges(self, status: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM sieges"
        params: tuple[object, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        payloads: List[Dict[str, Any]] = []
        for row in rows:
            item = self._row_dict(row)
            item["details"] = json.loads(str(item.get("details") or "{}"))
            payloads.append(item)
        return payloads

    def list_strategic_nodes(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, province, commandery_id, x, y FROM strategic_nodes ORDER BY id"
        ).fetchall()
        return [self._row_dict(row) for row in rows]

    def list_strategic_routes(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, source, target, kind, note FROM strategic_routes ORDER BY id"
        ).fetchall()
        return [self._row_dict(row) for row in rows]

    def issue_army_order(
        self,
        state: object,
        army_id: str,
        order_type: str,
        payload: Dict[str, object],
    ) -> int:
        if order_type not in PRIMARY_ORDERS:
            raise ArmyOrderError(f"非法主军令：{order_type}")
        turn = int(getattr(state, "turn"))
        if order_type in {"移动", "撤退"}:
            target = str(payload.get("to") or "").strip()
            if not target:
                raise ArmyOrderError(f"{order_type}军令缺少目标节点。")
            army = self.conn.execute(
                "SELECT station_node FROM armies WHERE id=? AND active=1", (army_id,)
            ).fetchone()
            if army is None:
                raise ArmyOrderError(f"军队不存在或已失效：{army_id}")
            validate_route_move(self, army_id, str(army["station_node"]), target)
        elif order_type == "围城":
            target = str(payload.get("target") or payload.get("to") or "").strip()
            if not target:
                raise ArmyOrderError("围城军令缺少目标节点。")
            validate_siege_target(self, army_id, target)
        elif order_type == "突袭":
            target = str(payload.get("target") or payload.get("to") or "").strip()
            defender_ids = [str(item) for item in (payload.get("defender_ids") or [])]
            if not target or not defender_ids:
                raise ArmyOrderError("突袭军令必须指定目标节点和守军。")
            try:
                preview_battle(self, [army_id], defender_ids, target)
                commander_row = self.conn.execute(
                    "SELECT commander FROM armies WHERE id=?", (army_id,)
                ).fetchone()
                validate_battle_plan(
                    self,
                    {"attacker_ids": [army_id], "defender_ids": defender_ids, "node_id": target},
                    payload.get("ai_choice") or {
                        "tactic": "正面交锋",
                        "actor": str(commander_row["commander"] if commander_row else ""),
                    },
                )
            except ValueError as error:
                raise ArmyOrderError(str(error)) from error
        try:
            cursor = self.conn.execute(
                """
                INSERT INTO army_orders (army_id, turn, order_type, payload)
                VALUES (?, ?, ?, ?)
                """,
                (army_id, turn, order_type, json.dumps(payload, ensure_ascii=False)),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as error:
            raise ArmyOrderError(f"军队 {army_id} 本回合已执行主军令。") from error
        return int(cursor.lastrowid)

    def list_army_orders(self, turn: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, army_id, turn, order_type, payload, status, result
            FROM army_orders WHERE turn = ? ORDER BY id
            """,
            (int(turn),),
        ).fetchall()
        orders: List[Dict[str, Any]] = []
        for row in rows:
            item = self._row_dict(row)
            item["payload"] = json.loads(str(item.get("payload") or "{}"))
            item["result"] = json.loads(str(item.get("result") or "{}"))
            orders.append(item)
        return orders

    # ─── 跨月战役 ─────────────────────────────────────────────

    def create_campaign(
        self,
        state: object,
        *,
        name: str,
        objective: str = "",
        theater_node: str = "",
        commander: str = "",
        army_ids: List[str] = None,
        planned_duration: int = 3,
    ) -> Dict[str, Any]:
        """创建跨月战役"""
        current_turn = int(getattr(state, "turn", 0))
        import json as _json
        cursor = self.conn.execute(
            """
            INSERT INTO campaigns
            (name, objective, theater_node, status, commander, participant_armies,
             started_turn, planned_duration)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                str(name),
                str(objective),
                str(theater_node),
                str(commander),
                _json.dumps(army_ids or [], ensure_ascii=False),
                current_turn,
                int(planned_duration),
            ),
        )
        self.conn.commit()
        return self.get_campaign(int(cursor.lastrowid))

    def get_campaign(self, campaign_id: int) -> Dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (int(campaign_id),)
        ).fetchone()
        if row is None:
            raise ValueError(f"战役不存在：{campaign_id}")
        item = self._row_dict(row)
        import json as _json
        item["participant_armies"] = _json.loads(item.get("participant_armies") or "[]")
        return item

    def list_campaigns(self, status: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM campaigns"
        params: tuple[object, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        sql += " ORDER BY id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        results = []
        import json as _json
        for row in rows:
            item = self._row_dict(row)
            item["participant_armies"] = _json.loads(item.get("participant_armies") or "[]")
            results.append(item)
        return results

    def update_campaign(self, campaign_id: int, **updates: Any) -> bool:
        """更新战役字段"""
        allowed = {"name", "objective", "theater_node", "status", "commander",
                   "result", "battle_count", "casualties"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return False
        import json as _json
        sets = []
        values = []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            values.append(v if not isinstance(v, (list, dict)) else _json.dumps(v, ensure_ascii=False))
        values.append(int(campaign_id))
        sets.append("updated_at=CURRENT_TIMESTAMP")
        self.conn.execute(
            f"UPDATE campaigns SET {', '.join(sets)} WHERE id=?", values
        )
        self.conn.commit()
        return True

    def advance_campaign(self, state: object, campaign_id: int) -> Dict[str, Any]:
        """推进战役一回合。返回战役状态摘要。"""
        campaign = self.get_campaign(campaign_id)
        if campaign.get("status") != "active":
            return campaign

        actual = campaign.get("actual_turns", 0) + 1
        planned = campaign.get("planned_duration", 3)
        updates = {"actual_turns": actual}

        # 检查是否超过计划时长
        if actual >= planned:
            updates["status"] = "completed"
            updates["result"] = f"战役 {campaign['name']} 完成 {actual} 回合"

        self.update_campaign(campaign_id, **updates)
        result = self.get_campaign(campaign_id)
        return result

    def advance_all_campaigns(self, state: object) -> List[Dict[str, Any]]:
        """月末推进所有 active 战役"""
        active = self.list_campaigns(status="active")
        results = []
        for c in active:
            r = self.advance_campaign(state, c["id"])
            results.append(r)
        return results

    def add_campaign_reinforcements(self, campaign_id: int, army_ids: List[str]) -> bool:
        """增援：追加军队到战役"""
        campaign = self.get_campaign(campaign_id)
        current = campaign.get("participant_armies", [])
        import json as _json
        merged = list(set(current) | set(army_ids))
        self.conn.execute(
            "UPDATE campaigns SET participant_armies=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (_json.dumps(merged, ensure_ascii=False), int(campaign_id)),
        )
        self.conn.commit()
        return True

    def order_campaign_retreat(self, campaign_id: int) -> bool:
        """撤军：标记战役为撤退中"""
        return self.update_campaign(campaign_id, status="retreating", result="下令撤军")
