"""Телеграм-бот. Сказ в чате/теме, версии историй, тест с «назад»."""

from __future__ import annotations

import asyncio
import io
import os
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, Message, PollAnswer

from khranitel.engine import decide, roll_check, verdict
from khranitel.format import Adventure, AdventureError, Choice, Scene, install_upload
from khranitel import admin, phrases, state, stats, tales, techlog, timing

ROOT = Path(__file__).resolve().parents[1]
ADVENTURES = ROOT / "adventures"
STATE_PATH = ROOT / "data" / "state.json"
POLL_QUESTION = "Что делаем?"
BEGIN_VOTE_MINUTES = 5
SPOILER_VOTE_MINUTES = 5
INSTANT_DEADLINE_PAD = 365 * 24 * 3600
BACK_NEXT = "__back__"
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
    """Пустой ADMIN_IDS — команды доступны всем. Для запуска достаточно токена."""
    admins = _admins()
    if not admins:
        return True
    user = message.from_user
    return user is not None and user.id in admins


def _is_private(message: Message) -> bool:
    return message.chat.type == "private"


def _is_group(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


def _thread_id(message: Message) -> int | None:
    """Тема форума, если команда пришла из топика; иначе None."""
    return message.message_thread_id


def _thread_kw(thread_id: int | None) -> dict:
    return {"message_thread_id": thread_id} if thread_id is not None else {}


async def _say(bot: Bot, chat_id: int, text: str, *, thread_id: int | None) -> None:
    await bot.send_message(chat_id, text, **_thread_kw(thread_id))


async def _expect_voters(bot: Bot, chat_id: int) -> int:
    try:
        total = await bot.get_chat_member_count(chat_id)
    except Exception:
        return 1
    return timing.expect_voters_from_member_count(total)


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


async def _maybe_welcome(message: Message) -> None:
    if not _is_private(message) or message.from_user is None:
        return
    async with _lock:
        data = state.load(STATE_PATH)
        first = state.mark_welcomed(data, message.from_user.id)
        if first:
            state.save(STATE_PATH, data)
    if first:
        await message.answer(phrases.WELCOME_PRIVATE)


@router.message(Command("start"))
async def start_command(message: Message) -> None:
    if _is_private(message):
        async with _lock:
            data = state.load(STATE_PATH)
            if message.from_user is not None:
                state.mark_welcomed(data, message.from_user.id)
                state.save(STATE_PATH, data)
        await message.answer(phrases.WELCOME_PRIVATE)
        await message.answer(phrases.help_text(private=True, group=False))
        return
    await message.answer(phrases.help_text(private=False, group=True))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await _maybe_welcome(message)
    await message.answer(
        phrases.help_text(private=_is_private(message), group=_is_group(message)))


@router.message(Command("adventures"))
async def adventures_command(message: Message) -> None:
    await _maybe_welcome(message)
    try:
        items = tales.discover_tales(ADVENTURES)
    except AdventureError as error:
        await message.answer("Сценарий повреждён:\n" + "\n".join(error.errors))
        return
    if not items:
        await message.answer("Историй пока нет. Пришлите yaml или zip в личку бота.")
        return
    lines = []
    for item in items:
        versions = ", ".join(item.variant_ids())
        lines.append(f"• {item.slug} — {item.title} (версии: {versions})")
    await message.answer("Истории:\n" + "\n".join(lines))


@router.message(Command("begin"))
async def begin_command(message: Message, command: CommandObject) -> None:
    await _maybe_welcome(message)
    if _is_group(message) and not _is_admin(message):
        await _deny(message)
        return
    thread_id = _thread_id(message)
    slug = (command.args or "").strip()
    async with _lock:
        data = state.load(STATE_PATH)
        if state.session(data, message.chat.id, thread_id):
            await message.answer("Здесь уже идёт сказ. /stop — оборвать.")
            return
    if slug:
        await _start_tale(
            message.bot, message.chat.id, slug,
            instant=_is_private(message), thread_id=thread_id)
        return
    await _open_begin_vote(
        message.bot, message.chat.id,
        instant=_is_private(message), thread_id=thread_id)


@router.message(Command("retell"))
async def retell_command(message: Message) -> None:
    await _maybe_welcome(message)
    thread_id = _thread_id(message)
    async with _lock:
        data = state.load(STATE_PATH)
        if state.session(data, message.chat.id, thread_id):
            await message.answer("Сначала дослушайте или /stop — иначе два сказа сразу.")
            return
        finished = state.last_finished(data, message.chat.id, thread_id)
    if not finished:
        await message.answer("Ещё нечего пересказывать — ни одна история здесь не закончилась.")
        return
    await _start_tale(
        message.bot,
        message.chat.id,
        finished["tale"],
        variant=finished.get("variant"),
        instant=_is_private(message) or bool(finished.get("test")),
        test=bool(finished.get("test")),
        thread_id=thread_id,
    )


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    await _maybe_welcome(message)
    thread_id = _thread_id(message)
    data = state.load(STATE_PATH)
    current = state.session(data, message.chat.id, thread_id)
    if not current:
        await message.answer("Здесь сказ не идёт.")
        return
    kind = current.get("kind", "scene")
    voted = len(current.get("voters") or [])
    expect = int(current.get("expect_voters") or 0)
    vote_tail = ""
    if expect and not current.get("instant"):
        vote_tail = f" Голосов {voted}/{expect}."
    if kind == "begin":
        left = max(0, int(current["deadline"] - time.time()))
        minutes, seconds = divmod(left, 60)
        await message.answer(
            f"Выбираем историю. До конца голосования {minutes} мин. {seconds} сек."
            f"{vote_tail}")
        return
    if kind == "spoiler":
        left = max(0, int(current["deadline"] - time.time()))
        minutes, seconds = divmod(left, 60)
        await message.answer(
            f"Голосуем за другую версию «{current.get('tale_title', current.get('title', ''))}». "
            f"Осталось {minutes} мин. {seconds} сек.{vote_tail}")
        return
    title = current.get("title", "?")
    node = current.get("node", "?")
    if current.get("instant"):
        await message.answer(f"«{title}», сцена {node}. Жду ваш голос — отвечу сразу.")
        return
    left = max(0, int(current["deadline"] - time.time()))
    minutes, seconds = divmod(left, 60)
    await message.answer(
        f"«{title}», сцена {node}. "
        f"До конца голосования {minutes} мин. {seconds} сек.{vote_tail}")


@router.message(Command("stop"))
async def stop_command(message: Message) -> None:
    await _maybe_welcome(message)
    if _is_group(message) and not _is_admin(message):
        await _deny(message)
        return
    thread_id = _thread_id(message)
    async with _lock:
        data = state.load(STATE_PATH)
        current = state.session(data, message.chat.id, thread_id)
        if current:
            state.put(data, message.chat.id, None, thread_id)
            state.save(STATE_PATH, data)
    if not current:
        await message.answer("Останавливать нечего — и так тихо.")
        return
    await message.answer(phrases.stop_lament())


@router.message(Command("spoiler"))
async def spoiler_command(message: Message) -> None:
    if not _is_group(message):
        return
    thread_id = _thread_id(message)
    async with _lock:
        data = state.load(STATE_PATH)
        current = state.session(data, message.chat.id, thread_id)
        finished = state.last_finished(data, message.chat.id, thread_id)
    tale_slug = None
    variant = None
    if current and current.get("kind") == "scene":
        tale_slug = current.get("tale")
        variant = current.get("variant")
    elif finished:
        tale_slug = finished.get("tale")
        variant = finished.get("variant")
    if not tale_slug:
        await message.answer("Нечего спасать от спойлеров — сказ сейчас не идёт и недавно не кончался.")
        return
    tale = tales.tale_by_slug(ADVENTURES, tale_slug)
    if tale is None:
        await message.answer("Свиток этой истории утерян.")
        return
    others = tales.other_variants(tale, variant or "")
    if not others:
        await message.answer(
            f"У «{tale.title}» пока одна версия. Сказитель ещё не положил другую.")
        return
    if current:
        async with _lock:
            data = state.load(STATE_PATH)
            state.put(data, message.chat.id, None, thread_id)
            state.save(STATE_PATH, data)
    labels = []
    nexts = []
    for vid in others:
        try:
            adv = tale.load(vid)
            labels.append(f"{adv.title} [{vid}]"[:100])
        except AdventureError:
            labels.append(vid[:100])
        nexts.append(vid)
    labels.append("Оставить как есть")
    nexts.append("__keep__")
    await message.answer(phrases.spoiler_prompt(tale.title))
    expect = await _expect_voters(message.bot, message.chat.id)
    wait = timing.vote_wait_seconds(expect, SPOILER_VOTE_MINUTES)
    poll = await message.bot.send_poll(
        message.chat.id, "Другая версия?", labels,
        is_anonymous=False, **_thread_kw(thread_id))
    async with _lock:
        data = state.load(STATE_PATH)
        state.put(data, message.chat.id, {
            "kind": "spoiler",
            "instant": False,
            "test": False,
            "thread_id": thread_id,
            "tale": tale.slug,
            "variant": variant,
            "tale_title": tale.title,
            "title": tale.title,
            "message_id": poll.message_id,
            "poll_id": poll.poll.id if poll.poll else "",
            "deadline": time.time() + wait,
            "labels": labels,
            "next": nexts,
            "path": [],
            "expect_voters": expect,
            "voters": [],
        }, thread_id)
        state.save(STATE_PATH, data)


@router.message(Command("test"))
async def test_command(message: Message, command: CommandObject) -> None:
    if not _is_private(message):
        return
    await _maybe_welcome(message)
    token = (command.args or "").strip()
    async with _lock:
        data = state.load(STATE_PATH)
        expected = state.ensure_admin_token(
            data, os.environ.get("ADMIN_TOKEN"))
        state.save(STATE_PATH, data)
    if not token or token != expected:
        await message.answer("Нужен верный админ-токен: /test <токен>")
        return
    if state.session(state.load(STATE_PATH), message.chat.id):
        await message.answer("Сначала /stop — тест не наслаивается на текущий сказ.")
        return
    await message.answer(
        "Тестовый режим. Дальше /begin — сказ с пунктом «назад» в опросах, "
        "ответ сразу после голоса. Здесь же видны скрытые скиллчеки сцен.")
    await _open_begin_vote(
        message.bot, message.chat.id, instant=True, test=True, thread_id=None)


@router.message(F.document)
async def upload(message: Message) -> None:
    if not _is_private(message):
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
        f"История «{adventure.title}» сохранена как {slug} (версия default). "
        f"Другие версии сказитель кладёт в adventures/{slug}/variants/<id>/.")


@router.message(F.chat.type == "private")
async def private_fallback(message: Message) -> None:
    """Любое иное личное сообщение — велком один раз, иначе подсказка."""
    if message.text and message.text.startswith("/"):
        return
    await _maybe_welcome(message)


@router.poll_answer()
async def on_poll_answer(answer: PollAnswer, bot: Bot) -> None:
    """Мгновенный режим или досрочное закрытие, когда проголосовали все."""
    poll_id = answer.poll_id
    async with _lock:
        data = state.load(STATE_PATH)
        found = state.find_by_poll(data, poll_id)
        if found is None:
            return
        _key, chat_id, thread_id, current = found
        if current.get("instant"):
            state.put(data, chat_id, None, thread_id)
            state.save(STATE_PATH, data)
            finish_now = True
            prefetched = answer.option_ids
        else:
            voters = {int(v) for v in current.get("voters") or []}
            user = answer.user
            if user is not None:
                if answer.option_ids:
                    voters.add(user.id)
                else:
                    voters.discard(user.id)
            current["voters"] = sorted(voters)
            state.put(data, chat_id, current, thread_id)
            expect = int(current.get("expect_voters") or 0)
            finish_now = expect > 0 and len(voters) >= expect
            if finish_now:
                state.put(data, chat_id, None, thread_id)
            state.save(STATE_PATH, data)
            prefetched = None
    if not finish_now:
        return
    await _finish(
        bot, chat_id, current,
        thread_id=thread_id,
        prefetched_option=prefetched,
    )


def _slug(filename: str) -> str:
    stem = Path(filename).stem
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")
    return (slug or "adventure")[:64]


async def _open_begin_vote(
    bot: Bot,
    chat_id: int,
    *,
    instant: bool,
    test: bool = False,
    thread_id: int | None = None,
) -> None:
    catalog = tales.discover_tales(ADVENTURES)
    if not catalog:
        await _say(bot, chat_id, "Историй нет. Сказитель ещё не положил свитки.",
                   thread_id=thread_id)
        return
    async with _lock:
        data = state.load(STATE_PATH)
        cool = state.chat_cooldowns(data, chat_id, thread_id)
        candidates = tales.pick_candidates(catalog, cool)
        state.save(STATE_PATH, data)
    if not candidates:
        await _say(bot, chat_id, "Не из чего выбирать.", thread_id=thread_id)
        return
    if len(candidates) == 1:
        only = candidates[0]
        async with _lock:
            data = state.load(STATE_PATH)
            cool = state.chat_cooldowns(data, chat_id, thread_id)
            tales.tick_cooldowns(cool)
            state.save(STATE_PATH, data)
        await _say(
            bot, chat_id,
            f"На кону одна история — «{only.title}». Иного свитка нет.",
            thread_id=thread_id)
        await _start_tale(
            bot, chat_id, only.slug, instant=instant, test=test, thread_id=thread_id)
        return
    labels = [f"{tale.title}"[:100] for tale in candidates]
    nexts = [tale.slug for tale in candidates]
    await _say(bot, chat_id, phrases.begin_prompt(), thread_id=thread_id)
    expect = 1 if instant else await _expect_voters(bot, chat_id)
    wait = (
        INSTANT_DEADLINE_PAD if instant
        else timing.vote_wait_seconds(expect, BEGIN_VOTE_MINUTES))
    poll = await bot.send_poll(
        chat_id,
        "Какую историю слушаем?",
        labels,
        is_anonymous=False,
        **_thread_kw(thread_id),
    )
    async with _lock:
        data = state.load(STATE_PATH)
        cool = state.chat_cooldowns(data, chat_id, thread_id)
        tales.tick_cooldowns(cool)
        state.put(data, chat_id, {
            "kind": "begin",
            "instant": instant,
            "test": test,
            "thread_id": thread_id,
            "message_id": poll.message_id,
            "poll_id": poll.poll.id if poll.poll else "",
            "deadline": time.time() + wait,
            "labels": labels,
            "next": nexts,
            "path": [],
            "expect_voters": expect,
            "voters": [],
        }, thread_id)
        state.save(STATE_PATH, data)


async def _start_tale(
    bot: Bot,
    chat_id: int,
    tale_slug: str,
    *,
    variant: str | None = None,
    instant: bool = False,
    test: bool = False,
    thread_id: int | None = None,
) -> None:
    tale = tales.tale_by_slug(ADVENTURES, tale_slug)
    if tale is None:
        await _say(bot, chat_id, f"Истории «{tale_slug}» нет.", thread_id=thread_id)
        return
    try:
        variant_id = variant if variant in tale.variants else tales.pick_variant(tale)
        adventure = tale.load(variant_id)
    except AdventureError as error:
        await _say(bot, chat_id, "Не запускаю:\n" + "\n".join(error.errors),
                   thread_id=thread_id)
        return
    except KeyError:
        await _say(bot, chat_id, "Версия истории не найдена.", thread_id=thread_id)
        return
    await _say(bot, chat_id, phrases.start_line(adventure.title), thread_id=thread_id)
    await _enter(
        bot, chat_id, adventure,
        adventure.start,
        tale_slug=tale.slug,
        variant_id=variant_id,
        instant=instant,
        test=test,
        path=[],
        thread_id=thread_id,
    )


async def _enter(
    bot: Bot,
    chat_id: int,
    adventure: Adventure,
    scene_id: str,
    *,
    tale_slug: str,
    variant_id: str,
    instant: bool,
    test: bool,
    path: list[str],
    thread_id: int | None,
    chain: set[str] | None = None,
) -> None:
    chain = set() if chain is None else chain
    if scene_id in chain:
        await _say(bot, chat_id, "Сценарий зациклился без выбора. Останавливаюсь.",
                   thread_id=thread_id)
        return
    scene = adventure.scene(scene_id)
    await _show_scene(bot, chat_id, adventure, scene, scene.text, thread_id=thread_id)
    choices = list(scene.choices)
    if len(choices) >= 2 or (test and path and len(choices) >= 1):
        await _open_scene_poll(
            bot, chat_id, adventure, scene,
            tale_slug=tale_slug,
            variant_id=variant_id,
            instant=instant,
            test=test,
            path=path,
            thread_id=thread_id,
        )
        return
    if len(choices) == 1 and not (test and path):
        only = choices[0]
        await _say(bot, chat_id, f"Другого пути нет: «{only.label}».", thread_id=thread_id)
        dest = only.next
        if only.is_check:
            dest, outcome, detail = roll_check(
                only.chance_min, only.chance_max,
                success=only.next, fail=only.fail)
            if test:
                await _say(
                    bot, chat_id,
                    phrases.skillcheck_admin_roll(only.label, outcome, detail),
                    thread_id=thread_id)
        if not test:
            try:
                stats.record_choice(tale_slug, variant_id, scene_id, only.label)
            except Exception:
                techlog.get().exception("stats record_choice failed")
        chain.add(scene_id)
        await _enter(
            bot, chat_id, adventure, dest,
            tale_slug=tale_slug,
            variant_id=variant_id,
            instant=instant,
            test=test,
            path=path + [scene_id],
            thread_id=thread_id,
            chain=chain,
        )
        return
    if test and path and len(choices) == 0:
        await _open_scene_poll(
            bot, chat_id, adventure, scene,
            tale_slug=tale_slug,
            variant_id=variant_id,
            instant=instant,
            test=test,
            path=path,
            thread_id=thread_id,
        )
        return
    await _finish_story(
        bot, chat_id, adventure, tale_slug, variant_id,
        ending_scene=scene_id,
        test=test, thread_id=thread_id)


async def _finish_story(
    bot: Bot,
    chat_id: int,
    adventure: Adventure,
    tale_slug: str,
    variant_id: str,
    *,
    ending_scene: str,
    test: bool,
    thread_id: int | None,
) -> None:
    async with _lock:
        data = state.load(STATE_PATH)
        state.put(data, chat_id, None, thread_id)
        cool = state.chat_cooldowns(data, chat_id, thread_id)
        tales.mark_played(cool, tale_slug)
        state.set_last_finished(data, chat_id, {
            "tale": tale_slug,
            "variant": variant_id,
            "title": adventure.title,
            "test": test,
        }, thread_id)
        state.save(STATE_PATH, data)
    if not test:
        try:
            stats.record_play(tale_slug, variant_id, ending_scene, completed=True)
        except Exception:
            techlog.get().exception("stats record_play failed")
    await _say(bot, chat_id, phrases.end_line(adventure.title), thread_id=thread_id)


async def _show_scene(
    bot: Bot,
    chat_id: int,
    adventure: Adventure,
    scene: Scene,
    text: str,
    *,
    thread_id: int | None,
) -> None:
    picture = adventure.image_path(scene)
    kw = _thread_kw(thread_id)
    if picture is None:
        await bot.send_message(chat_id, text, **kw)
        return
    photo = FSInputFile(picture)
    if len(text) <= 1024:
        await bot.send_photo(chat_id, photo, caption=text, **kw)
        return
    await bot.send_photo(chat_id, photo, **kw)
    await bot.send_message(chat_id, text, **kw)


def _check_payload(choice: Choice) -> dict | None:
    if not choice.is_check:
        return None
    return {
        "chance_min": choice.chance_min,
        "chance_max": choice.chance_max,
        "success": choice.next,
        "fail": choice.fail,
    }


async def _open_scene_poll(
    bot: Bot,
    chat_id: int,
    adventure: Adventure,
    scene: Scene,
    *,
    tale_slug: str,
    variant_id: str,
    instant: bool,
    test: bool,
    path: list[str],
    thread_id: int | None,
) -> None:
    labels = [choice.label for choice in scene.choices]
    nexts = [choice.next for choice in scene.choices]
    checks: list[dict | None] = [_check_payload(choice) for choice in scene.choices]
    if test and path and len(labels) < 10:
        labels = labels + [phrases.BACK_LABEL]
        nexts = nexts + [BACK_NEXT]
        checks = checks + [None]
    if len(labels) < 2:
        if labels:
            await _say(bot, chat_id, f"Можно только: «{labels[0]}».", thread_id=thread_id)
            if nexts[0] == BACK_NEXT:
                prev = path[-1]
                await _enter(
                    bot, chat_id, adventure, prev,
                    tale_slug=tale_slug,
                    variant_id=variant_id,
                    instant=instant,
                    test=test,
                    path=path[:-1],
                    thread_id=thread_id,
                )
            return
        await _finish_story(
            bot, chat_id, adventure, tale_slug, variant_id,
            ending_scene=scene.id,
            test=test, thread_id=thread_id)
        return
    if test:
        hint_lines = []
        for choice in scene.choices:
            if not choice.is_check:
                continue
            hint_lines.append(
                f"«{choice.label}» — шанс {choice.chance_min}–{choice.chance_max}% "
                f"→ {choice.next} / провал → {choice.fail}")
        if hint_lines:
            await _say(
                bot, chat_id,
                phrases.skillcheck_admin_hint(scene.id, hint_lines),
                thread_id=thread_id)
    expect = 1 if instant else await _expect_voters(bot, chat_id)
    wait = (
        INSTANT_DEADLINE_PAD if instant
        else timing.vote_wait_seconds(expect, adventure.vote_minutes))
    poll = await bot.send_poll(
        chat_id, POLL_QUESTION, labels,
        is_anonymous=False, **_thread_kw(thread_id))
    async with _lock:
        data = state.load(STATE_PATH)
        state.put(data, chat_id, {
            "kind": "scene",
            "instant": instant,
            "test": test,
            "thread_id": thread_id,
            "tale": tale_slug,
            "variant": variant_id,
            "adventure": adventure.slug,
            "title": adventure.title,
            "node": scene.id,
            "message_id": poll.message_id,
            "poll_id": poll.poll.id if poll.poll else "",
            "deadline": time.time() + wait,
            "labels": labels,
            "next": nexts,
            "checks": checks,
            "path": list(path),
            "expect_voters": expect,
            "voters": [],
        }, thread_id)
        state.save(STATE_PATH, data)


async def close_due(bot: Bot) -> None:
    """Закрыть голосования, у которых вышло время (групповой режим)."""
    async with _lock:
        data = state.load(STATE_PATH)
        due = []
        now = time.time()
        for key, current in list(data["chats"].items()):
            if not isinstance(current, dict):
                continue
            if current.get("instant"):
                continue
            if now >= float(current.get("deadline", 0)):
                chat_id, thread_id = state.parse_scope_key(key)
                due.append((chat_id, thread_id, current))
                state.put(data, chat_id, None, thread_id)
        if due:
            state.save(STATE_PATH, data)
    for chat_id, thread_id, current in due:
        await _finish(bot, chat_id, current, thread_id=thread_id)


async def _finish(
    bot: Bot,
    chat_id: int,
    current: dict,
    *,
    thread_id: int | None = None,
    prefetched_option: list[int] | None = None,
) -> None:
    if thread_id is None and current.get("thread_id") is not None:
        thread_id = current.get("thread_id")
    kind = current.get("kind", "scene")
    try:
        if prefetched_option is not None:
            try:
                await bot.stop_poll(chat_id, int(current["message_id"]))
            except Exception:
                pass
            if not prefetched_option:
                index = 0
            else:
                index = int(prefetched_option[0])
            labels = list(current["labels"])
            if index < 0 or index >= len(labels):
                await _say(bot, chat_id, "Голос не из этого опроса. Сказ остановлен.",
                           thread_id=thread_id)
                return
            counts = [0] * len(labels)
            counts[index] = 1
        else:
            closed = await bot.stop_poll(chat_id, int(current["message_id"]))
            counts = [option.voter_count for option in closed.options]
            labels = list(current["labels"])
            if len(counts) != len(labels):
                await _say(bot, chat_id, "Опрос не совпал со сценарием. Сказ остановлен.",
                           thread_id=thread_id)
                return
            index, _reason = decide(counts)
            if not current.get("instant"):
                await _say(bot, chat_id, verdict(labels, counts), thread_id=thread_id)
    except Exception:
        await _say(bot, chat_id, "Не удалось закрыть голосование. Сказ остановлен.",
                   thread_id=thread_id)
        return

    chosen = current["next"][index]

    if kind == "begin":
        await _start_tale(
            bot, chat_id, chosen,
            instant=bool(current.get("instant")),
            test=bool(current.get("test")),
            thread_id=thread_id,
        )
        return

    if kind == "spoiler":
        if chosen == "__keep__":
            await _say(
                bot, chat_id,
                "Оставляем текущую версию. Спойлеры — ваша ноша.",
                thread_id=thread_id)
            return
        await _start_tale(
            bot, chat_id, current["tale"],
            variant=chosen,
            instant=False,
            test=False,
            thread_id=thread_id,
        )
        return

    tale_slug = current["tale"]
    variant_id = current["variant"]
    path = list(current.get("path") or [])
    instant = bool(current.get("instant"))
    test = bool(current.get("test"))
    try:
        tale = tales.tale_by_slug(ADVENTURES, tale_slug)
        if tale is None:
            raise AdventureError(["история исчезла"])
        adventure = tale.load(variant_id)
    except AdventureError as error:
        details = getattr(error, "errors", None)
        text = "\n".join(details) if details else str(error)
        await _say(bot, chat_id, text, thread_id=thread_id)
        return

    if chosen == BACK_NEXT:
        if not path:
            await _say(bot, chat_id, "Назад уже некуда.", thread_id=thread_id)
            return
        prev = path[-1]
        await _enter(
            bot, chat_id, adventure, prev,
            tale_slug=tale_slug,
            variant_id=variant_id,
            instant=instant,
            test=test,
            path=path[:-1],
            thread_id=thread_id,
        )
        return

    checks = list(current.get("checks") or [])
    check = checks[index] if index < len(checks) else None
    dest = chosen
    if isinstance(check, dict):
        dest, outcome, detail = roll_check(
            int(check["chance_min"]),
            int(check["chance_max"]),
            success=str(check["success"]),
            fail=str(check["fail"]),
        )
        if test:
            label = labels[index] if index < len(labels) else chosen
            await _say(
                bot, chat_id,
                phrases.skillcheck_admin_roll(label, outcome, detail),
                thread_id=thread_id)

    node = current["node"]
    label = labels[index] if index < len(labels) else ""
    if not test and label and label != phrases.BACK_LABEL:
        try:
            stats.record_choice(tale_slug, variant_id, node, label)
        except Exception:
            techlog.get().exception("stats record_choice failed")
    await _enter(
        bot, chat_id, adventure, dest,
        tale_slug=tale_slug,
        variant_id=variant_id,
        instant=instant,
        test=test,
        path=path + [node],
        thread_id=thread_id,
    )


async def _watch(bot: Bot) -> None:
    while True:
        try:
            await close_due(bot)
        except Exception as error:
            print(f"голосование: {error}", flush=True)
        await asyncio.sleep(2)


async def main() -> None:
    _load_env()
    log = techlog.setup()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
    if not token:
        print("В .env нет токена. Запустите ещё раз и вставьте токен.", flush=True)
        raise SystemExit(2)
    data = state.load(STATE_PATH)
    admin_token = state.ensure_admin_token(data, os.environ.get("ADMIN_TOKEN"))
    state.save(STATE_PATH, data)
    log.info("bot start; admin token ready")
    print(f"Админ-токен (/admin и /test): {admin_token}", flush=True)
    bot = Bot(token)
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        await bot.session.close()
        print("Токен не подошёл. Телеграм его не признал.", flush=True)
        print("В Телеграме откройте @BotFather, отправьте /mybots,", flush=True)
        print("выберите бота и нажмите API Token. Скопируйте токен заново.", flush=True)
        raise SystemExit(2)
    if _admins():
        who = "команды только у ведущих из ADMIN_IDS"
    else:
        who = "ведущий не задан, команды доступны всем в чате"
    print(f"Бот @{me.username} запущен. {who}.", flush=True)
    print("Окно не закрывать. Остановить — закрыть это окно.", flush=True)
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(router)
    watcher = asyncio.create_task(_watch(bot))
    try:
        await dp.start_polling(bot)
    finally:
        watcher.cancel()
        await bot.session.close()
        log.info("bot stopped")
