"""ming_sim.ws_utils 工具函数单元测试。"""
import pytest
from ming_sim.ws_utils import decode_json, safe_list, status_terminal, clamp


class TestDecodeJson:
    def test_json_string(self):
        assert decode_json('{"a": 1}', {}) == {"a": 1}

    def test_json_list(self):
        assert decode_json('[1, 2, 3]', []) == [1, 2, 3]

    def test_already_dict(self):
        assert decode_json({"a": 1}, {}) == {"a": 1}

    def test_already_list(self):
        assert decode_json([1, 2], []) == [1, 2]

    def test_invalid_json_returns_fallback(self):
        assert decode_json("not json", "fallback") == "fallback"

    def test_empty_string_returns_fallback(self):
        assert decode_json("", {"default": True}) == {"default": True}

    def test_none_returns_fallback(self):
        assert decode_json(None, []) == []


class TestSafeList:
    def test_list_passthrough(self):
        assert safe_list([1, 2, 3]) == [1, 2, 3]

    def test_json_string_list(self):
        assert safe_list('[1, 2, 3]') == [1, 2, 3]

    def test_non_list_returns_empty(self):
        assert safe_list("not a list") == []
        assert safe_list(123) == []
        assert safe_list(None) == []

    def test_json_non_list_returns_empty(self):
        assert safe_list('{"a": 1}') == []


class TestStatusTerminal:
    def test_english_terminal(self):
        assert status_terminal("defeated") is True
        assert status_terminal("destroyed") is True
        assert status_terminal("collapsed") is True
        assert status_terminal("inactive") is True

    def test_chinese_terminal(self):
        assert status_terminal("已灭亡") is True
        assert status_terminal("已瓦解") is True
        assert status_terminal("已覆灭") is True
        assert status_terminal("已亡") is True

    def test_active_status(self):
        assert status_terminal("active") is False
        assert status_terminal("at_war") is False
        assert status_terminal("allied") is False

    def test_case_insensitive(self):
        assert status_terminal("DEFEATED") is True
        assert status_terminal("Destroyed") is True


class TestClamp:
    def test_default_bounds(self):
        assert clamp(50) == 50
        assert clamp(-150) == -100
        assert clamp(150) == 100

    def test_custom_bounds(self):
        assert clamp(50, 0, 100) == 50
        assert clamp(-10, 0, 100) == 0
        assert clamp(150, 0, 100) == 100

    def test_string_input(self):
        assert clamp("50", 0, 100) == 50
