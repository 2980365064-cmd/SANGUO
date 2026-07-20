from types import SimpleNamespace

from ming_sim.content import GameContent
from ming_sim.context import bind_content as bind_context_content
from ming_sim.db import GameDB
from ming_sim.models import CourtContext, GameState
import ming_sim.registry as registry_module
from ming_sim.tools import build_minister_tools
from ming_sim.tools import build_evidence_gate_context, classify_intel_categories
from web_app import WebGame


def _game():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    session = SimpleNamespace(
        db=db,
        content=content,
        state=GameState(
            year=208,
            period=8,
            turn=1,
            stage="流亡军",
            metrics={"军资": 60, "粮秣": 60, "民望": 55, "名分": 70, "军心": 65, "士族支持": 40},
        ),
        previous_summary="",
        last_decree="",
        last_report="",
    )
    instance = WebGame.__new__(WebGame)
    instance.session = session
    instance.favorites = set()
    return instance, db


def test_court_chat_roster_defaults_to_active_liu_bei_ministers():
    game, db = _game()
    try:
        roster = game._active_court_ministers([])
        names = {character.name for character in roster}
        assert {"刘备", "诸葛亮", "关羽", "张飞"} & names
        assert "曹操" not in names
        assert all(game.character_power_id(character) == "liu_bei" for character in roster)
    finally:
        db.close()


def test_court_chat_respects_requested_liu_bei_ministers_and_rejects_external_powers():
    game, db = _game()
    try:
        roster = game._active_court_ministers(["诸葛亮", "曹操", "孙权"])
        assert [character.name for character in roster] == ["诸葛亮"]
    finally:
        db.close()


def test_court_conclusion_prompt_uses_liubei_military_council_language():
    game, db = _game()
    try:
        prompt = game._court_conclusion_prompt("诸葛亮：宜联孙抗曹。")
        assert "军府方略" in prompt
        assert "主公" in prompt
        for forbidden in ("皇帝", "圣旨", "司礼监", "内阁", "陛下"):
            assert forbidden not in prompt
    finally:
        db.close()


def test_military_intel_brief_exposes_army_reality_for_character_dialogue():
    _game_instance, db = _game()
    try:
        db.conn.execute(
            "UPDATE armies SET supply=12, supply_turns=0, fatigue=41, starvation_turns=2, "
            "supply_combat_multiplier=0.65 WHERE id='liubei_main'"
        )
        db.conn.execute(
            "UPDATE characters SET status='imprisoned', status_reason='战役被俘', "
            "status_changed_turn=1, location='jiangxia' WHERE name='张飞'"
        )

        brief = db.military_intel_brief(turn=1)
        detail = db.army_roster(filter_names=["刘备本军"], index_only=False)

        for text in ("军情事实块", "刘备本军", "补给/月", "疲劳", "断粮", "战力补给倍率", "战俘/系狱将领", "张飞"):
            assert text in brief
        assert "我军各部" in detail
        assert "刘备本军" in detail
        assert "敌对/外部军" in db.army_roster(index_only=True)
    finally:
        db.close()


def test_minister_agent_registry_injects_military_intel_into_monthly_context():
    source = registry_module.create_minister_agent.__code__.co_names
    assert "build_intel_tool_index" in source
    assert "build_character_cognitive_strategy" in source
    assert "military_intel_brief" not in source


def test_world_intel_tools_cover_classified_read_only_dossiers():
    game, db = _game()
    try:
        registry_module.bind_content(game.content)
        bind_context_content(game.content)
        context = CourtContext(state=game.session.state, db=db)
        character = game.content.characters["诸葛亮"]
        tools = {getattr(tool, "__name__", ""): tool for tool in build_minister_tools(character, context, use_roster_tool=True, use_army_tool=True)}

        for name in (
            "query_world_index", "query_military_intel", "query_internal_intel",
            "query_diplomacy_intel", "query_personnel_intel", "query_secret_intel",
            "query_monthly_intel", "search_memories",
        ):
            assert name in tools

        military = tools["query_military_intel"](["刘备本军"])
        assert "刘备本军" in military and "补给" in military and "编制" in military
        internal = tools["query_internal_intel"](["江夏"])
        assert "江夏" in internal and "粮" in internal
        diplomacy = tools["query_diplomacy_intel"](["孙权"])
        assert "孙权" in diplomacy and "条约" in diplomacy
        personnel = tools["query_personnel_intel"](["诸葛亮"])
        assert "诸葛亮" in personnel and "任事职位" in personnel
        monthly = tools["query_monthly_intel"]("军事")
        assert "军政总计" in monthly and "军事" in monthly
    finally:
        db.close()


def test_classified_intel_tools_are_read_only():
    game, db = _game()
    try:
        registry_module.bind_content(game.content)
        bind_context_content(game.content)
        context = CourtContext(state=game.session.state, db=db)
        character = game.content.characters["诸葛亮"]
        tools = {getattr(tool, "__name__", ""): tool for tool in build_minister_tools(character, context, use_roster_tool=True, use_army_tool=True)}
        before_army = dict(db.conn.execute("SELECT manpower, supply FROM armies WHERE id='liubei_main'").fetchone())
        before_character = dict(db.conn.execute("SELECT status, location FROM characters WHERE name='张飞'").fetchone())
        before_relation = dict(db.conn.execute("SELECT * FROM diplomatic_relations ORDER BY power_a,power_b LIMIT 1").fetchone())

        tools["query_world_index"]("")
        tools["query_military_intel"](["刘备本军"])
        tools["query_internal_intel"](["江夏"])
        tools["query_diplomacy_intel"](["孙权"])
        tools["query_personnel_intel"](["诸葛亮"])
        tools["query_secret_intel"]("public")
        tools["query_monthly_intel"]("军事")

        assert dict(db.conn.execute("SELECT manpower, supply FROM armies WHERE id='liubei_main'").fetchone()) == before_army
        assert dict(db.conn.execute("SELECT status, location FROM characters WHERE name='张飞'").fetchone()) == before_character
        assert dict(db.conn.execute("SELECT * FROM diplomatic_relations ORDER BY power_a,power_b LIMIT 1").fetchone()) == before_relation
    finally:
        db.close()


def test_evidence_gate_prefetches_read_only_dossiers_for_fact_questions():
    game, db = _game()
    try:
        registry_module.bind_content(game.content)
        bind_context_content(game.content)
        context = CourtContext(state=game.session.state, db=db)
        character = game.content.characters["诸葛亮"]
        before_army = dict(db.conn.execute("SELECT manpower, supply, fatigue FROM armies WHERE id='liubei_main'").fetchone())
        before_region = dict(db.conn.execute("SELECT fiscal, public_support, unrest FROM regions WHERE id='jiangxia'").fetchone())

        categories = classify_intel_categories("刘备本军补给还能支撑多久，江夏经营是否该先修城防？")
        evidence = build_evidence_gate_context(character, context, "刘备本军补给还能支撑多久，江夏经营是否该先修城防？")

        assert "military" in categories
        assert "internal" in categories
        assert "证据门" in evidence
        assert "刘备本军" in evidence
        assert "补给" in evidence
        assert "江夏" in evidence
        assert "民心" in evidence
        assert "动乱" in evidence
        assert dict(db.conn.execute("SELECT manpower, supply, fatigue FROM armies WHERE id='liubei_main'").fetchone()) == before_army
        assert dict(db.conn.execute("SELECT fiscal, public_support, unrest FROM regions WHERE id='jiangxia'").fetchone()) == before_region
    finally:
        db.close()


def test_character_chat_routes_apply_evidence_gate_before_agent_run():
    import inspect

    from ming_sim.session import GameSession

    session_source = inspect.getsource(GameSession.chat)
    web_source = inspect.getsource(WebGame.chat_stream)

    assert "build_evidence_gate_context" in session_source
    assert session_source.index("build_evidence_gate_context") < session_source.index("agent.run")
    assert "build_evidence_gate_context" in web_source
    assert web_source.index("build_evidence_gate_context") < web_source.index("agent.run")


def test_character_cognitive_strategy_distinguishes_zhugeliang_and_zhangfei():
    content = GameContent.load()
    zhuge = registry_module.build_character_cognitive_strategy(content.characters["诸葛亮"])
    zhangfei = registry_module.build_character_cognitive_strategy(content.characters["张飞"])

    assert "军事、外交、内政、人事" in zhuge
    assert "多源交叉" in zhuge
    assert "优先查军事、敌情、士气、补给" in zhangfei
    assert "不主动深挖外交细账" in zhangfei
