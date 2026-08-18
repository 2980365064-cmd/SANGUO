"""军府编制的纯规则：七类兵种、克制、职务资格与确定性伤亡分摊。"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable

TROOP_TYPES = ("轻步", "重步", "弓弩", "骑兵", "突骑", "水军", "工兵")
SPECIALIST_TYPES = {"突骑", "水军", "工兵"}
RANKS = ("裨将", "校尉", "中郎将", "杂号将军", "重号将军")
RANK_LEVEL = {name: index + 1 for index, name in enumerate(RANKS)}
RANK_REQUIREMENTS = {"裨将": 0, "校尉": 20, "中郎将": 60, "杂号将军": 130, "重号将军": 240}
ROLE_REQUIREMENTS = {"主将": 2, "副将": 1, "军司马": 1}

# 仅记录结构性优势；最终相克修正在[-15%, +15%]内截断。
COUNTERS = {
    "重步": {"轻步": 0.08, "骑兵": 0.07, "突骑": 0.07},
    "弓弩": {"轻步": 0.08, "水军": 0.05},
    "骑兵": {"弓弩": 0.08, "工兵": 0.08},
    "突骑": {"弓弩": 0.10, "轻步": 0.08, "工兵": 0.08},
    "水军": {"轻步": 0.06, "重步": 0.06, "骑兵": 0.08},
}

LEGACY_TROOPS = {"步卒": "轻步", "步兵": "轻步", "弓弩": "弓弩", "骑兵": "骑兵", "水军": "水军"}


def normalize_composition(raw: object) -> Dict[str, int]:
    """把旧四类与旧存档的自由文本确定性归并为七类，不改变人数。"""
    source = raw if isinstance(raw, dict) else {}
    out: Dict[str, int] = defaultdict(int)
    for key, value in source.items():
        try:
            amount = max(0, int(value))
        except (TypeError, ValueError):
            continue
        name = str(key).strip()
        target = LEGACY_TROOPS.get(name)
        if not target:
            target = next((item for item in TROOP_TYPES if item in name), "轻步")
        if amount:
            out[target] += amount
    return {kind: out[kind] for kind in TROOP_TYPES if out[kind]}


def proportional_losses(composition: Dict[str, int], casualties: int) -> Dict[str, int]:
    """最大余数法分摊伤亡，精确守恒且可重放。"""
    comp = normalize_composition(composition)
    total = sum(comp.values())
    loss = max(0, min(total, int(casualties)))
    if not total or not loss:
        return comp
    base = {kind: min(amount, amount * loss // total) for kind, amount in comp.items()}
    remaining = loss - sum(base.values())
    order = sorted(comp, key=lambda kind: (-(comp[kind] * loss % total), kind))
    for kind in order:
        if not remaining:
            break
        if base[kind] < comp[kind]:
            base[kind] += 1
            remaining -= 1
    return {kind: amount - base[kind] for kind, amount in comp.items() if amount > base[kind]}


def composition_multiplier(own: Dict[str, int], enemy: Dict[str, int], terrain: str) -> tuple[float, list[str]]:
    own, enemy = normalize_composition(own), normalize_composition(enemy)
    total = max(1, sum(own.values()))
    enemy_total = max(1, sum(enemy.values()))
    delta, notes = 0.0, []
    for kind, amount in own.items():
        share = amount / total
        for target, advantage in COUNTERS.get(kind, {}).items():
            target_share = enemy.get(target, 0) / enemy_total
            if target_share:
                gained = share * target_share * advantage
                delta += gained
                if gained >= 0.01:
                    notes.append(f"{kind}制{target}")
    water_share = own.get("水军", 0) / total
    if terrain == "江河":
        delta += water_share * 0.12
        if water_share:
            notes.append("水军适江河")
    elif water_share:
        delta -= water_share * 0.08
        notes.append("水军离水受限")
    if terrain in {"山道", "关隘"}:
        delta -= (own.get("骑兵", 0) + own.get("突骑", 0)) / total * 0.10
    delta = max(-0.15, min(0.15, delta))
    return 1 + delta, notes


def eligible_for_role(rank: str, merit: int, role: str, composition: Dict[str, int]) -> tuple[bool, str]:
    level = RANK_LEVEL.get(str(rank), 0)
    if role not in ROLE_REQUIREMENTS:
        return False, "未知军府职务"
    if level < ROLE_REQUIREMENTS[role]:
        return False, f"{role}至少须{RANKS[ROLE_REQUIREMENTS[role] - 1]}"
    if merit < RANK_REQUIREMENTS.get(rank, 10**9):
        return False, "战功未达当前军衔门槛"
    specialist = any(kind in normalize_composition(composition) for kind in SPECIALIST_TYPES)
    if role == "主将" and specialist and level < 3:
        return False, "统带专门兵种的主将至少须中郎将"
    return True, ""


def morale_delta(*, supply_source: str = "", starvation_turns: int = 0, arrears: int = 0,
                 maintenance: int = 0, fatigue: int = 0, casualty_rate: float = 0.0,
                 won: bool | None = None, discipline: int = 50, has_deputy: bool = False,
                 has_adjutant: bool = False) -> tuple[int, list[str]]:
    """唯一的士气规则计算器；只根据已结算事实，不引入随机。"""
    delta, reasons = 0, []
    if supply_source == "granary":
        delta += 2; reasons.append("郡仓足供")
    elif supply_source == "carried":
        delta += 0; reasons.append("消耗携粮")
    if starvation_turns:
        # 延续既有断粮每月 -8 的硬规则；其他因素叠加但不暗改旧档平衡。
        loss = 8
        delta -= loss; reasons.append(f"断粮{starvation_turns}月")
    if maintenance and arrears >= maintenance * 2:
        loss = min(10, 2 + arrears // max(1, maintenance))
        delta -= loss; reasons.append("欠饷积压")
    if fatigue >= 70:
        delta -= min(8, 2 + (fatigue - 70) // 5); reasons.append("疲劳过甚")
    if won is not None:
        if won:
            gain = 4 if casualty_rate <= 0.08 else 2
            delta += gain; reasons.append("战胜")
        else:
            loss = min(16, 5 + round(casualty_rate * 35))
            delta -= loss; reasons.append("战败")
        if casualty_rate >= 0.15:
            extra = min(10, round(casualty_rate * 20))
            delta -= extra; reasons.append(f"战损{round(casualty_rate * 100)}%")
    if has_deputy and discipline >= 65:
        delta += 1; reasons.append("副将协同")
    if has_adjutant and discipline >= 70:
        delta += 1; reasons.append("军司马整肃")
    return max(-25, min(10, delta)), reasons
