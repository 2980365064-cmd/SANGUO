from ming_sim.military import composition_multiplier, eligible_for_role, morale_delta, normalize_composition, proportional_losses


def test_legacy_composition_migrates_without_losing_manpower():
    result = normalize_composition({"步卒": 6300, "弓弩": 2700})
    assert result == {"轻步": 6300, "弓弩": 2700}
    assert sum(result.values()) == 9000


def test_composition_counter_is_bounded_and_terrain_sensitive():
    multiplier, notes = composition_multiplier({"水军": 10000}, {"轻步": 10000}, "江河")
    assert multiplier == 1.15
    assert "水军适江河" in notes
    dry_multiplier, _ = composition_multiplier({"水军": 10000}, {"轻步": 10000}, "普通路")
    assert dry_multiplier < 1


def test_losses_are_proportional_and_exact():
    remaining = proportional_losses({"轻步": 700, "弓弩": 300}, 101)
    assert sum(remaining.values()) == 899
    assert remaining["轻步"] in {629, 630}


def test_specialist_commander_requires_rank_and_merit():
    assert not eligible_for_role("校尉", 100, "主将", {"水军": 1000})[0]
    assert eligible_for_role("中郎将", 60, "主将", {"水军": 1000})[0]


def test_morale_accounts_for_supply_pay_fatigue_loss_and_command():
    delta, reasons = morale_delta(
        supply_source="starvation", starvation_turns=1, arrears=40, maintenance=10,
        fatigue=80, casualty_rate=0.2, won=False, discipline=75,
        has_deputy=True, has_adjutant=True,
    )
    assert delta == -25  # 单次结算下限，避免连锁崩坏
    assert {"断粮1月", "欠饷积压", "疲劳过甚", "战败", "战损20%"} <= set(reasons)
