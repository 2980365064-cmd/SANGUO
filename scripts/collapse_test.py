"""崩坏判据测试（零 LLM）：验证去 kind 化后，situation 预设事件能否按
effect_on_fail 是否非空正确崩坏。

跑：.venv/bin/python scripts/collapse_test.py
对每个 situation 预设事件：event_to_issue 立 issue → advance_issue(delta_bar=-100)：
  - 期望可崩（effect_on_fail 非空）→ status=failed
  - 期望不可崩（effect_on_fail 空）→ status=active 且 bar==1（floor）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim import issues as issues_mod
from ming_sim.issues import event_to_issue
from ming_sim.models import GameState

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK ] {name} {detail}")
    else:
        FAIL += 1
        print(f"  [XX ] {name} {detail}")


def main() -> int:
    content = GameContent.load()
    issues_mod.bind_content(content)
    db = GameDB(":memory:", content)
    db.init_schema()
    state = GameState(year=1630, period=1, turn=30, metrics={"国库": 100, "内库": 50, "民心": 50, "皇威": 50})

    # 所有 situation 预设事件（node/ending 不走 event_to_issue）
    sit_events = [e for e in (*content.events, *content.seed_events) if e.event_type == "situation"]
    print(f"situation 预设事件数：{len(sit_events)}")
    print()

    for ev in sit_events:
        expect_collapse = bool(ev.effect_on_fail)
        issue_id = event_to_issue(db, state, ev)
        if issue_id is None:
            check(ev.id, False, "(event_to_issue 返回 None，立项失败)")
            continue
        # 推 bar 到底
        row = db.advance_issue(state, issue_id, trigger_kind="test", delta_bar=-100)
        status = row["status"]
        bar = row["bar_value"]
        if expect_collapse:
            check(ev.id, status == "failed", f"期望崩坏→failed，实际 status={status} bar={bar}")
        else:
            check(ev.id, status == "active" and bar == 1,
                  f"期望不崩→active@bar1，实际 status={status} bar={bar}")

    print()
    print(f"==== PASS={PASS}  FAIL={FAIL} ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
