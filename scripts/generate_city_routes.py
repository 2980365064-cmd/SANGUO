#!/usr/bin/env python3
"""一次性工具：为 72 城生成初版城际路线边表。

算法：
1. 以二维欧氏距离构建完整候选对。
2. Prim 最小生成树保证 72 城全连通。
3. 每座城再补最多 3 条最近的未重复边。
4. 补边时拒绝与既有边产生几何交叉的线段（共享端点不算交叉）。
5. 所有边去重并以 (source, target) 字典序规范化、排序。
6. 统一写为 kind: "普通路"、note: "地图锚点邻接"。

用法：
    python3 scripts/generate_city_routes.py

输出直接打印到 stdout，人工审核后将 edges 数组粘贴到
content/administrative_units.json 的 strategic.edges。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
ADMIN_UNITS_PATH = REPO_ROOT / "content" / "administrative_units.json"

MAX_EXTRA_EDGES_PER_CITY = 2
# 补边最大距离（像素）；超过此距离的边即使不交叉也拒绝
MAX_EXTRA_EDGE_DISTANCE = 200


def load_city_anchors() -> Dict[str, Tuple[float, float]]:
    """从 administrative_units.json 读取 strategic.nodes 的锚点。
    如果 strategic 字段尚未写入，则从 cities + 前端 CITY_TERRITORY_ANCHORS 合成。
    """
    with open(ADMIN_UNITS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    strategic = data.get("strategic")
    if strategic and strategic.get("nodes"):
        anchors: Dict[str, Tuple[float, float]] = {}
        for node in strategic["nodes"]:
            anchors[node["city_id"]] = (float(node["x"]), float(node["y"]))
        return anchors

    # Fallback: build from cities array + frontend anchors
    import re
    cities = data["cities"]
    ts_path = REPO_ROOT / "web" / "src" / "mapLogic.ts"
    ts_text = ts_path.read_text(encoding="utf-8")
    start = ts_text.find("const CITY_TERRITORY_ANCHORS")
    end = ts_text.find("};", start) + 2
    block = ts_text[start:end]
    pattern = r'"(city:[^"]+)":\s*\{\s*x:\s*(\d+)\s*,\s*y:\s*(\d+)\s*\}'
    matches = re.findall(pattern, block)
    frontend_anchors = {m[0]: (int(m[1]), int(m[2])) for m in matches}

    # Percentage-based fallbacks for cities not in frontend anchors
    pct_positions = {
        "changan": (54, 42), "chengdu": (48, 55), "hanzhong": (52, 50),
        "jiangzhou": (52, 65), "luoyang": (61, 42), "tongguan": (58, 42),
        "ye": (65, 32),
    }
    MAP_W, MAP_H = 1920, 1080

    anchors = {}
    for city in cities:
        cid = city["id"]
        if cid in frontend_anchors:
            anchors[cid] = frontend_anchors[cid]
        elif cid.replace("city:", "") in pct_positions:
            px, py = pct_positions[cid.replace("city:", "")]
            anchors[cid] = (round(px * MAP_W / 100), round(py * MAP_H / 100))
        elif cid == "city:xinye":
            anchors[cid] = (1099, 624)
        else:
            print(f"ERROR: No anchor for {cid}", file=sys.stderr)
            sys.exit(1)
    return anchors


def euclidean(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def segments_intersect(
    p1: Tuple[float, float], p2: Tuple[float, float],
    p3: Tuple[float, float], p4: Tuple[float, float],
) -> bool:
    """检查线段 p1-p2 与 p3-p4 是否交叉（不含共享端点）。"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def on_segment(p, q, r):
        return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and
                min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    if d1 == 0 and on_segment(p3, p1, p4):
        return True
    if d2 == 0 and on_segment(p3, p2, p4):
        return True
    if d3 == 0 and on_segment(p1, p3, p2):
        return True
    if d4 == 0 and on_segment(p1, p4, p2):
        return True

    return False


def prim_mst(
    city_ids: List[str],
    anchors: Dict[str, Tuple[float, float]],
) -> List[Tuple[str, str]]:
    """Prim 最小生成树，保证全连通。"""
    n = len(city_ids)
    if n <= 1:
        return []

    in_tree: Set[str] = {city_ids[0]}
    edges: List[Tuple[str, str]] = []

    while len(in_tree) < n:
        best_dist = float("inf")
        best_edge = None
        for u in in_tree:
            for v in city_ids:
                if v in in_tree:
                    continue
                d = euclidean(anchors[u], anchors[v])
                if d < best_dist:
                    best_dist = d
                    best_edge = (u, v)
        if best_edge is None:
            break
        u, v = best_edge
        in_tree.add(v)
        edge = tuple(sorted((u, v)))
        edges.append(edge)

    return edges


def edge_crosses_any(
    new_edge: Tuple[str, str],
    existing_edges: Set[Tuple[str, str]],
    anchors: Dict[str, Tuple[float, float]],
) -> bool:
    """检查新边是否与任何既有边几何交叉（共享端点不算）。"""
    u, v = new_edge
    p1, p2 = anchors[u], anchors[v]
    for eu, ev in existing_edges:
        # 共享端点不算交叉
        if u == eu or u == ev or v == eu or v == ev:
            continue
        p3, p4 = anchors[eu], anchors[ev]
        if segments_intersect(p1, p2, p3, p4):
            return True
    return False


def generate_routes(
    anchors: Dict[str, Tuple[float, float]],
) -> List[Tuple[str, str]]:
    """生成城际路线边表。"""
    city_ids = sorted(anchors.keys())

    # Step 1: Prim MST
    mst_edges = prim_mst(city_ids, anchors)
    all_edges: Set[Tuple[str, str]] = set(mst_edges)

    # Count existing edges per city
    edge_count: Dict[str, int] = {cid: 0 for cid in city_ids}
    for u, v in mst_edges:
        edge_count[u] += 1
        edge_count[v] += 1

    # Step 2: For each city, add up to MAX_EXTRA_EDGES_PER_CITY nearest edges
    for city in city_ids:
        # Sort other cities by distance
        candidates = sorted(
            (c for c in city_ids if c != city),
            key=lambda c: euclidean(anchors[city], anchors[c]),
        )
        added = 0
        for other in candidates:
            if added >= MAX_EXTRA_EDGES_PER_CITY:
                break
            edge = tuple(sorted((city, other)))
            if edge in all_edges:
                continue
            # Distance cap
            dist = euclidean(anchors[city], anchors[other])
            if dist > MAX_EXTRA_EDGE_DISTANCE:
                continue
            # Check geometric crossing
            if edge_crosses_any(edge, all_edges, anchors):
                continue
            all_edges.add(edge)
            edge_count[city] += 1
            edge_count[other] += 1
            added += 1

    # Step 3: Normalize and sort
    normalized = sorted(set(tuple(sorted(e)) for e in all_edges))
    return normalized


def main() -> None:
    anchors = load_city_anchors()
    print(f"Loaded {len(anchors)} city anchors", file=sys.stderr)

    edges = generate_routes(anchors)
    print(f"Generated {len(edges)} edges", file=sys.stderr)

    # Verify connectivity via BFS
    adj: Dict[str, List[str]] = {cid: [] for cid in anchors}
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)
    visited: Set[str] = set()
    queue = [next(iter(anchors))]
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        queue.extend(adj[node])
    if len(visited) != len(anchors):
        print(f"WARNING: Graph not fully connected! {len(visited)}/{len(anchors)}", file=sys.stderr)
    else:
        print("Graph is fully connected ✓", file=sys.stderr)

    # Print edges as JSON
    edge_list = [
        {
            "source": u,
            "target": v,
            "kind": "普通路",
            "note": "地图锚点邻接",
        }
        for u, v in edges
    ]
    print(json.dumps(edge_list, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
