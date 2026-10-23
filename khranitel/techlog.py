"""Технический лог: файл data/tech.log и stdout."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "tech.log"

_configured = False


def setup() -> logging.Logger:
    global _configured
    logger = logging.getLogger("khranitel.tech")
    if _configured:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    _configured = True
    return logger


def get() -> logging.Logger:
    return setup()
