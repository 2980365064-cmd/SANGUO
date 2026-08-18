"""外势内部动态（power internal dynamics）模块。

从 world_simulation.py 中提取。负责每月为非刘备势力生成内部政治/经济动态，
包括候选构建、加权抽取、效果落地。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from ming_sim.world_random import draw_int, draw_weighted
from ming_sim.ws_utils import decode_json as _decode, safe_list as _safe_list, clamp as _clamp, status_terminal as _status_terminal
from ming_sim.ws_utils import get_turn, get_year, get_period, to_json
from ming_sim.ws_common import seed_for as _seed_for, iter_active_powers, log_power_change


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_POWER_INTERNAL_DYNAMIC_TYPES: dict[str, dict] = {
    "court_rivalry": {
        "prerequisite": lambda p, _db, _wars, _unrest: int(p["cohesion"] or 0) <= 55,
        "weight_basis": lambda p, _db, _wars, _unrest: max(1, 55 - int(p["cohesion"] or 0)),
        "effects": [
            {"field": "cohesion", "low": -6, "high": -4},
        ],
        "severity_basis": lambda p, _db, _wars, _unrest: max(3, min(8, (55 - int(p["cohesion"] or 0)) // 8 + 3)),
    },
    "supply_dispute": {
        "prerequisite": lambda p, _db, _wars, _unrest: int(p["supply"] or 0) <= 45,
        "weight_basis": lambda p, _db, _wars, _unrest: max(1, 45 - int(p["supply"] or 0)),
        "effects": [
            {"field": "supply", "low": -5, "high": -3},
            {"field": "cohesion", "low": -2, "high": -2},
        ],
        "severity_basis": lambda p, _db, _wars, _unrest: max(3, min(8, (45 - int(p["supply"] or 0)) // 8 + 3)),
    },
    "command_dispute": {
        "prerequisite": lambda p, _db, wars, _unrest: (
            wars >= 1 and int(p["cohesion"] or 0) <= 70
        ),
        "weight_basis": lambda p, _db, wars, _unrest: max(1, wars * (70 - int(p["cohesion"] or 0))),
        "effects": [
            {"field": "cohesion", "low": -5, "high": -3},
        ],
        "severity_basis": lambda p, _db, wars, _unrest: max(3, min(8, wars + (70 - int(p["cohesion"] or 0)) // 10 + 3)),
    },
    "local_elite_pressure": {
        "prerequisite": lambda p, _db, _wars, unrest: unrest >= 55,
        "weight_basis": lambda p, _db, _wars, unrest: max(1, int(unrest - 55) + 1),
        "effects": [
            {"field": "cohesion", "low": -4, "high": -2},
        ],
        "severity_basis": lambda p, _db, _wars, unrest: max(3, min(8, int(unrest - 55) // 10 + 3)),
    },
    "court_consolidation": {
        "prerequisite": lambda p, _db, _wars, _unrest: (
            55 <= int(p["cohesion"] or 0) <= 75 and int(p["supply"] or 0) >= 50
        ),
        "weight_basis": lambda p, _db, _wars, _unrest: max(1, 75 - int(p["cohesion"] or 0) + 1),
        "effects": [
            {"field": "cohesion", "low": 2, "high": 4},
        ],
        "severity_basis": lambda p, _db, _wars, _unrest: 2,
    },
    # --- 新增类型（多因素交叉权重） ---
    "succession_crisis": {
        # 继承危机：低凝聚 + 多线战争 + 高不安
        "prerequisite": lambda p, db, wars, unrest: (
            int(p["cohesion"] or 0) < 30 and wars >= 1
        ),
        "weight_basis": lambda p, _db, wars, unrest: max(5.0,
            (100 - int(p["cohesion"] or 50))
            * (1.0 + wars * 0.3)
            * (1.0 + unrest / 100.0)
            / max(1.0, int(p["supply"] or 50) / 50.0)
        ),
        "effects": [
            {"field": "cohesion", "low": -8, "high": -5},
        ],
        "severity_basis": lambda p, _db, wars, _unrest: max(5, min(10, (30 - int(p["cohesion"] or 0)) // 5 + wars + 3)),
    },
    "economic_strain": {
        # 经济压力：低补给 + 高不安
        "prerequisite": lambda p, _db, _wars, unrest: (
            int(p["supply"] or 0) < 40 and unrest > 50
        ),
        "weight_basis": lambda p, _db, _wars, unrest: max(3.0,
            (40 - int(p["supply"] or 0))
            * (1.0 + (unrest - 50) / 50.0)
        ),
        "effects": [
            {"field": "supply", "low": -6, "high": -3},
            {"field": "cohesion", "low": -3, "high": -1},
        ],
        "severity_basis": lambda p, _db, _wars, unrest: max(4, min(9, (40 - int(p["supply"] or 0)) // 6 + (unrest - 50) // 15 + 3)),
    },
    "military_faction": {
        # 军阀派系：多线战争 + 低凝聚 + 多武将
        "prerequisite": lambda p, db, wars, _unrest: (
            wars >= 2 and int(p["cohesion"] or 0) <= 60
        ),
        "weight_basis": lambda p, db, wars, _unrest: max(4.0,
            wars * (60 - int(p["cohesion"] or 0)) * 0.5
        ),
        "effects": [
            {"field": "cohesion", "low": -7, "high": -4},
        ],
        "severity_basis": lambda p, _db, wars, _unrest: max(5, min(10, wars + (60 - int(p["cohesion"] or 0)) // 10 + 3)),
    },
    "diplomatic_isolation": {
        # 外交孤立：所有关系紧张
        "prerequisite": lambda p, db, _wars, _unrest: (
            _count_allied_or_friendly(db, str(p["id"])) == 0
            and int(p["cohesion"] or 0) <= 50
        ),
        "weight_basis": lambda p, db, _wars, _unrest: max(3.0,
            (50 - int(p["cohesion"] or 0)) * 0.8
        ),
        "effects": [
            {"field": "cohesion", "low": -5, "high": -3},
        ],
        "severity_basis": lambda p, _db, _wars, _unrest: max(4, min(8, (50 - int(p["cohesion"] or 0)) // 8 + 3)),
    },
    "natural_disaster_recovery": {
        # 灾后恢复：正面动态，有灾害但补给充足
        "prerequisite": lambda p, db, _wars, _unrest: (
            _has_natural_disaster(db, str(p["id"]))
            and int(p["supply"] or 0) >= 60
            and int(p["cohesion"] or 0) >= 40
        ),
        "weight_basis": lambda p, _db, _wars, _unrest: max(2.0,
            (int(p["supply"] or 0) - 50) * 0.3
        ),
        "effects": [
            {"field": "cohesion", "low": 1, "high": 3},
            {"field": "supply", "low": -2, "high": -1},  # 救灾消耗
        ],
        "severity_basis": lambda p, _db, _wars, _unrest: 3,
    },
}


def _count_allied_or_friendly(db, power_id: str) -> int:
    """统计势力的盟友/友好关系数量。"""
    row = db.conn.execute(
        """SELECT COUNT(*) as cnt FROM diplomatic_relations
           WHERE (power_a = ? OR power_b = ?)
             AND status IN ('allied', 'friendly')""",
        (power_id, power_id),
    ).fetchone()
    return int(row["cnt"]) if row else 0


def _has_natural_disaster(db, power_id: str) -> bool:
    """检查势力控制区是否有自然灾害。"""
    row = db.conn.execute(
        """SELECT 1 FROM regions
           WHERE controlled_by = ? AND natural_disaster != ''
           LIMIT 1""",
        (power_id,),
    ).fetchone()
    return row is not None

# 效果上限（用于测试验证）
_DYNAMIC_EFFECT_CAPS: dict[str, int] = {
    "court_rivalry_cohesion": 6,
    "supply_dispute_supply": 5,
    "supply_dispute_cohesion": 2,
    "command_dispute_cohesion": 5,
    "local_elite_pressure_cohesion": 4,
    "court_consolidation_cohesion": 4,
    # 新增类型
    "succession_crisis_cohesion": 8,
    "economic_strain_supply": 6,
    "economic_strain_cohesion": 3,
    "military_faction_cohesion": 7,
    "diplomatic_isolation_cohesion": 5,
    "natural_disaster_recovery_cohesion": 3,
    "natural_disaster_recovery_supply": 2,
}


# ---------------------------------------------------------------------------
# 候选构建
# ---------------------------------------------------------------------------

def _build_power_internal_candidates(db, state) -> list[dict]:
    """按盘面条件生成外势内部动态候选。

    仅处理非刘备活跃势力。每个候选包含 power_id、dynamic_type、weight、
    前提证据快照。
    """
    turn = get_turn(state)
    candidates: list[dict] = []
    for power in iter_active_powers(db):
        power_id = str(power["id"])
        if _status_terminal(str(power["status"])):
            continue
        # 计算战争关系数量
        wars = db.conn.execute(
            "SELECT COUNT(*) FROM diplomatic_relations "
            "WHERE (power_a=? OR power_b=?) AND status='war'",
            (power_id, power_id),
        ).fetchone()[0]
        # 计算控制地区平均 unrest
        regions_row = db.conn.execute(
            "SELECT AVG(unrest) as avg_unrest FROM regions WHERE controlled_by=?",
            (power_id,),
        ).fetchone()
        unrest_avg = float(regions_row["avg_unrest"] or 0) if regions_row else 0.0

        for dynamic_type, spec in _POWER_INTERNAL_DYNAMIC_TYPES.items():
            if not spec["prerequisite"](power, db, wars, unrest_avg):
                continue
            weight = float(spec["weight_basis"](power, db, wars, unrest_avg))
            severity = int(spec["severity_basis"](power, db, wars, unrest_avg))
            # 证据快照
            snapshot = {
                "cohesion": int(power["cohesion"] or 0),
                "supply": int(power["supply"] or 0),
                "war_count": int(wars),
                "avg_unrest": round(unrest_avg, 1),
            }
            candidates.append({
                "key": f"{power_id}:{dynamic_type}",
                "power_id": power_id,
                "dynamic_type": dynamic_type,
                "weight": weight,
                "severity": severity,
                "snapshot": snapshot,
            })
    return candidates


# ---------------------------------------------------------------------------
# 主入口：每月生成内部动态
# ---------------------------------------------------------------------------

def ensure_power_internal_dynamics(db, state) -> list[dict]:
    """每月生成最多 3 条外势内部动态，同势力最多 1 条。

    使用 world_random.draw_weighted 选择，结果落库保证幂等。
    """
    turn = get_turn(state)

    # 幂等守卫
    existing_count = db.conn.execute(
        "SELECT COUNT(*) FROM power_internal_dynamics WHERE turn=?", (turn,)
    ).fetchone()[0]
    if existing_count > 0:
        return _load_power_internal_dynamics(db, turn)

    max_slots = 3
    results: list[dict] = []
    used_powers: set[str] = set()

    for slot in range(1, max_slots + 1):
        all_candidates = _build_power_internal_candidates(db, state)
        # 排除已选势力
        filtered = [c for c in all_candidates if c["power_id"] not in used_powers]
        if not filtered:
            break
        # 构造 draw_weighted 候选
        choices = [
            {
                "key": c["key"],
                "weight": c["weight"],
                "power_id": c["power_id"],
                "dynamic_type": c["dynamic_type"],
                "severity": c["severity"],
                "snapshot": c["snapshot"],
            }
            for c in filtered
        ]
        chosen = draw_weighted(
            db, state=state,
            domain="power_internal_dynamic",
            subject_id=f"global_slot_{slot}",
            choices=choices,
            draw_kind="selection",
        )
        if chosen is None:
            break
        power_id = str(chosen["power_id"])
        dynamic_type = str(chosen["dynamic_type"])
        severity = int(chosen["severity"])
        snapshot = dict(chosen["snapshot"])

        # 检查是否已有（防御性重复检查）
        existing = db.conn.execute(
            "SELECT id FROM power_internal_dynamics WHERE turn=? AND power_id=? AND dynamic_type=?",
            (turn, power_id, dynamic_type),
        ).fetchone()
        if existing:
            used_powers.add(power_id)
            continue

        # 生成标题和摘要
        title, summary = _dynamic_title_and_summary(dynamic_type, power_id, snapshot)

        # 计算数值效果
        spec = _POWER_INTERNAL_DYNAMIC_TYPES[dynamic_type]
        rule_effects: list[dict] = []
        for effect_spec in spec["effects"]:
            field = effect_spec["field"]
            low = int(effect_spec["low"])
            high = int(effect_spec["high"])
            delta = draw_int(
                db, state=state,
                domain="power_internal_dynamic",
                subject_id=f"{power_id}:{dynamic_type}",
                low=min(low, high),
                high=max(low, high),
                draw_kind=f"effect_delta:{field}",
                metadata={"field": field, "dynamic_type": dynamic_type, "power_id": power_id},
            )
            rule_effects.append({"field": field, "delta": int(delta)})

        draw_refs = [
            {"domain": "power_internal_dynamic", "subject_id": f"global_slot_{slot}", "draw_kind": "selection"},
        ]
        for effect_spec in spec["effects"]:
            draw_refs.append({
                "domain": "power_internal_dynamic",
                "subject_id": f"{power_id}:{dynamic_type}",
                "draw_kind": f"effect_delta:{effect_spec['field']}",
            })

        # 落库
        db.conn.execute(
            """INSERT INTO power_internal_dynamics
            (turn, power_id, dynamic_type, severity, title, summary,
             state_snapshot_json, draw_refs_json, rule_effects_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'resolved_local')""",
            (
                turn, power_id, dynamic_type, severity, title, summary,
                to_json(snapshot),
                to_json(draw_refs),
                to_json(rule_effects),
            ),
        )
        db.conn.commit()
        used_powers.add(power_id)

    return _load_power_internal_dynamics(db, turn)


# ---------------------------------------------------------------------------
# 标题/摘要生成
# ---------------------------------------------------------------------------

def _dynamic_title_and_summary(dynamic_type: str, power_id: str, snapshot: dict) -> tuple[str, str]:
    """生成动态标题和摘要。"""
    cohesion = snapshot.get("cohesion", 0)
    supply = snapshot.get("supply", 0)
    wars = snapshot.get("war_count", 0)
    unrest = snapshot.get("avg_unrest", 0)
    titles = {
        "court_rivalry": f"{power_id}：朝堂倾轧加剧",
        "supply_dispute": f"{power_id}：补给分配争端",
        "command_dispute": f"{power_id}：将帅不和",
        "local_elite_pressure": f"{power_id}：地方豪族施压",
        "court_consolidation": f"{power_id}：朝局整合 consolidation",
    }
    summaries = {
        "court_rivalry": f"凝聚仅{cohesion}，派系斗争消耗行政效率。",
        "supply_dispute": f"补给仅{supply}，前线与后方争夺资源。",
        "command_dispute": f"交战{wars}方且凝聚{cohesion}，将领间出现分歧。",
        "local_elite_pressure": f"控制区平均动乱{unrest:.0f}，豪族借机要挟。",
        "court_consolidation": f"凝聚{cohesion}、补给{supply}，政局暂稳。",
    }
    return titles.get(dynamic_type, f"{power_id}：内部变动"), summaries.get(dynamic_type, "内部状态变化。")


# ---------------------------------------------------------------------------
# 效果应用
# ---------------------------------------------------------------------------

def apply_power_internal_dynamic_effects(db, state, dynamic: dict) -> list[dict]:
    """将内部动态的数值效果应用到 powers 表。

    效果仅通过 powers.cohesion、powers.supply 与 power_logs 落账；
    不得改人物生死、兵力、军队、领土、条约或结局。
    effects_applied_at 保证同一动态同一回合只生效一次。
    """
    effects = dynamic.get("rule_effects", [])
    if not effects:
        return []
    power_id = str(dynamic["power_id"])
    turn = get_turn(state)
    dynamic_id = dynamic.get("id")

    # 幂等检查
    if dynamic_id is not None:
        row = db.conn.execute(
            "SELECT effects_applied_at FROM power_internal_dynamics WHERE id=?",
            (dynamic_id,),
        ).fetchone()
        if row is not None:
            applied_at = int(row["effects_applied_at"] or 0)
            if applied_at >= turn:
                return []

    # 读取当前值
    power_row = db.conn.execute(
        "SELECT cohesion, supply FROM powers WHERE id=?", (power_id,)
    ).fetchone()
    if power_row is None:
        return []
    cohesion = int(power_row["cohesion"] or 0)
    supply = int(power_row["supply"] or 0)

    applied: list[dict] = []
    for effect in effects:
        field = str(effect["field"])
        delta = int(effect["delta"])
        if field == "cohesion":
            old = cohesion
            cohesion = _clamp(cohesion + delta)
            applied.append({"field": "cohesion", "delta": delta, "before": old, "after": cohesion})
            db.conn.execute(
                "UPDATE powers SET cohesion=? WHERE id=?", (cohesion, power_id)
            )
            log_power_change(db, state, power_id, "cohesion", old, cohesion,
                             f"{dynamic['dynamic_type']}: cohesion {old}->{cohesion}")
        elif field == "supply":
            old = supply
            supply = _clamp(supply + delta)
            applied.append({"field": "supply", "delta": delta, "before": old, "after": supply})
            db.conn.execute(
                "UPDATE powers SET supply=? WHERE id=?", (supply, power_id)
            )
            log_power_change(db, state, power_id, "supply", old, supply,
                             f"{dynamic['dynamic_type']}: supply {old}->{supply}")

    # 标记已应用
    if dynamic_id is not None and applied:
        db.conn.execute(
            "UPDATE power_internal_dynamics SET effects_applied_at=? WHERE id=?",
            (turn, dynamic_id),
        )
    db.conn.commit()
    return applied


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def _load_power_internal_dynamics(db, turn: int) -> list[dict]:
    """加载指定回合的所有内部动态。"""
    rows = db.conn.execute(
        "SELECT * FROM power_internal_dynamics WHERE turn=? ORDER BY id",
        (turn,),
    ).fetchall()
    results: list[dict] = []
    for r in rows:
        results.append({
            "id": int(r["id"]),
            "turn": int(r["turn"]),
            "power_id": str(r["power_id"]),
            "dynamic_type": str(r["dynamic_type"]),
            "severity": int(r["severity"]),
            "title": str(r["title"]),
            "summary": str(r["summary"]),
            "state_snapshot": json.loads(str(r["state_snapshot_json"] or "{}")),
            "draw_refs": json.loads(str(r["draw_refs_json"] or "[]")),
            "rule_effects": json.loads(str(r["rule_effects_json"] or "[]")),
            "effects_applied_at": int(r["effects_applied_at"] or 0),
            "status": str(r["status"]),
        })
    return results
