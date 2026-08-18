"""自由战术边界校验测试 - 验证 AI 自由战术裁决的安全边界。

测试覆盖：
1. delta 边界裁剪（[-5, +15]）
2. 特性匹配与无特性匹配的 delta 上限差异
3. actor 必须是参战统帅
4. feasibility=impossible 退回正面交锋
5. 禁止文本拦截（reasoning 中也不能写"阵亡"等）
6. 事实一致性检查（reasoning 声称的条件必须在盘面中存在）
7. 基准战术快速路径（向后兼容）
8. 自由战术完整 resolve_battle 流程
9. 确定性随机（同种子同结果）
"""

from types import SimpleNamespace

import pytest

from ming_sim.battle import (
    build_battle_adjudication_pack,
    resolve_battle,
    _validate_free_tactic,
)
from ming_sim.content import GameContent
from ming_sim.db import GameDB


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def _state(turn=1):
    return SimpleNamespace(turn=turn, year=208, period=turn)


def _build_pack(board, attacker_ids, defender_ids, node_id):
    return build_battle_adjudication_pack(
        board,
        _state(1),
        {
            "attacker_ids": attacker_ids,
            "defender_ids": defender_ids,
            "node_id": node_id,
        },
    )


# ============================================================================
# delta 边界检查
# ============================================================================


def test_validate_free_tactic_delta_above_max_is_clipped_with_trait(board):
    """有特性匹配时，delta 上限为 +15，超出部分被裁剪。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "连环火计",
        "actor": "关羽",
        "delta": 20,  # 超出 +15
        "feasibility": "high",
        "reasoning": ["关羽水战特性 + 连环船火攻"],
        "narrative": "关羽借水势放火，曹军连环船焚尽。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["delta"] == 15  # 裁剪到 +15


def test_validate_free_tactic_delta_above_max_is_clipped_without_trait(board):
    """无特性匹配时，delta 上限为 +10，超出部分被裁剪。"""
    # 使用刘备（没有 trait_modifiers）
    pack = _build_pack(board, ["liubei_main"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "奇袭粮道",
        "actor": "刘备",
        "delta": 18,  # 超出 +10（无特性匹配）
        "feasibility": "medium",
        "reasoning": ["派偏师绕后烧粮"],
        "narrative": "刘备分兵夜袭曹军粮仓。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["delta"] == 10  # 裁剪到 +10


def test_validate_free_tactic_delta_below_min_is_clipped(board):
    """delta 下限为 -5，低于部分被裁剪。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "冒险冲锋",
        "actor": "关羽",
        "delta": -10,  # 低于 -5
        "feasibility": "low",
        "reasoning": ["兵力劣势，胜算渺茫"],
        "narrative": "关羽强行冲锋，损失惨重。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["delta"] == -5  # 裁剪到 -5


def test_validate_free_tactic_delta_within_bounds_is_accepted(board):
    """delta 在边界内时直接接受。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    for delta in [-5, -3, 0, 5, 10, 15]:
        proposal = {
            "tactic_name": f"战术_{delta}",
            "actor": "关羽",
            "delta": delta,
            "feasibility": "medium",
            "reasoning": ["合理战术"],
            "narrative": "战术执行。",
        }
        result = _validate_free_tactic(pack, proposal)
        assert result["delta"] == delta


# ============================================================================
# actor 校验
# ============================================================================


def test_validate_free_tactic_actor_not_in_battle_is_rejected(board):
    """actor 不是参战统帅时被拒绝。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "刘备亲征",
        "actor": "刘备",  # 刘备不在参战军队中
        "delta": 5,
        "feasibility": "medium",
        "reasoning": ["刘备亲自上阵"],
        "narrative": "刘备率军冲锋。",
    }
    with pytest.raises(ValueError, match="执行者必须是已参战的攻方统帅"):
        _validate_free_tactic(pack, proposal)


def test_validate_free_tactic_actor_in_battle_is_accepted(board):
    """actor 是参战统帅时通过。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "关羽突击",
        "actor": "关羽",  # 关羽是 guanyu_fleet 的统帅
        "delta": 5,
        "feasibility": "medium",
        "reasoning": ["关羽率水军突击"],
        "narrative": "关羽冲锋。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["actor"] == "关羽"


# ============================================================================
# feasibility 校验
# ============================================================================


def test_validate_free_tactic_impossible_falls_back_to_frontal(board):
    """feasibility=impossible 时退回正面交锋，delta=0。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "天降陨石",
        "actor": "关羽",
        "delta": 15,
        "feasibility": "impossible",
        "reasoning": ["召唤陨石砸灭曹军"],
        "narrative": "陨石如雨，曹军覆灭。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["tactic"] == "正面交锋"
    assert result["delta"] == 0
    assert "不可行" in result["narrative"]


def test_validate_free_tactic_high_feasibility_accepted(board):
    """feasibility=high 时正常接受。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "水战火攻",
        "actor": "关羽",
        "delta": 12,
        "feasibility": "high",
        "reasoning": ["关羽水战特性 + 风向有利 + 曹军连环船"],
        "narrative": "关羽借东风放火，曹军大败。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["feasibility"] == "high"
    assert result["delta"] == 12


# ============================================================================
# 禁止文本检查
# ============================================================================


def test_validate_free_tactic_forbidden_text_in_reasoning_is_rejected(board):
    """reasoning 中包含禁止文本（如"阵亡"）时被拒绝。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "斩杀敌将",
        "actor": "关羽",
        "delta": 10,
        "feasibility": "high",
        "reasoning": ["关羽使曹军主将阵亡"],  # 包含"阵亡"
        "narrative": "关羽冲锋斩将。",
    }
    with pytest.raises(ValueError, match="不得写未获规则允许的人物死亡"):
        _validate_free_tactic(pack, proposal)


def test_validate_free_tactic_forbidden_text_in_narrative_is_rejected(board):
    """narrative 中包含禁止文本时被拒绝。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "割让荆州",
        "actor": "关羽",
        "delta": 5,
        "feasibility": "medium",
        "reasoning": ["战后谈判"],
        "narrative": "曹军割让荆州给刘备。",  # "割让" 是禁止文本
    }
    with pytest.raises(ValueError, match="不得写未获规则允许的领土变化"):
        _validate_free_tactic(pack, proposal)


# ============================================================================
# 事实一致性检查
# ============================================================================


def test_validate_free_tactic_claims_epidemic_but_low_pressure_is_rejected(board):
    """AI 声称"瘟疫"但 epidemic_pressure 低时被拒绝。"""
    # 确保襄阳的 epidemic_pressure 很低
    board.conn.execute(
        "UPDATE regional_world_states SET epidemic_pressure=10 WHERE region_id='xiangyang'"
    )
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "趁瘟疫突袭",
        "actor": "关羽",
        "delta": 10,
        "feasibility": "high",
        "reasoning": ["曹军正在闹瘟疫"],  # 只声称"瘟疫"
        "narrative": "关羽趁曹军瘟疫突袭。",
    }
    with pytest.raises(ValueError, match="声称.*瘟疫.*但裁决包事实不支持"):
        _validate_free_tactic(pack, proposal)


def test_validate_free_tactic_claims_epidemic_and_high_pressure_accepted(board):
    """AI 声称"瘟疫"且 epidemic_pressure 高时通过。"""
    # 插入一条记录到 regional_world_states（表默认为空，需要满足 NOT NULL 约束）
    # city:xiangyang 属于 jiangling 郡
    board.conn.execute(
        """INSERT INTO regional_world_states
           (region_id, turn, season, weather_kind, weather_severity, road_condition,
            grain_transport_pressure, harvest_outlook, epidemic_pressure, disaster_risk, public_mood_delta)
           VALUES ('jiangling', 1, '春', '酷暑', -15, 0, 0, 0, 70, 0, 0)"""
    )
    board.conn.commit()
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "趁瘟疫突袭",
        "actor": "关羽",
        "delta": 10,
        "feasibility": "high",
        "reasoning": ["曹军正在闹瘟疫"],  # 只声称"瘟疫"
        "narrative": "关羽趁曹军瘟疫突袭。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["delta"] == 10


def test_validate_free_tactic_claims_supply_shortage_and_low_supply_accepted(board):
    """AI 声称"粮草不济"且敌方 supply 低时通过。"""
    # 设置曹军补给很低（supply_combat_multiplier < 0.5 表示粮草不足）
    board.conn.execute(
        "UPDATE armies SET supply_combat_multiplier=0.3 WHERE id='cao_vanguard'"
    )
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "断粮突袭",
        "actor": "关羽",
        "delta": 8,
        "feasibility": "high",
        "reasoning": ["曹军粮草不济"],  # 只声称"粮草不济"
        "narrative": "关羽趁曹军断粮突袭。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["delta"] == 8


def test_validate_free_tactic_claims_good_weather_and_good_weather_accepted(board):
    """AI 声称"天晴"且天气 delta > 0 时通过。"""
    # 天气 delta 在 environment 中，需要构造正确的环境
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    # 检查 environment 的 probability_delta
    env_delta = pack["facts"]["environment"]["probability_delta"]
    if env_delta > 0:
        proposal = {
            "tactic_name": "趁晴天突袭",
            "actor": "关羽",
            "delta": 5,
            "feasibility": "medium",
            "reasoning": ["今日天晴，适合出战"],
            "narrative": "关羽趁晴天出战。",
        }
        result = _validate_free_tactic(pack, proposal)
        assert result["delta"] == 5


# ============================================================================
# 基准战术快速路径（向后兼容）
# ============================================================================


def test_baseline_tactic_still_works(board):
    """基准战术（如"正面交锋"）仍走原有逻辑，不受自由战术影响。"""
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "baseline_test_seed" + "0" * 43)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {"tactic": "正面交锋", "actor": "关羽", "narrative": "正面冲击。"},
    )
    assert result["ai_tactic"]["tactic"] == "正面交锋"
    assert result["ai_tactic"]["delta"] == 0


def test_baseline_tactic_with_trait_still_works(board):
    """带特性的基准战术（如"正面交锋"）仍正常工作。"""
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "baseline_trait_test" + "0" * 42)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {"tactic": "正面交锋", "actor": "关羽", "delta": 8, "narrative": "水军突击。"},
    )
    assert result["ai_tactic"]["tactic"] == "正面交锋"
    assert result["ai_tactic"]["delta"] == 8


# ============================================================================
# 自由战术完整流程
# ============================================================================


def test_resolve_battle_with_free_tactic(board):
    """自由战术走完整 resolve_battle 流程。"""
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "free_tactic_test_seed" + "0" * 41)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {
            "tactic_name": "夜袭粮仓",
            "actor": "关羽",
            "delta": 8,
            "feasibility": "medium",
            "reasoning": ["趁夜暗突袭曹军粮仓"],
            "narrative": "关羽率精锐夜袭曹军粮仓，火烧连营。",
        },
    )
    assert result["ai_tactic"]["tactic"] == "夜袭粮仓"
    assert result["ai_tactic"]["delta"] == 8
    assert result["ai_tactic"]["feasibility"] == "medium"
    assert "夜袭" in result["ai_tactic"]["narrative"]
    assert result["winner"] in ["attacker", "defender"]
    assert result["random_roll"] >= 1


def test_resolve_battle_with_impossible_free_tactic(board):
    """不可行的自由战术退回正面交锋后走正常流程。"""
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    board.kv_set(CAMPAIGN_SEED_KEY, "impossible_test_seed" + "0" * 42)
    result = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {
            "tactic_name": "天降神兵",
            "actor": "关羽",
            "delta": 15,
            "feasibility": "impossible",
            "reasoning": ["召唤天兵"],
            "narrative": "天兵降临。",
        },
    )
    # 应该退回正面交锋
    assert result["ai_tactic"]["tactic"] == "正面交锋"
    assert result["ai_tactic"]["delta"] == 0


# ============================================================================
# 确定性随机（同种子同结果）
# ============================================================================


def test_free_tactic_deterministic_with_same_seed(board):
    """同种子、同输入，自由战术的掷骰结果相同。"""
    from ming_sim.world_random import CAMPAIGN_SEED_KEY
    seed = "deterministic_test" + "0" * 43

    # 第一次
    board.kv_set(CAMPAIGN_SEED_KEY, seed)
    result1 = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {
            "tactic_name": "正面交锋",
            "actor": "关羽",
            "delta": 8,
            "feasibility": "high",
            "reasoning": ["水战有利"],
            "narrative": "关羽水军突击。",
        },
    )

    # 重置数据库状态
    board.conn.execute("DELETE FROM battles")
    board.conn.execute("DELETE FROM character_attribute_logs")
    board.conn.execute("UPDATE armies SET manpower=6500, morale=76, fatigue=0 WHERE id='guanyu_fleet'")
    board.conn.execute("UPDATE armies SET manpower=8000, morale=70, fatigue=0 WHERE id='cao_vanguard'")
    board.conn.commit()

    # 第二次
    board.kv_set(CAMPAIGN_SEED_KEY, seed)
    result2 = resolve_battle(
        board,
        _state(1),
        {
            "attacker_ids": ["guanyu_fleet"],
            "defender_ids": ["cao_vanguard"],
            "node_id": "city:xiangyang",
        },
        {
            "tactic_name": "正面交锋",
            "actor": "关羽",
            "delta": 8,
            "feasibility": "high",
            "reasoning": ["水战有利"],
            "narrative": "关羽水军突击。",
        },
    )

    assert result1["random_roll"] == result2["random_roll"]
    assert result1["winner"] == result2["winner"]


# ============================================================================
# 回归测试：既有禁止行为仍被拦截
# ============================================================================


def test_free_tactic_cannot_invent_reinforcements(board):
    """自由战术不能凭空生成援军。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "援军夹击",
        "actor": "关羽",
        "delta": 10,
        "feasibility": "high",
        "reasoning": ["天降援军夹击曹军"],  # "援军" 是禁止文本
        "narrative": "援军赶到，夹击曹军。",
    }
    with pytest.raises(ValueError, match="不得凭空生成援军"):
        _validate_free_tactic(pack, proposal)


def test_free_tactic_cannot_revive_characters(board):
    """自由战术不能复活人物。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "复活关羽",
        "actor": "关羽",
        "delta": 10,
        "feasibility": "high",
        "reasoning": ["复活已故将领"],  # "复活" 是禁止文本
        "narrative": "关羽复活。",
    }
    with pytest.raises(ValueError, match="不得复活人物"):
        _validate_free_tactic(pack, proposal)


# ============================================================================
# 边界情况
# ============================================================================


def test_validate_free_tactic_missing_fields_use_defaults(board):
    """缺少可选字段时使用默认值。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "tactic_name": "简单战术",
        "actor": "关羽",
        # 没有 delta、feasibility、reasoning、narrative
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["delta"] == 0  # 默认
    assert result["feasibility"] == "medium"  # 默认
    assert result["narrative"] == ""  # 默认


def test_validate_free_tactic_empty_tactic_name_uses_custom(board):
    """战术名为空时使用 "custom"。"""
    pack = _build_pack(board, ["guanyu_fleet"], ["cao_vanguard"], "city:xiangyang")
    proposal = {
        "actor": "关羽",
        "delta": 5,
        "feasibility": "medium",
        "reasoning": ["合理战术"],
        "narrative": "战术执行。",
    }
    result = _validate_free_tactic(pack, proposal)
    assert result["tactic"] == "custom"
