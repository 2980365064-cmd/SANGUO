"""随机事件框架 — P1（兼容旧存档）

第二阶段起，生产随机事件由 ming_sim.world_simulation.generate_regional_incidents() 生成。
本模块保留旧存档中 random_events 表的读写与 resolve_random_event() 逻辑，
但 generate_random_events() 不再独立使用未播种全局 RNG 抽取新事件。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ming_sim.db import GameDB
from ming_sim.models import GameState

# 预定义事件模板
RANDOM_EVENT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "category": "disaster",
        "title": "蝗灾袭扰",
        "description": "蝗虫过境，庄稼受损，粮秣紧张。",
        "options": ["开仓赈济（粮秣-20，民望+10）", "组织捕蝗（粮秣-5）", "暂不处理（民望-10）"],
        "base_probability": 0.12,
        "trigger_conditions": {"min_period": 4, "max_period": 9},  # 4-9月
        "apply_metric": "粮秣",
        "apply_value": -15,
        "option_effects": [
            {"metrics": {"粮秣": -20, "民望": 10}, "reputation": 3},
            {"metrics": {"粮秣": -5}},
            {"metrics": {"民望": -10}, "reputation": -4},
        ],
    },
    {
        "category": "harvest",
        "title": "风调雨顺",
        "description": "今年收成颇丰，各郡仓廪充实。",
        "options": ["储备粮秣", "减税惠农（军资-10，民望+15）"],
        "base_probability": 0.08,
        "trigger_conditions": {"min_period": 8, "max_period": 10},  # 8-10月
        "apply_metric": "粮秣",
        "apply_value": 25,
        "option_effects": [
            {"metrics": {"粮秣": 25}},
            {"metrics": {"军资": -10, "民望": 15}, "reputation": 2},
        ],
    },
    {
        "category": "population",
        "title": "流民归附",
        "description": "一批流民迁入境内，请求安置。",
        "options": ["开仓接纳（粮秣-15，民望+10）", "编入军中（军资+10）", "劝归原籍"],
        "base_probability": 0.10,
        "trigger_conditions": {},
        "apply_metric": "民望",
        "apply_value": 5,
        "option_effects": [
            {"metrics": {"粮秣": -15, "民望": 10}, "reputation": 3},
            {"metrics": {"军资": 10, "民望": -2}, "reputation": -2},
            {"metrics": {"民望": -3}},
        ],
    },
    {
        "category": "military",
        "title": "军马交易",
        "description": "有商队提出以优质战马换取军资。",
        "options": ["购买战马（军资-30，战斗力提升）", "拒绝交易"],
        "base_probability": 0.06,
        "trigger_conditions": {},
        "apply_metric": "军资",
        "apply_value": -20,
        "option_effects": [{"metrics": {"军资": -30}}, {}],
    },
    {
        "category": "security",
        "title": "境内盗匪",
        "description": "境内山匪为患，劫掠商旅。",
        "options": ["派兵清剿（军资-10）", "招安编入（军资+5）", "暂不处理（民望-10）"],
        "base_probability": 0.10,
        "trigger_conditions": {},
        "apply_metric": "民望",
        "apply_value": -8,
        "option_effects": [
            {"metrics": {"军资": -10, "民望": 2}},
            {"metrics": {"军资": 5, "民望": -2}, "reputation": -1},
            {"metrics": {"民望": -10}, "reputation": -3},
        ],
    },
    {
        "category": "disaster",
        "title": "境内水患",
        "description": "连降暴雨，河道泛滥，或需紧急救灾。",
        "options": ["拨款治水（军资-25，粮秣+5）", "迁民避险", "暂不处理（粮秣-10）"],
        "base_probability": 0.08,
        "trigger_conditions": {"min_period": 5, "max_period": 8},
        "apply_metric": "粮秣",
        "apply_value": -10,
        "option_effects": [
            {"metrics": {"军资": -25, "粮秣": 5}, "reputation": 2},
            {"metrics": {"民望": 3}},
            {"metrics": {"粮秣": -10, "民望": -5}, "reputation": -3},
        ],
    },
    {
        "category": "elite",
        "title": "士族请愿",
        "description": "本地士族联名上书，请求减免赋税并给予更多自治。",
        "options": ["部分妥协（军资-10，士族支持+8）", "婉拒（士族支持-5）", "强行压制（士族支持-15）"],
        "base_probability": 0.07,
        "trigger_conditions": {},
        "apply_metric": "士族支持",
        "apply_value": 0,
        "option_effects": [
            {"metrics": {"军资": -10, "士族支持": 8}},
            {"metrics": {"士族支持": -5}},
            {"metrics": {"士族支持": -15, "军心": 2}, "reputation": -3},
        ],
    },
    {
        "category": "opportunity",
        "title": "商队过境",
        "description": "一支西域商队途经境内，携带珍奇货物。",
        "options": ["设市贸易（军资+15）", "课征过路税（军资+8）", "不予理会"],
        "base_probability": 0.06,
        "trigger_conditions": {},
        "apply_metric": "军资",
        "apply_value": 12,
        "option_effects": [{"metrics": {"军资": 15}}, {"metrics": {"军资": 8}}, {}],
    },
]


def seed_random_event_templates(db: GameDB) -> None:
    """初始化随机事件模板（幂等：存在则跳过）。"""
    for tmpl in RANDOM_EVENT_TEMPLATES:
        existing = db.conn.execute(
            "SELECT 1 FROM random_event_templates WHERE category=? AND title=?",
            (tmpl["category"], tmpl["title"]),
        ).fetchone()
        effects = {"option_effects": tmpl.get("option_effects", [])}
        if existing:
            db.conn.execute(
                "UPDATE random_event_templates SET description=?, trigger_conditions=?, options=?, effects=?, base_probability=? WHERE category=? AND title=?",
                (
                    tmpl["description"], json.dumps(tmpl.get("trigger_conditions", {}), ensure_ascii=False),
                    json.dumps(tmpl.get("options", []), ensure_ascii=False), json.dumps(effects, ensure_ascii=False),
                    tmpl.get("base_probability", 0.1), tmpl["category"], tmpl["title"],
                ),
            )
            continue
        db.conn.execute(
            """
            INSERT INTO random_event_templates
            (category, title, description, trigger_conditions, options, effects, base_probability)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tmpl["category"],
                tmpl["title"],
                tmpl["description"],
                json.dumps(tmpl.get("trigger_conditions", {}), ensure_ascii=False),
                json.dumps(tmpl.get("options", []), ensure_ascii=False),
                json.dumps(effects, ensure_ascii=False),
                tmpl.get("base_probability", 0.1),
            ),
        )
    db.conn.commit()


def generate_random_events(state: GameState, db: GameDB, max_per_turn: int = 2) -> List[Dict[str, Any]]:
    """第二阶段：不再生成新随机事件。区域事件系统接管。

    返回空列表。旧存档中已有的 random_events 行通过 resolve_random_event() 仍可处理。
    """
    # 幂等：确保模板已播种（旧存档兼容）
    ensure_templates_seeded(db)
    return []


def _create_random_event(
    state: GameState, db: GameDB, tmpl: Dict[str, Any]
) -> Dict[str, Any]:
    """创建单个运行时随机事件。"""
    turn = int(getattr(state, "turn", 0))
    cursor = db.conn.execute(
        """
        INSERT INTO random_events
        (template_id, turn, title, description, options, status)
        VALUES (?, ?, ?, ?, ?, 'active')
        """,
        (
            tmpl["id"],
            int(turn),
            tmpl["title"],
            tmpl.get("description", ""),
            json.dumps(tmpl.get("options", []), ensure_ascii=False),
        ),
    )
    db.conn.commit()
    event_id = cursor.lastrowid

    # 同时创建 issue（进入局势卡片）
    try:
        db.insert_issue(
            state,
            kind="decree",
            title=f"【随机事件】{tmpl['title']}",
            origin_kind="random_event",
            severity=5 if tmpl["category"] == "disaster" else 3,
            turn=int(turn),
            goal=tmpl.get("description", ""),
        )
    except Exception:
        pass  # 如果 issue 创建失败不阻塞

    return {
        "id": event_id,
        "title": tmpl["title"],
        "category": tmpl["category"],
        "description": tmpl["description"],
        "options": tmpl.get("options", []),
    }


def advance_random_events(state: GameState, db: GameDB) -> List[Dict[str, Any]]:
    """月末推进随机事件。检查是否有超期未处理的事件并自动结算。"""
    results: List[Dict[str, Any]] = []
    active = db.conn.execute(
        "SELECT * FROM random_events WHERE status='active'"
    ).fetchall()

    for row in (dict(r) for r in active):
        event_id = row["id"]
        # 检查是否已过了 3 回合（自动结算）
        created_turn = row.get("turn", 0)
        current_turn = int(getattr(state, "turn", 0))
        if current_turn - created_turn >= 3:
            db.conn.execute(
                "UPDATE random_events SET status='expired', result='超期未处理' WHERE id=?",
                (event_id,),
            )
            db.conn.commit()
            results.append({"id": event_id, "status": "expired", "title": row["title"]})

    return results


def resolve_random_event(
    db: GameDB, state: GameState, event_id: int, choice: str
) -> Dict[str, Any]:
    """在方略执行阶段结算随机事件，写入确定的资源与口碑影响。"""
    row = db.conn.execute(
        "SELECT * FROM random_events WHERE id=?", (int(event_id),)
    ).fetchone()
    if not row:
        return {"error": "事件不存在"}
    if str(row["status"] or "") != "active":
        return {"error": "事件已处理或已失效"}

    choices_str = row["options"] or "[]"
    try:
        choices = json.loads(choices_str)
    except json.JSONDecodeError:
        choices = []

    if not isinstance(choice, str) or not choice.isdigit() or not 1 <= int(choice) <= len(choices):
        return {"error": "事件处理方案无效"}
    choice_index = int(choice) - 1
    choice_label = choices[choice_index]

    template = db.conn.execute(
        "SELECT effects FROM random_event_templates WHERE id=?", (row["template_id"],)
    ).fetchone()
    effects: Dict[str, Any] = {}
    if template is not None:
        try:
            effect_options = json.loads(str(template["effects"] or "{}")).get("option_effects", [])
            effects = dict(effect_options[choice_index] or {}) if choice_index < len(effect_options) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            effects = {}

    applied_metrics: Dict[str, int] = {}
    for metric, delta in dict(effects.get("metrics") or {}).items():
        if metric not in state.metrics:
            continue
        actual_delta = int(delta)
        state.metrics[metric] = max(0, int(state.metrics.get(metric, 0)) + actual_delta)
        applied_metrics[str(metric)] = actual_delta
    if applied_metrics:
        db.save_state(state)

    reputation_delta = int(effects.get("reputation") or 0)
    if reputation_delta:
        db.add_reputation_log(
            state,
            source_kind="random_event",
            source_id=str(event_id),
            metric="仁义",
            delta=reputation_delta,
            summary=f"处理“{row['title']}”：{choice_label}",
        )

    db.conn.execute(
        "UPDATE random_events SET status='resolved', player_choice=?, result=?, resolved_at=CURRENT_TIMESTAMP WHERE id=?",
        (str(choice), f"方略执行：{choice_label}", int(event_id)),
    )
    db.conn.commit()

    return {"id": event_id, "status": "resolved", "choice": choice_label, "metrics": applied_metrics, "reputation_delta": reputation_delta}


def ensure_templates_seeded(db: GameDB) -> None:
    """确保随机事件模板已初始化。"""
    existing = db.conn.execute(
        "SELECT COUNT(*) FROM random_event_templates"
    ).fetchone()[0]
    if existing == 0:
        seed_random_event_templates(db)
