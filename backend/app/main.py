"""Точка входа backend: Электронный кабинет студента."""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .logging import setup_logging
from .routers import auth, grades, schedule, subjects
from .tz import local_tz as _resolve_tz

setup_logging()


async def _sync_job() -> None:
    """Задача планировщика: никогда не роняет loop исключением."""
    from .sync import sync_all
    try:
        await sync_all()
    except Exception:  # noqa: BLE001 — планировщик обязан пережить всё
        logger.exception("Фоновая синхронизация упала")


async def _expire_job() -> None:
    """Фоновый перевод прошедших пар в completed.

    Вынесено из GET /schedule: чтение не должно писать в БД (гонки с синком,
    нагрузка, read-only реплики). На выдаче статусы всё равно считаются
    на лету (`schedule._display_status`), джоб лишь прибирает базу.
    """
    from .db import SessionLocal
    from .routers.auth import purge_expired_sessions
    from .routers.schedule import _expire_past_items
    try:
        async with SessionLocal() as session:
            n = await _expire_past_items(session)
            expired = await purge_expired_sessions(session)
        if n:
            logger.info(f"Переведено пар в completed: {n}")
        if expired:
            logger.info(f"Удалено истёкших сессий: {expired}")
    except Exception:  # noqa: BLE001 — планировщик обязан пережить всё
        logger.exception("Фоновое завершение пар упало")


def _int_env(name: str, default: int) -> int:
    """Целое из окружения; мусор — warning + дефолт (не роняем старт)."""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning(f"{name} не число, использую {default}")
        return default


DEFAULT_SYNC_TIMES = "09:30,11:00"


def _parse_sync_times(raw: str) -> list[tuple[int, int]]:
    """'09:30,11:00' -> [(9, 30), (11, 0)]. Мусор пропускается с warning."""
    out: list[tuple[int, int]] = []
    for part in (raw or "").split(","):
        m = part.strip().split(":")
        if len(m) != 2 or not (m[0].isdigit() and m[1].isdigit()):
            logger.warning(f"SYNC_TIMES: пропуск невалидного {part.strip()!r}")
            continue
        hh, mm = int(m[0]), int(m[1])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            out.append((hh, mm))
        else:
            logger.warning(f"SYNC_TIMES: пропуск невалидного {part.strip()!r}")
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Таблицы (ленивый путь вместо Alembic до первой эволюции схемы),
    демо-сид для разработки, Telegram-бот и планировщик синхронизации."""
    from .db import Base, engine

    if os.getenv("SKIP_DB_INIT") != "1":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        from .db import SessionLocal
        from .subject_descriptions import (
            ensure_description_column,
            fill_subject_descriptions,
        )
        await ensure_description_column(engine)
        async with SessionLocal() as session:
            n = await fill_subject_descriptions(session)
            if n:
                logger.info(f"Проставлено описаний предметов: {n}")
    if os.getenv("SEED_DEMO") == "1":
        from .seed import seed_demo
        await seed_demo()
        logger.info("Загружены демо-данные (SEED_DEMO=1)")

    from .routers.auth import dev_mode
    if dev_mode():
        logger.warning("AUTH_DEV_MODE=1: пароли возвращаются в ответе API, "
                       "Telegram не используется. Только для разработки!")
    bot_task = _start_bot()
    try:
        async with _scheduler():
            yield
    finally:
        if bot_task is not None:
            bot_task.cancel()


def _start_bot():
    """Polling Telegram-бота (привязка аккаунтов), если бот настроен."""
    import asyncio

    from . import telegram
    if not telegram.configured():
        logger.warning("TELEGRAM_BOT_TOKEN/TELEGRAM_GROUP_ID не заданы — "
                       "бот и вход через Telegram отключены")
        return None
    if os.getenv("TELEGRAM_POLLING") == "0":
        logger.info("Polling Telegram-бота отключён (TELEGRAM_POLLING=0)")
        return None
    from .bot import run_polling
    return asyncio.create_task(run_polling(), name="telegram-bot")


@asynccontextmanager
async def _scheduler():
    """APScheduler: синк по SYNC_TIMES и фоновое завершение пар."""
    expire_hours = _int_env("EXPIRE_INTERVAL_HOURS", 1)
    if os.getenv("SYNC_INTERVAL_HOURS") is not None:
        logger.warning("SYNC_INTERVAL_HOURS больше не используется — "
                       "время задаётся SYNC_TIMES (по умолчанию 09:30,11:00)")
    if os.getenv("SKIP_SCHEDULER") == "1":
        # Тесты/E2E: фоновые задачи не нужны и могут выстрелить по cron.
        logger.info("Планировщик пропущен (SKIP_SCHEDULER=1)")
        yield
        return
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    tz = _resolve_tz()
    times = _parse_sync_times(os.getenv("SYNC_TIMES", DEFAULT_SYNC_TIMES))
    if not times:
        logger.warning(f"SYNC_TIMES пуст/невалиден, использую {DEFAULT_SYNC_TIMES}")
        times = _parse_sync_times(DEFAULT_SYNC_TIMES)
    scheduler = AsyncIOScheduler()
    for hh, mm in times:
        scheduler.add_job(
            _sync_job, CronTrigger(hour=hh, minute=mm, timezone=tz),
            id=f"sync-{hh:02d}{mm:02d}",
            coalesce=True, max_instances=1, misfire_grace_time=3600,
        )
    scheduler.add_job(
        _expire_job, "interval", hours=expire_hours, id="expire",
        coalesce=True, max_instances=1,
    )
    scheduler.start()
    logger.info(f"Планировщик запущен: синхронизация {','.join(f'{h:02d}:{m:02d}' for h, m in times)} "
                f"({tz.key}), завершение пар каждые {expire_hours} ч")
    yield
    scheduler.shutdown()


app = FastAPI(title="Электронный кабинет студента", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Каждый HTTP-запрос — одной JSON-строкой в лог."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.bind(
        method=request.method, path=request.url.path,
        status=response.status_code, elapsed_ms=elapsed_ms,
    ).info("http_request")
    return response


app.include_router(auth.router)
app.include_router(schedule.router)
app.include_router(grades.router)
app.include_router(subjects.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка живости сервиса."""
    return {"status": "ok"}
