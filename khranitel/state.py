"""Текущие голосования. Файл переживает перезапуск бота."""

from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> dict:
    if not path.is_file():
        return {"chats": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"chats": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("chats"), dict):
        return {"chats": {}}
    return raw


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def session(data: dict, chat_id: int) -> dict | None:
    value = data["chats"].get(str(chat_id))
    return value if isinstance(value, dict) else None


def put(data: dict, chat_id: int, value: dict | None) -> None:
    key = str(chat_id)
    if value is None:
        data["chats"].pop(key, None)
    else:
        data["chats"][key] = value
