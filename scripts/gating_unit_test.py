"""gating.evaluate_gate 纯单元自测（零 LLM，可复现）。

跑：.venv/bin/python scripts/gating_unit_test.py
验证：布尔树 and/or 嵌套、character/event 叶子、扁平 dict 向后兼容、空 gate 恒真、缺数据判 False。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ming_sim.db import GameDB
from ming_sim.gating import evaluate_gate

PASS = 0
FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  [OK ] {name}: {got}")
    else:
        FAIL += 1
        print(f"  [XX ] {name}: got {got!r} want {want!r}")


def setup_db() -> GameDB:
    db = GameDB(":memory:")
    db.init_schema()
    c = db.conn

    def add_char(name, office, status, power, loc):
        c.execute(
            "INSERT INTO characters (name, office, office_type, faction, personal_skills, "
            "loyalty, ability, integrity, courage, style, status, power_id, location) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, office, "边镇", "军队", "[]", 50, 50, 50, 50, "", status, power, loc),
        )

    add_char("关羽", "前将军，驻守荆州", "active", "liu_bei", "jingzhou")
    add_char("张飞", "车骑将军，驻守阆中", "active", "liu_bei", "langzhong")
    # 最小 regions：放一个带 unrest 的省，验数值叶子 + 扁平 dict
    c.execute(
        "INSERT INTO regions (id, name, kind, population, public_support, unrest, "
        "natural_disaster, human_disaster, registered_land, hidden_land, tax_per_turn, "
        "gentry_resistance, military_pressure, status, controlled_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("jingzhou", "荆州", "州", 100, 40, 70, 0, 0, 0, 0, 0, 0, 0, "正常", "liu_bei"),
    )
    c.commit()
    return db


# guan_yu 的 require 布尔树（or-in-and）
GUAN_REQUIRE = {
    "and": [
        {"or": [
            {"key": "char.关羽.office_contains", "op": "contains", "val": "前将军"},
            {"key": "char.关羽.office_contains", "op": "contains", "val": "大将军"},
        ]},
        {"key": "char.关羽.in_region", "op": "==", "val": "jingzhou"},
        {"key": "char.张飞.in_region", "op": "==", "val": "langzhong"},
    ]
}


def main() -> int:
    db = setup_db()
    m = {"国库": 200, "民心": 40}

    print("== 向后兼容：扁平 dict == 显式 and ==")
    check("flat {国库<=240}", evaluate_gate({"国库": "<=240"}, m, db), True)
    check("flat == and 等价", evaluate_gate({"and": [{"key": "国库", "cond": "<=240"}]}, m, db), True)
    check("flat 两条全满足", evaluate_gate({"国库": "<=240", "民心": ">=30"}, m, db), True)
    check("flat 一条不满足", evaluate_gate({"国库": "<=240", "民心": ">=50"}, m, db), False)
    check("flat 文本相等 region", evaluate_gate({"region.jingzhou.controlled_by": "==liu_bei"}, m, db), True)
    check("flat 数值 region", evaluate_gate({"region.jingzhou.unrest": ">=65"}, m, db), True)

    print("== 空 gate / 非法 ==")
    check("空 dict 恒真", evaluate_gate({}, m, db), True)
    check("None 恒真", evaluate_gate(None, m, db), True)
    check("非 dict 判 False", evaluate_gate("xx", m, db), False)

    print("== guan_yu require：关羽在荆州（初始）应 True ==")
    check("初始(驻守荆州@jingzhou)", evaluate_gate(GUAN_REQUIRE, m, db), True)

    print("== 调关羽到成都 → False ==")
    db.conn.execute("UPDATE characters SET location='chengdu' WHERE name='关羽'")
    db.conn.commit()
    check("关羽@chengdu + 张飞@langzhong", evaluate_gate(GUAN_REQUIRE, m, db), False)

    print("== or 两支分别命中 ==")
    db.conn.execute("UPDATE characters SET office='大将军' WHERE name='关羽'")
    db.conn.execute("UPDATE characters SET location='jingzhou' WHERE name='关羽'")
    db.conn.commit()
    check("office=大将军（or 第二支）", evaluate_gate(GUAN_REQUIRE, m, db), True)

    print("== in_region 为空 → 该叶子 False（没地点就当不过）==")
    db.conn.execute("UPDATE characters SET location='' WHERE name='关羽'")
    db.conn.commit()
    check("关羽 location 空", evaluate_gate(GUAN_REQUIRE, m, db), False)

    print("== 人物不存在 → False ==")
    db.conn.execute("DELETE FROM characters WHERE name='关羽'")
    db.conn.commit()
    check("删关羽行", evaluate_gate(GUAN_REQUIRE, m, db), False)

    print("== char.status / char.power 叶子 ==")
    check("张飞 status==active", evaluate_gate({"key": "char.张飞.status", "op": "==", "val": "active"}, m, db), True)
    check("张飞 status==dead", evaluate_gate({"key": "char.张飞.status", "op": "==", "val": "dead"}, m, db), False)
    check("张飞 power==liu_bei", evaluate_gate({"key": "char.张飞.power", "op": "==", "val": "liu_bei"}, m, db), True)

    print("== event.<id>.triggered 叶子（未触发 → false）==")
    check("event 未触发", evaluate_gate({"key": "event.jisi_lubian.triggered", "op": "==", "val": "true"}, m, db), False)

    print()
    print(f"==== PASS={PASS}  FAIL={FAIL} ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
