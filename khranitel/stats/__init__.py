"""Статистика отыгранных историй — отдельный блок под бота и будущий сайт."""

from khranitel.stats.model import (
    choice_key,
    completeness,
    endings_map,
    export_public,
    load_stats,
    record_choice,
    record_play,
    summary_text,
    tale_report,
)
from khranitel.stats.render import render_overview_image, render_tale_image

__all__ = [
    "choice_key",
    "completeness",
    "endings_map",
    "export_public",
    "load_stats",
    "record_choice",
    "record_play",
    "render_overview_image",
    "render_tale_image",
    "summary_text",
    "tale_report",
]
