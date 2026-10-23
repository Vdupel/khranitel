"""Срок голосования и ключи тем форума."""

import tempfile
import unittest
from pathlib import Path

from khranitel import state, timing


class TimingTests(unittest.TestCase):
    def test_more_people_longer_wait_until_cap(self):
        short = timing.vote_wait_seconds(2, base_minutes=60)
        mid = timing.vote_wait_seconds(10, base_minutes=60)
        capped = timing.vote_wait_seconds(200, base_minutes=60)
        self.assertLess(short, mid)
        self.assertEqual(capped, 60 * 60)
        self.assertGreaterEqual(short, timing.MIN_VOTE_SECONDS)

    def test_adventure_cap_wins_over_crowd(self):
        # primer с 2 минутами не растягивается дольше базы
        self.assertEqual(timing.vote_wait_seconds(50, base_minutes=2), 120)

    def test_expect_voters_subtracts_bot(self):
        self.assertEqual(timing.expect_voters_from_member_count(1), 1)
        self.assertEqual(timing.expect_voters_from_member_count(12), 11)


class ScopeKeyTests(unittest.TestCase):
    def test_thread_sessions_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            data = state.load(path)
            state.put(data, 100, {"kind": "scene", "title": "A"}, thread_id=None)
            state.put(data, 100, {"kind": "scene", "title": "B"}, thread_id=7)
            state.save(path, data)
            again = state.load(path)
            self.assertEqual(state.session(again, 100)["title"], "A")
            self.assertEqual(state.session(again, 100, 7)["title"], "B")
            self.assertIsNone(state.session(again, 100, 8))

    def test_parse_and_find_by_poll(self):
        data = state.load(Path("/nonexistent-khranitel-state.json"))
        state.put(data, 5, {
            "poll_id": "p1",
            "kind": "begin",
        }, thread_id=9)
        found = state.find_by_poll(data, "p1")
        self.assertIsNotNone(found)
        key, chat_id, thread_id, current = found
        self.assertEqual(chat_id, 5)
        self.assertEqual(thread_id, 9)
        self.assertEqual(current["poll_id"], "p1")
        self.assertEqual(state.parse_scope_key(key), (5, 9))


if __name__ == "__main__":
    unittest.main()
