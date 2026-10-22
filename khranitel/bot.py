"""Телеграм-бот. Сценарий, опрос, по окончании срока — последствия и следующий опрос."""

from __future__ import annotations

import asyncio
import io
import os
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, Message

from khranitel.engine import decide, verdict
from khranitel.format import (
    Adventure, AdventureError, Scene, install_upload, list_adventures, load_adventure)
from khranitel import state

ROOT = Path(__file__).resolve().parents[1]
ADVENTURES = ROOT / "adventures"
STATE_PATH = ROOT / "data" / "state.json"
POLL_QUESTION = "Что делаем?"
router = Router()
_lock = asyncio.Lock()


def _admins() -> set[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    found = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            found.add(int(part))
    return found


def _is_admin(message: Message) -> bool:
    user = message.from_user
    return user is not None and user.id in _admins()


def _load_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def _deny(message: Message) -> None:
    await message.answer("Это может только ведущий. Его id записан в ADMIN_IDS.")


@router.message(Command("start", "help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Хранитель приключений ведёт общее приключение в чате.\n"
        "Ведущий запускает сценарий — бот показывает сцену и открывает голосование.\n"
        "Когда время выходит, бот пишет, какой путь взяло большинство, "
        "описание последствий, картинку и следующее голосование.\n\n"
        "/adventures — какие сценарии уже лежат у бота\n"
        "/begin имя — начать в этом чате\n"
        "/status — что идёт сейчас\n"
        "/stop — прервать\n\n"
        "Новый сценарий ведущий присылает боту в личку: файл adventure.yaml "
        "или zip с adventure.yaml и картинками. Свой сценарий собирает "
        "генератор: python -m generator")


@router.message(Command("adventures"))
async def adventures_command(message: Message) -> None:
    try:
        items = list_adventures(ADVENTURES)
    except AdventureError as error:
        await message.answer("Сценарий повреждён:\n" + "\n".join(error.errors))
        return
    if not items:
        await message.answer("Сценариев пока нет. Пришлите yaml или zip в личку бота.")
        return
    lines = [f"• {item.slug} — {item.title} ({item.vote_minutes} мин.)" for item in items]
    await message.answer("Сценарии:\n" + "\n".join(lines))


@router.message(Command("begin"))
async def begin_command(message: Message, command: CommandObject) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    slug = (command.args or "").strip()
    if not slug:
        await adventures_command(message)
        return
    folder = ADVENTURES / slug
    try:
        adventure = load_adventure(folder)
    except AdventureError as error:
        await message.answer("Не запускаю:\n" + "\n".join(error.errors))
        return
    async with _lock:
        data = state.load(STATE_PATH)
        if state.session(data, message.chat.id):
            await message.answer("В этом чате уже идёт приключение. /stop — прервать.")
            return
    await message.answer(f"Начинаем «{adventure.title}». На голосование — {adventure.vote_minutes} мин.")
    await _enter(message.bot, message.chat.id, adventure, adventure.start)


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    data = state.load(STATE_PATH)
    current = state.session(data, message.chat.id)
    if not current:
        await message.answer("В этом чате приключение не идёт.")
        return
    left = max(0, int(current["deadline"] - time.time()))
    minutes, seconds = divmod(left, 60)
    await message.answer(
        f"«{current['title']}», сцена {current['node']}. "
        f"До конца голосования {minutes} мин. {seconds} сек.")


@router.message(Command("stop"))
async def stop_command(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    async with _lock:
        data = state.load(STATE_PATH)
        current = state.session(data, message.chat.id)
        if current:
            state.put(data, message.chat.id, None)
            state.save(STATE_PATH, data)
    if not current:
        await message.answer("Останавливать нечего.")
        return
    await message.answer("Приключение остановлено. Голосование в чате можно закрыть вручную.")


@router.message(F.document)
async def upload(message: Message) -> None:
    if message.chat.type != "private":
        return
    if not _is_admin(message):
        await _deny(message)
        return
    document = message.document
    if document is None or not document.file_name:
        return
    name = document.file_name
    lower = name.lower()
    if not (lower.endswith(".yaml") or lower.endswith(".yml") or lower.endswith(".zip")):
        await message.answer("Нужен adventure.yaml или zip, в котором он лежит.")
        return
    if document.file_size and document.file_size > 20_000_000:
        await message.answer("Файл больше 20 МБ.")
        return
    blob = io.BytesIO()
    await message.bot.download(document, destination=blob)
    slug = _slug(name)
    try:
        adventure = install_upload(ADVENTURES / slug, name, blob.getvalue())
    except AdventureError as error:
        details = getattr(error, "errors", None)
        text = "\n".join(details) if details else str(error)
        await message.answer("Не принял сценарий:\n" + text)
        return
    await message.answer(
        f"Сценарий «{adventure.title}» сохранён как {slug}. "
        f"В чате сообщества: /begin {slug}")


def _slug(filename: str) -> str:
    stem = Path(filename).stem
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    return (slug or "adventure")[:64]


async def _enter(bot: Bot, chat_id: int, adventure: Adventure, scene_id: str,
                 *, chain: set[str] | None = None) -> None:
    chain = set() if chain is None else chain
    if scene_id in chain:
        await bot.send_message(chat_id, "Сценарий зациклился без выбора. Останавливаюсь.")
        return
    scene = adventure.scene(scene_id)
    await _show_scene(bot, chat_id, adventure, scene, scene.text)
    if len(scene.choices) >= 2:
        await _open_poll(bot, chat_id, adventure, scene)
        return
    if len(scene.choices) == 1:
        only = scene.choices[0]
        await bot.send_message(chat_id, f"Другого пути нет: «{only.label}».")
        chain.add(scene_id)
        await _enter(bot, chat_id, adventure, only.next, chain=chain)
        return
    async with _lock:
        data = state.load(STATE_PATH)
        state.put(data, chat_id, None)
        state.save(STATE_PATH, data)
    await bot.send_message(chat_id, f"«{adventure.title}» закончилось.")


async def _show_scene(bot: Bot, chat_id: int, adventure: Adventure, scene: Scene, text: str) -> None:
    picture = adventure.image_path(scene)
    if picture is None:
        await bot.send_message(chat_id, text)
        return
    photo = FSInputFile(picture)
    if len(text) <= 1024:
        await bot.send_photo(chat_id, photo, caption=text)
        return
    await bot.send_photo(chat_id, photo)
    await bot.send_message(chat_id, text)


async def _open_poll(bot: Bot, chat_id: int, adventure: Adventure, scene: Scene) -> None:
    labels = [choice.label for choice in scene.choices]
    poll = await bot.send_poll(chat_id, POLL_QUESTION, labels, is_anonymous=True)
    async with _lock:
        data = state.load(STATE_PATH)
        state.put(data, chat_id, {
            "adventure": adventure.slug,
            "title": adventure.title,
            "node": scene.id,
            "message_id": poll.message_id,
            "deadline": time.time() + adventure.vote_minutes * 60,
            "labels": labels,
            "next": [choice.next for choice in scene.choices],
        })
        state.save(STATE_PATH, data)


async def close_due(bot: Bot) -> None:
    """Закрыть голосования, у которых вышло время."""
    async with _lock:
        data = state.load(STATE_PATH)
        due = []
        now = time.time()
        for key, current in list(data["chats"].items()):
            if isinstance(current, dict) and now >= float(current.get("deadline", 0)):
                due.append((int(key), current))
                state.put(data, int(key), None)
        if due:
            state.save(STATE_PATH, data)
    for chat_id, current in due:
        await _finish(bot, chat_id, current)


async def _finish(bot: Bot, chat_id: int, current: dict) -> None:
    try:
        adventure = load_adventure(ADVENTURES / current["adventure"])
        closed = await bot.stop_poll(chat_id, int(current["message_id"]))
    except Exception as error:
        details = getattr(error, "errors", None)
        text = "\n".join(details) if details else "Не удалось закрыть голосование. Приключение остановлено."
        await bot.send_message(chat_id, text)
        return
    counts = [option.voter_count for option in closed.options]
    labels = list(current["labels"])
    if len(counts) != len(labels):
        await bot.send_message(chat_id, "Опрос не совпал со сценарием. Приключение остановлено.")
        return
    index, _reason = decide(counts)
    await bot.send_message(chat_id, verdict(labels, counts))
    await _enter(bot, chat_id, adventure, current["next"][index])


async def _watch(bot: Bot) -> None:
    while True:
        try:
            await close_due(bot)
        except Exception as error:
            print(f"голосование: {error}", flush=True)
        await asyncio.sleep(2)


async def main() -> None:
    _load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("В .env нет TELEGRAM_BOT_TOKEN")
    if not _admins():
        raise SystemExit("В .env нет ADMIN_IDS")
    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(router)
    watcher = asyncio.create_task(_watch(bot))
    try:
        await dp.start_polling(bot)
    finally:
        watcher.cancel()
        await bot.session.close()
