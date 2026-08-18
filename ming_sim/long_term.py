"""刘备势力的长期政治状态。

该模块只记录可审计事实；文本叙事由上层生成，不能反向改写这里的值。
"""

from __future__ import annotations

from typing import Any, Dict, List


FACTION_SPECS: tuple[Dict[str, str], ...] = (
    {"key": "veterans", "label": "元老集团", "agenda": "守住旧部名分与军中情义", "unlock": "opening"},
    {"key": "jingzhou", "label": "荆州士人", "agenda": "安定荆楚、广纳名士并维系孙刘关系", "unlock": "opening"},
    {"key": "local", "label": "地方豪强与流民", "agenda": "减轻兵灾、恢复生产并保全乡里", "unlock": "opening"},
    {"key": "yizhou", "label": "益州派", "agenda": "维护益州秩序与本地利益", "unlock": "chengdu"},
)


def _controlled_nodes(db) -> set[str]:
    return {
        str(row["id"])
        for row in db.conn.execute("SELECT id FROM regions WHERE controlled_by='liu_bei'").fetchall()
    }


def refresh_long_term_state(db, state) -> None:
    """初始化并按盘面激活政治群体；重复调用不改变既有支持度。"""
    controlled = _controlled_nodes(db)
    for spec in FACTION_SPECS:
        active = spec["unlock"] == "opening" or "chengdu" in controlled
        row = db.conn.execute(
            "SELECT status FROM political_faction_states WHERE faction_key=?", (spec["key"],)
        ).fetchone()
        if row is None:
            db.conn.execute(
                """
                INSERT INTO political_faction_states
                (faction_key, label, agenda, status, activated_turn, support)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (spec["key"], spec["label"], spec["agenda"], "active" if active else "locked", int(state.turn), 50),
            )
        elif active and str(row["status"]) == "locked":
            db.conn.execute(
                "UPDATE political_faction_states SET status='active', activated_turn=?, updated_at=CURRENT_TIMESTAMP WHERE faction_key=?",
                (int(state.turn), spec["key"]),
            )
    db.conn.commit()


def adjust_character_loyalty(db, state, character_name: str, delta: int, reason: str, *, source_kind: str, source_id: str = "") -> int:
    """以日志为先的忠诚调整；越界值由规则层夹住。"""
    row = db.conn.execute("SELECT loyalty FROM characters WHERE name=?", (character_name,)).fetchone()
    if row is None:
        raise ValueError(f"人物不存在：{character_name}")
    before = int(row["loyalty"] or 50)
    after = max(0, min(100, before + int(delta)))
    actual_delta = after - before
    db.conn.execute("UPDATE characters SET loyalty=? WHERE name=?", (after, character_name))
    db.conn.execute(
        """
        INSERT INTO character_loyalty_logs
        (turn, character_name, delta, before_value, after_value, reason, source_kind, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (int(state.turn), character_name, actual_delta, before, after, reason, source_kind, source_id),
    )
    db.conn.commit()
    return after


def adjust_faction_support(db, state, faction_key: str, delta: int, reason: str, *, source_kind: str, source_id: str = "") -> int:
    """派系支持同样必须由规则层改变，并留下可供月报解释的审计记录。"""
    row = db.conn.execute("SELECT support FROM political_faction_states WHERE faction_key=?", (faction_key,)).fetchone()
    if row is None:
        return 0
    before = int(row["support"] or 50)
    after = max(0, min(100, before + int(delta)))
    db.conn.execute(
        "UPDATE political_faction_states SET support=?, updated_at=CURRENT_TIMESTAMP WHERE faction_key=?",
        (after, faction_key),
    )
    db.conn.execute(
        """INSERT INTO character_loyalty_logs
           (turn, character_name, delta, before_value, after_value, reason, source_kind, source_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (int(state.turn), f"派系:{faction_key}", after - before, before, after, reason, source_kind, source_id),
    )
    db.conn.commit()
    return after


def long_term_summary(db, state, *, limit: int = 8, ensure_initialized: bool = False) -> Dict[str, Any]:
    """返回长期政治摘要。

    查询默认不写入世界；仅在新开局/结算等明确生命周期节点传入
    ``ensure_initialized=True``。这样重新打开行动枢纽或每月总计不会
    因一次阅读而改变派系事实。
    """
    if ensure_initialized:
        refresh_long_term_state(db, state)
    reputation_rows = db.conn.execute(
        "SELECT * FROM reputation_logs ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
    recent_reputation = [db._row_dict(row) for row in reputation_rows]
    total_reputation_delta = db.conn.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM reputation_logs WHERE metric='仁义'"
    ).fetchone()[0]
    reputation_score = max(0, min(100, 50 + int(total_reputation_delta or 0)))
    factions = [
        db._row_dict(row)
        for row in db.conn.execute(
            "SELECT faction_key, label, agenda, status, activated_turn, support FROM political_faction_states ORDER BY activated_turn, faction_key"
        ).fetchall()
    ]
    risks = [
        db._row_dict(row)
        for row in db.conn.execute(
            """
            SELECT name, loyalty FROM characters
            WHERE power_id='liu_bei' AND status='active' AND loyalty < 45
            ORDER BY loyalty ASC, name LIMIT 6
            """
        ).fetchall()
    ]
    return {
        "reputation": {"score": reputation_score, "recent": recent_reputation},
        "factions": factions,
        "loyalty_risks": risks,
        "identity": str(getattr(state, "stage", "流亡军")),
    }
