"""Скиллчеки: формат, бросок, скрытость от обычного help."""

import tempfile
import unittest
from pathlib import Path
from random import Random

from khranitel.engine import roll_check
from khranitel.format import AdventureError, load_adventure, save_adventure
from khranitel import phrases, tales

ROOT = Path(__file__).resolve().parents[1]


def _count_checks(adventure) -> int:
    return sum(1 for scene in adventure.scenes.values()
               for choice in scene.choices if choice.is_check)


class SkillcheckFormatTests(unittest.TestCase):
    def test_chance_requires_range_not_constant(self):
        with self.assertRaises(AdventureError) as caught:
            save_adventure(Path(tempfile.mkdtemp()) / "bad", {
                "title": "Проба",
                "vote_minutes": 5,
                "start": "a",
                "scenes": {
                    "a": {"text": "Тут", "choices": [
                        {"label": "Риск", "next": "ok", "fail": "bad", "chance": 50}]},
                    "ok": {"text": "Ок", "choices": []},
                    "bad": {"text": "Плох", "choices": []},
                },
            })
        self.assertTrue(any("chance" in line for line in caught.exception.errors))

    def test_success_and_fail_must_differ(self):
        with self.assertRaises(AdventureError) as caught:
            save_adventure(Path(tempfile.mkdtemp()) / "same", {
                "title": "Проба",
                "vote_minutes": 5,
                "start": "a",
                "scenes": {
                    "a": {"text": "Тут", "choices": [
                        {"label": "Риск", "next": "ok", "fail": "ok", "chance": [40, 60]}]},
                    "ok": {"text": "Ок", "choices": []},
                },
            })
        self.assertTrue(any("одну сцену" in line for line in caught.exception.errors))

    def test_valid_check_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "ok"
            save_adventure(folder, {
                "title": "Проба",
                "vote_minutes": 5,
                "start": "a",
                "scenes": {
                    "a": {"text": "Тут", "choices": [
                        {"label": "Риск", "next": "ok", "fail": "bad", "chance": [40, 60]},
                        {"label": "Безопасно", "next": "ok"},
                    ]},
                    "ok": {"text": "Ок", "choices": []},
                    "bad": {"text": "Плох", "choices": []},
                },
            })
            adventure = load_adventure(folder)
            check = adventure.scene("a").choices[0]
            self.assertTrue(check.is_check)
            self.assertEqual(check.chance_min, 40)
            self.assertEqual(check.fail, "bad")
            self.assertFalse(adventure.scene("a").choices[1].is_check)


class SkillcheckRollTests(unittest.TestCase):
    def test_threshold_varies_inside_range(self):
        thresholds = set()
        for seed in range(50):
            _dest, _outcome, detail = roll_check(
                40, 60, success="ok", fail="bad", rng=Random(seed))
            thresholds.add(detail["threshold"])
            self.assertGreaterEqual(detail["threshold"], 40)
            self.assertLessEqual(detail["threshold"], 60)
        self.assertGreater(len(thresholds), 1)

    def test_roll_splits_success_and_fail(self):
        # фиксированный rng: threshold и roll предсказуемы через перебор семян
        outcomes = set()
        for seed in range(200):
            _dest, outcome, _detail = roll_check(
                40, 60, success="ok", fail="bad", rng=Random(seed))
            outcomes.add(outcome)
        self.assertEqual(outcomes, {"success", "fail"})


class AdventureSkillchecksPresentTests(unittest.TestCase):
    def test_primer_default_and_alt_have_several_checks(self):
        default = load_adventure(ROOT / "adventures" / "primer")
        alt = load_adventure(ROOT / "adventures" / "primer" / "variants" / "alt")
        self.assertGreaterEqual(_count_checks(default), 3)
        self.assertGreaterEqual(_count_checks(alt), 3)
        # разные сцены, не один чек на всю историю
        scenes_default = {scene.id for scene in default.scenes.values()
                          if any(c.is_check for c in scene.choices)}
        scenes_alt = {scene.id for scene in alt.scenes.values()
                      if any(c.is_check for c in scene.choices)}
        self.assertGreaterEqual(len(scenes_default), 2)
        self.assertGreaterEqual(len(scenes_alt), 2)

    def test_other_tales_have_several_checks(self):
        zvon = tales.tale_by_slug(ROOT / "adventures", "zvon-kolodca")
        biowave = tales.tale_by_slug(ROOT / "adventures", "deti-biowave")
        self.assertIsNotNone(zvon)
        self.assertIsNotNone(biowave)
        self.assertGreaterEqual(_count_checks(zvon.load("default")), 3)
        self.assertGreaterEqual(_count_checks(biowave.load("default")), 3)


class SkillcheckVisibilityTests(unittest.TestCase):
    def test_private_help_does_not_mention_skillcheck(self):
        text = phrases.help_text(private=True, group=False)
        self.assertNotIn("скилл", text.casefold())
        self.assertNotIn("chance", text.casefold())

    def test_admin_hint_mentions_range(self):
        text = phrases.skillcheck_admin_hint("forest", [
            "«Заговорить» — шанс 35–65% → talk / провал → talk_snarl"])
        self.assertIn("/test", text)
        self.assertIn("35–65%", text)


if __name__ == "__main__":
    unittest.main()
