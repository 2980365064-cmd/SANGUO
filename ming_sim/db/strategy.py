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
            "SELECT id, name, province FROM strategic_nodes ORDER BY id"
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
