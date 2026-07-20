from types import SimpleNamespace

from ming_sim.models import LLMConfig
from web_app import WebGame


def test_live_llm_config_refreshes_agents_without_restarting_turn(monkeypatch):
    current = LLMConfig(
        api_key="old-key",
        base_url="https://old.example/v1",
        model="old-model",
    )
    lifecycle_calls = []
    session = SimpleNamespace(
        llm_config=current,
        refresh_registry=lambda: lifecycle_calls.append("refresh_registry"),
        begin_turn=lambda: lifecycle_calls.append("begin_turn"),
    )
    game = WebGame.__new__(WebGame)
    game.session = session
    monkeypatch.setattr("web_app._verify_llm_configs_or_raise", lambda _config: None)
    monkeypatch.setattr("web_app.save_runtime_llm", lambda *_args: None)

    saved = game.apply_llm_config(
        "https://new.example/v1",
        "new-model",
        "new-key",
    )

    assert saved.model == "new-model"
    assert lifecycle_calls == ["refresh_registry"]
