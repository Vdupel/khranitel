"""Запуск с watchdog в родительском процессе.

Дочерний процесс крутит бота. Код 75 или падение — родитель поднимает снова.
"""

from __future__ import annotations

import subprocess
import sys
import time

from khranitel import techlog
from khranitel.updater import RESTART_EXIT_CODE

CRASH_SLEEP_SEC = 5


def run() -> None:
    log = techlog.setup()
    log.info("watchdog parent start")
    child = [
        sys.executable,
        "-c",
        "import asyncio; from khranitel.bot import main; asyncio.run(main())",
    ]
    while True:
        log.info("watchdog: spawn bot child")
        completed = subprocess.run(child, check=False)
        code = completed.returncode
        if code == RESTART_EXIT_CODE:
            log.info("watchdog: child asked restart (%s)", code)
            continue
        if code == 0:
            log.info("watchdog: child exited cleanly — stop")
            return
        log.error("watchdog: child crashed with code %s — sleep %ss", code, CRASH_SLEEP_SEC)
        time.sleep(CRASH_SLEEP_SEC)


if __name__ == "__main__":
    run()
