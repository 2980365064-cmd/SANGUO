from dataclasses import replace

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.intelligence import (
    get_character_intel_level,
    raise_character_intel,
    visible_character_profile,
)


class _MemoryKV:
    def __init__(self):
        self.data = {}

    def kv_get(self, key):
        return self.data.get(key)

    def kv_set(self, key, value):
        self.data[key] = value


def test_own_six_abilities_are_public_even_with_no_intelligence():
    mifang = GameContent.load().characters["糜芳"]

    profile = visible_character_profile(mifang, intel_level=0)

    assert profile["abilities"]["visibility"] == "exact"
    assert profile["abilities"]["values"] == {
        "martial": mifang.martial,
        "leadership": mifang.leadership,
        "intelligence": mifang.intelligence,
        "politics": mifang.politics,
        "diplomacy": mifang.diplomacy,
        "charisma": mifang.charisma,
    }


def test_own_dynamic_personality_is_not_exact_when_intelligence_and_closeness_are_low():
    mifang = replace(
        GameContent.load().characters["糜芳"],
        closeness_to_liu_bei=35,
    )

    profile = visible_character_profile(mifang, intel_level=0)

    assert profile["personality"]["visibility"] == "tendency"
    assert all(isinstance(value, str) for value in profile["personality"]["values"].values())


def test_enemy_low_intelligence_exposes_only_assessments_and_tendencies():
    caocao = GameContent.load().characters["曹操"]

    profile = visible_character_profile(caocao, intel_level=0)

    assert profile["abilities"]["visibility"] == "assessment"
    assert profile["personality"]["visibility"] == "tendency"
    assert all(isinstance(value, str) for value in profile["abilities"]["values"].values())
    assert all(isinstance(value, str) for value in profile["personality"]["values"].values())


def test_enemy_mid_intelligence_exposes_ranges_without_raw_personality_values():
    caocao = GameContent.load().characters["曹操"]

    profile = visible_character_profile(caocao, intel_level=1)

    assert profile["abilities"]["visibility"] == "range"
    assert profile["personality"]["visibility"] == "range"
    for field, value in profile["personality"]["values"].items():
        raw = getattr(caocao, field)
        assert value["min"] <= raw <= value["max"]
        assert value["min"] < value["max"]


def test_high_intelligence_exposes_exact_enemy_profile():
    caocao = GameContent.load().characters["曹操"]

    profile = visible_character_profile(caocao, intel_level=3)

    assert profile["abilities"]["visibility"] == "exact"
    assert profile["personality"]["visibility"] == "exact"
    assert profile["personality"]["values"]["ambition"] == caocao.ambition


def test_high_closeness_reveals_exact_personality_without_high_intelligence():
    caocao = replace(
        GameContent.load().characters["曹操"],
        closeness_to_liu_bei=85,
    )

    profile = visible_character_profile(caocao, intel_level=0)

    assert profile["personality"]["visibility"] == "exact"


def test_intelligence_level_is_clamped_and_raw_fields_are_not_returned_at_top_level():
    caocao = GameContent.load().characters["曹操"]

    profile = visible_character_profile(caocao, intel_level=-99)

    assert profile["intel_level"] == 0
    for hidden_field in ("loyalty", "integrity", "ambition", "courage", "closeness_to_liu_bei"):
        assert hidden_field not in profile


def test_recon_spy_and_diplomacy_raise_persistent_intelligence_level():
    db = _MemoryKV()

    assert get_character_intel_level(db, "曹操") == 0
    assert raise_character_intel(db, "曹操", source="recon") == 1
    assert raise_character_intel(db, "曹操", source="spy", amount=2) == 3
    assert raise_character_intel(db, "曹操", source="diplomacy") == 3
    assert get_character_intel_level(db, "曹操") == 3


def test_unknown_intelligence_source_is_rejected():
    db = _MemoryKV()

    try:
        raise_character_intel(db, "曹操", source="free_debug_cheat")
    except ValueError as exc:
        assert "情报来源" in str(exc)
    else:
        raise AssertionError("非法情报来源必须被拒绝")


def test_web_public_character_payload_does_not_leak_legacy_raw_fields(tmp_path, monkeypatch):
    # 测试环境未安装上传头像所需的 python-multipart；这里只为加载路由模块，
    # 用最小替身满足 FastAPI 的导入检查，不参与本测试的请求解析。
    import sys
    import types

    multipart = types.ModuleType("multipart")
    multipart.__version__ = "0.0.20"
    multipart_parser = types.ModuleType("multipart.multipart")
    multipart_parser.parse_options_header = lambda value: (value, {})
    monkeypatch.setitem(sys.modules, "multipart", multipart)
    monkeypatch.setitem(sys.modules, "multipart.multipart", multipart_parser)
    from web_app import WebGame

    content = GameContent.load()
    db = GameDB(str(tmp_path / "public-profile.db"), content=content)
    db.seed_static_data()
    game = WebGame.__new__(WebGame)
    game.session = types.SimpleNamespace(db=db)
    game.favorites = set()
    game._runtime_skill_payloads = lambda _character: []
    try:
        payload = game.public_character(content.characters["曹操"])
        assert payload["abilities"]["visibility"] == "assessment"
        assert payload["personality"]["visibility"] == "tendency"
        for legacy_raw_field in (
            "loyalty", "ability", "integrity", "courage", "diplomacy",
            "martial", "stewardship", "intrigue", "learning", "ambition",
            "closeness_to_liu_bei",
        ):
            assert legacy_raw_field not in payload
    finally:
        db.close()
