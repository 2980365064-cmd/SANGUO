from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_llm_configuration_types_cover_safe_status_and_editable_payload():
    source = (ROOT / "web/src/types.ts").read_text(encoding="utf-8")
    assert "export type LlmConfigSummary" in source
    assert "export type LlmConfigPayload" in source
    assert "has_api_key: boolean" in source
    assert "has_advanced_api_key: boolean" in source
    assert "llm: LlmConfigSummary" in source


def test_api_layer_exposes_menu_and_live_llm_configuration():
    source = (ROOT / "web/src/api.ts").read_text(encoding="utf-8")
    assert '"/api/menu/llm"' in source
    assert '"/api/llm/config"' in source
    for name in ("saveMenuLlmConfig", "getGameLlmConfig", "saveGameLlmConfig"):
        assert f"export const {name}" in source


def test_shared_modal_preserves_secrets_and_exposes_advanced_fields():
    source = (ROOT / "web/src/components/apiConfigModal.tsx").read_text(encoding="utf-8")
    assert 'type="password"' in source
    assert '"__keep__"' in source
    for label in ("API Base URL", "模型名称", "API Key", "高级配置", "测试并保存"):
        assert label in source


def test_menu_and_game_sidebar_share_api_config_modal():
    source = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
    # 新架构中，API 配置在 MenuScreen 中提供
    # 游戏内 API 配置将迁移到设置页面（Step 5）
    assert 'mode="menu"' in source
    assert "<ApiConfigModal" in source
