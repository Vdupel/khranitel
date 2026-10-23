"""Истории, кулдаун /begin и реплики — без Телеграма."""

import tempfile
import unittest
from pathlib import Path
from random import Random

from khranitel import phrases, state, tales
from khranitel.format import save_adventure

ROOT = Path(__file__).resolve().parents[1]


class TalesDiscoveryTests(unittest.TestCase):
    def test_repo_tales_include_primer_with_alt(self):
        catalog = tales.discover_tales(ROOT / "adventures")
        slugs = {tale.slug: tale for tale in catalog}
        self.assertIn("primer", slugs)
        self.assertIn("default", slugs["primer"].variants)
        self.assertIn("alt", slugs["primer"].variants)
        self.assertGreaterEqual(len(catalog), 3)

    def test_variants_only_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tale_dir = root / "saga"
            (tale_dir / "variants" / "a").mkdir(parents=True)
            (tale_dir / "variants" / "b").mkdir(parents=True)
            raw = {
                "title": "Сага",
                "vote_minutes": 5,
                "start": "s",
                "scenes": {"s": {"text": "Раз", "choices": []}},
            }
            save_adventure(tale_dir / "variants" / "a", raw)
            save_adventure(tale_dir / "variants" / "b", {**raw, "title": "Сага Б"})
            (tale_dir / "tale.yaml").write_text("title: Общий заголовок\n", encoding="utf-8")
            catalog = tales.discover_tales(root)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0].title, "Общий заголовок")
            self.assertEqual(catalog[0].variant_ids(), ["a", "b"])


class CooldownTests(unittest.TestCase):
    def test_recent_excluded_for_two_begin_votes(self):
        catalog = [
            tales.Tale("a", "A", {"default": Path(".")}),
            tales.Tale("b", "B", {"default": Path(".")}),
            tales.Tale("c", "C", {"default": Path(".")}),
            tales.Tale("d", "D", {"default": Path(".")}),
            tales.Tale("e", "E", {"default": Path(".")}),
        ]
        cool: dict[str, int] = {}
        tales.mark_played(cool, "a")
        tales.mark_played(cool, "b")
        first = tales.pick_candidates(catalog, cool, count=3, rng=Random(0))
        first_slugs = {t.slug for t in first}
        self.assertEqual(len(first), 3)
        self.assertNotIn("a", first_slugs)
        self.assertNotIn("b", first_slugs)
        tales.tick_cooldowns(cool)
        second = tales.pick_candidates(catalog, cool, count=3, rng=Random(1))
        second_slugs = {t.slug for t in second}
        self.assertNotIn("a", second_slugs)
        self.assertNotIn("b", second_slugs)
        tales.tick_cooldowns(cool)
        third = tales.pick_candidates(catalog, cool, count=5, rng=Random(2))
        third_slugs = {t.slug for t in third}
        self.assertIn("a", third_slugs)
        self.assertIn("b", third_slugs)

    def test_pads_cooldown_only_when_fewer_than_two_free(self):
        catalog = [
            tales.Tale("a", "A", {"default": Path(".")}),
            tales.Tale("b", "B", {"default": Path(".")}),
            tales.Tale("c", "C", {"default": Path(".")}),
        ]
        cool = {"a": 2, "b": 2}
        chosen = tales.pick_candidates(catalog, cool, count=3, rng=Random(0))
        # свободна только c — добиваем одной кулдаунной, чтобы опрос состоялся
        self.assertEqual(len(chosen), 2)
        self.assertIn("c", {t.slug for t in chosen})

    def test_pick_variant_avoids_current(self):
        tale = tales.Tale("x", "X", {
            "default": Path("."),
            "alt": Path("."),
        })
        for _ in range(20):
            self.assertEqual(tales.pick_variant(tale, avoid="default", rng=Random(7)), "alt")


class StateTokenTests(unittest.TestCase):
    def test_admin_token_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            data = state.load(path)
            token = state.ensure_admin_token(data, None)
            state.save(path, data)
            again = state.load(path)
            self.assertEqual(again["admin_token"], token)
            forced = state.ensure_admin_token(again, "from-env")
            self.assertEqual(forced, "from-env")


class PhrasesTests(unittest.TestCase):
    def test_start_not_boring(self):
        line = phrases.start_line("Звон колодца")
        self.assertIn("Звон колодца", line)
        self.assertNotIn("Начинаем приключение", line)

    def test_help_hides_spoiler_in_private(self):
        private = phrases.help_text(private=True, group=False)
        group = phrases.help_text(private=False, group=True)
        self.assertNotIn("/spoiler", private)
        self.assertIn("/spoiler", group)
        self.assertIn("/begin", private)

    def test_end_mentions_retell(self):
        text = phrases.end_line("Сага")
        self.assertIn("/retell", text)
        self.assertIn("по-другому", text)


if __name__ == "__main__":
    unittest.main()
