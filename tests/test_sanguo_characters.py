import json
from pathlib import Path

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from scripts.import_sanguo_characters import LOCATION_IDS


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NAMES = {
    "刘备", "关羽", "张飞", "赵云", "诸葛亮", "孙乾", "简雍", "糜竺", "糜芳", "刘封",
    "庞统", "法正", "黄忠", "魏延", "陈到", "马良", "蒋琬", "费祎", "刘禅", "李严",
    "曹操", "曹丕", "曹仁", "夏侯惇", "夏侯渊", "张辽", "徐晃", "张郃", "于禁", "乐进",
    "许褚", "典韦", "荀彧", "荀攸", "郭嘉", "贾诩", "程昱", "司马懿", "满宠", "蔡瑁",
    "孙权", "周瑜", "鲁肃", "吕蒙", "陆逊", "甘宁", "太史慈", "黄盖", "程普", "韩当",
    "周泰", "凌统", "诸葛瑾", "张昭", "孙尚香", "潘璋", "刘璋", "张松", "黄权", "严颜",
    "张任", "吴懿", "张鲁", "杨松", "杨昂", "马腾", "马超", "韩遂", "马岱", "刘琦",
    "刘表", "黄祖", "刘巴", "公孙康", "士燮", "士壹", "汉献帝", "伏皇后", "刘琮", "董承", "左慈",
}
MANDATORY_SECOND_WAVE = {
    "阎圃", "杨任", "昌奇", "公孙恭", "柳毅", "韩忠", "士武", "士徽", "桓治", "文聘", "王威",
}
REQUIRED_FIELDS = {
    "name", "office", "office_type", "faction", "aliases", "personal_skills",
    "loyalty", "integrity", "ambition", "courage", "closeness_to_liu_bei",
    "martial", "leadership", "intelligence", "politics", "diplomacy", "charisma",
    "power_id", "location", "status", "debut_year", "debut_month", "core_tier",
    "style", "summary", "portrait_id",
}


def test_audited_yongan_location_maps_to_strategic_node():
    assert LOCATION_IDS["永安/白帝"] == "yongan"


def _raw_characters():
    raw = json.loads((ROOT / "content" / "characters.json").read_text(encoding="utf-8"))
    return raw["characters"]


def test_full_roster_has_140_unique_historical_characters_and_preserves_opening_roster():
    characters = _raw_characters()
    names = [item["name"] for item in characters]
    assert len(characters) == 140
    assert len(names) == len(set(names))
    assert EXPECTED_NAMES <= set(names)
    assert MANDATORY_SECOND_WAVE <= set(names)
    assert names.count("马超") == 1


def test_every_character_has_complete_valid_sanguo_fields():
    for character in _raw_characters():
        assert REQUIRED_FIELDS <= set(character), character["name"]
        for field in (
            "loyalty", "integrity", "ambition", "courage", "closeness_to_liu_bei",
            "martial", "leadership", "intelligence", "politics", "diplomacy", "charisma",
        ):
            assert 0 <= character[field] <= 100, (character["name"], field)
        assert character["core_tier"] in {"S", "1", "2", "3"}
        assert character["status"] in {"active", "offstage", "dead"}
        assert character["aliases"]
        assert character["personal_skills"]
        assert character["portrait_id"]


def test_content_and_database_preserve_approved_values_and_dead_status(tmp_path):
    content = GameContent.load()
    assert len(content.characters) == 140
    assert content.characters["刘备"].leadership == 80
    assert content.characters["刘备"].charisma == 96
    assert content.characters["马超"].power_id == "ma_han"
    assert content.characters["马超"].debut_year == 211

    db = GameDB(str(tmp_path / "sanguo.db"), content=content)
    try:
        db.seed_static_data()
        liu_bei = db.conn.execute(
            "SELECT leadership, charisma, ambition, closeness_to_liu_bei, core_tier FROM characters WHERE name='刘备'"
        ).fetchone()
        assert dict(liu_bei) == {
            "leadership": 80,
            "charisma": 96,
            "ambition": 45,
            "closeness_to_liu_bei": 100,
            "core_tier": "S",
        }
        dead_names = {
            row["name"]
            for row in db.conn.execute("SELECT name FROM characters WHERE status='dead'").fetchall()
        }
        assert {"典韦", "郭嘉", "太史慈", "刘表", "黄祖", "董承"} <= dead_names
        assert not db.conn.execute(
            "SELECT 1 FROM characters WHERE name='典韦' AND status='active'"
        ).fetchone()
    finally:
        db.close()
