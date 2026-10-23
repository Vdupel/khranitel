"""Истории и их версии. Кулдаун недавних для /begin."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml

from khranitel.format import Adventure, AdventureError, load_adventure

COOLDOWN_VOTES = 2  # исключать на это и следующее голосование /begin
PICK_COUNT = 3


@dataclass(frozen=True)
class Tale:
    """Семья версий одной истории."""

    slug: str
    title: str
    variants: dict[str, Path]  # id версии → папка с adventure.yaml

    def variant_ids(self) -> list[str]:
        return sorted(self.variants)

    def folder(self, variant_id: str) -> Path:
        return self.variants[variant_id]

    def load(self, variant_id: str) -> Adventure:
        return load_adventure(self.folder(variant_id))


def discover_tales(root: Path) -> list[Tale]:
    """Найти истории.

    Два вида раскладки:
    - legacy: adventures/<slug>/adventure.yaml → одна версия ``default``;
    - variants: adventures/<slug>/variants/<id>/adventure.yaml;
    опционально adventures/<slug>/tale.yaml с полем title.
    """
    if not root.is_dir():
        return []
    tales: list[Tale] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        variants = _variants_in(child)
        if not variants:
            continue
        title = _tale_title(child, variants)
        tales.append(Tale(child.name, title, variants))
    return tales


def tale_by_slug(root: Path, slug: str) -> Tale | None:
    for tale in discover_tales(root):
        if tale.slug == slug:
            return tale
    return None


def pick_candidates(
    tales: list[Tale],
    cooldowns: dict[str, int],
    *,
    count: int = PICK_COUNT,
    rng: random.Random | None = None,
) -> list[Tale]:
    """До ``count`` историй вне кулдауна.

    Недавние не подмешиваем, пока хватает свободных хотя бы на опрос (2).
    Если свободных меньше двух — добиваем кулдаунными, иначе голосовать нечем.
    """
    rng = rng or random.Random()
    free = [t for t in tales if int(cooldowns.get(t.slug, 0)) <= 0]
    blocked = [t for t in tales if int(cooldowns.get(t.slug, 0)) > 0]
    rng.shuffle(free)
    chosen = free[:count]
    if len(chosen) < 2:
        rng.shuffle(blocked)
        for tale in blocked:
            if len(chosen) >= 2:
                break
            chosen.append(tale)
    return chosen


def mark_played(cooldowns: dict[str, int], tale_slug: str) -> None:
    """После сессии: исключить на COOLDOWN_VOTES голосования /begin."""
    cooldowns[tale_slug] = COOLDOWN_VOTES


def tick_cooldowns(cooldowns: dict[str, int]) -> None:
    """Вызвать после проведения голосования /begin (это или следующее)."""
    for slug in list(cooldowns):
        left = int(cooldowns[slug]) - 1
        if left <= 0:
            cooldowns.pop(slug, None)
        else:
            cooldowns[slug] = left


def pick_variant(
    tale: Tale,
    *,
    avoid: str | None = None,
    rng: random.Random | None = None,
) -> str:
    """Случайная версия; при ``avoid`` — другая, если есть."""
    rng = rng or random.Random()
    ids = tale.variant_ids()
    if avoid and len(ids) > 1:
        ids = [vid for vid in ids if vid != avoid]
    return rng.choice(ids)


def other_variants(tale: Tale, current: str) -> list[str]:
    return [vid for vid in tale.variant_ids() if vid != current]


def _variants_in(folder: Path) -> dict[str, Path]:
    variants_root = folder / "variants"
    found: dict[str, Path] = {}
    if variants_root.is_dir():
        for child in sorted(variants_root.iterdir()):
            if child.is_dir() and (child / "adventure.yaml").is_file():
                found[child.name] = child
    if (folder / "adventure.yaml").is_file():
        found.setdefault("default", folder)
    return found


def _tale_title(folder: Path, variants: dict[str, Path]) -> str:
    meta = folder / "tale.yaml"
    if meta.is_file():
        try:
            raw = yaml.safe_load(meta.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raw = None
        if isinstance(raw, dict) and isinstance(raw.get("title"), str) and raw["title"].strip():
            return raw["title"].strip()
    # заголовок первой удачно читаемой версии
    for path in variants.values():
        try:
            return load_adventure(path).title
        except AdventureError:
            continue
    return folder.name
