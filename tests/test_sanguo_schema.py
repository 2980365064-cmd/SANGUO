from ming_sim.db import GameDB
from ming_sim.models import GameState


def _columns(db: GameDB, table: str) -> set[str]:
    return {row["name"] for row in db.conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_sanguo_schema_has_required_character_and_campaign_fields(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        assert {
            "leadership", "intelligence", "politics", "charisma", "ambition",
            "closeness_to_liu_bei", "core_tier",
        } <= _columns(db, "characters")
        assert {
            "fatigue", "experience", "discipline", "hazard_turns", "specialties",
            "hazard_combat_multiplier", "hazard_mobility_multiplier", "starvation_turns",
            "supply_combat_multiplier", "supply_last_settled_turn",
        } <= _columns(db, "armies")
        assert {"stage", "collapse_turns", "chengdu_crisis_turns"} <= _columns(db, "game_state")
    finally:
        db.close()


def test_sanguo_strategic_tables_seed_from_approved_route_catalog(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        db.seed_static_data()
        nodes = db.conn.execute("SELECT COUNT(*) AS n FROM strategic_nodes").fetchone()["n"]
        edges = db.conn.execute("SELECT COUNT(*) AS n FROM strategic_routes").fetchone()["n"]
        assert nodes == 49
        assert edges == 79
    finally:
        db.close()


def test_campaign_tables_cover_orders_sieges_treaties_and_attribute_logs(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        for table in ("army_orders", "sieges", "diplomacy_treaties", "character_attribute_logs", "pending_adjudications"):
            assert db.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone() is not None
    finally:
        db.close()


def test_strategy_mixin_lists_routes_and_enforces_one_order_per_army_turn(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        db.seed_static_data()
        assert len(db.list_strategic_nodes()) == 49
        assert len(db.list_strategic_routes()) == 79

        state = GameState(turn=7)
        order_id = db.issue_army_order(state, "liubei_main", "移动", {"to": "xiangyang"})
        assert order_id > 0
        orders = db.list_army_orders(7)
        assert orders[0]["id"] == order_id
        assert orders[0]["payload"] == {"to": "xiangyang"}

        try:
            db.issue_army_order(state, "liubei_main", "补给", {})
        except ValueError as error:
            assert "本回合已执行主军令" in str(error)
        else:
            raise AssertionError("同一军队同一回合的第二道主军令应被拒绝")
    finally:
        db.close()


def test_sanguo_campaign_state_fields_round_trip(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        state = GameState(
            year=214,
            period=8,
            turn=70,
            stage="益州牧",
            collapse_turns=2,
            chengdu_crisis_turns=1,
        )
        db.save_state(state)
        loaded = db.load_state()
        assert loaded.stage == "益州牧"
        assert loaded.collapse_turns == 2
        assert loaded.chengdu_crisis_turns == 1
    finally:
        db.close()


def test_seed_static_data_does_not_overwrite_existing_strategic_board(tmp_path):
    db = GameDB(str(tmp_path / "sanguo.db"))
    try:
        db.seed_static_data()
        db.conn.execute("UPDATE strategic_nodes SET name='玩家改写名称' WHERE id='changan'")
        db.conn.commit()
        db.seed_static_data()
        row = db.conn.execute("SELECT name FROM strategic_nodes WHERE id='changan'").fetchone()
        assert row["name"] == "玩家改写名称"
    finally:
        db.close()
