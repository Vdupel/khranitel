"""Формат приключения.

Папка сценария:

    adventure.yaml
    images/....png     картинки, на которые ссылается сценарий

В yaml: название, сколько минут длится голосование, id стартовой сцены
и словарь сцен. У сцены — текст, необязательная картинка и варианты.
Вариант — подпись на кнопке голосования и id следующей сцены.
Пустой список вариантов — конец. Один вариант — бот идёт туда без голосования.
Два и больше — опрос в чате.

Этот же файл потом будет отдавать веб-генератор.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

ID_RE = re.compile(r"^[\w-]{1,64}$", re.UNICODE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LABEL_LIMIT = 100
CHOICE_LIMIT = 10
TEXT_LIMIT = 4000
YAML_LIMIT = 1_000_000


class AdventureError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class Choice:
    label: str
    next: str


@dataclass(frozen=True)
class Scene:
    id: str
    text: str
    image: str | None
    choices: tuple[Choice, ...]


@dataclass(frozen=True)
class Adventure:
    """Загруженный сценарий. root — папка, откуда читаются картинки."""

    slug: str
    title: str
    vote_minutes: int
    start: str
    scenes: dict[str, Scene]
    root: Path

    def scene(self, scene_id: str) -> Scene:
        return self.scenes[scene_id]

    def image_path(self, scene: Scene) -> Path | None:
        if not scene.image:
            return None
        path = (self.root / scene.image).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            return None
        return path if path.is_file() else None


def load_adventure(folder: Path) -> Adventure:
    folder = folder.resolve()
    path = folder / "adventure.yaml"
    if not path.is_file():
        raise AdventureError([f"В {folder.name} нет adventure.yaml"])
    if path.stat().st_size > YAML_LIMIT:
        raise AdventureError(["adventure.yaml больше 1 МБ"])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise AdventureError([f"Не читается YAML: {error}"]) from error
    return parse_adventure(raw, slug=folder.name, root=folder)


def parse_adventure(raw, *, slug: str, root: Path) -> Adventure:
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise AdventureError(["Корень файла должен быть словарём"])

    title = _text(raw.get("title"), "title", errors)
    start = _ident(raw.get("start"), "start", errors)
    minutes = raw.get("vote_minutes", 60)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1 or minutes > 10080:
        errors.append("vote_minutes — целое число минут от 1 до 10080 (неделя)")
        minutes = 60

    scenes_raw = raw.get("scenes")
    scenes: dict[str, Scene] = {}
    if not isinstance(scenes_raw, dict) or not scenes_raw:
        errors.append("scenes — непустой словарь сцен")
    else:
        for scene_id, body in scenes_raw.items():
            ident = _ident(scene_id, "id сцены", errors)
            if ident is None:
                continue
            if ident in scenes:
                errors.append(f"Сцена «{ident}» повторяется")
                continue
            scenes[ident] = _scene(ident, body, errors)

    if start and scenes and start not in scenes:
        errors.append(f"Стартовая сцена «{start}» не описана")
    for scene in scenes.values():
        for choice in scene.choices:
            if choice.next not in scenes:
                errors.append(
                    f"Сцена «{scene.id}»: вариант «{choice.label}» ведёт "
                    f"в несуществующую сцену «{choice.next}»")

    if errors:
        raise AdventureError(errors)
    return Adventure(slug, title or slug, int(minutes), start or "", scenes, root)


def list_adventures(folder: Path) -> list[Adventure]:
    if not folder.is_dir():
        return []
    found = []
    for child in sorted(folder.iterdir()):
        if child.is_dir() and (child / "adventure.yaml").is_file():
            found.append(load_adventure(child))
    return found


def install_upload(folder: Path, filename: str, payload: bytes) -> Adventure:
    """Положить присланный yaml или zip в папку и сразу проверить."""
    if len(payload) > 20_000_000:
        raise AdventureError(["Файл больше 20 МБ"])
    folder.mkdir(parents=True, exist_ok=True)
    lower = filename.lower()
    if lower.endswith(".zip"):
        _unpack(folder, payload)
    elif lower.endswith(".yaml") or lower.endswith(".yml"):
        if len(payload) > YAML_LIMIT:
            raise AdventureError(["adventure.yaml больше 1 МБ"])
        (folder / "adventure.yaml").write_bytes(payload)
    else:
        raise AdventureError(["Нужен adventure.yaml или zip, в котором он лежит"])
    try:
        return load_adventure(folder)
    except AdventureError:
        written = folder / "adventure.yaml"
        if written.is_file():
            written.unlink()
        raise


def _unpack(folder: Path, payload: bytes) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise AdventureError(["Архив повреждён"]) from error
    with archive:
        yaml_name = _yaml_member(archive)
        if yaml_name is None:
            raise AdventureError(["В архиве нет adventure.yaml"])
        info = archive.getinfo(yaml_name)
        if info.file_size > YAML_LIMIT:
            raise AdventureError(["adventure.yaml больше 1 МБ"])
        (folder / "adventure.yaml").write_bytes(archive.read(yaml_name))
        base = Path(yaml_name).parent
        for member in archive.infolist():
            if member.is_dir() or member.file_size > 8_000_000:
                continue
            relative = Path(member.filename)
            if ".." in relative.parts or relative.is_absolute():
                continue
            if base.parts and base != Path("."):
                try:
                    inside = relative.relative_to(base)
                except ValueError:
                    continue
            else:
                inside = relative
            if inside.name == "adventure.yaml":
                continue
            if inside.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            target = (folder / inside).resolve()
            root = folder.resolve()
            if root != target.parent and root not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))


def _yaml_member(archive: zipfile.ZipFile) -> str | None:
    names = [name for name in archive.namelist()
             if Path(name).name == "adventure.yaml" and ".." not in Path(name).parts]
    if not names:
        return None
    return sorted(names, key=lambda name: (len(Path(name).parts), len(name)))[0]


def save_adventure(folder: Path, raw: dict) -> None:
    """Записать сценарий. Сначала проверяет тот же разбор, что и бот."""
    parse_adventure(raw, slug=folder.name, root=folder)
    folder.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=88)
    (folder / "adventure.yaml").write_text(text, encoding="utf-8")


def _scene(scene_id: str, body, errors: list[str]) -> Scene:
    if not isinstance(body, dict):
        errors.append(f"Сцена «{scene_id}» должна быть словарём")
        return Scene(scene_id, "", None, ())
    text = _text(body.get("text"), f"текст сцены «{scene_id}»", errors) or ""
    if len(text) > TEXT_LIMIT:
        errors.append(f"Текст сцены «{scene_id}» длиннее {TEXT_LIMIT} знаков")
    image = body.get("image")
    if image is None or image == "":
        image_name = None
    elif not isinstance(image, str) or image.startswith(("/", "\\")) or ".." in Path(image).parts:
        errors.append(f"Сцена «{scene_id}»: картинка — относительный путь внутри папки")
        image_name = None
    elif Path(image).suffix.lower() not in IMAGE_SUFFIXES:
        errors.append(f"Сцена «{scene_id}»: картинка png, jpg, webp или gif")
        image_name = None
    else:
        image_name = image.replace("\\", "/")
    choices_raw = body.get("choices", [])
    choices: list[Choice] = []
    if not isinstance(choices_raw, list):
        errors.append(f"Сцена «{scene_id}»: choices — список")
    elif len(choices_raw) > CHOICE_LIMIT:
        errors.append(f"Сцена «{scene_id}»: вариантов больше {CHOICE_LIMIT} — столько не берёт опрос")
    else:
        labels = set()
        for index, item in enumerate(choices_raw, start=1):
            choice = _choice(scene_id, index, item, errors)
            if choice is None:
                continue
            key = choice.label.casefold()
            if key in labels:
                errors.append(f"Сцена «{scene_id}»: два варианта с подписью «{choice.label}»")
            labels.add(key)
            choices.append(choice)
    return Scene(scene_id, text, image_name, tuple(choices))


def _choice(scene_id: str, index: int, item, errors: list[str]) -> Choice | None:
    where = f"сцена «{scene_id}», вариант {index}"
    if not isinstance(item, dict):
        errors.append(f"{where}: нужен словарь label и next")
        return None
    label = item.get("label")
    if not isinstance(label, str) or not label.strip():
        errors.append(f"{where}: пустая подпись")
        label = ""
    else:
        label = " ".join(label.split())
        if len(label) > LABEL_LIMIT:
            errors.append(f"{where}: подпись длиннее {LABEL_LIMIT} знаков")
    nxt = _ident(item.get("next"), f"{where}, next", errors)
    if not label or nxt is None:
        return None
    return Choice(label, nxt)


def _text(value, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field}: нужна непустая строка")
        return None
    return value.strip()


def _ident(value, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not ID_RE.match(value):
        errors.append(f"{field}: id из букв, цифр, «_» и «-», до 64 знаков")
        return None
    return value
