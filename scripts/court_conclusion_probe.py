"""朝会裁断结构化输出验证脚本。

直接调 WebGame.court_chat_stream，跑一场真朝议，打印 conclusion 事件的
content + options，检查 <<DECISION>> JSON 解析是否给出完整可下旨方案
（而不是正则切出来的句子片段）。

用法：
  set -a; source .env; set +a   # 或已在环境变量里有 OPENAI_*
  .venv/bin/python scripts/court_conclusion_probe.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 用独立临时档，不碰真存档
os.environ["MING_SIM_DB"] = str(ROOT / "data" / "court_conclusion_probe.db")
os.environ.setdefault("MING_SIM_SEED", "7")

# 清掉残留临时档，保证干净开局
for suffix in ("", "-shm", "-wal", ".emperor.db", ".emperor.db-shm", ".emperor.db-wal"):
    p = Path(os.environ["MING_SIM_DB"] + suffix)
    if p.exists():
        p.unlink()

import web_app  # noqa: E402

game = web_app.WebGame(fresh=True)
print(f"=== 开局：{game.session.state.year}年{game.session.state.period}月，turn={game.session.state.turn} ===")

# 取在场可参会大臣（内阁+六部范围），自动取前 4 个
roster = game._active_court_ministers([])
names = [c.name for c in roster if c.office_type in ("内阁", "户部", "兵部", "吏部", "刑部", "工部", "礼部")][:4]
print(f"参会大臣：{names}")

message = "陕西连年大旱、流民四起，辽东军饷又告急，钱粮从哪里出？诸卿议一议章程。"
print(f"\n御问：{message}\n")
print("=" * 60)

conclusion_event = None
for event in game.court_chat_stream(message, names):
    etype = event.get("type")
    if etype == "speaker":
        print(f"\n[{event.get('speaker')}]", end=" ", flush=True)
    elif etype == "delta":
        print(event.get("delta", ""), end="", flush=True)
    elif etype == "reply":
        pass  # 完整段已通过 delta 流式打印
    elif etype == "conclusion":
        conclusion_event = event
    elif etype == "error":
        print(f"\n!! ERROR: {event}")
    elif etype == "done":
        pass

print("\n" + "=" * 60)
if conclusion_event:
    print("\n--- 朝议结论正文 ---")
    print(conclusion_event.get("content"))
    print("\n--- 裁断选项 options（应为完整可下旨方案，非片段）---")
    options = conclusion_event.get("options") or []
    if not options:
        print("(空 —— <<DECISION>> 解析失败或 LLM 未按格式输出)")
    for i, opt in enumerate(options, 1):
        print(f"{i}. {opt}")
        frag_like = len(opt) < 8 or opt.strip().startswith(("一、", "二、", "三、", "四、", "甲、", "乙、"))
        if frag_like:
            print("   ^^ 警告：看起来仍像片段，不像完整旨意")
else:
    print("\n!! 未收到 conclusion 事件")
