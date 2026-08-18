"""区域世界状态与区域事件生成。

从 world_simulation.py 提取。负责：
- 每回合为每个地区生成天气、道路、粮运、收成、疫病、灾害风险、民心变动
- 生成区域事件（普通 + 重大）
- 计算并应用局部效果
"""
from __future__ import annotations

import json
from typing import Any, Dict

from ming_sim.world_random import draw_int, draw_weighted
from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list, clamp as _clamp_base
from ming_sim.ws_utils import get_turn, get_period, to_json
from ming_sim.ws_common import seed_for as _seed_for, season as _season


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_STATE_CLAMP = (-100, 100)

# 道路衰减速率：每月向 0 恢复的量（无新负面事件时）
_ROAD_RECOVERY_PER_TURN = 8
# 其他维度的衰减速率
_GENERIC_DECAY_PER_TURN = 5


def _clamp(value: int, lo: int = _STATE_CLAMP[0], hi: int = _STATE_CLAMP[1]) -> int:
    """数值截断。默认边界由 _STATE_CLAMP 控制。已委托至 ws_utils.clamp。"""
    return _clamp_base(value, lo, hi)


ALLOWED_INCIDENT_TYPES = frozenset({
    "flood", "drought", "epidemic", "landslide",
    "harvest_bumper", "grain_convoy_loss", "refugee_influx",
    "bandit_surge", "market_opportunity", "gentry_petition",
})

# 局部效果单次上限（普通事件）
_ORDINARY_EFFECT_CAPS = {
    "public_support": 5,
    "unrest": 7,
    "military_pressure": 7,
    "road_condition": 15,
    "grain_transport_pressure": 12,
    "harvest_outlook": 10,
    "epidemic_pressure": 12,
    "hazard_combat_multiplier_floor": 0.90,
    "supply_combat_multiplier_floor": 0.90,
}

# 局部效果单次上限（重大事件）
_DRAMATIC_EFFECT_CAPS = {
    "public_support": 12,
    "unrest": 15,
    "military_pressure": 15,
    "road_condition": 35,
    "grain_transport_pressure": 30,
    "harvest_outlook": 25,
    "epidemic_pressure": 30,
    "hazard_combat_multiplier_floor": 0.80,
    "supply_combat_multiplier_floor": 0.80,
}


# ---------------------------------------------------------------------------
# 天气
# ---------------------------------------------------------------------------

def _weather_for_region(
    db, state, *, region_kind: str, season: str, has_disaster: bool,
    domain: str, subject_id: str,
) -> tuple[str, int, list[str]]:
    """为一个地区抽取天气。返回 (weather_kind, severity, draw_refs)。

    severity 范围 [-100, 100]，正值表示天气恶劣。
    """
    # 按季节+地区类型确定天气候选池
    pool: list[dict[str, object]]
    if season == "春":
        base = [
            {"key": "细雨", "severity_base": -10, "weight": 30},
            {"key": "阴晴", "severity_base": 0, "weight": 40},
            {"key": "东风", "severity_base": 5, "weight": 20},
            {"key": "春雨", "severity_base": -15, "weight": 10},
        ]
    elif season == "夏":
        base = [
            {"key": "暑湿", "severity_base": -10, "weight": 25},
            {"key": "暴雨", "severity_base": -40, "weight": 20},
            {"key": "江风", "severity_base": 10, "weight": 20},
            {"key": "酷暑", "severity_base": -20, "weight": 15},
            {"key": "洪涝", "severity_base": -60, "weight": 5 if region_kind == "江河" else 15},
        ]
    elif season == "秋":
        base = [
            {"key": "清朗", "severity_base": 10, "weight": 35},
            {"key": "干燥", "severity_base": -5, "weight": 25},
            {"key": "秋雨", "severity_base": -15, "weight": 20},
            {"key": "丰收", "severity_base": 15, "weight": 20},
        ]
    elif season == "冬":
        base = [
            {"key": "严寒", "severity_base": -30, "weight": 25},
            {"key": "朔风", "severity_base": -15, "weight": 25},
            {"key": "晴冷", "severity_base": -5, "weight": 25},
            {"key": "大雪封路", "severity_base": -50, "weight": 10 if region_kind in {"山道", "关隘"} else 15},
        ]
    else:
        base = [{"key": "阴晴", "severity_base": 0, "weight": 100}]

    # 灾害加成：已有灾害时恶劣天气概率增大
    if has_disaster:
        for item in base:
            if item["severity_base"] < -20:
                item["weight"] = float(item["weight"]) * 2.0

    chosen = draw_weighted(
        db, state=state, domain=domain, subject_id=subject_id,
        choices=base, draw_kind="weather",
    )
    if chosen is None:
        return "阴晴", 0, []

    weather_key = str(chosen["key"])
    severity_base = int(chosen["severity_base"])

    # 地区类型修正 severity
    severity_delta = 0
    if region_kind == "江河" and weather_key in {"暴雨", "洪涝", "江风"}:
        severity_delta -= 10
    elif region_kind == "山道" and weather_key in {"暴雨", "大雪封路", "细雨"}:
        severity_delta -= 10
    elif region_kind == "关隘" and weather_key in {"严寒", "大雪封路", "朔风"}:
        severity_delta -= 10

    severity = _clamp(severity_base + severity_delta + draw_int(
        db, state=state, domain=domain, subject_id=subject_id,
        low=-10, high=10, draw_kind="weather_jitter",
    ))

    draw_refs = [
        f"world_random:turn:{state.turn}:domain:{domain}:subject:{subject_id}:kind:weather",
        f"world_random:turn:{state.turn}:domain:{domain}:subject:{subject_id}:kind:weather_jitter",
    ]
    return weather_key, severity, draw_refs


# ---------------------------------------------------------------------------
# 区域世界状态
# ---------------------------------------------------------------------------

def ensure_regional_world_states(db, state) -> list[dict]:
    """为每个地区生成本回合状态。幂等：同 turn 重复调用返回已落库结果。"""
    turn = get_turn(state)
    period = get_period(state)
    season = _season(period)

    # 幂等守卫
    existing = db.conn.execute(
        "SELECT COUNT(*) FROM regional_world_states WHERE turn=?", (turn,)
    ).fetchone()[0]
    if existing > 0:
        return _load_regional_states(db, turn)

    prev_turn = turn - 1
    results: list[dict] = []

    regions = db.conn.execute(
        "SELECT id, kind, population, public_support, unrest, military_pressure, "
        "natural_disaster, human_disaster, controlled_by, fiscal "
        "FROM regions ORDER BY id"
    ).fetchall()

    for region in regions:
        region_id = str(region["id"])
        region_kind = str(region["kind"])
        has_disaster = bool(
            str(region["natural_disaster"] or "").strip()
            or str(region["human_disaster"] or "").strip()
        )
        population = int(region["population"] or 0)
        public_support = int(region["public_support"] or 0)
        unrest = int(region["unrest"] or 0)
        military_pressure = int(region["military_pressure"] or 0)

        # 读上回合状态
        prev = db.conn.execute(
            "SELECT * FROM regional_world_states WHERE region_id=? AND turn=?",
            (region_id, prev_turn),
        ).fetchone()

        if prev is not None:
            prev_road = int(prev["road_condition"])
            prev_grain = int(prev["grain_transport_pressure"])
            prev_harvest = int(prev["harvest_outlook"])
            prev_epidemic = int(prev["epidemic_pressure"])
            prev_disaster = int(prev["disaster_risk"])
            prev_mood = int(prev["public_mood_delta"])
        else:
            prev_road = prev_grain = prev_harvest = 0
            prev_epidemic = prev_disaster = prev_mood = 0

        # 天气抽取
        weather_kind, weather_severity, draw_refs = _weather_for_region(
            db, state, region_kind=region_kind, season=season,
            has_disaster=has_disaster,
            domain="regional_state", subject_id=region_id,
        )

        # 道路：天气恶劣则下降，正常天气则恢复
        road_delta = 0
        if weather_severity < -30:
            road_delta = weather_severity // 3  # 暴雨 → road -13 左右
        elif weather_severity < -10:
            road_delta = weather_severity // 5
        else:
            road_delta = _ROAD_RECOVERY_PER_TURN
        road_condition = _clamp(prev_road + road_delta)

        # 粮运压力：受天气、人口、军压影响
        grain_delta = 0
        if weather_severity < -20:
            grain_delta += abs(weather_severity) // 5
        if military_pressure > 50:
            grain_delta += 5
        if population > 80:
            grain_delta += 3
        # 自然恢复
        if grain_delta == 0:
            grain_delta = -_GENERIC_DECAY_PER_TURN
        grain_transport = _clamp(prev_grain + grain_delta)

        # 收成预期：受季节、天气、灾害影响
        harvest_delta = 0
        if weather_kind in {"丰收", "清朗"}:
            harvest_delta += 10
        elif weather_kind in {"洪涝", "暴雨", "旱灾"}:
            harvest_delta -= 20
        elif weather_kind in {"酷暑", "暑湿"}:
            harvest_delta -= 5
        if has_disaster:
            harvest_delta -= 15
        if harvest_delta == 0:
            harvest_delta = -_GENERIC_DECAY_PER_TURN // 2
        harvest_outlook = _clamp(prev_harvest + harvest_delta)

        # 疫病压力：人口高+天气恶劣+已有灾害时升高
        epidemic_delta = 0
        if weather_kind in {"暑湿", "洪涝"}:
            epidemic_delta += 10
        if has_disaster:
            epidemic_delta += 15
        if population > 70 and weather_severity < -20:
            epidemic_delta += 5
        if epidemic_delta == 0:
            epidemic_delta = -_GENERIC_DECAY_PER_TURN
        epidemic_pressure = _clamp(max(0, prev_epidemic + epidemic_delta))

        # 灾害风险
        disaster_delta = 0
        if has_disaster:
            disaster_delta += 10
        if weather_severity < -40:
            disaster_delta += 15
        if disaster_delta == 0:
            disaster_delta = -_GENERIC_DECAY_PER_TURN
        disaster_risk = _clamp(max(0, prev_disaster + disaster_delta))

        # 民心变动
        mood_delta = 0
        if public_support >= 65 and road_condition > 0:
            mood_delta += 5
        if unrest >= 55:
            mood_delta -= 10
        if harvest_outlook > 30:
            mood_delta += 5
        elif harvest_outlook < -30:
            mood_delta -= 10
        if epidemic_pressure > 40:
            mood_delta -= 5
        public_mood = _clamp(prev_mood + mood_delta)

        # 审计因子
        audit_factors = {
            "weather_kind": weather_kind,
            "weather_severity": weather_severity,
            "region_kind": region_kind,
            "has_disaster": has_disaster,
            "population": population,
            "public_support": public_support,
            "unrest": unrest,
            "military_pressure": military_pressure,
            "prev_road": prev_road,
            "road_delta": road_delta,
            "prev_grain": prev_grain,
            "grain_delta": grain_delta,
            "prev_harvest": prev_harvest,
            "harvest_delta": harvest_delta,
            "prev_epidemic": prev_epidemic,
            "epidemic_delta": epidemic_delta,
            "prev_disaster": prev_disaster,
            "disaster_delta": disaster_delta,
            "prev_mood": prev_mood,
            "mood_delta": mood_delta,
        }

        db.conn.execute(
            """INSERT INTO regional_world_states
            (region_id, turn, season, weather_kind, weather_severity,
             road_condition, grain_transport_pressure, harvest_outlook,
             epidemic_pressure, disaster_risk, public_mood_delta,
             state_json, source_draw_refs_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                region_id, turn, season, weather_kind, weather_severity,
                road_condition, grain_transport, harvest_outlook,
                epidemic_pressure, disaster_risk, public_mood,
                to_json(audit_factors),
                to_json(draw_refs),
            ),
        )

        results.append({
            "region_id": region_id, "turn": turn, "season": season,
            "weather_kind": weather_kind, "weather_severity": weather_severity,
            "road_condition": road_condition,
            "grain_transport_pressure": grain_transport,
            "harvest_outlook": harvest_outlook,
            "epidemic_pressure": epidemic_pressure,
            "disaster_risk": disaster_risk,
            "public_mood_delta": public_mood,
        })

    db.conn.commit()
    return results


def _load_regional_states(db, turn: int) -> list[dict]:
    rows = db.conn.execute(
        "SELECT * FROM regional_world_states WHERE turn=? ORDER BY region_id",
        (turn,),
    ).fetchall()
    return [
        {
            "region_id": str(r["region_id"]), "turn": int(r["turn"]),
            "season": str(r["season"]),
            "weather_kind": str(r["weather_kind"]),
            "weather_severity": int(r["weather_severity"]),
            "road_condition": int(r["road_condition"]),
            "grain_transport_pressure": int(r["grain_transport_pressure"]),
            "harvest_outlook": int(r["harvest_outlook"]),
            "epidemic_pressure": int(r["epidemic_pressure"]),
            "disaster_risk": int(r["disaster_risk"]),
            "public_mood_delta": int(r["public_mood_delta"]),
        }
        for r in rows
    ]


def region_world_state(db, *, turn: int, region_id: str) -> dict:
    """读取某地区某回合的状态；不存在则返回中性基线。"""
    row = db.conn.execute(
        "SELECT * FROM regional_world_states WHERE region_id=? AND turn=?",
        (region_id, turn),
    ).fetchone()
    if row is not None:
        return {
            "region_id": str(row["region_id"]), "turn": int(row["turn"]),
            "season": str(row["season"]),
            "weather_kind": str(row["weather_kind"]),
            "weather_severity": int(row["weather_severity"]),
            "road_condition": int(row["road_condition"]),
            "grain_transport_pressure": int(row["grain_transport_pressure"]),
            "harvest_outlook": int(row["harvest_outlook"]),
            "epidemic_pressure": int(row["epidemic_pressure"]),
            "disaster_risk": int(row["disaster_risk"]),
            "public_mood_delta": int(row["public_mood_delta"]),
        }
    # 中性基线
    return {
        "region_id": region_id, "turn": turn, "season": "",
        "weather_kind": "未定", "weather_severity": 0,
        "road_condition": 0, "grain_transport_pressure": 0,
        "harvest_outlook": 0, "epidemic_pressure": 0,
        "disaster_risk": 0, "public_mood_delta": 0,
    }


# ---------------------------------------------------------------------------
# 区域事件
# ---------------------------------------------------------------------------

def _incident_title_and_summary(incident_type: str, region_name: str, tier: str) -> tuple[str, str]:
    """生成事件标题和摘要。"""
    templates = {
        "flood": ("洪水", "{region}暴雨成灾，河水漫溢，道路受损。"),
        "drought": ("旱灾", "{region}久旱无雨，田地龟裂，粮价恐涨。"),
        "epidemic": ("瘟疫", "{region}疫气蔓延，民众多有染病。"),
        "landslide": ("山崩", "{region}山道崩裂，岩石阻路。"),
        "harvest_bumper": ("丰收", "{region}风调雨顺，秋收丰盛。"),
        "grain_convoy_loss": ("粮车损失", "{region}粮车途中折损，补给延迟。"),
        "refugee_influx": ("流民涌入", "{region}四方流民聚集，安置压力大。"),
        "bandit_surge": ("盗匪蜂起", "{region}盗匪趁乱蜂起，乡里不安。"),
        "market_opportunity": ("商机", "{region}商路畅通，市贾活跃。"),
        "gentry_petition": ("士族请愿", "{region}士族联名上书，有所诉求。"),
    }
    title_cn, summary_tmpl = templates.get(incident_type, ("异事", "{region}发生异事。"))
    title = f"{region_name}{title_cn}"
    summary = summary_tmpl.format(region=region_name)
    if tier == "dramatic":
        summary = f"【重大】{summary}"
    return title, summary


def _build_ordinary_candidates(states: list[dict], db) -> list[dict[str, object]]:
    """从区域状态构建普通事件候选。每项含 incident_type, region_id, weight。"""
    candidates: list[dict[str, object]] = []

    for s in states:
        rid = s["region_id"]
        # 读盘面数据
        region = db.conn.execute(
            "SELECT name, public_support, unrest, military_pressure, population "
            "FROM regions WHERE id=?",
            (rid,),
        ).fetchone()
        if region is None:
            continue
        rname = str(region["name"])
        public_support = int(region["public_support"] or 0)
        unrest = int(region["unrest"] or 0)
        military_pressure = int(region["military_pressure"] or 0)
        population = int(region["population"] or 0)

        road = s["road_condition"]
        harvest = s["harvest_outlook"]
        epidemic = s["epidemic_pressure"]

        # road_condition <= -35 → landslide / grain_convoy_loss
        if road <= -35:
            candidates.append({
                "incident_type": "landslide", "region_id": rid, "region_name": rname,
                "weight": 30 + abs(road) // 2,
            })
            candidates.append({
                "incident_type": "grain_convoy_loss", "region_id": rid, "region_name": rname,
                "weight": 20 + abs(road) // 3,
            })

        # harvest_outlook <= -40 → drought
        if harvest <= -40:
            candidates.append({
                "incident_type": "drought", "region_id": rid, "region_name": rname,
                "weight": 25 + abs(harvest) // 2,
            })

        # flood：天气为暴雨/洪涝 + road 差
        if s["weather_kind"] in {"暴雨", "洪涝"} and road <= -20:
            candidates.append({
                "incident_type": "flood", "region_id": rid, "region_name": rname,
                "weight": 25 + abs(road) // 2,
            })

        # epidemic_pressure >= 45 且人口高 → epidemic
        if epidemic >= 45 and population > 50:
            candidates.append({
                "incident_type": "epidemic", "region_id": rid, "region_name": rname,
                "weight": 20 + epidemic // 2,
            })

        # unrest >= 55 → bandit_surge / refugee_influx
        if unrest >= 55:
            candidates.append({
                "incident_type": "bandit_surge", "region_id": rid, "region_name": rname,
                "weight": 20 + unrest // 3,
            })
            candidates.append({
                "incident_type": "refugee_influx", "region_id": rid, "region_name": rname,
                "weight": 15 + unrest // 4,
            })

        # harvest_outlook >= 55 → harvest_bumper
        if harvest >= 55:
            candidates.append({
                "incident_type": "harvest_bumper", "region_id": rid, "region_name": rname,
                "weight": 25,
            })

        # public_support >= 65 且道路畅通 → market_opportunity
        if public_support >= 65 and road >= 10:
            candidates.append({
                "incident_type": "market_opportunity", "region_id": rid, "region_name": rname,
                "weight": 20,
            })

        # public_support >= 50 → gentry_petition（低门槛）
        if public_support >= 50:
            candidates.append({
                "incident_type": "gentry_petition", "region_id": rid, "region_name": rname,
                "weight": 10,
            })

    return candidates


def _compute_local_effects(
    incident_type: str, *, tier: str, weather_severity: int,
    road_condition: int, harvest_outlook: int, epidemic_pressure: int,
    unrest: int,
) -> list[dict[str, object]]:
    """计算局部效果，严格受 caps 限制。"""
    caps = _DRAMATIC_EFFECT_CAPS if tier == "dramatic" else _ORDINARY_EFFECT_CAPS
    effects: list[dict[str, object]] = []

    def _bounded(field: str, value: int) -> int:
        cap = caps.get(field, 10)
        return max(-cap, min(cap, int(value)))

    if incident_type == "flood":
        effects.append({"field": "road_condition", "delta": _bounded("road_condition", weather_severity // 2)})
        effects.append({"field": "grain_transport_pressure", "delta": _bounded("grain_transport_pressure", abs(weather_severity) // 3)})
        effects.append({"field": "public_support", "delta": _bounded("public_support", -3)})
    elif incident_type == "drought":
        effects.append({"field": "harvest_outlook", "delta": _bounded("harvest_outlook", -abs(weather_severity) // 2)})
        effects.append({"field": "public_support", "delta": _bounded("public_support", -2)})
    elif incident_type == "epidemic":
        effects.append({"field": "epidemic_pressure", "delta": _bounded("epidemic_pressure", 15)})
        effects.append({"field": "public_support", "delta": _bounded("public_support", -5)})
        effects.append({"field": "unrest", "delta": _bounded("unrest", 5)})
    elif incident_type == "landslide":
        effects.append({"field": "road_condition", "delta": _bounded("road_condition", -20)})
    elif incident_type == "harvest_bumper":
        effects.append({"field": "harvest_outlook", "delta": _bounded("harvest_outlook", 20)})
        effects.append({"field": "public_support", "delta": _bounded("public_support", 5)})
    elif incident_type == "grain_convoy_loss":
        effects.append({"field": "grain_transport_pressure", "delta": _bounded("grain_transport_pressure", 15)})
    elif incident_type == "refugee_influx":
        effects.append({"field": "unrest", "delta": _bounded("unrest", 8)})
        effects.append({"field": "public_support", "delta": _bounded("public_support", -3)})
    elif incident_type == "bandit_surge":
        effects.append({"field": "unrest", "delta": _bounded("unrest", 10)})
        effects.append({"field": "military_pressure", "delta": _bounded("military_pressure", 5)})
    elif incident_type == "market_opportunity":
        effects.append({"field": "public_support", "delta": _bounded("public_support", 5)})
        effects.append({"field": "grain_transport_pressure", "delta": _bounded("grain_transport_pressure", -5)})
    elif incident_type == "gentry_petition":
        effects.append({"field": "public_support", "delta": _bounded("public_support", -2)})

    return effects


def _apply_effects_to_region(db, state, region_id: str, effects: list[dict]) -> None:
    """将局部效果写入 regions 表和 regional_world_states 表。

    严格限定字段：不写 controlled_by、人物状态、兵力、条约。
    """
    turn = get_turn(state)

    for effect in effects:
        field = str(effect["field"])
        delta = int(effect["delta"])
        if delta == 0:
            continue

        if field in {"public_support", "unrest", "military_pressure"}:
            # 写入 regions 表
            current = db.conn.execute(
                f"SELECT {field} FROM regions WHERE id=?", (region_id,)
            ).fetchone()
            if current is not None:
                old_val = int(current[field] or 0)
                new_val = max(0, min(100, old_val + delta))
                db.conn.execute(
                    f"UPDATE regions SET {field}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_val, region_id),
                )
                # 记入 region_logs 审计
                db.conn.execute(
                    """INSERT INTO region_logs
                    (turn, year, period, region_id, field, old_value, new_value, delta, reason, actor)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        turn, int(getattr(state, "year", 208)),
                        int(getattr(state, "period", 1)),
                        region_id, field,
                        str(old_val), str(new_val), delta,
                        f"区域事件即时效果 turn={turn}", "regional_incident",
                    ),
                )

        elif field in {
            "road_condition", "grain_transport_pressure",
            "harvest_outlook", "epidemic_pressure",
        }:
            current = db.conn.execute(
                "SELECT * FROM regional_world_states WHERE region_id=? AND turn=?",
                (region_id, turn),
            ).fetchone()
            if current is not None:
                old_val = int(current[field] or 0)
                new_val = max(-100, min(100, old_val + delta))
                db.conn.execute(
                    f"UPDATE regional_world_states SET {field}=? WHERE region_id=? AND turn=?",
                    (new_val, region_id, turn),
                )

        elif field in {"hazard_combat_multiplier", "supply_combat_multiplier"}:
            # 写入受影响区域的己方军队
            armies = db.conn.execute(
                "SELECT id, hazard_combat_multiplier, supply_combat_multiplier, station_node "
                "FROM armies WHERE owner_power='liu_bei' AND active=1"
            ).fetchall()
            for army in armies:
                station = str(army["station_node"] or "")
                if station == region_id:
                    old_val = float(army[field] or 1.0)
                    new_val = max(0.5, min(1.5, old_val + delta / 100.0))
                    db.conn.execute(
                        f"UPDATE armies SET {field}=? WHERE id=?",
                        (new_val, army["id"]),
                    )


def generate_regional_incidents(db, state) -> list[dict]:
    """生成本回合区域事件：最多 2 项普通 + 1 项重大。幂等。"""
    turn = get_turn(state)

    # 幂等守卫
    existing = db.conn.execute(
        "SELECT COUNT(*) FROM regional_incidents WHERE turn=?", (turn,)
    ).fetchone()[0]
    if existing > 0:
        from ming_sim.ws_incident_chain import _load_incidents
        return _load_incidents(db, turn)

    states = ensure_regional_world_states(db, state)
    if not states:
        return []

    results: list[dict] = []

    # === 重大事件：35% 命中率 ===
    dramatic_roll = draw_int(
        db, state=state, domain="regional_incident",
        subject_id="dramatic_global", low=1, high=100,
        draw_kind="dramatic_gate",
    )
    if dramatic_roll <= 35:
        # 按风险权重选目标地区
        dramatic_candidates: list[dict[str, object]] = []
        for s in states:
            rid = s["region_id"]
            risk = (
                abs(s["road_condition"]) + abs(s["harvest_outlook"])
                + s["epidemic_pressure"] + s["disaster_risk"]
            )
            if risk > 20:
                region = db.conn.execute(
                    "SELECT name FROM regions WHERE id=?", (rid,)
                ).fetchone()
                rname = str(region["name"]) if region else rid
                dramatic_candidates.append({
                    "incident_type": "dramatic_target",
                    "region_id": rid, "region_name": rname,
                    "weight": risk,
                })

        if dramatic_candidates:
            target = draw_weighted(
                db, state=state, domain="regional_incident",
                subject_id="dramatic_target",
                choices=dramatic_candidates,
                draw_kind="dramatic_target",
            )
            if target:
                # 按风险条件决定事件类型
                ts = next((s for s in states if s["region_id"] == target["region_id"]), None)
                if ts:
                    if ts["epidemic_pressure"] >= 50:
                        inc_type = "epidemic"
                    elif ts["harvest_outlook"] <= -50:
                        inc_type = "drought"
                    elif ts["road_condition"] <= -50:
                        inc_type = "flood"
                    else:
                        inc_type = "landslide"

                    title, summary = _incident_title_and_summary(
                        inc_type, str(target["region_name"]), "dramatic",
                    )
                    effects = _compute_local_effects(
                        inc_type, tier="dramatic",
                        weather_severity=ts["weather_severity"],
                        road_condition=ts["road_condition"],
                        harvest_outlook=ts["harvest_outlook"],
                        epidemic_pressure=ts["epidemic_pressure"],
                        unrest=0,
                    )
                    cursor = db.conn.execute(
                        """INSERT INTO regional_incidents
                        (turn, region_id, incident_type, tier, title, summary,
                         visibility, risk_snapshot_json, draw_refs_json,
                         local_effects_json, status)
                        VALUES (?, ?, ?, 'dramatic', ?, ?, 'own', ?, ?, ?, 'resolved_local')""",
                        (
                            turn, str(target["region_id"]), inc_type,
                            title, summary,
                            to_json({
                                "dramatic_roll": dramatic_roll,
                                "region_risk": sum(abs(v) for v in [
                                    ts["road_condition"], ts["harvest_outlook"],
                                    ts["epidemic_pressure"], ts["disaster_risk"],
                                ]),
                            }),
                            to_json([
                                f"world_random:turn:{turn}:domain:regional_incident:subject:dramatic_gate",
                                f"world_random:turn:{turn}:domain:regional_incident:subject:dramatic_target",
                            ]),
                            to_json(effects),
                        ),
                    )
                    results.append({
                        "id": int(cursor.lastrowid),
                        "turn": turn, "region_id": str(target["region_id"]),
                        "incident_type": inc_type, "tier": "dramatic",
                        "title": title, "summary": summary,
                        "visibility": "own", "status": "resolved_local",
                        "effects_applied_at": 0,
                        "local_effects": effects,
                    })

    # === 普通事件：最多 2 项 ===
    ordinary_candidates = _build_ordinary_candidates(states, db)
    drawn_types: set[str] = set()
    drawn_regions: set[str] = set()

    for slot in range(2):
        if not ordinary_candidates:
            break
        # 排除已选的 (region, type) 组合
        filtered = [
            c for c in ordinary_candidates
            if (c["region_id"], c["incident_type"]) not in drawn_types
            and c["region_id"] not in drawn_regions
        ]
        if not filtered:
            break

        chosen = draw_weighted(
            db, state=state, domain="regional_incident",
            subject_id=f"ordinary_slot_{slot}",
            choices=filtered,
            draw_kind="ordinary",
        )
        if not chosen:
            break

        rid = str(chosen["region_id"])
        inc_type = str(chosen["incident_type"])
        rname = str(chosen["region_name"])
        drawn_types.add((rid, inc_type))
        drawn_regions.add(rid)

        ts = next((s for s in states if s["region_id"] == rid), None)
        title, summary = _incident_title_and_summary(inc_type, rname, "ordinary")
        effects = _compute_local_effects(
            inc_type, tier="ordinary",
            weather_severity=ts["weather_severity"] if ts else 0,
            road_condition=ts["road_condition"] if ts else 0,
            harvest_outlook=ts["harvest_outlook"] if ts else 0,
            epidemic_pressure=ts["epidemic_pressure"] if ts else 0,
            unrest=0,
        )
        cursor = db.conn.execute(
            """INSERT INTO regional_incidents
            (turn, region_id, incident_type, tier, title, summary,
             visibility, risk_snapshot_json, draw_refs_json,
            local_effects_json, status)
            VALUES (?, ?, ?, 'ordinary', ?, ?, 'own', ?, ?, ?, 'resolved_local')""",
            (
                turn, rid, inc_type,
                title, summary,
                json.dumps({
                    "region_state": ts if ts else {},
                }, ensure_ascii=False, default=str),
                to_json([
                    f"world_random:turn:{turn}:domain:regional_incident:subject:ordinary_slot_{slot}",
                ]),
                to_json(effects),
            ),
        )
        results.append({
            "id": int(cursor.lastrowid),
            "turn": turn, "region_id": rid,
            "incident_type": inc_type, "tier": "ordinary",
            "title": title, "summary": summary,
            "visibility": "own", "status": "resolved_local",
            "effects_applied_at": 0,
            "local_effects": effects,
        })

    db.conn.commit()
    return results
