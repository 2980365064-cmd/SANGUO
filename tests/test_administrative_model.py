import json

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import GameState
from ming_sim.siege import start_siege


def _board():
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    return db


def test_administrative_detail_exposes_confirmed_archive_summary_risks_and_history():
    db = _board()
    try:
        city = db.administrative_detail("city", "city:jiangxia")
        commandery = db.administrative_detail("commandery", "jiangxia")
        province = db.administrative_detail("province", "荆州")
        for detail in (city, commandery, province):
            assert isinstance(detail["summary"], str)
            assert isinstance(detail["risk_notes"], list)
            assert isinstance(detail["recent_history"], list)
        assert "stationed_manpower" in city
        assert "available_grain" in commandery
        assert province["commanderies"] == sorted(
            province["commanderies"], key=lambda item: (-len(item["risk"]), item["name"])
        )
    finally:
        db.close()


def test_three_administrative_scopes_are_seeded_without_overwriting_commandery_facts():
    db = _board()
    try:
        original = GameContent.load().regions["jiangxia"]
        before = dict(db.conn.execute("SELECT population, fiscal FROM regions WHERE id='jiangxia'").fetchone())
        assert db.conn.execute("SELECT COUNT(*) AS n FROM administrative_provinces").fetchone()["n"] == 13
        assert db.conn.execute("SELECT COUNT(*) AS n FROM regions").fetchone()["n"] == 67
        assert db.conn.execute("SELECT COUNT(*) AS n FROM administrative_cities").fetchone()["n"] == 72
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:langzhong'").fetchone() is not None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:zitong'").fetchone() is None
        assert db.conn.execute("SELECT commandery_id FROM administrative_cities WHERE id='city:shangyong'").fetchone()["commandery_id"] == "hanzhong"
        assert db.conn.execute("SELECT name FROM regions WHERE id='zitong'").fetchone()["name"] == "阆中/巴西郡"
        jiaozhou_commanderies = db.conn.execute(
            """SELECT DISTINCT commandery_id FROM administrative_cities
            WHERE province_id='交州' ORDER BY commandery_id"""
        ).fetchall()
        assert [row["commandery_id"] for row in jiaozhou_commanderies] == [
            "cangwu", "hepu", "jiaozhi", "jiuzhen", "nanhai", "yulin"
        ]
        assert db.conn.execute(
            "SELECT commandery_id FROM administrative_cities WHERE id='city:guangxin'"
        ).fetchone()["commandery_id"] == "cangwu"
        assert db.conn.execute(
            "SELECT is_commandery_capital FROM administrative_cities WHERE id='city:longbian'"
        ).fetchone()["is_commandery_capital"] == 1
        assert db.administrative_detail("province", "荆州")["commandery_count"] == 8
        jingzhou_commanderies = db.conn.execute(
            """SELECT DISTINCT commandery_id FROM administrative_cities
            WHERE province_id='荆州' ORDER BY commandery_id"""
        ).fetchall()
        # 行政城池覆盖 5 个郡（有些郡在 regions 表中存在但无行政城池）
        assert [row["commandery_id"] for row in jingzhou_commanderies] == [
            "jiangling", "jiangxia", "jingnan", "wancheng", "wuling",
        ]
        assert db.conn.execute("SELECT commandery_id FROM administrative_cities WHERE id='city:xiangyang'").fetchone()["commandery_id"] == "jiangling"
        # xiangyang/guiyang 等旧郡节点仍保留在 regions 表中，但不在行政城池名册中
        assert db.conn.execute("SELECT 1 FROM regions WHERE id='xiangyang'").fetchone() is not None
        assert db.conn.execute("SELECT 1 FROM regions WHERE id='guiyang'").fetchone() is not None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:guiyang'").fetchone() is None
        assert db.administrative_detail("province", "交州")["commandery_count"] == 7
        assert db.conn.execute("SELECT 1 FROM regions WHERE id='rinan'").fetchone() is not None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:xijuan'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:xuwen'").fetchone() is None
        yangzhou = db.administrative_detail("province", "扬州")
        assert yangzhou["commandery_count"] == 9
        assert {row["id"] for row in yangzhou["commanderies"]} == {
            "danyang", "jiujiang", "wu", "kuaiji", "yuzhang",
            "chaisang", "hefei", "jianye", "lujiang",
        }
        assert db.conn.execute("SELECT commandery_id FROM administrative_cities WHERE id='city:hefei'").fetchone()["commandery_id"] == "jiujiang"
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:shu'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:mianzhu'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:baoxie'").fetchone() is None
        assert db.conn.execute("SELECT commandery_id FROM administrative_cities WHERE id='city:wanling'").fetchone()["commandery_id"] == "danyang"
        assert db.conn.execute("SELECT commandery_id FROM administrative_cities WHERE id='city:chaisang'").fetchone()["commandery_id"] == "yuzhang"
        xuzhou = db.administrative_detail("province", "徐州")
        assert xuzhou["commandery_count"] == 3
        assert {row["id"] for row in xuzhou["commanderies"]} == {
            "guangling", "pengcheng", "xiapi",
        }
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:pizhou'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:haixi'").fetchone() is None
        sili = db.administrative_detail("province", "司隶")
        assert sili["commandery_count"] == 3
        assert {row["id"] for row in sili["commanderies"]} == {"changan", "luoyang", "tongguan"}
        assert db.administrative_detail("commandery", "tongguan")["cities"] == [
            db.administrative_detail("commandery", "tongguan")["city"]
        ]
        assert db.administrative_detail("commandery", "tongguan")["city"]["id"] == "city:tongguan"
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:hangu'").fetchone() is None
        jizhou = db.administrative_detail("province", "冀州")
        assert jizhou["commandery_count"] == 4
        assert {row["id"] for row in jizhou["commanderies"]} == {"ye", "changshan", "nanpi", "bohai"}
        nanpi = db.administrative_detail("commandery", "nanpi")
        assert nanpi["city_count"] == 1
        assert nanpi["city"]["id"] == "city:nanpi"
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:bohai'").fetchone() is None
        bingzhou = db.administrative_detail("province", "并州")
        assert bingzhou["commandery_count"] == 6
        assert {row["id"] for row in bingzhou["commanderies"]} == {"taiyuan", "shangdang", "jiuyuan", "yunzhong", "xihe", "yanmen"}
        assert db.administrative_detail("commandery", "taiyuan")["city"]["name"] == "晋阳"
        assert db.administrative_detail("commandery", "shangdang")["city"]["name"] == "长子"
        assert db.administrative_detail("commandery", "jiuyuan")["city"]["name"] == "九原"
        assert db.administrative_detail("commandery", "yunzhong")["city"]["name"] == "云中"
        assert db.administrative_detail("commandery", "xihe")["city"]["name"] == "离石"
        assert db.administrative_detail("commandery", "yanmen")["city"]["name"] == "阴馆"
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:jinyang-pass'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:zhangzi'").fetchone() is None
        liangzhou = db.administrative_detail("province", "凉州")
        assert liangzhou["commandery_count"] == 6
        assert {row["id"] for row in liangzhou["commanderies"]} == {"wuwei", "zhangye", "jiuquan", "dunhuang", "tianshui", "longxi"}
        assert db.administrative_detail("commandery", "jiuquan")["city"]["name"] == "禄福"
        assert db.administrative_detail("commandery", "dunhuang")["city"]["name"] == "敦煌"
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:gaotai'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:shanggui'").fetchone() is None
        youzhou = db.administrative_detail("province", "幽州")
        assert youzhou["commandery_count"] == 6
        assert {row["id"] for row in youzhou["commanderies"]} == {
            "ji", "zhuojun", "yuyang", "youbeiping", "liaoxi", "liaodong",
        }
        assert db.administrative_detail("commandery", "yuyang")["city"]["name"] == "渔阳"
        assert db.administrative_detail("commandery", "liaoxi")["city"]["name"] == "阳乐"
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:juyong'").fetchone() is None
        assert db.conn.execute("SELECT 1 FROM administrative_cities WHERE id='city:wuzhong'").fetchone() is None
        commandery = db.administrative_detail("commandery", "jiangxia")
        assert commandery["city"]["id"] == "city:jiangxia"
        assert {city["id"] for city in commandery["cities"]} == {"city:jiangxia"}
        assert db.administrative_detail("city", "city:jiangxia")["scope"] == "city"
        assert before["population"] == original.population
        regional_stock = json.loads(before["fiscal"])["grain_stock"]
        city_stock = sum(city["grain_stock"] for city in commandery["cities"])
        assert regional_stock + city_stock == original.fiscal["grain_stock"]
    finally:
        db.close()


def test_city_control_is_the_only_direct_control_write_and_commandery_follows():
    db = _board()
    try:
        db.conn.execute("UPDATE administrative_cities SET controlled_by='liu_bei' WHERE commandery_id='jiangxia'")
        db.recompute_administrative_control()
        assert db.conn.execute("SELECT controlled_by FROM regions WHERE id='jiangxia'").fetchone()["controlled_by"] == "liu_bei"
        assert db.conn.execute("SELECT controlled_by FROM administrative_cities WHERE commandery_id='jiangxia'").fetchone()["controlled_by"] == "liu_bei"
    finally:
        db.close()


def test_multi_city_commandery_uses_majority_and_capital_breaks_a_tie():
    db = _board()
    try:
        # 江夏有西陵（郡治）与夏口；单城改权形成平手时必须仍由郡治裁断。
        original = db.conn.execute("SELECT controlled_by FROM regions WHERE id='jiangxia'").fetchone()["controlled_by"]
        db.conn.execute("UPDATE administrative_cities SET controlled_by='liu_bei' WHERE id='city:xiakou'")
        db.recompute_administrative_control()
        assert db.conn.execute("SELECT controlled_by FROM regions WHERE id='jiangxia'").fetchone()["controlled_by"] == original
        db.conn.execute("UPDATE administrative_cities SET controlled_by='liu_bei' WHERE id='city:jiangxia'")
        db.recompute_administrative_control()
        assert db.conn.execute("SELECT controlled_by FROM regions WHERE id='jiangxia'").fetchone()["controlled_by"] == 'liu_bei'
    finally:
        db.close()


def test_multicity_supply_is_conserved_across_old_and_new_city_stores():
    db = _board()
    try:
        original = GameContent.load().regions["jiangxia"].fiscal["grain_stock"]
        regional = json.loads(db.conn.execute("SELECT fiscal FROM regions WHERE id='jiangxia'").fetchone()["fiscal"])["grain_stock"]
        cities = db.conn.execute("SELECT grain_stock FROM administrative_cities WHERE commandery_id='jiangxia'").fetchall()
        assert regional + sum(row["grain_stock"] for row in cities) == original
    finally:
        db.close()


def test_monthly_admin_settlement_is_deterministic_and_audited():
    db = _board()
    try:
        state = GameState(year=208, period=8, turn=1)
        db.conn.execute("INSERT INTO sieges (target_node, attacker_army_id, defender_power, progress, status, started_turn, last_turn, details) VALUES ('jiangxia','liubei_main','liu_qi',10,'active',1,1,'{}')")
        changes = db.settle_administrative_layers(state)
        city = db.administrative_detail("city", "city:jiangxia")
        assert city["siege_status"] == "围城中"
        assert any(item["scope"] == "city" for item in changes)
        assert db.conn.execute("SELECT COUNT(*) AS n FROM administrative_logs WHERE turn=1").fetchone()["n"] > 0
    finally:
        db.close()


def test_city_reserve_is_consumed_before_commandery_supply_without_double_counting():
    db = _board()
    try:
        state = GameState(year=208, period=8, turn=1)
        before = db.region_grain_stock("jiangxia")
        city_before = db.administrative_detail("city", "city:jiangxia")["grain_stock"]
        remaining = db.adjust_region_grain_stock(state, "jiangxia", -(city_before + 3), "军粮调拨")
        city_after = db.administrative_detail("city", "city:jiangxia")["grain_stock"]
        assert remaining == before - city_before - 3
        assert city_after == 0
        assert db.conn.execute("SELECT COUNT(*) AS n FROM administrative_logs WHERE scope='city'").fetchone()["n"] >= 1
    finally:
        db.close()


def test_siege_order_writes_the_explicit_city_target():
    db = _board()
    try:
        state = GameState(year=208, period=8, turn=1)
        db.conn.execute("UPDATE armies SET station_node='city:langzhong' WHERE id='liubei_main'")
        db.conn.execute("UPDATE administrative_cities SET controlled_by='cao_cao' WHERE id='city:langzhong'")
        db.conn.commit()
        # 需要从一个友方城池围一个相邻的敌方城池
        # langzhong 属于 zhanglu，找一个相邻的敌方城池来围
        # 先将 liubei_main 移到 jiangxia（友方）
        db.conn.execute("UPDATE armies SET station_node='city:jiangxia' WHERE id='liubei_main'")
        db.conn.execute("UPDATE administrative_cities SET controlled_by='cao_cao' WHERE id='city:jiangling'")
        db.conn.commit()
        siege_id = start_siege(db, state, 'liubei_main', 'city:jiangling')
        siege = db.conn.execute("SELECT target_node FROM sieges WHERE id=?", (siege_id,)).fetchone()
        assert siege['target_node'] == 'city:jiangling'
    finally:
        db.close()
