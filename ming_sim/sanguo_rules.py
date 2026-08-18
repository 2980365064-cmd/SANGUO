"""三国版战略地图与基础硬规则。

72 城池网络：administrative_units.json.strategic 是城池节点与城际路线的唯一目录。
行军、围城、战役、补给、AI 候选都只使用城池节点 (city:*) 和直连城际边。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from ming_sim.assets import load_json_asset, require_dict, require_list, str_field


PRIMARY_ORDERS = {"移动", "驻守", "围城", "突袭", "补给", "撤退", "军政"}
DANGEROUS_ROUTES = {"江河", "山道"}
# 首版所有边均为普通路；保留扩展类型供未来路线编辑使用
ROUTE_KINDS = {"普通路", "江河", "山道", "关隘"}


class ArmyOrderError(ValueError):
    pass


# ── 城池战略目录数据结构（administrative_units.json.strategic） ──


@dataclass(frozen=True)
class CityStrategicNode:
    """城池战略节点：city_id 即 administrative_cities.id。"""
    city_id: str
    name: str
    commandery_id: str
    province_id: str
    x: float
    y: float


@dataclass(frozen=True)
class CityStrategicEdge:
    """城际路线边：source/target 均为 city:* ID。"""
    source: str
    target: str
    kind: str
    note: str = ""


@dataclass(frozen=True)
class CityStrategicCatalog:
    """城池战略目录：72 城节点 + 固化路线边表。"""
    topology_version: str
    nodes: List[CityStrategicNode]
    edges: List[CityStrategicEdge]

    @property
    def city_ids(self) -> Set[str]:
        return {n.city_id for n in self.nodes}

    @property
    def node_map(self) -> Dict[str, CityStrategicNode]:
        return {n.city_id: n for n in self.nodes}


def load_city_strategic_catalog(admin_units: Dict[str, object]) -> CityStrategicCatalog:
    """从 administrative_units 加载结果中解析并严格校验城池战略目录。

    加载期验证：
    - strategic 字段存在且 topology_version 非空
    - 节点数 = 城池数，city_id 集合严格相等
    - 所有 city_id 以 city: 开头，无重复
    - 锚点坐标为数值且非缺失
    - 路线端点均在现役城池中，无自环、无重复无向边
    - 路线类型合法
    - 图连通
    """
    strategic = admin_units.get("strategic")
    if not isinstance(strategic, dict):
        raise SystemExit("administrative_units.json 缺少 strategic 字段。")

    topology_version = str(strategic.get("topology_version") or "").strip()
    if not topology_version:
        raise SystemExit("administrative_units.json.strategic.topology_version 不可为空。")

    # 解析行政城池索引
    cities: List[Dict] = admin_units.get("cities", [])  # type: ignore[assignment]
    city_index: Dict[str, Dict] = {}
    for city in cities:
        cid = str(city["id"])
        if not cid.startswith("city:"):
            raise SystemExit(f"行政城池 id 必须以 city: 开头：{cid}")
        if cid in city_index:
            raise SystemExit(f"行政城池 id 重复：{cid}")
        city_index[cid] = city

    # 解析节点
    raw_nodes = require_list(strategic.get("nodes"), "strategic.nodes")
    nodes: List[CityStrategicNode] = []
    node_ids: Set[str] = set()
    anchor_keys: Set[Tuple[float, float]] = set()

    for idx, raw in enumerate(raw_nodes, 1):
        item = require_dict(raw, f"strategic.nodes[{idx}]")
        city_id = str_field(item, "city_id", f"strategic.nodes[{idx}]")
        if not city_id.startswith("city:"):
            raise SystemExit(f"strategic.nodes[{idx}] city_id 必须以 city: 开头：{city_id}")
        if city_id in node_ids:
            raise SystemExit(f"strategic.nodes 节点 city_id 重复：{city_id}")
        if city_id not in city_index:
            raise SystemExit(
                f"strategic.nodes 中的 {city_id} 不在行政城池名册中。"
            )
        node_ids.add(city_id)

        # 坐标校验
        x_raw = item.get("x")
        y_raw = item.get("y")
        if x_raw is None or y_raw is None:
            raise SystemExit(f"strategic.nodes[{idx}] ({city_id}) 缺少坐标。")
        try:
            x = float(x_raw)
            y = float(y_raw)
        except (TypeError, ValueError):
            raise SystemExit(
                f"strategic.nodes[{idx}] ({city_id}) 坐标非数值：x={x_raw!r}, y={y_raw!r}"
            )
        anchor = (x, y)
        if anchor in anchor_keys:
            raise SystemExit(f"strategic.nodes 锚点坐标重复：({x}, {y})")
        anchor_keys.add(anchor)

        city_data = city_index[city_id]
        nodes.append(CityStrategicNode(
            city_id=city_id,
            name=str(city_data["name"]),
            commandery_id=str(city_data["commandery_id"]),
            province_id=str(city_data["province_id"]),
            x=x,
            y=y,
        ))

    # 节点集合必须与城池集合严格相等
    missing_from_nodes = set(city_index.keys()) - node_ids
    if missing_from_nodes:
        raise SystemExit(
            f"strategic.nodes 缺少以下行政城池节点：{sorted(missing_from_nodes)}"
        )
    extra_nodes = node_ids - set(city_index.keys())
    if extra_nodes:
        raise SystemExit(
            f"strategic.nodes 包含不在行政城池名册中的节点：{sorted(extra_nodes)}"
        )

    # 解析边
    raw_edges = require_list(strategic.get("edges"), "strategic.edges")
    edges: List[CityStrategicEdge] = []
    edge_keys: Set[Tuple[str, str]] = set()

    for idx, raw in enumerate(raw_edges, 1):
        item = require_dict(raw, f"strategic.edges[{idx}]")
        source = str_field(item, "source", f"strategic.edges[{idx}]")
        target = str_field(item, "target", f"strategic.edges[{idx}]")
        kind = str_field(item, "kind", f"strategic.edges[{idx}]")
        note = str(item.get("note") or "")

        if source == target:
            raise SystemExit(f"strategic.edges[{idx}] 不允许自环：{source}")
        if source not in node_ids:
            raise SystemExit(
                f"strategic.edges[{idx}] source '{source}' 不在现役城池节点中。"
            )
        if target not in node_ids:
            raise SystemExit(
                f"strategic.edges[{idx}] target '{target}' 不在现役城池节点中。"
            )
        if kind not in ROUTE_KINDS:
            raise SystemExit(
                f"strategic.edges[{idx}] 路线类型非法：{kind!r}（合法值：{sorted(ROUTE_KINDS)}）"
            )
        edge_key = tuple(sorted((source, target)))
        if edge_key in edge_keys:
            raise SystemExit(
                f"strategic.edges[{idx}] 路线重复：{source}—{target}"
            )
        edge_keys.add(edge_key)
        edges.append(CityStrategicEdge(
            source=edge_key[0],
            target=edge_key[1],
            kind=kind,
            note=note,
        ))

    # 图连通性检查（BFS）
    if nodes:
        adj: Dict[str, List[str]] = {n.city_id: [] for n in nodes}
        for e in edges:
            adj[e.source].append(e.target)
            adj[e.target].append(e.source)
        visited: Set[str] = set()
        queue = [nodes[0].city_id]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            queue.extend(adj[node])
        if len(visited) != len(nodes):
            unreachable = node_ids - visited
            raise SystemExit(
                f"strategic.edges 图不连通，以下节点不可达：{sorted(unreachable)}"
            )

    return CityStrategicCatalog(
        topology_version=topology_version,
        nodes=nodes,
        edges=edges,
    )


# ── 城池节点校验与城际路线查询 ──


def require_city_node(node_id: str, *, label: str = "节点") -> str:
    """校验 node_id 以 city: 开头，否则报错。"""
    if not node_id or not str(node_id).startswith("city:"):
        raise ArmyOrderError(f"{label}必须是城池节点 (city:*)：{node_id!r}")
    return str(node_id)


def find_strategic_route(db, source: str, target: str) -> CityStrategicEdge | None:
    """查询两城池节点之间的直连路线。同节点返回 None（无需路线）。"""
    if source == target:
        return None
    row = db.conn.execute(
        """SELECT source, target, kind, note FROM strategic_routes
           WHERE (source=? AND target=?) OR (source=? AND target=?)
           LIMIT 1""",
        (source, target, target, source),
    ).fetchone()
    if row is None:
        return None
    return CityStrategicEdge(
        source=str(row["source"]),
        target=str(row["target"]),
        kind=str(row["kind"]),
        note=str(row["note"] or ""),
    )


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


def validate_route_move(
    db,
    army_id: str,
    source: str,
    target: str,
) -> CityStrategicEdge:
    """验证军队按直连城际路线移动。"""
    require_city_node(source, label="出发节点")
    require_city_node(target, label="目标节点")
    army = db.conn.execute(
        "SELECT id, station_node, owner_power, supply, hazard_turns FROM armies WHERE id=? AND active=1",
        (army_id,),
    ).fetchone()
    if army is None:
        raise ArmyOrderError(f"军队不存在或已失效：{army_id}")
    if str(army["station_node"]) != source:
        raise ArmyOrderError(f"军队 {army_id} 当前不在 {source}。")
    if source == target:
        return CityStrategicEdge(source=source, target=target, kind="同地", note="同节点")
    edge = find_strategic_route(db, source, target)
    if edge is None:
        raise ArmyOrderError(f"{source} 与 {target} 之间无直连路线，不可移动。")
    return edge


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
    """结算一道当前已支持的结构化军令；移动按直连路线耗时一回合。"""
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
            "SELECT name FROM administrative_cities WHERE id=?", (target,)
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
        WHERE turn=? AND status='issued' AND order_type IN ('移动', '撤退', '驻守', '军政')
        ORDER BY id
        """,
        (int(turn),),
    ).fetchall()
    state = type("StrategicTurn", (), {"turn": int(turn)})()
    results: List[Dict[str, object]] = []
    for row in rows:
        order_id = int(row["id"])
        try:
            order = db.conn.execute("SELECT army_id, order_type, payload FROM army_orders WHERE id=?", (order_id,)).fetchone()
            if order is not None and str(order["order_type"]) == "军政":
                military_state = type("MilitaryTurn", (), {"turn": int(turn), "year": 208, "period": 1})()
                outcome = db.execute_military_reform(military_state, str(order["army_id"]), json.loads(str(order["payload"] or "{}")))
                db.conn.execute("UPDATE army_orders SET status='resolved', result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (json.dumps(outcome, ensure_ascii=False), order_id))
                db.conn.commit()
                results.append(outcome)
            else:
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
