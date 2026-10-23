"""Чистое решение по итогам опроса и скиллчеков. Сеть сюда не входит."""

from __future__ import annotations

import random
from typing import Any


def decide(counts: list[int]) -> tuple[int, str]:
    """Индекс победителя и причина: majority, tie или none.

    Ничья — побеждает вариант, который в сценарии стоит раньше.
    Никто не голосовал — тоже первый вариант.
    """
    if not counts:
        raise ValueError("пустой опрос")
    if sum(counts) == 0:
        return 0, "none"
    best = max(counts)
    leaders = [index for index, count in enumerate(counts) if count == best]
    if len(leaders) > 1:
        return leaders[0], "tie"
    return leaders[0], "majority"


def verdict(labels: list[str], counts: list[int]) -> str:
    """Короткий абзац перед текстом победившей сцены."""
    index, reason = decide(counts)
    label = labels[index]
    votes = counts[index]
    if reason == "none":
        return f"Никто не проголосовал. Идём по первому пути: «{label}»."
    if reason == "tie":
        tied = [labels[i] for i, count in enumerate(counts) if count == votes]
        names = "», «".join(tied)
        return (f"Ничья между «{names}» ({votes}). "
                f"Берём тот, что раньше в сценарии: «{label}».")
    word = _votes(votes)
    return f"Большинство выбрало «{label}» — {votes} {word}."


def roll_check(
    chance_min: int,
    chance_max: int,
    *,
    success: str,
    fail: str,
    rng: random.Random | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Бросок скиллчека.

    Сначала из диапазона берётся свежий порог успеха (не константа),
    затем d100. Возвращает (сцена, 'success'|'fail', детали для админа).
    """
    if chance_min >= chance_max:
        raise ValueError("шанс должен быть диапазоном, не константой")
    if success == fail:
        raise ValueError("успех и провал не могут вести в одну сцену")
    rng = rng or random.Random()
    threshold = rng.randint(chance_min, chance_max)
    roll = rng.randint(1, 100)
    if roll <= threshold:
        return success, "success", {
            "threshold": threshold,
            "roll": roll,
            "chance_min": chance_min,
            "chance_max": chance_max,
            "dest": success,
        }
    return fail, "fail", {
        "threshold": threshold,
        "roll": roll,
        "chance_min": chance_min,
        "chance_max": chance_max,
        "dest": fail,
    }


def _votes(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        return "голосов"
    last = count % 10
    if last == 1:
        return "голос"
    if 2 <= last <= 4:
        return "голоса"
    return "голосов"
