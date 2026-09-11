"""Простой in-memory rate limiter (fixed window) для публичных эндпоинтов.

Защищает /auth от перебора ФИО и 6-значных Telegram-кодов.
Для мультиинстанс-деплоя заменить на Redis (интерфейс — dependency).
"""

import time

from fastapi import HTTPException, Request

_hits: dict[str, list[float]] = {}
_MAX_KEYS = 10_000


def _purge(now: float) -> None:
    """Удаляет давно неактивные ключи, чтобы словарь не рос бесконечно."""
    for key in [k for k, v in _hits.items()
                if not v or v[-1] < now - 3600]:
        del _hits[key]


def reset() -> None:
    """Сброс состояния (нужен тестам)."""
    _hits.clear()


def rate_limit(prefix: str, limit: int, window_s: int):
    """Dependency-фабрика: не более `limit` запросов за `window_s` секунд с IP.

    Превышение — 429. Окно фиксированное, отсчёт — monotonic (не зависит
    от перевода системных часов).
    """

    async def dep(request: Request) -> None:
        now = time.monotonic()
        ip = request.client.host if request.client else "unknown"
        key = f"{prefix}:{ip}"
        hits = [t for t in _hits.get(key, []) if t > now - window_s]
        if len(hits) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Слишком много запросов, попробуйте позже",
            )
        hits.append(now)
        _hits[key] = hits
        if len(_hits) > _MAX_KEYS:
            _purge(now)

    return dep
