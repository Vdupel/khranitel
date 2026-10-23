"""Статистика прохождений и картинка."""

import tempfile
import unittest
from pathlib import Path

from khranitel.format import load_adventure, save_adventure
from khranitel import stats
from khranitel.stats import store

ROOT = Path(__file__).resolve().parents[1]


class StatsModelTests(unittest.TestCase):
    def test_record_play_and_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.json"
            stats.record_choice("primer", "default", "crossroads", "Свернуть в лес", path=path)
            stats.record_choice("primer", "default", "crossroads", "Свернуть в лес", path=path)
            stats.record_choice("primer", "default", "forest", "Заговорить", path=path)
            stats.record_play("primer", "default", "talk", path=path)
            data = store.load(path)
            self.assertEqual(data["plays_total"], 1)
            bucket = data["tales"]["primer"]
            self.assertEqual(bucket["plays"], 1)
            self.assertEqual(bucket["endings"]["talk"], 1)
            key = stats.choice_key("crossroads", "Свернуть в лес")
            self.assertEqual(bucket["choices"]["default"][key], 2)
            self.assertTrue(bucket["seen_choices"]["default"][key])

    def test_completeness_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "saga"
            save_adventure(folder, {
                "title": "Сага",
                "vote_minutes": 5,
                "start": "a",
                "scenes": {
                    "a": {"text": "А", "choices": [
                        {"label": "Вперёд", "next": "b"},
                        {"label": "Вбок", "next": "c"},
                    ]},
                    "b": {"text": "Б", "choices": []},
                    "c": {"text": "В", "choices": []},
                },
            })
            adventure = load_adventure(folder)
            path = Path(tmp) / "stats.json"
            stats.record_choice("saga", "default", "a", "Вперёд", path=path)
            stats.record_play("saga", "default", "b", path=path)
            report = stats.tale_report("saga", {"default": adventure}, path=path)
            comp = report["completeness"]["default"]
            self.assertEqual(comp["total_choices"], 2)
            self.assertEqual(comp["seen_choices"], 1)
            self.assertEqual(report["open_endings"]["default"]["opened"], ["b"])
            public = stats.export_public(path=path)
            self.assertEqual(public["plays_total"], 1)
            self.assertIn("saga", public["tales"])

    def test_render_overview_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.json"
            stats.record_play("primer", "default", "village", path=path)
            stats.record_play("zvon-kolodca", "default", "ending_peace", path=path)
            png = stats.render_overview_image(path=path)
            self.assertTrue(png.startswith(b"\x89PNG"))
            self.assertGreater(len(png), 200)

    def test_summary_mentions_plays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.json"
            stats.record_play("primer", "default", "village", path=path)
            text = stats.summary_text(path=path)
            self.assertIn("Всего прохождений: 1", text)
            self.assertIn("primer", text)


class PrimerCompletenessSmokeTests(unittest.TestCase):
    def test_primer_endings_detected(self):
        adventure = load_adventure(ROOT / "adventures" / "primer")
        endings = stats.endings_map(adventure)
        self.assertIn("village", endings)
        self.assertTrue(len(endings) >= 2)


if __name__ == "__main__":
    unittest.main()
