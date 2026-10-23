"""Срок голосования от числа людей в группе."""

from __future__ import annotations

# Нижняя граница: даже в крошечной группе дать минуту с лишним прочитать сцену.
MIN_VOTE_SECONDS = 90
# Сколько секунд запаса на одного ожидаемого голосующего.
SECONDS_PER_VOTER = 60


def vote_wait_seconds(voter_count: int, base_minutes: int) -> int:
    """Секунды до дедлайна.

    Больше людей — длиннее ожидание (по ``SECONDS_PER_VOTER`` на человека),
    но не дольше ``base_minutes`` из сценария и не короче ``MIN_VOTE_SECONDS``.
    """
    people = max(1, int(voter_count))
    base_cap = max(MIN_VOTE_SECONDS, int(base_minutes) * 60)
    scaled = people * SECONDS_PER_VOTER
    return max(MIN_VOTE_SECONDS, min(base_cap, scaled))


def expect_voters_from_member_count(member_count: int) -> int:
    """Ожидаемые голосующие: участники минус сам бот, минимум 1."""
    return max(1, int(member_count) - 1)
