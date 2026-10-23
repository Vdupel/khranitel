"""Админ-режим в личке: обновление, перезапуск, статистика."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from khranitel import stats as stats_mod
from khranitel import state, tales, techlog, updater
from khranitel.format import AdventureError

ROOT = Path(__file__).resolve().parents[1]
ADVENTURES = ROOT / "adventures"
STATE_PATH = ROOT / "data" / "state.json"
ADMIN_TTL_SEC = 6 * 3600

router = Router()


def _panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обновить код с GitHub", callback_data="adm:pull_full")],
        [
            InlineKeyboardButton(text="Обновить истории", callback_data="adm:pull_stories"),
            InlineKeyboardButton(text="Перечитать истории", callback_data="adm:reload"),
        ],
        [
            InlineKeyboardButton(text="Статистика", callback_data="adm:stats"),
            InlineKeyboardButton(text="Картинка статистики", callback_data="adm:stats_img"),
        ],
        [InlineKeyboardButton(text="Перезапуск бота", callback_data="adm:restart")],
    ])


def _is_private(message: Message) -> bool:
    return message.chat.type == "private"


def grant_admin(user_id: int) -> None:
    data = state.load(STATE_PATH)
    sessions = data.setdefault("admin_sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        data["admin_sessions"] = sessions
    sessions[str(user_id)] = time.time()
    state.save(STATE_PATH, data)


def is_admin_session(user_id: int) -> bool:
    data = state.load(STATE_PATH)
    sessions = data.get("admin_sessions")
    if not isinstance(sessions, dict):
        return False
    stamp = sessions.get(str(user_id))
    if stamp is None:
        return False
    try:
        when = float(stamp)
    except (TypeError, ValueError):
        return False
    if time.time() - when > ADMIN_TTL_SEC:
        sessions.pop(str(user_id), None)
        state.save(STATE_PATH, data)
        return False
    return True


def _deny_cb() -> str:
    return "Нужен админ-режим: /admin <токен> в личке."


@router.message(Command("admin"))
async def admin_command(message: Message, command: CommandObject) -> None:
    if not _is_private(message):
        return
    token = (command.args or "").strip()
    data = state.load(STATE_PATH)
    state.ensure_admin_token(data, None)
    state.save(STATE_PATH, data)
    data = state.load(STATE_PATH)
    expected = data.get("admin_token")
    if not token or token != expected:
        await message.answer("Нужен верный админ-токен: /admin <токен>")
        return
    if message.from_user is None:
        return
    grant_admin(message.from_user.id)
    techlog.get().info("admin panel opened by %s", message.from_user.id)
    await message.answer(
        "Админ-режим Хранителя.\n"
        "Обновление с GitHub, перечитывание историй, перезапуск и статистика.",
        reply_markup=_panel_keyboard(),
    )


@router.callback_query(F.data.startswith("adm:"))
async def admin_callbacks(query: CallbackQuery, bot: Bot) -> None:
    user = query.from_user
    if user is None or not is_admin_session(user.id):
        await query.answer(_deny_cb(), show_alert=True)
        return
    action = (query.data or "").split(":", 1)[-1]
    log = techlog.get()
    chat_id = query.message.chat.id if query.message else user.id

    if action == "pull_full":
        await query.answer("Тяну код…")
        result = await asyncio.to_thread(updater.pull_full)
        log.info("admin pull_full: ok=%s changed=%s %s", result.ok, result.changed, result.message)
        text = result.message
        if result.detail:
            text += "\n" + result.detail[:500]
        await bot.send_message(chat_id, text)
        if result.ok and result.changed:
            await bot.send_message(chat_id, "Перезапускаюсь…")
            await asyncio.sleep(1)
            updater.request_exit_for_watchdog()
        return

    if action == "pull_stories":
        await query.answer("Проверяю истории…")
        result = await asyncio.to_thread(updater.pull_adventures)
        log.info("admin pull_stories: ok=%s changed=%s %s", result.ok, result.changed, result.message)
        text = result.message
        if result.detail:
            text += "\n" + result.detail[:500]
        if result.ok and result.changed:
            text += "\n" + _reload_catalog_text()
        await bot.send_message(chat_id, text)
        return

    if action == "reload":
        await query.answer("Перечитываю…")
        text = _reload_catalog_text()
        log.info("admin reload catalog")
        await bot.send_message(chat_id, text)
        return

    if action == "stats":
        await query.answer()
        text = stats_mod.summary_text(adventures_root=ADVENTURES)
        await bot.send_message(chat_id, text)
        return

    if action == "stats_img":
        await query.answer("Рисую…")
        try:
            png = await asyncio.to_thread(stats_mod.render_overview_image)
        except Exception as error:
            log.exception("stats image failed")
            await bot.send_message(chat_id, f"Не нарисовал картинку: {error}")
            return
        await bot.send_photo(
            chat_id,
            BufferedInputFile(png, filename="stats.png"),
            caption="Сводка прохождений",
        )
        # дополнительно — картинки по топ-историям
        data = stats_mod.load_stats()
        ranked = sorted(
            ((int(b.get("plays", 0)), slug)
             for slug, b in (data.get("tales") or {}).items()
             if isinstance(b, dict)),
            reverse=True,
        )[:3]
        for _plays, slug in ranked:
            tale = tales.tale_by_slug(ADVENTURES, slug)
            if tale is None:
                continue
            advs = {}
            for vid in tale.variant_ids():
                try:
                    advs[vid] = tale.load(vid)
                except AdventureError:
                    continue
            try:
                png = await asyncio.to_thread(
                    stats_mod.render_tale_image, slug, advs, tale.title)
            except Exception as error:
                log.exception("tale image %s failed", slug)
                await bot.send_message(chat_id, f"{slug}: {error}")
                continue
            await bot.send_photo(
                chat_id,
                BufferedInputFile(png, filename=f"stats-{slug}.png"),
                caption=f"Статистика «{tale.title}»",
            )
        return

    if action == "restart":
        await query.answer("Перезапуск…")
        log.info("admin requested restart")
        await bot.send_message(chat_id, "Перезапускаюсь по команде ведущего.")
        await asyncio.sleep(1)
        updater.request_exit_for_watchdog()
        return

    await query.answer("Неизвестная кнопка", show_alert=True)


def _reload_catalog_text() -> str:
    try:
        catalog = tales.discover_tales(ADVENTURES)
    except Exception as error:
        techlog.get().exception("reload failed")
        return f"Не перечитал каталог: {error}"
    if not catalog:
        return "Каталог пуст — историй нет."
    lines = [f"Перечитал {len(catalog)} историй:"]
    for tale in catalog:
        lines.append(f"• {tale.slug} — {tale.title} ({', '.join(tale.variant_ids())})")
    return "\n".join(lines)
