"""Хранение статистики в data/stats.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "stats.json"


def empty() -> dict:
    return {"version": 1, "plays_total": 0, "tales": {}}


def load(path: Path = DEFAULT_PATH) -> dict:
    if not path.is_file():
        return empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty()
    if not isinstance(raw, dict):
        return empty()
    tales = raw.get("tales")
    if not isinstance(tales, dict):
        tales = {}
    plays_total = raw.get("plays_total", 0)
    if not isinstance(plays_total, int) or plays_total < 0:
        plays_total = 0
    return {"version": 1, "plays_total": plays_total, "tales": tales}


def save(data: dict, path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
