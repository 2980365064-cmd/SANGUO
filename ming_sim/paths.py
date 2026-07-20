"""路径解析：分离只读资源（bundled）与用户数据（可写）。L0。

打包发布模式（PyInstaller --onefile）：
  - bundled_path("content/foo.json") → sys._MEIPASS/content/foo.json（只读，临时解压目录）
  - user_data_dir() → ~/.ming_sim/（跨进程持久，user 可写）

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
_SANGUO_MIGRATION_MARKER = ".sanguo_liubei_208_migrated"
_LEGACY_POWER_IDS = {"ming", "houjin", "mongol", "korea", "japan", "rebels"}


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
    frozen：~/.ming_sim/（首次自动建）。
    源码：<repo>/data/（沿用旧布局，便于开发期切换存档）。"""
    override = os.environ.get("MING_SIM_USER_DATA_DIR", "").strip()
    if override:
        d = Path(override).expanduser()
    elif is_frozen():
        d = Path.home() / ".ming_sim"
    else:
        d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_data_path(*parts: str) -> str:
    """拼 user data 路径，自动建父目录。例：user_data_path('saves', 'auto.db')。"""
    p = user_data_dir().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _is_recognizable_legacy_ming_db(path: Path) -> bool:
    """只识别没有场景标记、且含旧明末势力 id 的 SQLite 数据库。"""
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "kv_store" in tables:
                row = conn.execute(
                    "SELECT value FROM kv_store WHERE key='scenario_id'"
                ).fetchone()
                if row and str(row[0]).strip():
                    return False
            if "powers" in tables:
                power_ids = {str(row[0]) for row in conn.execute("SELECT id FROM powers")}
                if power_ids & _LEGACY_POWER_IDS:
                    return True
            if "characters" in tables:
                return bool(conn.execute(
                    "SELECT 1 FROM characters WHERE power_id='ming' LIMIT 1"
                ).fetchone())
            return False
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def migrate_legacy_ming_data(data_root: Path | str | None = None) -> list[str]:
    """首次启动时删除可明确识别的旧明末主库和存档，其他文件不动。"""
    root = Path(data_root) if data_root is not None else user_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / _SANGUO_MIGRATION_MARKER
    if marker.exists():
        return []
    candidates = [root / "ming_sim.db"]
    saves = root / "saves"
    if saves.is_dir():
        candidates.extend(sorted(saves.glob("*.db")))
    removed: list[str] = []
    for candidate in candidates:
        if not _is_recognizable_legacy_ming_db(candidate):
            continue
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(f"{candidate}{suffix}").unlink()
            except FileNotFoundError:
                pass
        removed.append(str(candidate))
    marker.touch(exist_ok=True)
    return removed
