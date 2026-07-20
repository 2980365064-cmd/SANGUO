"""三国版战略地图与基础硬规则。前端按州块交互，旧路线数据仅作州邻接兼容源。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Dict, List

from ming_sim.assets import load_json_asset, require_dict, require_list, str_field


PRIMARY_ORDERS = {"移动", "驻守", "围城", "突袭", "补给", "撤退"}
DANGEROUS_ROUTES = {"江河", "山道"}
ROUTE_KINDS = {"普通路", "江河", "山道", "关隘", "州块"}


class ArmyOrderError(ValueError):
    pass


@dataclass(frozen=True)
class StrategicNode:
    id: str
    name: str
    province: str


@dataclass(frozen=True)
class StrategicEdge:
    source: str
    target: str
    kind: str
    note: str = ""


@dataclass(frozen=True)
class StrategicRouteCatalog:
    nodes: List[StrategicNode]
    edges: List[StrategicEdge]


def load_strategic_routes() -> StrategicRouteCatalog:
    raw = require_dict(load_json_asset("routes.json"), "routes.json")
    nodes = [
        StrategicNode(
            id=str_field(require_dict(item, f"routes.json.nodes[{idx}]"), "id", f"routes.json.nodes[{idx}]"),
            name=str_field(require_dict(item, f"routes.json.nodes[{idx}]"), "name", f"routes.json.nodes[{idx}]"),
            province=str_field(require_dict(item, f"routes.json.nodes[{idx}]"), "province", f"routes.json.nodes[{idx}]"),
        )
        for idx, item in enumerate(require_list(raw.get("nodes"), "routes.json.nodes"), 1)
    ]
    node_ids = {node.id for node in nodes}
    if len(node_ids) != len(nodes):
        raise SystemExit("routes.json 节点 id 重复。")
    node_names = {node.name for node in nodes}
    if len(node_names) != len(nodes):
        raise SystemExit("routes.json 节点名称重复。")
    edges: List[StrategicEdge] = []
    edge_keys: set[tuple[str, str]] = set()
    for idx, raw_edge in enumerate(require_list(raw.get("edges"), "routes.json.edges"), 1):
        item = require_dict(raw_edge, f"routes.json.edges[{idx}]")
        edge = StrategicEdge(
            source=str_field(item, "source", f"routes.json.edges[{idx}]"),
            target=str_field(item, "target", f"routes.json.edges[{idx}]"),
            kind=str_field(item, "kind", f"routes.json.edges[{idx}]"),
            note=str(item.get("note") or ""),
        )
        if edge.source not in node_ids or edge.target not in node_ids:
            raise SystemExit(f"routes.json.edges[{idx}] 引用了不存在的节点。")
        if edge.kind not in ROUTE_KINDS:
            raise SystemExit(f"routes.json.edges[{idx}] 路线类型非法：{edge.kind}")
        if edge.source == edge.target:
            raise SystemExit(f"routes.json.edges[{idx}] 不允许节点自连。")
        edge_key = tuple(sorted((edge.source, edge.target)))
        if edge_key in edge_keys:
            raise SystemExit(f"routes.json.edges[{idx}] 路线重复：{edge.source}—{edge.target}")
        edge_keys.add(edge_key)
        edges.append(edge)
    return StrategicRouteCatalog(nodes=nodes, edges=edges)


def apply_route_entry(kind: str, *, supply: int, hazard_turns: int) -> Dict[str, float | int]:
    if kind not in ROUTE_KINDS:
        raise ArmyOrderError(f"未知路线类型：{kind}")
    if kind in DANGEROUS_ROUTES:
        if supply < 20:
            raise ArmyOrderError("粮秣低于20，不可主动进入江河或山道。")
        return {
            "supply": supply - 20,
            "hazard_turns": 3,
            "combat_multiplier": 0.5,
            "mobility_multiplier": 0.5,
        }
    return {
        "supply": supply,
        "hazard_turns": max(0, int(hazard_turns)),
        "combat_multiplier": 1.0,
        "mobility_multiplier": 1.0,
    }


def _node_province(db, node_id: str) -> str:
    row = db.conn.execute(
        "SELECT province FROM strategic_nodes WHERE id=?", (node_id,)
    ).fetchone()
    if row is None:
        raise ArmyOrderError(f"目标节点不存在：{node_id}")
    return str(row["province"])


def province_block_between(db, source: str, target: str) -> StrategicEdge:
    """按州块验证行动：同州内可调动，相邻州之间可跨州，不再使用具体路线。"""
    if source == target:
        return StrategicEdge(source=source, target=target, kind="州块", note="同郡")
    source_province = _node_province(db, source)
    target_province = _node_province(db, target)
    if source_province == target_province:
        return StrategicEdge(source=source, target=target, kind="州块", note=source_province)
    row = db.conn.execute(
        """
        SELECT 1
        FROM strategic_routes sr
        JOIN strategic_nodes s ON s.id = sr.source
        JOIN strategic_nodes t ON t.id = sr.target
        WHERE (s.province=? AND t.province=?) OR (s.province=? AND t.province=?)
        LIMIT 1
        """,
        (source_province, target_province, target_province, source_province),
    ).fetchone()
    if row is None:
        raise ArmyOrderError(f"{source_province} 与 {target_province} 不接壤，不可跨州行动。")
    return StrategicEdge(
        source=source,
        target=target,
        kind="州块",
        note=f"{source_province}-{target_province}",
    )


def issue_army_order(
    conn: sqlite3.Connection,
    *,
    army_id: str,
    turn: int,
    order_type: str,
    payload: Dict[str, object],
) -> None:
    if order_type not in PRIMARY_ORDERS:
        raise ArmyOrderError(f"非法主军令：{order_type}")
    try:
        conn.execute(
            "INSERT INTO army_orders (army_id, turn, order_type, payload) VALUES (?, ?, ?, ?)",
            (army_id, int(turn), order_type, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    except sqlite3.IntegrityError as error:
        raise ArmyOrderError(f"军队 {army_id} 本回合已执行主军令。") from error


def validate_route_move(
    db,
    army_id: str,
    source: str,
    target: str,
) -> StrategicEdge:
    """验证军队按州块移动：同州或邻州合法，不再执行路线/关隘硬阻断。"""
    army = db.conn.execute(
        "SELECT id, station_node, owner_power, supply, hazard_turns FROM armies WHERE id=? AND active=1",
        (army_id,),
    ).fetchone()
    if army is None:
        raise ArmyOrderError(f"军队不存在或已失效：{army_id}")
    if str(army["station_node"]) != source:
        raise ArmyOrderError(f"军队 {army_id} 当前不在 {source}。")
    return province_block_between(db, source, target)


def _decode_json_list(raw: object) -> List[str]:
    try:
        value = json.loads(str(raw or "[]"))
    except (TypeError, json.JSONDecodeError):
        value = []
    return [str(item) for item in value] if isinstance(value, list) else []


def _settle_route_hazards(db, turn: int) -> None:
    """每个战略回合至多衰减一次，避免重复调用月末结算重复扣时长。"""
    key = "route_hazard_last_settled_turn"
    try:
        last_turn = int(db.kv_get(key) or 0)
    except (TypeError, ValueError):
        last_turn = 0
    if int(turn) <= last_turn:
        return
    db.conn.execute(
        """
        UPDATE armies
        SET hazard_turns=CASE WHEN hazard_turns > 0 THEN hazard_turns - 1 ELSE 0 END,
            hazard_combat_multiplier=CASE WHEN hazard_turns <= 1 THEN 1.0 ELSE hazard_combat_multiplier END,
            hazard_mobility_multiplier=CASE WHEN hazard_turns <= 1 THEN 1.0 ELSE hazard_mobility_multiplier END
        WHERE active=1
        """
    )
    db.kv_set(key, str(int(turn)))
    db.conn.commit()


def resolve_army_order(db, state: object, order_id: int) -> Dict[str, object]:
    """结算一道当前已支持的结构化军令；移动按州块耗时一回合。"""
    order = db.conn.execute(
        "SELECT id, army_id, turn, order_type, payload, status, result FROM army_orders WHERE id=?",
        (int(order_id),),
    ).fetchone()
    if order is None:
        raise ArmyOrderError(f"军令不存在：{order_id}")
    if str(order["status"]) == "resolved":
        return json.loads(str(order["result"] or "{}"))
    if str(order["status"]) != "issued":
        raise ArmyOrderError(f"军令 {order_id} 当前状态不可结算：{order['status']}")
    try:
        payload = json.loads(str(order["payload"] or "{}"))
    except (TypeError, json.JSONDecodeError) as error:
        raise ArmyOrderError(f"军令 {order_id} 参数损坏。") from error
    order_type = str(order["order_type"])
    army_id = str(order["army_id"])

    if order_type in {"移动", "撤退"}:
        army = db.conn.execute("SELECT * FROM armies WHERE id=?", (army_id,)).fetchone()
        if army is None:
            raise ArmyOrderError(f"军队不存在：{army_id}")
        source = str(army["station_node"])
        target = str(payload.get("to") or "").strip()
        edge = validate_route_move(db, army_id, source, target)
        entry = apply_route_entry(
            edge.kind,
            supply=int(army["supply"] or 0),
            hazard_turns=int(army["hazard_turns"] or 0),
        )
        combat_multiplier = float(entry["combat_multiplier"])
        mobility_multiplier = float(entry["mobility_multiplier"])
        specialties = _decode_json_list(army["specialties"])
        if edge.kind == "山道" and "山地" in specialties:
            mobility_multiplier = 0.65
        target_row = db.conn.execute(
            "SELECT name FROM strategic_nodes WHERE id=?", (target,)
        ).fetchone()
        target_name = str(target_row["name"] if target_row else target)
        update_fields = [
            "station_node=?", "station=?", "supply=?", "status=?",
        ]
        params: List[object] = [target, target_name, int(entry["supply"]), "行军后整备"]
        if edge.kind in DANGEROUS_ROUTES:
            update_fields.extend([
                "hazard_turns=?",
                "hazard_combat_multiplier=?",
                "hazard_mobility_multiplier=?",
            ])
            params.extend([3, combat_multiplier, mobility_multiplier])
        params.append(army_id)
        db.conn.execute(
            f"UPDATE armies SET {', '.join(update_fields)} WHERE id=?",
            tuple(params),
        )
        result: Dict[str, object] = {
            "status": "resolved",
            "order_type": order_type,
            "from": source,
            "to": target,
            "route_kind": edge.kind,
            "duration_turns": 1,
            "supply_after": int(entry["supply"]),
            "hazard_turns": 3 if edge.kind in DANGEROUS_ROUTES else int(army["hazard_turns"] or 0),
            "combat_multiplier": combat_multiplier,
            "mobility_multiplier": mobility_multiplier,
        }
    elif order_type == "驻守":
        db.conn.execute("UPDATE armies SET status='驻守' WHERE id=?", (army_id,))
        result = {"status": "resolved", "order_type": "驻守", "duration_turns": 1}
    else:
        raise ArmyOrderError(f"军令 {order_type} 将由对应战役系统结算，当前不可直接执行。")

    db.conn.execute(
        "UPDATE army_orders SET status='resolved', result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (json.dumps(result, ensure_ascii=False), int(order_id)),
    )
    db.conn.commit()
    return result


def resolve_army_orders_for_turn(db, turn: int) -> List[Dict[str, object]]:
    """衰减旧险路状态并结算本回合已支持的主军令，重复调用幂等。"""
    _settle_route_hazards(db, int(turn))
    rows = db.conn.execute(
        """
        SELECT id FROM army_orders
        WHERE turn=? AND status='issued' AND order_type IN ('移动', '撤退', '驻守')
        ORDER BY id
        """,
        (int(turn),),
    ).fetchall()
    state = type("StrategicTurn", (), {"turn": int(turn)})()
    results: List[Dict[str, object]] = []
    for row in rows:
        order_id = int(row["id"])
        try:
            results.append(resolve_army_order(db, state, order_id))
        except ArmyOrderError as error:
            result = {"status": "rejected", "reason": str(error)}
            db.conn.execute(
                "UPDATE army_orders SET status='rejected', result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(result, ensure_ascii=False), order_id),
            )
            db.conn.commit()
            results.append(result)
    return results


def calculate_siege_progress(progress: int, *, attacker_score: int, defender_score: int) -> int:
    if attacker_score <= 0 or defender_score <= 0:
        raise ValueError("攻守评分必须大于0。")
    monthly = round(34 * attacker_score / defender_score)
    monthly = max(10, min(60, monthly))
    return min(100, max(0, int(progress)) + monthly)
