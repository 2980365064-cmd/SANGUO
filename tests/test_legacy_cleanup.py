import sqlite3
from pathlib import Path

import pytest
from fastapi import HTTPException
from ming_sim.paths import SANGUO_SCENARIO_ID, migrate_legacy_ming_data
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import GameState
from ming_sim.models import LLMConfig
from ming_sim.session import GameSession, prune_auto_saves
from web_app import WebGame


def _make_db(path: Path, *, scenario_id: str = "", legacy_power: str = "") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE kv_store (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("CREATE TABLE powers (id TEXT PRIMARY KEY)")
        if scenario_id:
            conn.execute("INSERT INTO kv_store VALUES ('scenario_id', ?)", (scenario_id,))
        if legacy_power:
            conn.execute("INSERT INTO powers VALUES (?)", (legacy_power,))
        conn.commit()
    finally:
        conn.close()


def test_first_start_removes_only_recognizable_ming_databases(tmp_path):
    saves = tmp_path / "saves"
    saves.mkdir()
    legacy_main = tmp_path / "ming_sim.db"
    legacy_save = saves / "old_ming.db"
    sanguo_save = saves / "sanguo.db"
    unrelated = saves / "notes.db"
    _make_db(legacy_main, legacy_power="houjin")
    _make_db(legacy_save, legacy_power="ming")
    _make_db(sanguo_save, scenario_id=SANGUO_SCENARIO_ID)
    unrelated.write_text("not sqlite", encoding="utf-8")

    removed = migrate_legacy_ming_data(tmp_path)

    assert {Path(item).name for item in removed} == {"ming_sim.db", "old_ming.db"}
    assert not legacy_main.exists() and not legacy_save.exists()
    assert sanguo_save.exists() and unrelated.exists()
    assert (tmp_path / ".sanguo_liubei_208_migrated").exists()


def test_legacy_cleanup_runs_only_once(tmp_path):
    (tmp_path / "saves").mkdir()
    migrate_legacy_ming_data(tmp_path)
    late_legacy = tmp_path / "saves" / "late.db"
    _make_db(late_legacy, legacy_power="houjin")

    assert migrate_legacy_ming_data(tmp_path) == []
    assert late_legacy.exists()


def test_new_database_is_stamped_with_unambiguous_sanguo_scenario_id():
    db = GameDB(":memory:", content=GameContent.load())
    try:
        db.seed_static_data()
        assert db.kv_get("scenario_id") == SANGUO_SCENARIO_ID
    finally:
        db.close()


def test_runtime_prompts_do_not_expose_ming_scenario_language():
    forbidden = ("崇祯", "大明", "后金", "皇太极", "辽饷", "后宫", "选妃", "晚明")
    prompt_dir = Path(__file__).resolve().parents[1] / "content" / "prompts"
    for prompt in prompt_dir.glob("*.md"):
        text = prompt.read_text(encoding="utf-8")
        for stale in forbidden:
            assert stale not in text, (prompt.name, stale)


def test_default_game_state_is_208_liubei_campaign():
    state = GameState()
    assert (state.year, state.period, state.turn, state.stage) == (208, 8, 1, "流亡军")
    assert set(state.metrics) == {"军资", "粮秣", "民望", "名分", "军心", "士族支持"}


def test_new_session_enters_208_campaign_without_legacy_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MING_SIM_USER_DATA_DIR", str(tmp_path / "user-data"))
    session = GameSession(
        str(tmp_path / "game.db"),
        LLMConfig(api_key="", base_url="http://127.0.0.1/v1", model="test"),
        verify_llm=False,
    )
    try:
        snapshot = session.begin_turn()
        assert (snapshot.year, snapshot.period, snapshot.turn) == (208, 8, 1)
        assert session.db.kv_get("scenario_id") == SANGUO_SCENARIO_ID
        assert "国库" not in snapshot.metrics and "皇威" not in snapshot.metrics
        ministers = {item.name for item in session.list_ministers()}
        assert "刘备" in ministers and "诸葛亮" in ministers
        assert "曹操" not in ministers and "孙权" not in ministers
    finally:
        session.close()


def test_session_resolves_one_sanguo_month_without_legacy_fiscal_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("MING_SIM_USER_DATA_DIR", str(tmp_path / "user-data"))
    session = GameSession(
        str(tmp_path / "game.db"),
        LLMConfig(api_key="", base_url="http://127.0.0.1/v1", model="test"),
        verify_llm=False,
    )
    try:
        session.begin_turn()
        result = session.resolve_turn()
        assert not result.awaiting
        assert (session.state.year, session.state.period, session.state.turn) == (208, 9, 2)
        assert result.report
        assert "国库" not in result.report and "皇威" not in result.report
    finally:
        session.close()


def test_sanguo_month_uses_llm_only_to_narrate_settled_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("MING_SIM_USER_DATA_DIR", str(tmp_path / "user-data"))
    session = GameSession(
        str(tmp_path / "game.db"),
        LLMConfig(api_key="test", base_url="http://127.0.0.1/v1", model="narrator"),
        verify_llm=False,
    )
    captured = {}

    def fake_narrate(hard_report):
        captured["hard_report"] = hard_report
        return "《赤壁月报》\n硬规则事实已经裁定，以下仅作叙事。"

    monkeypatch.setattr(session, "_narrate_sanguo_month", fake_narrate)
    try:
        session.begin_turn()
        result = session.resolve_turn()
        assert captured["hard_report"].startswith("《月末军政报》")
        assert result.report.startswith("《赤壁月报》")
        assert session.db.get_turn_report(1) == result.report
    finally:
        session.close()


def test_auto_save_rotation_keeps_three_turns_and_all_manual_saves(tmp_path):
    campaign = "abc123"
    for turn in range(1, 6):
        for tag in ("begin", "preresolve"):
            (tmp_path / f"auto_{campaign}_0208_08_t{turn}_{tag}.db").touch()
    manual = tmp_path / "赤壁前夕.db"
    manual.touch()

    prune_auto_saves(str(tmp_path), campaign, keep_turns=3)

    remaining = {path.name for path in tmp_path.glob("*.db")}
    assert manual.name in remaining
    assert all(f"_t{turn}_" not in name for turn in (1, 2) for name in remaining)
    assert all(any(f"_t{turn}_" in name for name in remaining) for turn in (3, 4, 5))


def test_manual_save_and_hot_load_restore_sanguo_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MING_SIM_USER_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.setattr("web_app.verify_llm_available", lambda _config: None)
    monkeypatch.setattr("ming_sim.session.verify_llm_available", lambda _config: None)
    config = LLMConfig(api_key="test", base_url="http://127.0.0.1/v1", model="test")
    session = GameSession(str(tmp_path / "game.db"), config, verify_llm=False)
    session.begin_turn()
    game = WebGame.__new__(WebGame)
    game.session = session
    game.db_path = str(tmp_path / "game.db")
    game.favorites = {"刘备"}
    game.chat_history = {}
    try:
        game.save_to("赤壁前夕")
        session.state.metrics["军资"] = 1
        session.db.save_state(session.state)

        game.load_save("赤壁前夕")

        assert game.state.metrics["军资"] == 60
        assert game.db.kv_get("scenario_id") == SANGUO_SCENARIO_ID
    finally:
        game.session.close()


def test_223_resolution_persists_ending_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("MING_SIM_USER_DATA_DIR", str(tmp_path / "user-data"))
    session = GameSession(
        str(tmp_path / "game.db"),
        LLMConfig(api_key="", base_url="http://127.0.0.1/v1", model="test"),
        verify_llm=False,
    )
    try:
        session.begin_turn()
        session.state.year, session.state.period, session.state.turn = 223, 4, 178
        session.db.save_state(session.state)
        result = session.resolve_turn()

        assert session.state.ended
        assert session.state.ending_status in {"historical_baidi", "rewritten_223"}
        assert session.db.get_ending_summary()
        assert "本局" in result.report or "收束" in result.report
    finally:
        session.close()


def test_hot_load_rejects_non_sanguo_database_without_replacing_current_game(tmp_path, monkeypatch):
    monkeypatch.setenv("MING_SIM_USER_DATA_DIR", str(tmp_path / "user-data"))
    config = LLMConfig(api_key="test", base_url="http://127.0.0.1/v1", model="test")
    session = GameSession(str(tmp_path / "game.db"), config, verify_llm=False)
    session.begin_turn()
    game = WebGame.__new__(WebGame)
    game.session = session
    game.db_path = str(tmp_path / "game.db")
    game.favorites = set()
    game.chat_history = {}
    legacy = Path(game.saves_dir()) / "旧档.db"
    _make_db(legacy, legacy_power="ming")
    try:
        with pytest.raises(HTTPException) as error:
            game.load_save("旧档")
        assert error.value.status_code == 409
        assert game.db.kv_get("scenario_id") == SANGUO_SCENARIO_ID
    finally:
        game.session.close()
