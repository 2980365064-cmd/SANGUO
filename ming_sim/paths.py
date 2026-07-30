"""路径解析：分离只读资源（bundled）与用户数据（可写）。L0。

打包发布模式（PyInstaller --onefile）：
  - bundled_path("content/foo.json") → sys._MEIPASS/content/foo.json（只读，临时解压目录）
  - user_data_dir() → ~/.sanguo_sim/（跨进程持久，user 可写）

源码开发模式：
  - bundled_path("content/foo.json") → <repo>/content/foo.json
  - user_data_dir() → <repo>/data/（沿用旧布局）

判依据：sys.frozen 由 PyInstaller 注入。
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


SANGUO_SCENARIO_ID = "sanguo_liubei_208"


def sqlite_scenario_id(path: Path | str) -> str:
    """只读提取 SQLite 的场景 id；非 SQLite、缺表或缺标记均返回空串。"""
    target = Path(path)
    if not target.is_file():
        return ""
    try:
        conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        try:
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='kv_store'"
            ).fetchone() is None:
                return ""
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key='scenario_id'"
            ).fetchone()
            return str(row[0]).strip() if row else ""
        finally:
            conn.close()
    except sqlite3.Error:
        return ""


def is_city_topology_database(path: Path | str) -> bool:
    """检查 SQLite 存档是否使用 72 城池网络拓扑 (city:* 节点)。

    判定规则：kv_store 中 strategic_node_model='city_only'，
    或 strategic_nodes 表中所有 ID 均以 'city:' 开头。
    """
    target = Path(path)
    if not target.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        try:
            # 快速路径：检查 kv_store 标记
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='kv_store'"
            ).fetchone() is not None:
                row = conn.execute(
                    "SELECT value FROM kv_store WHERE key='strategic_node_model'"
                ).fetchone()
                if row and str(row[0]).strip() == "city_only":
                    return True
            # 备用路径：检查 strategic_nodes 是否全为 city:* 前缀
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategic_nodes'"
            ).fetchone() is None:
                return False
            count = conn.execute("SELECT COUNT(*) FROM strategic_nodes").fetchone()[0]
            if count == 0:
                return False
            city_count = conn.execute(
                "SELECT COUNT(*) FROM strategic_nodes WHERE id LIKE 'city:%'"
            ).fetchone()[0]
            return city_count == count
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def is_frozen() -> bool:
    """是否在 PyInstaller 打包产物里跑。"""
    return getattr(sys, "frozen", False)


def bundled_root() -> Path:
    """只读资源根目录。
    frozen：PyInstaller 解压临时目录 _MEIPASS。
    源码：仓库根（ming_sim/ 父目录）。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass)
        exe_dir = Path(os.path.dirname(sys.executable))
        internal_dir = exe_dir / "_internal"
        if internal_dir.is_dir():
            return internal_dir
        return exe_dir
    return Path(__file__).resolve().parent.parent


def bundled_path(*parts: str) -> str:
    """拼 bundled 资源路径。例：bundled_path('content', 'events.json')。"""
    return str(bundled_root().joinpath(*parts))


def user_data_dir() -> Path:
    """用户可写数据目录。
    frozen：~/.sanguo_sim/（首次自动建）。
    源码：<repo>/data/（沿用旧布局，便于开发期切换存档）。"""
    override = os.environ.get("MING_SIM_USER_DATA_DIR", "").strip()
    if override:
        d = Path(override).expanduser()
    elif is_frozen():
        d = Path.home() / ".sanguo_sim"
    else:
        d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_data_path(*parts: str) -> str:
    """拼 user data 路径，自动建父目录。例：user_data_path('saves', 'auto.db')。"""
    p = user_data_dir().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)
