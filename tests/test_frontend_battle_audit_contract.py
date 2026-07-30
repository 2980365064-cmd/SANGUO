from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monthly_report_exposes_structured_battle_audit_factors_inside_monthly_summary():
    source = (ROOT / "web/src/components/monthlyReportPanel.tsx").read_text(encoding="utf-8")
    map_info = (ROOT / "web/src/components/mapInfo/MapInfoDrawer.tsx").read_text(encoding="utf-8")
    # MonthlyReportPanel 已迁移到新页面架构
    situation_hub = (ROOT / "web/src/pages/SituationHub.tsx").read_text(encoding="utf-8")
    monthly_summary = (ROOT / "web/src/pages/MonthlySummary.tsx").read_text(encoding="utf-8")
    api_source = (ROOT / "web/src/api.ts").read_text(encoding="utf-8")

    # MonthlyReportPanel 或月报功能在新页面中可用
    assert "MonthlyReport" in situation_hub or "MonthlyReport" in monthly_summary or "monthlyReport" in situation_hub
    assert "getMonthlyReport" in api_source
    assert "state.battles" not in map_info
    for label in ("兵力、统率、士气、补给、地形、特性细目", "随机值", "计策贡献", "army_breakdown"):
        assert label in source
