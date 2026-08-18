"""tests/test_city_strategic_nodes.py：72 城池战略网络合同测试。

验证：
  - 所有 strategic_nodes 使用 city:* 前缀
  - strategic_routes 仅连接 city:* 节点
  - GameContent.routes 返回正确的 CityStrategicCatalog
  - require_city_node 校验前缀
  - find_strategic_route 查直连边（双向查询）
  - 旧存档被 is_city_topology_database 拒绝
  - 拓扑版本标记已写入 kv_store
"""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.paths import is_city_topology_database
from ming_sim.sanguo_rules import (
    ArmyOrderError,
    CityStrategicEdge,
    find_strategic_route,
    require_city_node,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def content():
    return GameContent.load()


@pytest.fixture
def board(content):
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 拓扑结构
# ---------------------------------------------------------------------------


def test_all_strategic_nodes_use_city_prefix(board):
    """所有 strategic_nodes 的 ID 必须以 city: 开头。"""
    rows = board.conn.execute("SELECT id FROM strategic_nodes").fetchall()
    assert len(rows) == 72
    for row in rows:
        assert str(row["id"]).startswith("city:"), f"节点 ID 不以 city: 开头：{row['id']}"


def test_all_strategic_routes_connect_city_nodes(board):
    """所有 strategic_routes 的 source 和 target 必须是 city:* 节点。"""
    rows = board.conn.execute("SELECT source, target FROM strategic_routes").fetchall()
    assert len(rows) > 0
    for row in rows:
        assert str(row["source"]).startswith("city:"), f"source 不是 city:*：{row['source']}"
        assert str(row["target"]).startswith("city:"), f"target 不是 city:*：{row['target']}"


def test_topology_version_is_city_only(board):
    """kv_store 中应标记 strategic_node_model='city_only'。"""
    row = board.conn.execute(
        "SELECT value FROM kv_store WHERE key='strategic_node_model'"
    ).fetchone()
    assert row is not None
    assert str(row["value"]) == "city_only"


def test_strategic_routes_count_matches_catalog(board, content):
    """数据库中的路线数与目录一致（177 条无向边）。"""
    db_count = board.conn.execute("SELECT COUNT(*) FROM strategic_routes").fetchone()[0]
    assert db_count == len(content.routes.edges)


def test_no_self_loops(board):
    """不存在自连边（source == target）。"""
    rows = board.conn.execute(
        "SELECT source, target FROM strategic_routes WHERE source = target"
    ).fetchall()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# CityStrategicCatalog (via GameContent.routes)
# ---------------------------------------------------------------------------


def test_catalog_has_72_nodes(content):
    assert len(content.routes.nodes) == 72


def test_catalog_node_has_city_id(content):
    for node in content.routes.nodes:
        assert node.city_id.startswith("city:")
        assert node.commandery_id  # 必须有郡 ID
        assert node.province_id  # 必须有州 ID
        assert node.name  # 必须有名称


def test_catalog_edges_are_177(content):
    """72 城池网络共 177 条无向边。"""
    assert len(content.routes.edges) == 177


def test_catalog_all_edges_are_ordinary(content):
    """v1 版本所有边均为普通路。"""
    for edge in content.routes.edges:
        assert edge.kind == "普通路", f"边 {edge.source}→{edge.target} 类型为 {edge.kind}"


# ---------------------------------------------------------------------------
# require_city_node
# ---------------------------------------------------------------------------


def test_require_city_node_accepts_valid_id():
    assert require_city_node("city:changan") == "city:changan"
    assert require_city_node("city:xiangyang") == "city:xiangyang"


def test_require_city_node_rejects_bare_id():
    with pytest.raises(ArmyOrderError, match="必须是城池节点"):
        require_city_node("changan")


def test_require_city_node_rejects_empty():
    with pytest.raises(ArmyOrderError, match="必须是城池节点"):
        require_city_node("")


# ---------------------------------------------------------------------------
# find_strategic_route
# ---------------------------------------------------------------------------


def test_find_strategic_route_returns_edge_for_adjacent(board):
    """相邻城市应返回直连边。"""
    edge = find_strategic_route(board, "city:changan", "city:hanzhong")
    assert edge is not None
    assert isinstance(edge, CityStrategicEdge)
    assert edge.kind == "普通路"


def test_find_strategic_route_returns_none_for_same_node(board):
    """同节点返回 None。"""
    assert find_strategic_route(board, "city:changan", "city:changan") is None


def test_find_strategic_route_returns_none_for_non_adjacent(board):
    """不相邻城市返回 None。"""
    # changan 和 jianye 不相邻
    assert find_strategic_route(board, "city:changan", "city:jianye") is None


def test_find_strategic_route_is_bidirectional(board):
    """A→B 和 B→A 均能查到同一条边。"""
    edge_ab = find_strategic_route(board, "city:changan", "city:hanzhong")
    edge_ba = find_strategic_route(board, "city:hanzhong", "city:changan")
    assert edge_ab is not None
    assert edge_ba is not None


# ---------------------------------------------------------------------------
# is_city_topology_database（旧存档拒绝）
# ---------------------------------------------------------------------------


def test_new_game_database_passes_topology_check(tmp_path):
    """新游戏 DB 应通过拓扑检查。"""
    content = GameContent.load()
    db = GameDB(str(tmp_path / "new_game.db"), content=content)
    db.seed_static_data()
    db.close()
    assert is_city_topology_database(str(tmp_path / "new_game.db")) is True


def test_old_format_database_fails_topology_check(tmp_path):
    """旧格式 DB（strategic_nodes 无 city: 前缀）应被拒绝。"""
    import sqlite3
    db_path = str(tmp_path / "old_game.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE strategic_nodes (id TEXT PRIMARY KEY, name TEXT, province TEXT)"
    )
    conn.execute("INSERT INTO strategic_nodes VALUES ('changan', '长安', '司隶')")
    conn.execute("INSERT INTO strategic_nodes VALUES ('luoyang', '洛阳', '司隶')")
    conn.commit()
    conn.close()
    assert is_city_topology_database(db_path) is False


def test_empty_database_fails_topology_check(tmp_path):
    """空 DB 应被拒绝。"""
    import sqlite3
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE strategic_nodes (id TEXT PRIMARY KEY, name TEXT, province TEXT)"
    )
    conn.commit()
    conn.close()
    assert is_city_topology_database(db_path) is False


def test_kv_marked_database_passes_topology_check(tmp_path):
    """有 kv_store 标记的 DB 应通过。"""
    import sqlite3
    db_path = str(tmp_path / "kv_marked.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE kv_store (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO kv_store VALUES ('strategic_node_model', 'city_only')")
    conn.commit()
    conn.close()
    assert is_city_topology_database(db_path) is True


def test_nonexistent_file_fails_topology_check():
    assert is_city_topology_database("/nonexistent/path.db") is False


# ---------------------------------------------------------------------------
# 行政城池与战略节点一致
# ---------------------------------------------------------------------------


def test_all_city_nodes_have_administrative_entry(board):
    """每个 strategic_node 都有对应的 administrative_cities 记录。"""
    nodes = board.conn.execute("SELECT id FROM strategic_nodes").fetchall()
    for node in nodes:
        city = board.conn.execute(
            "SELECT id FROM administrative_cities WHERE id=?", (node["id"],)
        ).fetchone()
        assert city is not None, f"strategic_node {node['id']} 无对应 administrative_cities"


def test_army_station_nodes_are_city_prefixed(board):
    """所有活跃军队的 station_node 必须是 city:* 格式。"""
    rows = board.conn.execute(
        "SELECT id, station_node FROM armies WHERE active=1"
    ).fetchall()
    for row in rows:
        sn = str(row["station_node"])
        assert sn.startswith("city:"), f"军队 {row['id']} 的 station_node 不是 city:*：{sn}"
