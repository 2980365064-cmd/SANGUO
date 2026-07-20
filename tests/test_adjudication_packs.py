from types import SimpleNamespace

import ming_sim.adjudication as adjudication_module
from ming_sim.adjudication import (
    ADJUDICATION_KIND_POLICIES,
    record_pending_adjudication,
    run_adjudication,
    run_monthly_adjudication_batch,
)
from ming_sim.battle import build_battle_adjudication_pack
from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.db.secret_orders import build_secret_order_adjudication_pack, run_secret_order_ai_judge
from ming_sim.diplomacy import build_diplomacy_adjudication_pack, run_diplomacy_ai_judge
from ming_sim.government import build_personnel_adjudication_pack, run_personnel_ai_judge
from ming_sim.historical_events import build_world_event_adjudication_pack
from ming_sim.monthly_report import build_monthly_report
from ming_sim.national_focus import build_region_investment_adjudication_pack, start_region_investment
from ming_sim.power_ai import build_power_action_adjudication_pack, run_power_action_ai_judge
from ming_sim.siege import build_siege_adjudication_pack, start_siege
from ming_sim.supply import build_supply_adjudication_pack, run_supply_ai_judge, settle_army_supply


def _state(turn=1):
    return SimpleNamespace(
        turn=turn,
        year=208,
        period=8,
        metrics={"军资": 60, "民望": 55, "名分": 65, "士族支持": 45, "军心": 60, "粮秣": 60},
        collapse_turns=0,
        chengdu_crisis_turns=0,
        ended=False,
    )


def _board():
    db = GameDB(":memory:", content=GameContent.load())
    db.seed_static_data()
    return db


def _assert_pack(pack, kind):
    assert pack["protocol_version"] == 1
    assert pack["kind"] == kind
    assert pack["randomness_level"] == ADJUDICATION_KIND_POLICIES[kind]["randomness_level"]
    assert isinstance(pack["randomness_bounds"], dict)
    assert isinstance(pack["apply_contract"], dict)
    assert isinstance(pack["facts"], dict)
    assert isinstance(pack["rules"], dict)
    assert isinstance(pack["allowed_outcomes"], list)
    assert isinstance(pack["forbidden_outcomes"], list)
    assert isinstance(pack["validated_changes"], list)
    assert "source_tables" in pack["audit"]


def test_all_adjudication_pack_categories_are_built_from_structured_sources():
    db = _board()
    state = _state()
    try:
        battle = build_battle_adjudication_pack(
            db,
            state,
            {"attacker_ids": ["liubei_main"], "defender_ids": ["cao_main"], "node_id": "jiangling"},
        )
        _assert_pack(battle, "battle")

        siege_id = start_siege(db, state, "liubei_main", "jiangling")
        _assert_pack(build_siege_adjudication_pack(db, state, siege_id), "siege")
        _assert_pack(build_supply_adjudication_pack(db, state, "liubei_main"), "supply")
        _assert_pack(
            build_diplomacy_adjudication_pack(
                db,
                state,
                "liu_bei",
                "sun_quan",
                {
                    "treaty_key": "audit_envoy",
                    "treaty_type": "盟约",
                    "envoy": "诸葛亮",
                    "obligations": [{"type": "共同抗曹"}],
                    "territorial_claims": {},
                    "marriage_hostages": {},
                    "military_coordination": 20,
                },
            ),
            "diplomacy",
        )
        _assert_pack(build_region_investment_adjudication_pack(db, state, "jiangxia", "屯田粮仓"), "region_investment")
        _assert_pack(build_personnel_adjudication_pack(db, state, "chief_strategist", "诸葛亮"), "personnel")
        order_id = db.create_secret_order(state, "赵云", "护民暗线", "护送江夏流民，不得扰民。", ["护民"])
        _assert_pack(build_secret_order_adjudication_pack(db, state, order_id, viewer="赵云"), "secret_order")
        _assert_pack(build_power_action_adjudication_pack(db, state, "cao_cao"), "power_action")
        _assert_pack(build_world_event_adjudication_pack(db, state), "world_event")
    finally:
        db.close()


def test_ai_proposal_violations_enter_pending_review_instead_of_changing_world():
    db = _board()
    state = _state()
    try:
        supply_pack = build_supply_adjudication_pack(db, state, "liubei_main")
        before = db.conn.execute("SELECT manpower FROM armies WHERE id='liubei_main'").fetchone()[0]
        result = run_supply_ai_judge(
            db,
            state,
            supply_pack,
            {"outcome": "granary_supply", "narrative": "天降援军，兵力大增。", "changes": []},
        )
        assert result["status"] == "pending_review"
        assert db.conn.execute("SELECT manpower FROM armies WHERE id='liubei_main'").fetchone()[0] == before

        diplomacy_pack = build_diplomacy_adjudication_pack(
            db,
            state,
            "liu_bei",
            "sun_quan",
            {"obligations": [], "territorial_claims": {}, "marriage_hostages": {}, "military_coordination": 0},
        )
        result = run_diplomacy_ai_judge(
            db,
            state,
            diplomacy_pack,
            {"outcome": "accept_terms", "narrative": "条约生效并割让江夏。", "changes": []},
        )
        assert result["status"] == "pending_review"

        assert db.conn.execute("SELECT COUNT(*) FROM pending_adjudications").fetchone()[0] == 2
    finally:
        db.close()


def test_personnel_secret_and_power_judges_reject_unstructured_world_changes():
    db = _board()
    state = _state()
    try:
        personnel = build_personnel_adjudication_pack(db, state, "chief_strategist", "诸葛亮")
        assert run_personnel_ai_judge(
            db,
            state,
            personnel,
            {"outcome": "appoint_candidate", "changes": [{"kind": "spawn_army"}]},
        )["status"] == "pending_review"

        order_id = db.create_secret_order(state, "赵云", "查探敌营", "只许查证，不得擅杀。", ["敌情"])
        secret = build_secret_order_adjudication_pack(db, state, order_id, viewer="赵云")
        assert run_secret_order_ai_judge(
            db,
            state,
            secret,
            {"outcome": "close_done", "narrative": "密令成功，曹操死亡。", "changes": []},
        )["status"] == "pending_review"

        power = build_power_action_adjudication_pack(db, state, "cao_cao")
        assert run_power_action_ai_judge(
            db,
            state,
            power,
            {"outcome": "attack", "action_type": "annex", "region_control": {"jiangxia": "cao_cao"}, "changes": []},
        )["status"] == "pending_review"
    finally:
        db.close()


def test_monthly_report_surfaces_pending_adjudications():
    db = _board()
    state = _state(turn=2)
    try:
        pack = build_world_event_adjudication_pack(db, _state(turn=1))
        record_pending_adjudication(db, _state(turn=1), pack, "模型输出越界", {"narrative": "凭空灭国"})
        report = build_monthly_report(db, state)
        pending = next(section for section in report["sections"] if section["id"] == "pending")
        assert pending["items"]
        assert "模型输出越界" in pending["items"][0]["summary"]
    finally:
        db.close()


def test_unified_adjudication_dispatcher_routes_power_action_and_records_pending(monkeypatch):
    db = _board()
    state = _state()
    try:
        def fake_judge(_llm_config, _agno_db, pack, *, tag):
            selected = pack["facts"]["legal_candidates"][0]
            return {"outcome": selected["action_type"], "action": selected, "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
        result = run_adjudication(
            db,
            state,
            "power_action",
            "cao_cao",
            llm_config=object(),
            agno_db=None,
        )

        assert result["status"] == "validated"
        assert result["kind"] == "power_action"
        assert result["pack"]["subject_id"] == "cao_cao"
        assert result["validated"]["action"]["power_id"] == "cao_cao"

        def bad_judge(_llm_config, _agno_db, pack, *, tag):
            return {"outcome": "annex", "region_control": {"jiangxia": "cao_cao"}, "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", bad_judge)
        pending = run_adjudication(
            db,
            state,
            "power_action",
            "sun_quan",
            llm_config=object(),
            agno_db=None,
        )

        assert pending["status"] == "pending_review"
        assert pending["pending_adjudication"]["kind"] == "power_action"
        assert db.conn.execute(
            "SELECT COUNT(*) FROM pending_adjudications WHERE kind='power_action'"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_unified_adjudication_dispatcher_skips_without_llm_config():
    db = _board()
    state = _state()
    try:
        result = run_adjudication(
            db,
            state,
            "power_action",
            "cao_cao",
            llm_config=None,
            agno_db=None,
        )

        assert result["status"] == "skipped"
        assert result["kind"] == "power_action"
        assert db.conn.execute("SELECT COUNT(*) FROM pending_adjudications").fetchone()[0] == 0
    finally:
        db.close()


def test_unified_adjudication_dispatcher_records_battle_validation_failure(monkeypatch):
    db = _board()
    state = _state()
    try:
        def bad_judge(_llm_config, _agno_db, pack, *, tag):
            return {"tactic": "火攻", "actor": "刘备", "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", bad_judge)
        result = run_adjudication(
            db,
            state,
            "battle",
            "liubei_main:cao_main:jiangling",
            llm_config=object(),
            agno_db=None,
            battle_input={"attacker_ids": ["liubei_main"], "defender_ids": ["cao_main"], "node_id": "jiangling"},
        )

        assert result["status"] == "pending_review"
        assert result["pending_adjudication"]["kind"] == "battle"
        assert db.conn.execute(
            "SELECT COUNT(*) FROM pending_adjudications WHERE kind='battle'"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_unified_adjudication_dispatcher_runs_supply_as_controlled_narrative(monkeypatch):
    db = _board()
    state = _state()
    called = {"llm": False}
    try:
        def fake_judge(_llm_config, _agno_db, pack, *, tag):
            called["llm"] = True
            return {"outcome": "granary_supply", "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
        result = run_adjudication(
            db,
            state,
            "supply",
            "liubei_main",
            llm_config=object(),
            agno_db=None,
        )

        assert result["status"] == "validated"
        assert result["kind"] == "supply"
        assert result["randomness_level"] == "modifier"
        assert result["proposal_summary"]
        assert called["llm"] is True
    finally:
        db.close()


def test_unified_adjudication_response_includes_audit_fields(monkeypatch):
    db = _board()
    state = _state()
    try:
        def fake_judge(_llm_config, _agno_db, pack, *, tag):
            selected = pack["facts"]["legal_candidates"][0]
            return {"outcome": selected["action_type"], "action": selected, "reason": "择高分合法候选。", "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
        result = run_adjudication(
            db,
            state,
            "power_action",
            "cao_cao",
            llm_config=object(),
            agno_db=None,
        )

        assert result["status"] == "validated"
        assert result["randomness_level"] == "decision"
        assert result["proposal_summary"] == "择高分合法候选。"
        assert isinstance(result["validated_changes"], list)
        assert isinstance(result["applied_changes"], list)
        assert "合法候选" in result["audit_reason"]
    finally:
        db.close()


def test_record_pending_adjudication_dedupes_same_turn_kind_and_subject():
    db = _board()
    state = _state()
    try:
        pack = build_supply_adjudication_pack(db, state, "liubei_main")
        first = record_pending_adjudication(db, state, pack, "第一次越界", {"narrative": "天降援军"})
        second = record_pending_adjudication(db, state, pack, "第二次越界", {"narrative": "再来一次"})

        assert second["id"] == first["id"]
        assert db.conn.execute(
            "SELECT COUNT(*) FROM pending_adjudications WHERE kind='supply' AND subject_id='liubei_main'"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_monthly_adjudication_batch_routes_multiple_categories_and_skips_without_llm(monkeypatch):
    db = _board()
    state = _state(turn=2)
    try:
        db.create_secret_order(_state(turn=1), "赵云", "查访民变", "查证江夏动乱源头。", ["内政"])
        db.conn.execute("UPDATE regions SET controlled_by='liu_bei' WHERE id='jiangxia'")
        db.conn.commit()
        start_region_investment(db, _state(turn=1), "jiangxia", "屯田粮仓")
        start_siege(db, _state(turn=1), "liubei_main", "jiangling")
        db.propose_treaty = None  # 防止测试误以为 batch 依赖动态属性。
        db.conn.execute(
            """
            INSERT INTO diplomacy_treaties
            (treaty_key, proposer, target, treaty_type, status, terms, start_turn)
            VALUES ('batch_diplo', 'liu_bei', 'sun_quan', '盟约', 'proposed', '{}', 2)
            """
        )
        db.conn.commit()

        skipped = run_monthly_adjudication_batch(db, state)
        assert skipped["status"] == "skipped"
        assert db.conn.execute("SELECT COUNT(*) FROM pending_adjudications").fetchone()[0] == 0

        seen = []

        def fake_judge(_llm_config, _agno_db, pack, *, tag):
            seen.append(pack["kind"])
            if pack["kind"] == "power_action":
                selected = pack["facts"]["legal_candidates"][0]
                return {"outcome": selected["action_type"], "action": selected, "reason": "按候选执行。", "changes": []}
            if pack["kind"] == "world_event":
                return {"outcome": "wait_for_window", "reason": "未到窗口。", "changes": []}
            return {"outcome": (pack["allowed_outcomes"][0] if pack["allowed_outcomes"] else ""), "reason": "本月例行裁决。", "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
        from ming_sim.adjudication import attach_adjudication_runtime

        attach_adjudication_runtime(state, object(), None)
        result = run_monthly_adjudication_batch(db, state)

        assert result["status"] == "completed"
        assert {"power_action", "diplomacy", "secret_order", "siege", "region_investment", "personnel", "supply", "world_event"} <= set(seen)
        assert result["summary"]["total"] >= len(set(seen))
    finally:
        db.close()


def test_supply_settlement_logs_model_audit_and_monthly_overview(monkeypatch):
    db = _board()
    state = _state(turn=2)
    try:
        from ming_sim.adjudication import attach_adjudication_runtime

        attach_adjudication_runtime(state, object(), None)

        def fake_judge(_llm_config, _agno_db, pack, *, tag):
            assert pack["kind"] == "supply"
            return {"outcome": pack["allowed_outcomes"][0], "reason": "粮道尚通，但需防疲兵。", "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
        result = settle_army_supply(db, state, "liubei_main")

        assert result["adjudication"]["status"] == "validated"
        log = db.conn.execute(
            "SELECT new_value FROM army_logs WHERE turn=2 AND army_id='liubei_main' AND field='ai_judge'"
        ).fetchone()
        assert log is not None
        assert "AI裁判依据" in log["new_value"]

        report = build_monthly_report(db, _state(turn=3))
        overview = next(section for section in report["sections"] if section["id"] == "adjudication")
        assert any("粮道尚通" in item["summary"] for item in overview["items"])
    finally:
        db.close()


def test_due_secret_orders_call_model_for_sim_note_and_keep_status(monkeypatch):
    db = _board()
    state = _state(turn=2)
    try:
        order_id = db.create_secret_order(
            _state(turn=1), "赵云", "查访民变", "查证江夏动乱源头。", ["内政"]
        )
        db.rush_secret_order(order_id, state, 0, "本月核议")
        db.auto_submit_due_secret_orders(state)

        def fake_judge(_llm_config, _agno_db, pack, *, tag):
            assert pack["kind"] == "secret_order"
            return {
                "outcome": "add_progress_note",
                "reason": "查得豪右借粮价惑众，尚需核实。",
                "risk_note": "若急捕，恐激民心。",
                "changes": [{"kind": "secret_sim_note", "note": "查得豪右借粮价惑众，尚需核实。"}],
            }

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", fake_judge)
        results = db.adjudicate_pending_secret_orders(state, llm_config=object(), agno_db=None)

        assert results[0]["status"] == "validated"
        order = db.get_secret_order(order_id)
        assert order["status"] == "pending_review"
        assert "豪右" in order["sim_note"]
        assert "AI裁判依据" in order["sim_note"]
    finally:
        db.close()


def test_due_secret_orders_reject_illegal_death(monkeypatch):
    db = _board()
    state = _state(turn=2)
    try:
        order_id = db.create_secret_order(
            _state(turn=1), "赵云", "查探敌营", "只许查证，不得擅杀。", ["敌情"]
        )
        db.rush_secret_order(order_id, state, 0, "本月核议")
        db.auto_submit_due_secret_orders(state)

        def bad_judge(_llm_config, _agno_db, pack, *, tag):
            return {"outcome": "close_done", "narrative": "曹操死亡。", "changes": []}

        monkeypatch.setattr(adjudication_module, "run_adjudication_llm", bad_judge)
        results = db.adjudicate_pending_secret_orders(state, llm_config=object(), agno_db=None)

        assert results[0]["status"] == "pending_review"
        assert db.get_secret_order(order_id)["status"] == "pending_review"
        assert db.conn.execute(
            "SELECT COUNT(*) FROM pending_adjudications WHERE kind='secret_order'"
        ).fetchone()[0] == 1
    finally:
        db.close()
