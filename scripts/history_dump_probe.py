"""推演：dump 大臣跨多回合喂 LLM 的完整 message 列表，验跨月历史顺序。

patch Model.response 截 messages（不烧真 LLM，返假回复），跑真 GameSession：
跨 3 个月、每月召同一大臣聊 2 轮，复刻 web_app 流程
（_history_messages 拼历史 → session.chat(history_messages=) → 落 chat_messages）。
每轮打印实际进模型的 system/user/assistant 排列，看往月是否在本月之前、时序是否正确。

跑法：set -a; source .env; set +a; .venv/bin/python scripts/history_dump_probe.py
（.env 只为起 config，真 LLM 调用被 patch 掉，不花钱不联网。）
"""
from __future__ import annotations
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agno.models.base import Model
from agno.models.message import Message
from agno.models.response import ModelResponse
from agno.models.openai import OpenAIChat

from ming_sim.session import GameSession
from ming_sim.registry import NUM_HISTORY_RUNS
from ming_sim.llm_config import load_llm_config

MINISTER = "毕自严"   # 户部尚书，开局在朝
FAKE_REPLY_PREFIX = "【假回复】臣以为"
_call_no = 0


def _fake_response(self, messages, *a, **k):
    """截真实进模型的 messages（只 dump 大臣对话那种），返假回复不联网。"""
    global _call_no
    # 只 dump 含大臣 system（minister_agent）的调用，跳过拟旨/simulator/extractor 等
    sys_msgs = [m for m in messages if m.role == "system"]
    is_minister = any("你当前扮演" in (str(m.content) or "") for m in sys_msgs)
    if is_minister:
        _call_no += 1
        print(f"\n{'='*70}\n  第 {_call_no} 次大臣对话调用 — 进模型的 messages（{len(messages)} 条）\n{'='*70}")
        for m in messages:
            fh = getattr(m, "from_history", False)
            tag = "  ⟵往月" if fh else ""
            content = str(m.content or "").replace("\n", " ⏎ ")
            head = content[:90] + ("…" if len(content) > 90 else "")
            print(f"  [{m.role:9}]{tag} {head}")
    return ModelResponse(role="assistant", content=f"{FAKE_REPLY_PREFIX}（call#{_call_no}）当如此办理。")


def _history_messages(db, minister_name):
    """复刻 web_app.GameServer._history_messages：从 chat_messages 读尾 N 轮真历史。"""
    rows = db.load_recent_chat_rounds(minister_name, NUM_HISTORY_RUNS)
    return [
        Message(role=("user" if r["role"] == "user" else "assistant"),
                content=r["content"], from_history=True)
        for r in rows
    ]


def _do_chat(session, minister_name, text):
    """复刻 web_app 流程：session.chat（历史走 agno 每月一个 session 自管）→ 落 chat_messages（仅展示）。
    注：原自管历史前置已废（改回 agno session 自管），本探针 _history_messages 仅留作旧路对照。"""
    result = session.chat(minister_name, text)
    # 复刻 _chat_payload 落库（整轮 user+minister，仅供展示）
    session.db.append_chat_message(minister_name, session.state.turn, "user", text)
    session.db.append_chat_message(minister_name, session.state.turn, "minister", result.answer)
    return result.answer


def main():
    Model.response = _fake_response  # 全局 patch，省真 LLM

    db = "data/probe_history_dump.db"
    if os.path.exists(db):
        os.remove(db)
    if os.path.exists(db + ".emperor.db"):
        os.remove(db + ".emperor.db")
    llm_config = load_llm_config(
        os.environ.get("OPENAI_BASE_URL", "http://x"),
        os.environ.get("OPENAI_MODEL", "fake-model"),
        api_key=os.environ.get("OPENAI_API_KEY", "fake-key"),
    )
    session = GameSession(db, llm_config)

    # 每月聊 2 句，跨 3 个月，全召同一大臣
    monthly_questions = [
        ["一月：太仓存银几何？", "一月：辽饷缺口怎么补？"],
        ["二月：上月辽饷的事办得如何？", "二月：宗室禄米可有裁减余地？"],
        ["三月：京营欠饷拖到几时？", "三月：盐税整顿你怎么看？"],
    ]

    for month_idx, questions in enumerate(monthly_questions, 1):
        session.begin_turn()
        print(f"\n\n############ 第 {month_idx} 月 "
              f"(turn={session.state.turn}, {session.state.year}.{session.state.period:02d}) "
              f"召见 {MINISTER} ############")
        for q in questions:
            print(f"\n>>> 皇帝问：{q}")
            ans = _do_chat(session, MINISTER, q)
            print(f"<<< {MINISTER}答：{ans}")
        if month_idx < len(monthly_questions):
            session.advance_without_decree()   # 不结算，直接进下月

    print("\n\n========== 验证要点 ==========")
    print("· 第2、3月每轮：system 之后应先排【往月】历史（fh=⟵往月），再排本月已聊轮，最后本月新问")
    print(f"· 历史滑窗 = 尾 {NUM_HISTORY_RUNS} 轮，跨月连续")
    print("· 本月新问那条不带 ⟵往月（fh=False）→ 正常入库")


if __name__ == "__main__":
    main()
