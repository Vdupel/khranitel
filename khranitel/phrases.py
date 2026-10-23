"""Реплики Хранителя: старты, финалы, стоп, велком."""

from __future__ import annotations

import random

START_PHRASES = (
    "Сказитель откашливается. «{title}» — слушайте.",
    "Огонь в очаге щёлкает. Пора для «{title}».",
    "Тише у костра — начинается «{title}».",
    "Хранитель раскрывает свиток: «{title}».",
    "Ветер приносит первую строку «{title}».",
    "Кто-то уже шепчет название: «{title}». Дальше — вслух.",
    "Скамьи подвинули. Расскажу «{title}».",
)

STOP_LAMENTS = (
    "Эх… историю не дослушали. Свиток закрываю на середине строки.",
    "Жаль. Герои замерли на полуслове — сказ оборвали.",
    "Костёр ещё горит, а слушатели уже ушли. Останавливаю сказ.",
    "Страница так и останется недочитанной. Сокрушаюсь, но молчу.",
    "Знал бы сказитель, что оборвут на самом вкусе… Стоп.",
)

END_PHRASES = (
    "«{title}» досказана.\n\nА может, было по-другому? /retell — рассказать снова.",
    "Конец «{title}».\n\nА может, было по-другому? Команда /retell вернёт вас к началу.",
    "Свиток «{title}» свёрнут.\n\nА может, было по-другому? Жмите /retell.",
)

BEGIN_PROMPTS = (
    "Три истории на языке. За какую голосовать?",
    "Сказитель предлагает на выбор. Что слушаем?",
    "У костра три свитка. Какой развернуть?",
)

SPOILER_PROMPTS = (
    "Спойлеры испортили сказ? Можно взять другую версию «{title}».",
    "Кто-то уже выболтал сюжет. Перейти на иную версию «{title}»?",
    "Историю проспойлерили. Хранитель может рассказать «{title}» иначе.",
)

WELCOME_PRIVATE = (
    "Вы написали Хранителю в личку.\n"
    "Здесь сказ идёт только для вас: голосуете — и сразу следующий кусок, "
    "без ожидания таймера.\n\n"
    "Команды: /help"
)

BACK_LABEL = "↩ Назад"


def skillcheck_admin_hint(scene_id: str, lines: list[str]) -> str:
    """Текст только для /test: где в этой сцене спрятаны скиллчеки."""
    body = "\n".join(f"• {line}" for line in lines)
    return (
        f"Админ /test — скиллчеки сцены «{scene_id}» "
        f"(игрокам не видно):\n{body}"
    )


def skillcheck_admin_roll(label: str, outcome: str, detail: dict) -> str:
    word = "успех" if outcome == "success" else "провал"
    return (
        f"Админ /test — скиллчек «{label}»: порог {detail['threshold']}% "
        f"(диапазон {detail['chance_min']}–{detail['chance_max']}), "
        f"d100 = {detail['roll']} → {word} → {detail['dest']}"
    )


def pick(options: tuple[str, ...] | list[str]) -> str:
    return random.choice(list(options))


def start_line(title: str) -> str:
    return pick(START_PHRASES).format(title=title)


def stop_lament() -> str:
    return pick(STOP_LAMENTS)


def end_line(title: str) -> str:
    return pick(END_PHRASES).format(title=title)


def begin_prompt() -> str:
    return pick(BEGIN_PROMPTS)


def spoiler_prompt(title: str) -> str:
    return pick(SPOILER_PROMPTS).format(title=title)


def help_text(*, private: bool, group: bool) -> str:
    if private:
        return (
            "Хранитель в личке — ваш личный сказитель.\n\n"
            "/begin — выбрать одну из трёх историй и слушать сразу\n"
            "/retell — пересказать только что оконченную историю\n"
            "/status — где вы сейчас в сказе\n"
            "/stop — оборвать сказ\n"
            "/help — этот список\n\n"
            "В личке бот не ждёт таймер: ответил в опросе — сразу продолжение."
        )
    # group
    lines = [
        "Хранитель ведёт общее приключение в чате.",
        "",
        "/begin — голосование: три истории на выбор",
        "/retell — пересказать только что оконченную",
        "/status — сколько осталось до конца голосования",
        "/stop — оборвать сказ (ведущий)",
        "/spoiler — другая версия: эту уже проспойлерили",
        "/adventures — список свитков у бота",
        "/help — этот список",
        "",
        "Новый сценарий ведущий шлёт в личку: adventure.yaml или zip.",
    ]
    if group:
        return "\n".join(lines)
    return "\n".join(lines)
