import unittest

from ming_sim.content import GameContent
from ming_sim.db import GameDB
from ming_sim.models import Event, GameState


class ArmyDeltaSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.content = GameContent.load()
        self.db = GameDB(":memory:", self.content)
        self.db.seed_static_data()
        self.state = GameState()
        self.event = Event(
            id="test",
            title="军队增减测试",
            kind="测试",
            summary="",
            urgency=0,
            severity=0,
            credibility=100,
            interests=[],
            audiences=[],
        )

    def test_existing_army_manpower_is_delta_only(self):
        before = self.db.conn.execute(
            "SELECT manpower FROM armies WHERE id = 'cao_main'"
        ).fetchone()["manpower"]

        self.db.apply_army_deltas(
            self.state,
            self.event,
            None,
            "测试",
            {"cao_main": {"manpower": 8000, "reason": "补兵八千"}},
        )

        after = self.db.conn.execute(
            "SELECT manpower FROM armies WHERE id = 'cao_main'"
        ).fetchone()["manpower"]
        log = self.db.conn.execute(
            """
            SELECT old_value, new_value, delta
            FROM army_logs
            WHERE army_id = 'cao_main' AND field = 'manpower'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        self.assertEqual(after, before + 8000)
        self.assertEqual(int(log["old_value"]), before)
        self.assertEqual(int(log["new_value"]), before + 8000)
        self.assertEqual(log["delta"], 8000)

    def test_existing_army_maintenance_is_delta_only(self):
        before = self.db.conn.execute(
            "SELECT maintenance_per_turn FROM armies WHERE id = 'cao_main'"
        ).fetchone()["maintenance_per_turn"]

        self.db.apply_army_deltas(
            self.state,
            self.event,
            None,
            "测试",
            {"cao_main": {"maintenance_per_turn": 5, "reason": "月饷增五万"}},
        )

        after = self.db.conn.execute(
            "SELECT maintenance_per_turn FROM armies WHERE id = 'cao_main'"
        ).fetchone()["maintenance_per_turn"]

        self.assertEqual(after, before + 5)

    def test_existing_army_can_be_renamed_and_queried_by_new_name(self):
        self.db.apply_army_deltas(
            self.state,
            self.event,
            None,
            "测试",
            {"cao_main": {"name": "忠勇中军", "status": "赐号改编", "reason": "赐曹操中军新番号"}},
        )

        row = self.db.conn.execute(
            "SELECT name, status FROM armies WHERE id = 'cao_main'"
        ).fetchone()
        log = self.db.conn.execute(
            """
            SELECT old_value, new_value, delta
            FROM army_logs
            WHERE army_id = 'cao_main' AND field = 'name'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        self.assertEqual(row["name"], "忠勇中军")
        self.assertEqual(row["status"], "赐号改编")
        self.assertEqual(log["old_value"], "曹操中军")
        self.assertEqual(log["new_value"], "忠勇中军")
        self.assertIsNone(log["delta"])
        self.assertIn("忠勇中军", self.db.army_detail("忠勇中军"))

    def test_duplicate_new_army_does_not_merge_into_existing_army(self):
        before = self.db.conn.execute(
            "SELECT manpower FROM armies WHERE id = 'cao_main'"
        ).fetchone()["manpower"]

        created = self.db.create_armies_from_extraction(
            self.state,
            [
                {
                    "id": "cao_main",
                    "name": "曹操中军",
                    "owner_power": "cao_cao",
                    "station": "江陵",
                    "commander": "曹操",
                    "troop_type": "步骑混编",
                    "manpower": before,
                    "maintenance_per_turn": 15,
                    "supply": 38,
                    "morale": 52,
                    "training": 68,
                    "equipment": 62,
                    "mobility": 48,
                    "loyalty": 55,
                    "status": "重复抽成新建军队",
                }
            ],
        )

        after = self.db.conn.execute(
            "SELECT manpower FROM armies WHERE id = 'cao_main'"
        ).fetchone()["manpower"]
        log_count = self.db.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM army_logs
            WHERE army_id = 'cao_main' AND field = 'manpower'
            """
        ).fetchone()["count"]

        self.assertEqual(created, [])
        self.assertEqual(after, before)
        self.assertEqual(log_count, 0)


if __name__ == "__main__":
    unittest.main()
