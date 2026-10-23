"""Учёт прохождений, выборов и концовок. Публичный JSON — для будущего сайта."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from khranitel.format import Adventure
from khranitel.stats import store


def choice_key(scene_id: str, label: str) -> str:
    return f"{scene_id}|{label}"


def _tale_bucket(data: dict, tale: str) -> dict:
    tales = data.setdefault("tales", {})
    bucket = tales.get(tale)
    if not isinstance(bucket, dict):
        bucket = {
            "plays": 0,
            "variants": {},
            "endings": {},
            "choices": {},
            "seen_choices": {},
        }
        tales[tale] = bucket
    for field, default in (
        ("plays", 0),
        ("variants", {}),
        ("endings", {}),
        ("choices", {}),
        ("seen_choices", {}),
    ):
        if field not in bucket or not isinstance(bucket[field], type(default)):
            bucket[field] = default if not isinstance(default, int) else 0
    return bucket


def record_choice(
    tale: str,
    variant: str,
    scene_id: str,
    label: str,
    *,
    path: Path | None = None,
) -> None:
    """Засчитать один сделанный выбор (после победы в опросе)."""
    stats_path = path or store.DEFAULT_PATH
    data = store.load(stats_path)
    bucket = _tale_bucket(data, tale)
    choices = bucket["choices"].setdefault(variant, {})
    key = choice_key(scene_id, label)
    choices[key] = int(choices.get(key, 0)) + 1
    seen = bucket["seen_choices"].setdefault(variant, {})
    seen[key] = True
    store.save(data, stats_path)


def record_play(
    tale: str,
    variant: str,
    ending_scene: str,
    *,
    completed: bool = True,
    path: Path | None = None,
) -> None:
    """Засчитать завершённое (или оборванное) прохождение."""
    stats_path = path or store.DEFAULT_PATH
    data = store.load(stats_path)
    data["plays_total"] = int(data.get("plays_total", 0)) + 1
    bucket = _tale_bucket(data, tale)
    bucket["plays"] = int(bucket.get("plays", 0)) + 1
    variants = bucket["variants"]
    variants[variant] = int(variants.get(variant, 0)) + 1
    if completed and ending_scene:
        endings = bucket["endings"]
        endings[ending_scene] = int(endings.get(ending_scene, 0)) + 1
    store.save(data, stats_path)


def load_stats(path: Path | None = None) -> dict:
    return store.load(path or store.DEFAULT_PATH)


def completeness(adventure: Adventure, seen: dict[str, bool]) -> dict[str, Any]:
    """Доля выборов, которые хотя бы раз были сделаны."""
    total = 0
    hit = 0
    missing: list[str] = []
    for scene in adventure.scenes.values():
        for choice in scene.choices:
            total += 1
            key = choice_key(scene.id, choice.label)
            if seen.get(key):
                hit += 1
            else:
                missing.append(key)
    ratio = (hit / total) if total else 1.0
    return {
        "total_choices": total,
        "seen_choices": hit,
        "ratio": ratio,
        "missing": missing,
    }


def endings_map(adventure: Adventure) -> list[str]:
    """Сцены без вариантов — концовки."""
    return sorted(
        scene.id for scene in adventure.scenes.values() if not scene.choices)


def tale_report(
    tale_slug: str,
    adventures: dict[str, Adventure],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Сводка по одной истории: частота, концовки, полнота по версиям."""
    data = load_stats(path)
    bucket = data.get("tales", {}).get(tale_slug) or {}
    plays = int(bucket.get("plays", 0))
    variants = dict(bucket.get("variants") or {})
    endings = dict(bucket.get("endings") or {})
    seen_all = bucket.get("seen_choices") or {}
    completeness_by_variant = {}
    open_endings = {}
    for variant_id, adventure in adventures.items():
        seen = seen_all.get(variant_id) or {}
        if not isinstance(seen, dict):
            seen = {}
        completeness_by_variant[variant_id] = completeness(adventure, seen)
        known = set(endings_map(adventure))
        opened = sorted(eid for eid in endings if eid in known and endings[eid] > 0)
        open_endings[variant_id] = {
            "all": sorted(known),
            "opened": opened,
            "opened_count": len(opened),
            "all_count": len(known),
        }
    return {
        "tale": tale_slug,
        "plays": plays,
        "variants": variants,
        "endings": endings,
        "choices": bucket.get("choices") or {},
        "completeness": completeness_by_variant,
        "open_endings": open_endings,
    }


def summary_text(
    *,
    adventures_root: Path | None = None,
    path: Path | None = None,
) -> str:
    from khranitel import tales as tales_mod

    data = load_stats(path)
    total = int(data.get("plays_total", 0))
    lines = [f"Всего прохождений: {total}"]
    tale_rows = []
    for slug, bucket in sorted((data.get("tales") or {}).items()):
        if not isinstance(bucket, dict):
            continue
        tale_rows.append((int(bucket.get("plays", 0)), slug))
    tale_rows.sort(reverse=True)
    if not tale_rows:
        lines.append("Пока пусто — ни одна история не досказана.")
        return "\n".join(lines)
    lines.append("Частота историй:")
    for plays, slug in tale_rows:
        lines.append(f"  • {slug}: {plays}")
    if adventures_root is not None:
        for plays, slug in tale_rows[:5]:
            tale = tales_mod.tale_by_slug(adventures_root, slug)
            if tale is None:
                continue
            advs = {}
            for vid in tale.variant_ids():
                try:
                    advs[vid] = tale.load(vid)
                except Exception:
                    continue
            report = tale_report(slug, advs, path=path)
            lines.append(f"«{tale.title}» — концовки и полнота:")
            for vid, open_info in report["open_endings"].items():
                comp = report["completeness"].get(vid) or {}
                pct = int(round(float(comp.get("ratio", 0)) * 100))
                lines.append(
                    f"  [{vid}] концовки {open_info['opened_count']}/{open_info['all_count']}, "
                    f"выборы {comp.get('seen_choices', 0)}/{comp.get('total_choices', 0)} ({pct}%)")
    return "\n".join(lines)


def export_public(path: Path | None = None) -> dict[str, Any]:
    """Стабильный JSON для сайта: частоты, концовки, полнота без внутренних деталей."""
    data = load_stats(path)
    tales_out = {}
    for slug, bucket in (data.get("tales") or {}).items():
        if not isinstance(bucket, dict):
            continue
        tales_out[slug] = {
            "plays": int(bucket.get("plays", 0)),
            "variants": dict(bucket.get("variants") or {}),
            "endings": dict(bucket.get("endings") or {}),
            "choices": dict(bucket.get("choices") or {}),
            "seen_choices": {
                vid: sorted(k for k, v in (seen or {}).items() if v)
                for vid, seen in (bucket.get("seen_choices") or {}).items()
            },
        }
    return {
        "version": 1,
        "plays_total": int(data.get("plays_total", 0)),
        "tales": tales_out,
    }
