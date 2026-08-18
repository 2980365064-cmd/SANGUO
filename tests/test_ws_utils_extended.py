"""tests/test_ws_utils_extended.py：第六期新增工具函数测试（阶段 A）。

验证：
  - get_turn / get_year / get_period
  - to_json
  - is_already_processed
"""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.ws_utils import (
    get_turn, get_year, get_period, to_json,
    is_already_processed, decode_json, safe_list, status_terminal, clamp,
)


# ---------------------------------------------------------------------------
# get_turn / get_year / get_period
# ---------------------------------------------------------------------------

class TestStateAccessors:
    def test_get_turn_basic(self):
        state = SimpleNamespace(turn=42, year=208, period=8)
        assert get_turn(state) == 42

    def test_get_turn_missing_defaults_to_zero(self):
        state = SimpleNamespace()
        assert get_turn(state) == 0

    def test_get_turn_string_coerced(self):
        state = SimpleNamespace(turn="7")
        assert get_turn(state) == 7

    def test_get_year_basic(self):
        state = SimpleNamespace(year=220)
        assert get_year(state) == 220

    def test_get_year_missing(self):
        state = SimpleNamespace()
        assert get_year(state) == 0

    def test_get_period_basic(self):
        state = SimpleNamespace(period=3)
        assert get_period(state) == 3

    def test_get_period_missing(self):
        state = SimpleNamespace()
        assert get_period(state) == 0


# ---------------------------------------------------------------------------
# to_json
# ---------------------------------------------------------------------------

class TestToJson:
    def test_dict_roundtrip(self):
        import json
        data = {"a": 1, "b": "中"}
        result = to_json(data)
        assert json.loads(result) == data

    def test_ensure_ascii_false(self):
        """中文字符不应被转义。"""
        result = to_json({"name": "关羽"})
        assert "关羽" in result
        assert "\\u" not in result

    def test_list(self):
        result = to_json([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_nested(self):
        result = to_json({"effects": [{"delta": -5}]})
        assert '"delta": -5' in result


# ---------------------------------------------------------------------------
# is_already_processed
# ---------------------------------------------------------------------------

class TestIsAlreadyProcessed:
    def _board(self, tmp_path: Path) -> GameDB:
        db = GameDB(str(tmp_path / "idempotent.db"), content=GameContent.load())
        db.seed_static_data()
        db.conn.execute(
            "INSERT OR IGNORE INTO game_state (id, year, period, turn) VALUES (1, 208, 8, 1)"
        )
        db.conn.commit()
        return db

    def test_returns_false_when_empty(self, tmp_path):
        db = self._board(tmp_path)
        assert is_already_processed(
            db, "power_logs", ("turn", "power_id"), (1, "cao_cao"),
        ) is False

    def test_returns_true_after_insert(self, tmp_path):
        db = self._board(tmp_path)
        db.conn.execute(
            "INSERT INTO power_logs (turn, year, period, power_id, field, old_value, new_value, delta, reason) "
            "VALUES (1, 208, 8, 'cao_cao', 'cohesion', 50, 45, -5, 'test')"
        )
        db.conn.commit()
        assert is_already_processed(
            db, "power_logs", ("turn", "power_id"), (1, "cao_cao"),
        ) is True

    def test_multi_column_match(self, tmp_path):
        db = self._board(tmp_path)
        db.conn.execute(
            "INSERT OR IGNORE INTO diplomatic_relations (power_a, power_b, public_relation, trust, status) "
            "VALUES ('cao_cao', 'liu_bei', -30, 10, 'neutral')"
        )
        db.conn.commit()
        assert is_already_processed(
            db, "diplomatic_relations", ("power_a", "power_b"), ("cao_cao", "liu_bei"),
        ) is True
        assert is_already_processed(
            db, "diplomatic_relations", ("power_a", "power_b"), ("sun_quan", "liu_bei"),
        ) is False


# ---------------------------------------------------------------------------
# 原有函数回归
# ---------------------------------------------------------------------------

class TestOriginalFunctions:
    def test_decode_json_dict(self):
        assert decode_json({"a": 1}, {}) == {"a": 1}

    def test_decode_json_string(self):
        assert decode_json('{"a":1}', {}) == {"a": 1}

    def test_decode_json_fallback(self):
        assert decode_json("not json", {"x": 0}) == {"x": 0}

    def test_safe_list(self):
        assert safe_list([1, 2]) == [1, 2]
        assert safe_list("[1,2]") == [1, 2]
        assert safe_list(None) == []

    def test_status_terminal_english(self):
        assert status_terminal("defeated") is True
        assert status_terminal("destroyed") is True
        assert status_terminal("active") is False

    def test_status_terminal_chinese(self):
        assert status_terminal("灭亡") is True
        assert status_terminal("覆灭") is True
        assert status_terminal("已亡") is True
        assert status_terminal("活跃") is False

    def test_clamp_default(self):
        assert clamp(150) == 100
        assert clamp(-200) == -100
        assert clamp(50) == 50

    def test_clamp_custom_range(self):
        assert clamp(150, lo=0, hi=100) == 100
        assert clamp(-5, lo=0, hi=100) == 0
