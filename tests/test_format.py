"""Формат сценария и подсчёт голосов — без Телеграма."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from khranitel.engine import decide, verdict
from khranitel.format import AdventureError, install_upload, load_adventure, save_adventure

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def test_majority(self):
        self.assertEqual(decide([1, 4, 2]), (1, "majority"))
        self.assertIn("Большинство", verdict(["лес", "село", "костёр"], [1, 4, 2]))

    def test_tie_keeps_the_earlier_choice(self):
        self.assertEqual(decide([3, 3, 1]), (0, "tie"))
        text = verdict(["лес", "село", "костёр"], [3, 3, 1])
        self.assertIn("Ничья", text)
        self.assertIn("лес", text)

    def test_nobody_voted(self):
        self.assertEqual(decide([0, 0]), (0, "none"))
        self.assertIn("Никто не проголосовал", verdict(["а", "б"], [0, 0]))

    def test_one_vote_is_one_voice(self):
        self.assertIn("1 голос.", verdict(["а", "б"], [1, 0]))
        self.assertIn("2 голоса.", verdict(["а", "б"], [2, 0]))
        self.assertIn("5 голосов.", verdict(["а", "б"], [5, 0]))


class FormatTests(unittest.TestCase):
    def test_primer_loads(self):
        adventure = load_adventure(ROOT / "adventures" / "primer")
        self.assertEqual(adventure.start, "crossroads")
        self.assertEqual(len(adventure.scene("crossroads").choices), 3)
        self.assertEqual(adventure.scene("village").choices, ())

    def test_missing_scene_is_rejected(self):
        with self.assertRaises(AdventureError) as caught:
            save_adventure(Path(tempfile.mkdtemp()) / "broken", {
                "title": "Проба",
                "vote_minutes": 5,
                "start": "start",
                "scenes": {"start": {"text": "Тут", "choices": [
                    {"label": "Туда", "next": "nowhere"}]}}})
        self.assertTrue(any("nowhere" in line for line in caught.exception.errors))

    def test_image_cannot_leave_the_folder(self):
        with self.assertRaises(AdventureError):
            save_adventure(Path(tempfile.mkdtemp()) / "pic", {
                "title": "Проба",
                "vote_minutes": 5,
                "start": "start",
                "scenes": {"start": {
                    "text": "Тут",
                    "image": "../secret.png",
                    "choices": []}}})

    def test_zip_roundtrip(self):
        raw = (ROOT / "adventures" / "primer" / "adventure.yaml").read_bytes()
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as archive:
            archive.writestr("pack/adventure.yaml", raw)
            archive.writestr("pack/images/oak.png", b"\x89PNG")
        with tempfile.TemporaryDirectory() as tmp:
            adventure = install_upload(Path(tmp) / "primer", "primer.zip", blob.getvalue())
            self.assertEqual(adventure.title, "Перекрёсток у старого дуба")
            self.assertTrue((Path(tmp) / "primer" / "images" / "oak.png").is_file())

    def test_bad_yaml_is_not_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "bad"
            with self.assertRaises(AdventureError):
                install_upload(folder, "bad.yaml", "title: только название\n".encode())
            self.assertFalse((folder / "adventure.yaml").exists())


if __name__ == "__main__":
    unittest.main()
