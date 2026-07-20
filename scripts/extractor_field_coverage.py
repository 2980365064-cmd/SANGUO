"""extractor 全字段覆盖测试。

读 scripts/extractor_cases.json，逐 case：
  1. 起独立临时 DB（reset），begin_turn
  2. 可选 sql / set_metric / jump_to（透传）
  3. add_directive(诏书) → enter_review → resolve_turn(cheat=既成事实)
  4. 从 db.get_turn_extraction(turn) 读 extractor_output（4 档房合并 JSON）
  5. 算「非空顶层字段集」对照 case.expect_fields → PASS / 缺失 / 多余
  6. 负样本（expect_fields=[] 且带 neg_note）：抽出该为空，抽到即 FAIL

结论写 markdown（默认 docs/extractor-field-coverage.md），并在末尾做
「字段遗漏校验」：all_fields 里未被任何 case expect 覆盖的字段 → 标红，
便于人工补 case。

用法：
  set -a; source .env; set +a
  .venv/bin/python scripts/extractor_field_coverage.py            # 跑全部
  .venv/bin/python scripts/extractor_field_coverage.py --limit 5  # 先验脚本
  .venv/bin/python scripts/extractor_field_coverage.py --only c099,c100
  .venv/bin/python scripts/extractor_field_coverage.py --out docs/cov.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ming_sim.session import GameSession            # noqa: E402
from ming_sim.llm_config import load_llm_config     # noqa: E402
import ming_sim.decree as _decree                   # noqa: E402

CASES_FILE = ROOT / "scripts" / "extractor_cases.json"
DEFAULT_OUT = ROOT / "docs" / "extractor-field-coverage.md"


def disable_hitl() -> None:
    """测试时关掉 HITL：保留 <<DECISION>> 块剥离（防污染邸报），但永不暂停。

    根因：phase1 检测到决策点会 save_resolve_context 暂停，但该上下文不含
    cheat_directive，phase2 续跑时 cheat 丢失 → extractor 收不到既成事实 →
    目标字段漏抽（FAIL）。单字段测试不需要 HITL，直接令 decisions 恒为空，
    强制走「无决策点·透明续跑」分支，cheat 全程保留喂 extractor。
    """
    _orig = _decree.parse_decision_blocks

    def _no_decisions(narrative: str):
        clean, _decisions = _orig(narrative)  # 仍剥离决策块，只丢弃 decisions
        return clean, []

    _decree.parse_decision_blocks = _no_decisions


def disable_simulator() -> None:
    """跳过 simulator LLM：只走「诏书 → cheat 既成事实 → extractor」结算链。

    原因：simulator（season_simulator）每 case 思考链长达数分钟，且会把诏书
    演成失败/减额/全景叙事，把目标事件淹没或推翻，干扰单字段验证。本测只想验
    「诏书+既成事实 → extractor 抽对字段」，simulator 的叙事发挥纯属噪声。

    patch 后：simulator_payload 照常构建（extractor 的 system context 需要它，
    无 LLM、快），但 narrative 直接取诏书原文，不调 simulator LLM。cheat 仍走
    decree.py 的 CHEAT_NARRATIVE_PREFIX 注入路径拼在 narrative 前喂 extractor。
    每 case 从 ~5min 降到 ~30s，且去掉 simulator 噪声。
    """
    import ming_sim.simulation as _sim
    _orig = _sim.build_simulator_payload

    # 用 *args/**kwargs 吞掉所有调用参数，避免真实 simulate_season_with_payload
    # 签名增删（如新增 structured_directives）导致 fake 收不下而整步骤异常→extractor 被跳过。
    def _fake_simulate(agent, state, db, decree_text, previous_narrative,
                       *args, **kwargs):
        payload = kwargs.get("simulator_payload") or _orig(
            state, db, decree_text, previous_narrative,
            deaths_this_turn=kwargs.get("deaths_this_turn"),
            debuts_this_turn=kwargs.get("debuts_this_turn"),
            relevant_memories=kwargs.get("relevant_memories"),
            secret_orders=kwargs.get("secret_orders"),
        )
        narrative = f"《{state.year}年{state.period}月诏书施行》\n{decree_text}"
        return narrative, payload

    # decree.py 内 from simulation import simulate_season_with_payload → patch 引用名
    _decree.simulate_season_with_payload = _fake_simulate


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default=str(CASES_FILE))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--start-ym", default="1631.08", help="统一开局年月")
    p.add_argument("--limit", type=int, default=0, help=">0 只跑前 N 个 case")
    p.add_argument("--only", default="", help="逗号分隔 case id，只跑这些")
    p.add_argument("--tmp-dir", default="data/cov", help="临时 DB 目录")
    p.add_argument("--keep-db", action="store_true", help="不删临时 DB（调试）")
    p.add_argument("--keep-hitl", action="store_true",
                   help="保留 HITL（默认关）。默认关掉 HITL 以免决策点暂停吞掉 cheat")
    p.add_argument("--keep-simulator", action="store_true",
                   help="保留 simulator LLM（默认跳）。默认跳过以提速并去噪，直接 诏书+cheat → extractor")
    return p.parse_args()


def _nonempty_top_fields(extracted: dict) -> set[str]:
    """抽出 JSON 里有实际内容的顶层字段集合。{} / [] / null / '' 视为空。"""
    out: set[str] = set()
    if not isinstance(extracted, dict):
        return out
    for k, v in extracted.items():
        if v is None or v == {} or v == [] or v == "":
            continue
        out.add(k)
    return out


# 字段名中英别名：expect_values 里写中文，实抽 JSON 可能落英文 key（mode/value/direction…）
_VALUE_KEY_ALIASES = {
    "口径": "mode", "数值": "value", "增量": "delta", "账户": "account",
    "方向": "direction", "显示名": "display", "初值": "init_value",
    "计税公式": "formula", "计税依据": "basis", "税率单位": "rate_unit",
    "原因": "reason", "目标编号": "target_id", "用途": "purpose",
    "局势编号": "issue_id", "进度增量": "delta_bar", "密令编号": "order_id",
    "状态": "status", "新势力": "new_power", "归属": "owner_power",
}


def _val_eq(want: object, got: object) -> bool:
    """单值比对：数字容差 0.01，其余按字符串精确（去空白）。"""
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        return abs(float(want) - float(got)) <= 0.01
    return str(want).strip() == str(got).strip()


def _subdict_matches(want: dict, got: dict) -> bool:
    """got 是否满足 want 里**每一个**键值（只查 want 写出的键，多余键无所谓）。
    键支持中英别名：want 写 '口径'，got 落 'mode' 也算命中。"""
    if not isinstance(got, dict):
        return False
    for wk, wv in want.items():
        candidates = {wk, _VALUE_KEY_ALIASES.get(wk, wk)}
        # 反向：want 写英文、got 落中文
        candidates |= {cn for cn, en in _VALUE_KEY_ALIASES.items() if en == wk}
        gv = next((got[c] for c in candidates if c in got), KeyError)
        if gv is KeyError or not _val_eq(wv, gv):
            return False
    return True


def _check_expect_values(expect_values: dict, extracted: dict) -> list[str]:
    """深度值校验。返回失败说明列表（空=全过）。
    - list 字段（如 财政制度变化/钱粮收支）：want 每条断言，须在实抽 list 里找到**一条**子项满足。
    - dict 字段（如 地区变化 {region_id:{...}}）：want 每个 key，实抽对应 key 须满足其断言子 dict。
    """
    fails: list[str] = []
    for field, want in (expect_values or {}).items():
        got = extracted.get(field)
        if got is None or got == [] or got == {}:
            fails.append(f"{field}: 实抽为空，无法核值")
            continue
        if isinstance(want, list):
            arr = got if isinstance(got, list) else [got]
            for i, w in enumerate(want):
                if not any(_subdict_matches(w, item) for item in arr):
                    fails.append(f"{field}[期望项{i}]={json.dumps(w, ensure_ascii=False)} "
                                 f"未在实抽中找到匹配；实抽={json.dumps(arr, ensure_ascii=False)[:200]}")
        elif isinstance(want, dict):
            gd = got if isinstance(got, dict) else {}
            for wk, wv in want.items():
                if wk not in gd:
                    fails.append(f"{field}.{wk} 缺失；实抽键={list(gd.keys())}")
                elif isinstance(wv, dict):
                    if not _subdict_matches(wv, gd.get(wk)):
                        fails.append(f"{field}.{wk}={json.dumps(wv, ensure_ascii=False)} "
                                     f"不符；实抽={json.dumps(gd.get(wk), ensure_ascii=False)[:120]}")
                elif not _val_eq(wv, gd.get(wk)):
                    fails.append(f"{field}.{wk} 期望 {wv!r} 实得 {gd.get(wk)!r}")
    return fails


def run_case(case: dict, args: argparse.Namespace) -> dict:
    """跑单 case，返回结果 dict。"""
    cid = case["id"]
    db_path = os.path.join(ROOT, args.tmp_dir, f"{cid}.db")
    agno_db = db_path.replace(".db", "_agno.db")
    emperor_db = f"{agno_db}.emperor.db"
    for p in (db_path, agno_db, emperor_db):
        if os.path.exists(p):
            os.remove(p)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    base_url = os.environ.get("OPENAI_BASE_URL", "")
    model = os.environ.get("OPENAI_MODEL", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    llm_config = load_llm_config(base_url, model, api_key=api_key)

    result = {"id": cid, "expect": case.get("expect_fields", []), "got": [],
              "missing": [], "extra": [], "status": "ERROR", "error": "",
              "emperor_fate": None,
              # neg 分支：负样本(neg_note)或任何带 neg_check_fields 的「禁抽」断言都走它
              "neg": bool(case.get("neg_note")) or bool(case.get("neg_check_fields")),
              "value_fails": []}
    try:
        session = GameSession(db_path, llm_config, start_ym=args.start_ym or None)

        if case.get("jump_to"):
            y, m = case["jump_to"].split(".")
            ty, tm = int(y), int(m)
            cy, cm = session.state.year, session.state.period
            diff = (ty - cy) * 12 + (tm - cm)
            if diff >= 0:
                session.state.year, session.state.period = ty, tm
                session.state.turn += diff
                session.db.save_state(session.state)

        session.begin_turn()
        turn = session.state.turn

        for spec in case.get("set_metric", []):
            key, val = spec.split("=", 1)
            session.state.metrics[key.strip()] = int(val)
        session.db.save_state(session.state)

        for sql in case.get("sql", []):
            session.db.conn.execute(sql)
        session.db.conn.commit()

        session.add_directive(case["directive"], notes="cov")
        session.enter_review()

        res = session.resolve_turn(decree="", cheat_directive=case.get("cheat", ""))
        if getattr(res, "awaiting", False):
            choices = []
            for d in res.decisions:
                opts = d.get("options") or []
                choices.append(dict(opts[0]) if opts else {})
            session.submit_decisions(choices)
        session.end_turn()

        ext = session.db.get_turn_extraction(turn) or {}
        extracted = ext.get("extractor_output", {})
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except Exception:
                extracted = {}

        got = _nonempty_top_fields(extracted)
        # 崇祯结局特判：非 null 才算命中
        fate = extracted.get("崇祯结局") if isinstance(extracted, dict) else None
        result["emperor_fate"] = fate
        if fate in (None, "", "null"):
            got.discard("崇祯结局")
        else:
            got.add("崇祯结局")

        expect = set(case.get("expect_fields", []))
        # expect 里可能含子字段名（如 士绅阻力/军事压力）——非顶层，忽略出顶层比对
        ALL = set(CASES_META["all_fields"])
        expect_top = expect & ALL
        result["got"] = sorted(got)
        result["missing"] = sorted(expect_top - got)
        result["extra"] = sorted(got - expect_top)

        if result["neg"]:
            # 负样本：验「不该抽某敏感字段」。给了 neg_check_fields 则只查这些字段
            # 不在 got 即 PASS（其余联想字段无所谓）；没给则回落「全空才 PASS」。
            # 混合断言：若同时给了 expect_fields（如「该抽 A 且不该抽 B」），
            # 先校验正向 missing 再校验负向 violations，两者都过才 PASS。
            check = set(case.get("neg_check_fields") or [])
            violated = sorted(check & got)
            result["neg_violations"] = violated
            if violated:
                result["error"] = f"误抽敏感字段: {'、'.join(violated)}"
            if check:
                if expect_top:
                    # 混合：缺正向期望或误抽敏感字段，任一即 FAIL
                    result["status"] = "PASS" if (not result["missing"] and not violated) else "FAIL"
                else:
                    # 纯负样本：只看 neg_check_fields 是否被误抽
                    result["missing"] = [] if violated else result["missing"]
                    result["status"] = "PASS" if not violated else "FAIL"
            else:
                # 无 neg_check_fields 的纯负样本：抽出任何字段即 FAIL
                result["status"] = "PASS" if not got else "FAIL"
        else:
            result["status"] = "PASS" if not result["missing"] else "FAIL"

        # 崇祯结局值校验
        if "expect_emperor_fate" in case:
            want = case["expect_emperor_fate"]
            ok = (fate == want) or (want is None and fate in (None, "", "null"))
            if not ok:
                result["status"] = "FAIL"
                result["error"] = f"emperor_fate={fate!r} 期望 {want!r}"

        # 深度值校验：顶层命中后核字段内部值（口径/数值/账户…）是否抽对。
        # 字段名对但值错（如『月额设为30』错成『增减-90』）会被这里抓出降 FAIL。
        if case.get("expect_values"):
            vfails = _check_expect_values(case["expect_values"], extracted)
            result["value_fails"] = vfails
            if vfails:
                result["status"] = "FAIL"
                joined = "；".join(vfails)
                result["error"] = (result["error"] + " | " if result["error"] else "") + f"值不符: {joined}"
    except Exception as exc:
        result["error"] = f"{exc}\n{traceback.format_exc()[:500]}"
    finally:
        if not args.keep_db:
            for p in (db_path, agno_db, emperor_db):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
    return result


CASES_META: dict = {}


def main() -> int:
    args = parse_args()
    if not (os.environ.get("OPENAI_BASE_URL") and os.environ.get("OPENAI_MODEL")
            and os.environ.get("OPENAI_API_KEY")):
        print("[ERROR] 需 export OPENAI_BASE_URL/OPENAI_MODEL/OPENAI_API_KEY", file=sys.stderr)
        return 2

    if not args.keep_hitl:
        disable_hitl()
        print("[cov] HITL 已关（防决策点暂停吞 cheat）。--keep-hitl 可保留")
    if not args.keep_simulator:
        disable_simulator()
        print("[cov] simulator 已跳（诏书+cheat 直喂 extractor，提速去噪）。--keep-simulator 可保留")

    global CASES_META
    CASES_META = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    all_fields = CASES_META["all_fields"]
    cases = CASES_META["cases"]

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    if only:
        cases = [c for c in cases if c["id"] in only]
    if args.limit > 0:
        cases = cases[: args.limit]

    print(f"[cov] 跑 {len(cases)} case，全字段 {len(all_fields)} 个")
    results = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} ...", flush=True)
        r = run_case(case, args)
        tag = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}.get(r["status"], "?")
        print(f"    {tag} got={r['got']} missing={r['missing']} extra={r['extra']}"
              + (f" err={r['error'][:80]}" if r["error"] else ""), flush=True)
        results.append(r)

    write_report(args.out, all_fields, cases, results, time.time() - t0)
    n_pass = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n[cov] 完成 {n_pass}/{len(results)} PASS。报告 → {args.out}")
    return 0 if n_pass == len(results) else 1


def write_report(out_path: str, all_fields: list, cases: list, results: list, secs: float) -> None:
    by_id = {r["id"]: r for r in results}
    # 字段级覆盖：每个顶层字段被哪些 case 期望 / 实际抽到过
    expected_by_field: dict[str, list[str]] = {f: [] for f in all_fields}
    got_by_field: dict[str, list[str]] = {f: [] for f in all_fields}
    for c in cases:
        for f in c.get("expect_fields", []):
            if f in expected_by_field:
                expected_by_field[f].append(c["id"])
    for r in results:
        for f in r["got"]:
            if f in got_by_field:
                got_by_field[f].append(r["id"])

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_fail = sum(1 for r in results if r["status"] == "FAIL")
    n_err = sum(1 for r in results if r["status"] == "ERROR")

    lines = []
    lines.append("# Extractor 全字段覆盖测试报告\n")
    lines.append(f"- 跑 case：**{len(results)}**　PASS **{n_pass}** / FAIL **{n_fail}** / ERROR **{n_err}**")
    lines.append(f"- 顶层字段总数：**{len(all_fields)}**")
    lines.append(f"- 耗时：{secs:.0f}s\n")

    # 1. 字段遗漏校验（核心）
    lines.append("## 一、字段遗漏校验\n")
    never_expected = [f for f in all_fields if not expected_by_field[f]]
    never_got = [f for f in all_fields if not got_by_field[f]]
    if never_expected:
        lines.append(f"⚠️ **无任何 case 验证的字段（{len(never_expected)}）**：" + "、".join(never_expected))
    else:
        lines.append("✅ 全部顶层字段都有 case 覆盖（每个字段至少被一个 case 的 expect_fields 引用）。")
    if never_got:
        lines.append(f"\n❌ **有 case 期望但实测从未抽到的字段（{len(never_got)}）**："
                     + "、".join(never_got) + "　← 需排查 prompt 或 case")
    else:
        lines.append("\n✅ 所有被期望的字段在实测中均至少命中过一次。")
    lines.append("")

    # 2. 字段覆盖矩阵
    lines.append("## 二、字段覆盖矩阵\n")
    lines.append("| 顶层字段 | 期望次数 | 实测命中次数 | 命中 case |")
    lines.append("|---|---|---|---|")
    for f in all_fields:
        gc = got_by_field[f]
        mark = "✅" if gc else ("⚠️" if expected_by_field[f] else "—")
        sample = "、".join(gc[:6]) + ("…" if len(gc) > 6 else "")
        lines.append(f"| {mark} {f} | {len(expected_by_field[f])} | {len(gc)} | {sample} |")
    lines.append("")

    # 3. 逐 case 明细
    lines.append("## 三、逐 case 明细\n")
    lines.append("| case | 状态 | 期望 | 实测命中 | 缺失 | 多余 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in cases:
        r = by_id[c["id"]]
        tag = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}.get(r["status"], "?")
        note = c.get("neg_note") or c.get("note") or r.get("error", "")
        lines.append(
            f"| {c['id']} | {tag} | {'、'.join(c.get('expect_fields', [])) or '—'} "
            f"| {'、'.join(r['got']) or '—'} | {'、'.join(r['missing']) or '—'} "
            f"| {'、'.join(r['extra']) or '—'} | {note[:60].replace(chr(10),' ')} |"
        )
    lines.append("")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
