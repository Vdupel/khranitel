"""Спросить сцены у человека и записать папку сценария.

Запуск из корня проекта: python -m generator
Веб-страница позже соберёт тот же adventure.yaml и zip, который бот уже принимает.
"""

from __future__ import annotations

from pathlib import Path

from khranitel.format import AdventureError, save_adventure

ROOT = Path(__file__).resolve().parents[1]
ADVENTURES = ROOT / "adventures"


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def collect() -> dict:
    print("Генератор приключения. Пустой id сцены — записать файл и закончить.\n")
    title = ask("Название")
    while not title:
        title = ask("Название")
    slug = ask("Папка латиницей", "adventure")
    minutes = ask("Минут на голосование", "60")
    while not minutes.isdigit() or not 1 <= int(minutes) <= 10080:
        minutes = ask("Минут на голосование, число от 1 до 10080", "60")

    scenes: dict[str, dict] = {}
    while True:
        scene_id = ask("Id сцены (пусто — закончить)")
        if not scene_id:
            break
        text = ask("Текст сцены")
        image = ask("Картинка, путь внутри папки (пусто — без картинки)")
        choices = []
        print("Варианты. Пустая подпись — к следующей сцене.")
        while True:
            label = ask("  Подпись варианта")
            if not label:
                break
            nxt = ask("  Id следующей сцены")
            choices.append({"label": label, "next": nxt})
        body: dict = {"text": text, "choices": choices}
        if image:
            body["image"] = image.replace("\\", "/")
        scenes[scene_id] = body

    if not scenes:
        raise SystemExit("Нет ни одной сцены.")
    start = ask("Id стартовой сцены", next(iter(scenes)))
    return {
        "folder": slug,
        "document": {
            "title": title,
            "vote_minutes": int(minutes),
            "start": start,
            "scenes": scenes,
        },
    }


def main() -> None:
    collected = collect()
    folder = ADVENTURES / collected["folder"]
    try:
        save_adventure(folder, collected["document"])
    except AdventureError as error:
        print("Не записал. Исправьте и запустите снова:")
        print("\n".join(error.errors))
        raise SystemExit(1) from error
    print(f"Готово: {folder / 'adventure.yaml'}")
    print("Картинки положите по путям из файла. В чат бота эту папку можно отправить zip-архивом.")


if __name__ == "__main__":
    main()
