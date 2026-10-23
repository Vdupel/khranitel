"""Состояние чатов, кулдауны и админ-токен. Файл переживает перезапуск."""

from __future__ import annotations

import json
import secrets
from pathlib import Path


def load(path: Path) -> dict:
    if not path.is_file():
        return _empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(raw, dict):
        return _empty()
    chats = raw.get("chats")
    if not isinstance(chats, dict):
        chats = {}
    cooldowns = raw.get("cooldowns")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
    # cooldowns: chat_id -> {tale_slug: remaining_begin_votes}
    last_finished = raw.get("last_finished")
    if not isinstance(last_finished, dict):
        last_finished = {}
    welcomed = raw.get("welcomed")
    if not isinstance(welcomed, list):
        welcomed = []
    token = raw.get("admin_token")
    if not isinstance(token, str) or not token.strip():
        token = None
    return {
        "chats": chats,
        "cooldowns": cooldowns,
        "last_finished": last_finished,
        "welcomed": [int(x) for x in welcomed if str(x).lstrip("-").isdigit()],
        "admin_token": token,
    }


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _empty() -> dict:
    return {
        "chats": {},
        "cooldowns": {},
        "last_finished": {},
        "welcomed": [],
        "admin_token": None,
    }


def session(data: dict, chat_id: int) -> dict | None:
    value = data["chats"].get(str(chat_id))
    return value if isinstance(value, dict) else None


def put(data: dict, chat_id: int, value: dict | None) -> None:
    key = str(chat_id)
    if value is None:
        data["chats"].pop(key, None)
    else:
        data["chats"][key] = value


def chat_cooldowns(data: dict, chat_id: int) -> dict[str, int]:
    raw = data["cooldowns"].get(str(chat_id))
    if not isinstance(raw, dict):
        raw = {}
        data["cooldowns"][str(chat_id)] = raw
    # нормализовать к int
    cleaned = {str(k): int(v) for k, v in raw.items() if str(v).lstrip("-").isdigit()}
    data["cooldowns"][str(chat_id)] = cleaned
    return cleaned


def set_last_finished(data: dict, chat_id: int, payload: dict | None) -> None:
    key = str(chat_id)
    if payload is None:
        data["last_finished"].pop(key, None)
    else:
        data["last_finished"][key] = payload


def last_finished(data: dict, chat_id: int) -> dict | None:
    value = data["last_finished"].get(str(chat_id))
    return value if isinstance(value, dict) else None


def ensure_admin_token(data: dict, env_token: str | None) -> str:
    """Токен тестового режима: из env, из файла состояния или новый."""
    if env_token and env_token.strip():
        data["admin_token"] = env_token.strip()
        return data["admin_token"]
    if isinstance(data.get("admin_token"), str) and data["admin_token"].strip():
        return data["admin_token"]
    data["admin_token"] = secrets.token_urlsafe(16)
    return data["admin_token"]


def mark_welcomed(data: dict, user_id: int) -> bool:
    """True, если это первое приветствие."""
    if user_id in data["welcomed"]:
        return False
    data["welcomed"].append(user_id)
    return True
