from types import SimpleNamespace

from fastapi.testclient import TestClient

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import GameState
import web_app
from web_app import WebGame, app


def _game():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    state = GameState(
        year=208,
        period=8,
        turn=1,
        stage="流亡军",
        metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
    )
    session = SimpleNamespace(
        db=db,
        content=content,
        state=state,
        previous_summary="",
        last_decree="",
        last_report="",
        victory=lambda: {"status": "ongoing", "summary": "天下未定"},
        list_structured_directives=lambda: [],
        pending_count=lambda: 0,
        pending_decisions=lambda: [],
    )
    instance = WebGame.__new__(WebGame)
    instance.session = session
    instance.favorites = {"刘备", "诸葛亮"}
    return instance


def test_action_intent_confirm_ongoing_plan_and_month_agenda_api(monkeypatch):
    game = _game()
    monkeypatch.setattr(web_app, "web_game", game)
    client = TestClient(app)

    created = client.post(
        "/api/action_intents",
        json={"text": "让张飞率军平定江夏叛军，三个月内完成，不得滥杀百姓。", "source": "自由命令"},
    )
    assert created.status_code == 200
    intent = created.json()["intent"]
    assert intent["draft"]["action_type"] == "长期方略"

    confirmed = client.post(f"/api/action_intents/{intent['id']}/confirm")
    assert confirmed.status_code == 200
    plan_id = confirmed.json()["plan"]["id"]

    game.db.update_ongoing_plan(plan_id, status="blocked", last_result="粮道受扰，需主公裁断。")
    agenda = client.get("/api/month_agenda")
    assert agenda.status_code == 200
    assert any(item["ref_id"] == plan_id for item in agenda.json()["items"])

    plans = client.get("/api/ongoing_plans")
    assert plans.status_code == 200
    assert plans.json()["plans"][0]["status"] == "blocked"


def test_envoy_and_reputation_interfaces(monkeypatch):
    game = _game()
    monkeypatch.setattr(web_app, "web_game", game)
    client = TestClient(app)

    envoy = client.post(
        "/api/envoys",
        json={
            "target_power": "sun_quan",
            "envoy": "诸葛亮",
            "goal": "续盟并借粮",
            "boundaries": "不得割让江夏，不得背盟。",
        },
    )
    assert envoy.status_code == 200
    assert envoy.json()["mission"]["status"] == "active"

    missions = client.get("/api/envoys")
    assert missions.status_code == 200
    assert missions.json()["missions"][0]["envoy"] == "诸葛亮"

    game.db.add_reputation_log(game.state, source_kind="envoy", source_id="1", metric="仁义", delta=2, summary="守约遣使，孙刘互信稍增。")
    reputation = client.get("/api/reputation")
    assert reputation.status_code == 200
    assert reputation.json()["summary"]["recent"][0]["metric"] == "仁义"
