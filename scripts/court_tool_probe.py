"""大臣 court tool 触发率探针。

给大臣明确诱导其调某 court tool 的场景 message，跑真 LLM，统计目标 tool 是否触发。
每场景默认重复 5 次，看触发稳不稳、要不要加强 prompt。

覆盖 tool：
  propose_directive   拟旨（任意理政大臣）
  propose_appointment 吏部铨选任命
  secret_order        密令（司礼监/厂卫）
  present_consort_candidates  选妃呈选（礼部/司礼监）
  cultivate_consort   调教妃嫔（召后宫妃嫔时）

用法：
  set -a; source .env; set +a
  .venv/bin/python scripts/court_tool_probe.py                 # 全 tool，每场景 5 次
  .venv/bin/python scripts/court_tool_probe.py --tools 拟旨,密令 --repeat 3
  .venv/bin/python scripts/court_tool_probe.py --db data/tooltest.db

只读跑局取数，不改平衡不改 prompt。每次 run 独立建临时档（默认 data/court_tool_probe.db）。
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# .env 注入（兼容 CLI_* → OPENAI_* 映射，与 secret_order_probe 一致）
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
for src, dst in (("CLI_API_KEY", "OPENAI_API_KEY"),
                 ("CLI_BASE_URL", "OPENAI_BASE_URL"),
                 ("CLI_MODEL", "OPENAI_MODEL")):
    if os.environ.get(src) and not os.environ.get(dst):
        os.environ[dst] = os.environ[src]

from ming_sim.content import GameContent
from ming_sim.llm_config import load_llm_config
from ming_sim.session import GameSession


# 每个 tool 一组场景：(中文名, 目标 tool_name, 承办大臣, 诱导 message)。
# message 写成皇帝明确要这件事，正常情况下大臣应调对应 tool。
# 承办大臣取开局在朝者；选妃用礼部/司礼监；调教需先有可召的后宫妃嫔（开局未必有，缺则跳过并提示）。
SCENARIOS: List[Dict] = [
    {
        "label": "拟旨",
        "tool": "propose_directive",
        "minister": "毕自严",
        "messages": [
            "拟旨如下：拨内库银六十万两，补发辽东关宁军欠饷。",
            "辽东关宁军欠饷已久、军心浮动，朕意拨内库银六十万两补发。卿即拟一道旨意来，朕用印颁下。",
        ],
    },
    {
        "label": "调税",
        "tool": "adjust_tax",
        "minister": "毕自严",
        "messages": [
            # 前端「调税」按钮固定话术（硬触发 tax-adjust skill）
            "调税如下：把田赋全国加征三成。",
            "调税如下：把南直隶田赋加征四成。",
            "调税如下：把盐税全国减半。",
            "调税如下：把陕西田赋罢废。",
            # 自然语言诱导（软触发）
            "辽饷不敷，朕意全国田赋加征三成，以济军需。卿户部即办，立项征收。",
            "陕西连年大旱、流民四起，着即罢废陕西一省田赋，以纾民困。卿即办理。",
        ],
    },
    {
        "label": "任命",
        "tool": "propose_appointment",
        "minister": "王绍徽",
        "messages": [
            "蓟辽总督出缺，边事孔急，须得一通晓兵事、可独当一面者。卿是吏部，即拟一员来补此缺。",
            "陕西巡抚胡廷宴抚寇无能，已革职。卿即铨选一员干练之臣补陕西巡抚，安定地方。",
        ],
    },
    {
        "label": "密令",
        "tool": "secret_order",
        "minister": "曹化淳",
        "messages": [
            "密令如下：密查阉党余孽内外暗通款曲者，逐一密记底册，密奏御前，不得声张。",
            "朕疑兵部尚书与边将私通书信、虚报军功。卿暗中查访其往来书札，密报于朕，勿令人知。",
        ],
    },
    {
        "label": "选妃",
        "tool": "present_consort_candidates",
        "minister": "王体乾",
        "messages": [
            "选妃如下：从良家女子中拣选数名淑媛，呈上名册供朕拣择。",
            "朕意充实后宫，卿即呈选几位才貌出众、堪为妃嫔的候选女子，列名以闻。",
        ],
    },
    {
        "label": "调教",
        "tool": "cultivate_consort",
        "minister": "__consort__",   # 运行时换成一个在场后宫妃嫔
        "messages": [
            "爱妃近来可有长进？朕望你多习诗书礼仪，温婉持重，将来协理六宫。",
            "你天资聪颖，朕盼你研习琴棋书画、通晓宫闱规矩，日后好母仪后宫。",
        ],
    },
]


def _load_env_llm():
    return load_llm_config(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        os.environ.get("OPENAI_API_KEY", ""),
    )


def _first_active_consort(content: GameContent) -> Optional[str]:
    for name, ch in content.characters.items():
        if ch.office_type == "后宫" and ch.status == "active":
            return name
    return None


_RUN_SEQ = 0


def _run_once(sess: GameSession, minister: str, message: str) -> Tuple[List[str], str]:
    """跑一轮大臣对话，返回 (本轮触发的 tool_name 列表, answer 摘要)。
    直接用 registry agent.run 读 run_output.tools，覆盖所有 tool（含 consort）。

    **每次用唯一 session_id + add_history_to_context=False**，隔离 agno 对话历史——
    否则同一大臣连跑多次共享 session，第 2 次起 agent 看到自己上轮已答/已调，
    后续就纯文字不再调 tool，触发率被历史污染成假 0%。测「单轮触发率」必须无历史。"""
    global _RUN_SEQ
    _RUN_SEQ += 1
    character = sess._character(minister)
    agent = sess.registry.get(character)
    run_output = agent.run(
        message,
        session_id=f"tooltest-{minister}-{_RUN_SEQ}",
        add_history_to_context=False,
    )
    fired = [getattr(t, "tool_name", "") for t in (getattr(run_output, "tools", None) or [])]
    from ming_sim.llm_model import extract_agent_text
    answer = (extract_agent_text(run_output) or "").replace("\n", " ")[:60]
    return fired, answer


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/court_tool_probe.db")
    p.add_argument("--start-ym", default="1627.10")
    p.add_argument("--repeat", type=int, default=5, help="每个场景 message 重复次数")
    p.add_argument("--tools", default="", help="只测这些（逗号分隔中文名，如 拟旨,密令）；空=全测")
    args = p.parse_args()

    want = {s.strip() for s in args.tools.split(",") if s.strip()} or None

    # 清旧档，保证干净起步
    for suffix in ("", ".emperor.db", "_agno.db"):
        f = Path(args.db + suffix)
        if f.exists():
            f.unlink()

    content = GameContent.load()
    sess = GameSession(args.db, _load_env_llm(), content=content,
                       verify_llm=True, start_ym=args.start_ym)
    sess.begin_turn()

    consort_name = _first_active_consort(content)

    # 统计：label → (命中次数, 总次数, 旁触发其它 tool 的样本)
    stats: Dict[str, Dict] = {}
    print(f"\n大臣 court tool 触发率探针｜每场景 message × {args.repeat} 次\n" + "=" * 56)

    for sc in SCENARIOS:
        label = sc["label"]
        if want and label not in want:
            continue
        target = sc["tool"]
        minister = sc["minister"]
        if minister == "__consort__":
            if not consort_name:
                print(f"\n【{label}】跳过：开局无在场后宫妃嫔可召（cultivate_consort 需先有妃嫔）。")
                continue
            minister = consort_name

        hit = total = 0
        other_fired: Dict[str, int] = defaultdict(int)
        print(f"\n【{label}】tool={target} 承办={minister}")
        for msg in sc["messages"]:
            for i in range(args.repeat):
                total += 1
                try:
                    fired, answer = _run_once(sess, minister, msg)
                except Exception as exc:
                    print(f"  ! 第{total}次异常：{exc}")
                    continue
                ok = target in fired
                hit += int(ok)
                for t in fired:
                    if t != target:
                        other_fired[t] += 1
                mark = "✓" if ok else "✗"
                extra = f" [旁触发:{','.join(t for t in fired if t != target)}]" if (not ok and fired) else ""
                print(f"  {mark} fired={fired or '无'}{extra}  «{answer}»")
        stats[label] = {"hit": hit, "total": total, "target": target, "other": dict(other_fired)}

    # 汇总
    print("\n" + "=" * 56 + "\n触发率汇总：")
    print(f"  {'tool':<26}{'触发率':>10}   评级")
    for label, s in stats.items():
        rate = s["hit"] / s["total"] if s["total"] else 0
        grade = "稳定" if rate >= 0.9 else ("尚可" if rate >= 0.7 else ("偏弱-建议加强prompt" if rate >= 0.4 else "差-必须加强prompt"))
        print(f"  {label+'/'+s['target']:<26}{s['hit']}/{s['total']} ({rate:.0%})".ljust(40) + f"  {grade}")
        if s["other"]:
            print(f"      旁触发其它 tool：{s['other']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
