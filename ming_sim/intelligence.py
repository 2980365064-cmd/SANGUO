"""人物情报可见性。

界面和 API 只能消费本模块产出的可见档案，避免把数据库中的动态人格原值
直接序列化给玩家。情报等级：0=传闻，1=探知，2=详报，3=洞悉。
"""

from __future__ import annotations

from typing import Dict, Union

from ming_sim.models import Character


VisibleValue = Union[int, str, Dict[str, int]]

ABILITY_FIELDS = (
    "martial",
    "leadership",
    "intelligence",
    "politics",
    "diplomacy",
    "charisma",
)
PERSONALITY_FIELDS = (
    "loyalty",
    "integrity",
    "ambition",
    "courage",
    "closeness_to_liu_bei",
)
INTEL_SOURCES = {"recon", "spy", "diplomacy"}


def _intel_key(character_name: str, viewer_power: str) -> str:
    return f"character_intel:{viewer_power}:{character_name}"


def get_character_intel_level(
    db,
    character_name: str,
    viewer_power: str = "liu_bei",
) -> int:
    raw = db.kv_get(_intel_key(character_name, viewer_power))
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    return max(0, min(3, value))


def raise_character_intel(
    db,
    character_name: str,
    source: str,
    amount: int = 1,
    viewer_power: str = "liu_bei",
) -> int:
    """由侦察、细作或外交接触提升人物情报，最高为 3。"""
    if source not in INTEL_SOURCES:
        raise ValueError(f"不支持的情报来源：{source}")
    current = get_character_intel_level(db, character_name, viewer_power)
    new_level = max(0, min(3, current + max(0, int(amount))))
    db.kv_set(_intel_key(character_name, viewer_power), str(new_level))
    return new_level


def _assessment(value: int) -> str:
    if value >= 90:
        return "卓绝"
    if value >= 75:
        return "出众"
    if value >= 60:
        return "良好"
    if value >= 45:
        return "中常"
    if value >= 30:
        return "偏弱"
    return "孱弱"


def _tendency(value: int) -> str:
    if value >= 85:
        return "极高"
    if value >= 65:
        return "偏高"
    if value >= 45:
        return "中等"
    if value >= 25:
        return "偏低"
    return "极低"


def _range(value: int) -> Dict[str, int]:
    """返回稳定的宽区间；不会伪装成精确值。"""
    if value < 40:
        lower, upper = 0, 39
    elif value < 60:
        lower, upper = 40, 59
    elif value < 75:
        lower, upper = 60, 74
    elif value < 90:
        lower, upper = 75, 89
    else:
        lower, upper = 90, 100
    return {"min": lower, "max": upper}


def _values(
    character: Character,
    fields: tuple[str, ...],
    visibility: str,
) -> Dict[str, VisibleValue]:
    converters = {
        "exact": int,
        "assessment": _assessment,
        "tendency": _tendency,
        "range": _range,
    }
    converter = converters[visibility]
    return {field: converter(int(getattr(character, field))) for field in fields}


def visible_character_profile(
    character: Character,
    intel_level: int,
    viewer_power: str = "liu_bei",
) -> Dict[str, object]:
    """把人物规则数据裁成玩家当前有权看到的档案。

    己方六维能力始终公开。动态人格仅在详报、洞悉或与刘备关系足够密切时
    公开精确值；敌方能力则随侦察情报逐级从评价、区间提升为精确值。
    """
    level = max(0, min(3, int(intel_level)))
    is_own = character.power_id == viewer_power
    close = int(character.closeness_to_liu_bei) >= 80

    if is_own:
        ability_visibility = "exact"
    elif level == 0:
        ability_visibility = "assessment"
    elif level == 1:
        ability_visibility = "range"
    else:
        ability_visibility = "exact"

    if close or level >= 3 or (is_own and level >= 2):
        personality_visibility = "exact"
    elif level >= 1:
        personality_visibility = "range"
    else:
        personality_visibility = "tendency"

    return {
        "intel_level": level,
        "abilities": {
            "visibility": ability_visibility,
            "values": _values(character, ABILITY_FIELDS, ability_visibility),
        },
        "personality": {
            "visibility": personality_visibility,
            "values": _values(character, PERSONALITY_FIELDS, personality_visibility),
        },
    }
