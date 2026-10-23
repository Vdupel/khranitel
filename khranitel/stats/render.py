"""Картинка-сводка статистики (Pillow)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from khranitel.stats.model import load_stats, tale_report

# Спокойная палитра: чернила на холодной бумаге, без фиолетового клише.
BG = (232, 238, 242)
INK = (28, 43, 51)
MUTED = (90, 110, 120)
ACCENT = (47, 111, 122)
BAR = (62, 140, 152)
CARD = (255, 255, 255)


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ):
        path = Path(name)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _bar_chart(
    draw: ImageDraw.ImageDraw,
    *,
    origin: tuple[int, int],
    size: tuple[int, int],
    items: list[tuple[str, int]],
    font: ImageFont.ImageFont,
) -> None:
    x0, y0 = origin
    width, height = size
    if not items:
        draw.text((x0, y0), "нет данных", fill=MUTED, font=font)
        return
    max_val = max(v for _, v in items) or 1
    row_h = max(22, height // max(len(items), 1))
    label_w = 160
    for index, (label, value) in enumerate(items):
        y = y0 + index * row_h
        text = label if len(label) <= 22 else label[:21] + "…"
        draw.text((x0, y + 2), text, fill=INK, font=font)
        bar_x = x0 + label_w
        bar_max = width - label_w - 40
        bar_w = int(bar_max * (value / max_val))
        draw.rounded_rectangle(
            (bar_x, y + 2, bar_x + max(bar_w, 2), y + row_h - 6),
            radius=6, fill=BAR)
        draw.text((bar_x + max(bar_w, 2) + 6, y + 2), str(value), fill=MUTED, font=font)


def render_overview_image(*, path: Path | None = None) -> bytes:
    data = load_stats(path)
    total = int(data.get("plays_total", 0))
    rows = []
    for slug, bucket in (data.get("tales") or {}).items():
        if isinstance(bucket, dict):
            rows.append((slug, int(bucket.get("plays", 0))))
    rows.sort(key=lambda item: item[1], reverse=True)
    rows = rows[:10]

    width, height = 900, 520
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    title_font = _font(28)
    body = _font(16)
    small = _font(14)

    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=18, fill=CARD)
    draw.text((48, 44), "Хранитель — статистика", fill=INK, font=title_font)
    draw.text((48, 88), f"Всего прохождений: {total}", fill=ACCENT, font=body)
    draw.text((48, 120), "Частота историй", fill=MUTED, font=small)
    _bar_chart(
        draw,
        origin=(48, 150),
        size=(width - 96, height - 200),
        items=rows,
        font=body,
    )
    return _to_png(image)


def render_tale_image(
    tale_slug: str,
    adventures: dict,
    title: str,
    *,
    path: Path | None = None,
) -> bytes:
    report = tale_report(tale_slug, adventures, path=path)
    ending_items = sorted(
        ((eid, count) for eid, count in report["endings"].items()),
        key=lambda item: item[1], reverse=True)[:8]
    width, height = 900, 620
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    title_font = _font(26)
    body = _font(16)
    small = _font(14)

    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=18, fill=CARD)
    draw.text((48, 44), title[:48], fill=INK, font=title_font)
    draw.text((48, 86), f"Прохождений: {report['plays']}", fill=ACCENT, font=body)

    y = 120
    draw.text((48, y), "Открытые концовки и полнота выборов", fill=MUTED, font=small)
    y += 28
    for vid, open_info in report["open_endings"].items():
        comp = report["completeness"].get(vid) or {}
        pct = int(round(float(comp.get("ratio", 0)) * 100))
        line = (
            f"[{vid}] концовки {open_info['opened_count']}/{open_info['all_count']} · "
            f"выборы {comp.get('seen_choices', 0)}/{comp.get('total_choices', 0)} ({pct}%)"
        )
        draw.text((48, y), line[:90], fill=INK, font=body)
        y += 26

    y += 10
    draw.text((48, y), "Частота концовок", fill=MUTED, font=small)
    y += 24
    _bar_chart(
        draw,
        origin=(48, y),
        size=(width - 96, height - y - 48),
        items=ending_items,
        font=body,
    )
    return _to_png(image)


def _to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
