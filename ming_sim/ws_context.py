"""可复现的月度活世界上下文。

本模块只生成规则可审计的环境、证据化奏议和情报记录；它不直接改变
兵力、领土、人物生死或条约状态。
"""
from __future__ import annotations

from typing import Any, Dict

from ming_sim.world_random import draw_int, draw_weighted
from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list, status_terminal as _status_terminal
from ming_sim.ws_utils import get_turn, get_year, get_period, to_json
from ming_sim.ws_common import seed_for as _seed_for, season as _season, iter_active_powers


def get_or_create_world_context(db, state: object) -> Dict[str, Any]:
    """按回合持久化种子和派生变量；同一存档重跑不会改变结果。

    全局天气、民情趋势和民情数值均通过 world_random 抽取，
    与区域事件共用同一 campaign_seed_v2 派生流，保证不同存档
    产生不同但可重放的全局环境。
    """
    turn = get_turn(state)
    row = db.conn.execute("SELECT * FROM world_simulation_contexts WHERE turn=?", (turn,)).fetchone()
    if row is not None:
        return {
            "turn": turn, "seed": str(row["seed"]), "season": str(row["season"]),
            "weather": _decode(row["weather_json"], {}), "regional_conditions": _decode(row["regional_conditions_json"], {}),
            "public_mood": _decode(row["public_mood_json"], {}), "power_budgets": _decode(row["power_budgets_json"], {}),
        }
    seed = _seed_for(state)  # 仅用于 world_simulation_contexts.seed 向后兼容字段，不再作为随机源
    season = _season(get_period(state))
    weather_pool = {
        "春": [("细雨", -2), ("阴晴", 0), ("东风", 1)],
        "夏": [("暑湿", -2), ("暴雨", -5), ("江风", 2)],
        "秋": [("清朗", 2), ("干燥", 1), ("秋雨", -2)],
        "冬": [("严寒", -3), ("朔风", -1), ("晴冷", 0)],
    }.get(season, [("阴晴", 0)])
    # 全局天气：通过 world_random.draw_weighted 抽取
    weather_choices = [
        {"key": kind, "weight": 1, "battle_delta": delta}
        for kind, delta in weather_pool
    ]
    weather_draw = draw_weighted(
        db, state=state, domain="world_context", subject_id="global",
        choices=weather_choices, draw_kind="weather",
    )
    weather_kind = str(weather_draw["key"]) if weather_draw else "阴晴"
    battle_delta = int(weather_draw["battle_delta"]) if weather_draw else 0
    weather = {
        "kind": weather_kind,
        "battle_probability_delta": battle_delta,
        "source": "campaign_seed_weather",
        "draw_refs": {"domain": "world_context", "subject_id": "global", "draw_kind": "weather"},
    }
    regional = {
        "江河": {"delta": 2 if weather_kind in {"江风", "东风"} else (-3 if weather_kind in {"暴雨", "严寒"} else 0)},
        "山道": {"delta": -3 if weather_kind in {"暴雨", "细雨"} else 0},
        "关隘": {"delta": 2 if weather_kind in {"严寒", "朔风"} else 0},
        "普通路": {"delta": 0},
    }
    # 民情趋势：通过 world_random.draw_weighted 抽取
    trend_choices = [{"key": t, "weight": 1} for t in ["安", "观望", "忧"]]
    trend_draw = draw_weighted(
        db, state=state, domain="world_context", subject_id="global",
        choices=trend_choices, draw_kind="public_mood_trend",
    )
    trend_value = str(trend_draw["key"]) if trend_draw else "观望"
    # 民情数值：通过 world_random.draw_int 抽取
    mood_delta = draw_int(
        db, state=state, domain="world_context", subject_id="global",
        low=-2, high=2, draw_kind="public_mood_delta",
    )
    public_mood = {
        "trend": trend_value,
        "delta": int(mood_delta),
        "source": "campaign_seed_public_mood",
        "draw_refs": {
            "trend": {"domain": "world_context", "subject_id": "global", "draw_kind": "public_mood_trend"},
            "delta": {"domain": "world_context", "subject_id": "global", "draw_kind": "public_mood_delta"},
        },
    }
    budgets = {}
    for power in iter_active_powers(db):
        if _status_terminal(str(power["status"])):
            budgets[str(power["id"])] = 0
        else:
            # 预算 0/1/2：活跃且凝聚≥75、补给≥70 → 2；其他活跃 → 1
            budgets[str(power["id"])] = (
                2 if (int(power["cohesion"] or 0) >= 75 and int(power["supply"] or 0) >= 70)
                else 1
            )
    db.conn.execute(
        """INSERT INTO world_simulation_contexts
        (turn, year, period, seed, season, weather_json, regional_conditions_json, public_mood_json, power_budgets_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (turn, get_year(state), get_period(state), seed, season,
         to_json(weather), to_json(regional),
         to_json(public_mood), to_json(budgets)),
    )
    db.conn.commit()
    return {"turn": turn, "seed": seed, "season": season, "weather": weather, "regional_conditions": regional, "public_mood": public_mood, "power_budgets": budgets}


def battle_environment(db, state: object, terrain: str, *, node_id: str = "") -> Dict[str, Any]:
    """读取已生成的月度环境；包含区域状态引用用于审计。"""
    turn = get_turn(state)
    row = db.conn.execute("SELECT * FROM world_simulation_contexts WHERE turn=?", (turn,)).fetchone()
    if row is None:
        return {
            "seed": "", "season": _season(get_period(state)),
            "weather": {"kind": "未定", "battle_probability_delta": 0, "source": "no_world_context"},
            "terrain_condition": {"delta": 0}, "probability_delta": 0,
            "campaign_seed_ref": "", "regional_state_refs": [],
            "attacker_origin": {}, "battlefield": {}, "route_conditions": [],
        }
    context = get_or_create_world_context(db, state)
    regional = context["regional_conditions"].get(str(terrain), {}) if isinstance(context["regional_conditions"], dict) else {}
    delta = int((context["weather"] or {}).get("battle_probability_delta") or 0) + int(regional.get("delta") or 0)

    # 读取战场的区域状态引用
    regional_state_refs = []
    battlefield = {}
    if node_id:
        rs = db.conn.execute(
            "SELECT * FROM regional_world_states WHERE region_id=? AND turn=?",
            (node_id, turn),
        ).fetchone()
        if rs:
            battlefield = {
                "region_id": node_id,
                "weather_kind": str(rs["weather_kind"]),
                "road_condition": int(rs["road_condition"]),
            }
            regional_state_refs.append(f"region:{node_id}:turn:{turn}")

    return {
        "seed": context["seed"],
        "season": context["season"],
        "weather": context["weather"],
        "terrain_condition": regional,
        "probability_delta": max(-8, min(8, delta)),
        "campaign_seed_ref": context["seed"],
        "regional_state_refs": regional_state_refs,
        "battlefield": battlefield,
    }
