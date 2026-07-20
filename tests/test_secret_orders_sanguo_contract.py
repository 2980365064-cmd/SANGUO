import pytest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import GameState


@pytest.fixture
def board():
    content = GameContent.load()
    db = GameDB(":memory:", content=content)
    db.seed_static_data()
    try:
        yield db
    finally:
        db.close()


def test_secret_order_assignee_must_be_active_liu_bei_minister(board):
    state = GameState(turn=1, year=208, period=8)
    order_id = board.create_secret_order(
        state,
        "诸葛亮",
        "探曹营",
        "授权来源：建安十三年八月军帐密谈；执行者：诸葛亮；目标：刺探曹军水寨虚实；边界：不得伤民，不得暴露刘备名义；风险：细作暴露损害盟约互信；回奏：月末军政推演回报。",
        ["曹操", "水寨"],
        deadline_months=1,
    )
    assert order_id > 0

    with pytest.raises(ValueError, match="不属刘备军府"):
        board.create_secret_order(state, "曹操", "探刘营", "刺探夏口。", ["夏口"])


def test_secret_order_sim_payload_exposes_authorization_boundaries_risk_and_report():
    state = GameState(turn=1, year=208, period=8)
    board = GameDB(":memory:", content=GameContent.load())
    board.seed_static_data()
    try:
        order_id = board.create_secret_order(
            state,
            "诸葛亮",
            "护民渡江",
            "授权来源：军议后私下托付；执行者：诸葛亮；目标：联络江夏渡船护送百姓；边界：不得强征民船，不得背盟；风险：耽误军机，消耗粮秣；回奏：本月月底回报进展。",
            ["护民"],
        )
        order = board.get_secret_order(order_id)
        payload = board.secret_order_sim_payload(order)
        assert "授权来源" in payload["content"]
        assert "边界" in payload["content"]
        assert "风险" in payload["content"]
        assert "回奏" in payload["content"]
    finally:
        board.close()
