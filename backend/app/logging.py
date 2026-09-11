"""Настройка структурированного (JSON) логирования через loguru."""

import os
import sys

from loguru import logger


def setup_logging() -> None:
    """JSON-логи в stderr: запросы, парсинг, фоновые задачи — всё сюда."""
    logger.remove()
    logger.add(
        sys.stderr,
        serialize=True,  # одна строка = один JSON-объект
        level=os.getenv("LOG_LEVEL", "INFO"),
        backtrace=False,
        diagnose=False,
    )
