"""调试用通用表 CRUD（白名单核心表）。

_AdminMixin：拆自原 db.py，方法体逐字未改。"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from ming_sim.assets import format_money, format_money_delta
from ming_sim.constants import (
    ARMY_FIELD_ALIASES, ARMY_FIELD_LABELS, ARMY_QUANTITY_FIELDS, ARMY_SCORE_FIELDS, ARMY_TEXT_FIELDS,
    BUILDING_CATEGORIES, BUILDING_FIELD_LABELS, BUILDING_OUTPUT_METRICS,
    BUILDING_QUANTITY_FIELDS, BUILDING_SCORE_FIELDS, BUILDING_TEXT_FIELDS,
    ECONOMY_ACCOUNTS, POWER_FIELD_LABELS, POWER_SCORE_FIELDS,
    POWER_FIELD_ALIASES, POWER_TEXT_FIELDS, MONEY_UNIT, REGION_FIELD_LABELS, REGION_QUANTITY_FIELDS,
    FISCAL_SCORE_FIELDS, REGION_FIELD_ALIASES, REGION_SCORE_FIELDS, REGION_TEXT_FIELDS, TURN_UNIT,
)
from ming_sim.content import GameContent
from ming_sim.matching import match_army_id_from_text, match_region_id_from_text
from ming_sim.models import Event, GameState, monthly_amount, period_label
from ming_sim.token_stats import tlog
from ming_sim.db._helpers import (
    normalize_office, infer_office_type_from_office,
    _compact_lookup_text, _normalize_power_id,
    COURT_OFFICE_TYPES, MINISTRY_OFFICE_TYPES,
)


class _AdminMixin:
    # ── 调试用通用 CRUD（仅限白名单核心表）──────────────────────
    # 表名 → 主键列。只暴露核心几张，防误删元数据/日志表。
    ADMIN_TABLES: Dict[str, str] = {
        "game_state": "id",        # 局势
        "metrics": "key",          # 国家修正（国库/内库/民心/皇威）
        "regions": "id",           # 地区
        "armies": "id",            # 军队
        "characters": "name",      # 人物
        "buildings": "id",         # 建筑
    }

    def admin_check_table(self, table: str) -> str:
        pk = self.ADMIN_TABLES.get(table)
        if pk is None:
            raise ValueError(f"表 {table!r} 不在调试白名单")
        return pk

    def admin_columns(self, table: str) -> List[Dict[str, object]]:
        """PRAGMA 取列定义：name/type/notnull/pk/default。"""
        self.admin_check_table(table)
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        return [
            {
                "name": r["name"],
                "type": r["type"],
                "notnull": bool(r["notnull"]),
                "pk": bool(r["pk"]),
                "default": r["dflt_value"],
            }
            for r in cur.fetchall()
        ]

    def admin_rows(self, table: str) -> List[Dict[str, object]]:
        pk = self.admin_check_table(table)
        cur = self.conn.execute(f"SELECT * FROM {table} ORDER BY {pk}")
        return [dict(r) for r in cur.fetchall()]

    def _admin_valid_cols(self, table: str) -> set:
        return {c["name"] for c in self.admin_columns(table)}

    def admin_upsert(self, table: str, values: Dict[str, object]) -> Dict[str, object]:
        """按主键 INSERT OR REPLACE，返回落库后的行。只接受表内有的列。"""
        pk = self.admin_check_table(table)
        valid = self._admin_valid_cols(table)
        data = {k: v for k, v in values.items() if k in valid}
        if pk not in data or data[pk] in (None, ""):
            raise ValueError(f"缺主键 {pk}")
        cols = list(data.keys())
        placeholders = ",".join("?" for _ in cols)
        collist = ",".join(cols)
        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
            [data[c] for c in cols],
        )
        # 国库/内库同时落在 economy_accounts.balance，load_state 会用后者盖回 metrics。
        # 只改 metrics 表会在下回合被覆盖，故此处同步 economy_accounts。
        if table == "metrics" and data.get("key") in ("国库", "内库") and "value" in data:
            self.conn.execute(
                "UPDATE economy_accounts SET balance = ? WHERE account = ?",
                (float(data["value"]), data["key"]),
            )
        self.conn.commit()
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {pk}=?", (data[pk],)).fetchone()
        return dict(row) if row else {}

    def admin_delete(self, table: str, pk_value: object) -> int:
        """按主键删行，返回受影响行数。"""
        pk = self.admin_check_table(table)
        cur = self.conn.execute(f"DELETE FROM {table} WHERE {pk}=?", (pk_value,))
        self.conn.commit()
        return cur.rowcount
