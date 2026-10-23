"""Обновление с GitHub и перезапуск процесса."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from khranitel import techlog

ROOT = Path(__file__).resolve().parents[1]
RESTART_EXIT_CODE = 75
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    message: str
    changed: bool = False
    detail: str = ""


def _run(args: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def git_available() -> bool:
    return (ROOT / ".git").is_dir()


def fetch(remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH) -> UpdateResult:
    log = techlog.get()
    if not git_available():
        return UpdateResult(False, "Репозиторий git не найден — обновление недоступно.")
    log.info("git fetch %s %s", remote, branch)
    proc = _run(["git", "fetch", remote, branch])
    if proc.returncode != 0:
        log.error("fetch failed: %s", proc.stderr.strip())
        return UpdateResult(False, "git fetch не удался.", detail=proc.stderr.strip())
    return UpdateResult(True, "fetch ok")


def has_remote_updates(
    remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH,
) -> tuple[bool, str]:
    """Есть ли новые коммиты на remote/branch относительно HEAD."""
    proc = _run(["git", "rev-list", "--count", f"HEAD..{remote}/{branch}"])
    if proc.returncode != 0:
        return False, proc.stderr.strip()
    try:
        count = int(proc.stdout.strip() or "0")
    except ValueError:
        return False, proc.stdout.strip()
    return count > 0, f"впереди коммитов: {count}"


def pull_full(
    remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH,
) -> UpdateResult:
    """Полный ff-only pull кода и историй."""
    log = techlog.get()
    fetched = fetch(remote, branch)
    if not fetched.ok:
        return fetched
    ahead, info = has_remote_updates(remote, branch)
    if not ahead:
        log.info("pull: уже актуально (%s)", info)
        return UpdateResult(True, "Уже актуально — новых коммитов нет.", changed=False, detail=info)
    log.info("git pull --ff-only %s %s", remote, branch)
    proc = _run(["git", "pull", "--ff-only", remote, branch])
    if proc.returncode != 0:
        log.error("pull failed: %s", proc.stderr.strip())
        return UpdateResult(False, "git pull не удался (нужен fast-forward).", detail=proc.stderr.strip())
    log.info("pull ok: %s", proc.stdout.strip())
    return UpdateResult(True, "Код и истории обновлены с GitHub.", changed=True, detail=proc.stdout.strip())


def pull_adventures(
    remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH,
) -> UpdateResult:
    """Подтянуть только папку adventures/ с remote без полного merge рабочей копии."""
    log = techlog.get()
    fetched = fetch(remote, branch)
    if not fetched.ok:
        return fetched
    # есть ли отличия в adventures
    diff = _run(["git", "diff", "--name-only", f"HEAD..{remote}/{branch}", "--", "adventures"])
    if diff.returncode != 0:
        return UpdateResult(False, "Не удалось сравнить adventures.", detail=diff.stderr.strip())
    files = [line for line in diff.stdout.splitlines() if line.strip()]
    if not files:
        log.info("adventures: без изменений на %s/%s", remote, branch)
        return UpdateResult(
            True, "Новых историй на GitHub нет — adventures без изменений.", changed=False)
    log.info("checkout adventures from %s/%s (%s files)", remote, branch, len(files))
    proc = _run(["git", "checkout", f"{remote}/{branch}", "--", "adventures"])
    if proc.returncode != 0:
        log.error("checkout adventures failed: %s", proc.stderr.strip())
        return UpdateResult(False, "Не удалось забрать adventures.", detail=proc.stderr.strip())
    return UpdateResult(
        True,
        f"Истории обновлены ({len(files)} файлов). Перечитываю каталог.",
        changed=True,
        detail="\n".join(files[:20]),
    )


def restart_process() -> None:
    """Немедленно заменить процесс (после короткой задержки вызывающий код шлёт ответ)."""
    log = techlog.get()
    log.info("restart: exec %s -m khranitel", sys.executable)
    os.environ["KHRANITEL_RESTARTED"] = "1"
    os.execv(sys.executable, [sys.executable, "-m", "khranitel"])


def request_exit_for_watchdog() -> None:
    """Завершить процесс кодом, который родительский watchdog перезапустит."""
    log = techlog.get()
    log.info("restart via watchdog exit %s", RESTART_EXIT_CODE)
    # os._exit — немедленно, минуя asyncio; родитель ждёт returncode
    os._exit(RESTART_EXIT_CODE)
