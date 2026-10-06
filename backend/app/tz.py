"""Часовой пояс кабинета: расписание и cron синхронизации — по нему."""

import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

DEFAULT_TIMEZONE = "Europe/Moscow"


def local_tz() -> ZoneInfo:
    """Часовой пояс из SYNC_TIMEZONE; мусор — warning + Москва.

    Время сервера (в Docker — UTC) для расписания не годится: пары
    в таблицах указаны по Москве.
    """
    name = os.getenv("SYNC_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(f"SYNC_TIMEZONE {name!r} неизвестен, использую {DEFAULT_TIMEZONE}")
        return ZoneInfo(DEFAULT_TIMEZONE)
