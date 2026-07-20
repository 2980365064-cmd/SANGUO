from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monthly_report_exposes_structured_battle_audit_factors_inside_monthly_summary():
    source = (ROOT / "web/src/components/monthlyReportPanel.tsx").read_text(encoding="utf-8")
    army_panel = (ROOT / "web/src/components/armyCommandPanel.tsx").read_text(encoding="utf-8")
    main_source = (ROOT / "web/src/main.tsx").read_text(encoding="utf-8")
    api_source = (ROOT / "web/src/api.ts").read_text(encoding="utf-8")

    assert "MonthlyReportPanel" in main_source
    assert "getMonthlyReport" in api_source
    assert "state.battles" not in army_panel
    for label in ("兵力、统率、士气、补给、地形、特性细目", "随机值", "计策贡献", "army_breakdown"):
        assert label in source
