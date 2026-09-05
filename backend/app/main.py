"""Точка входа backend: Электронный кабинет студента."""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .logging import setup_logging
from .routers import auth, grades, schedule, students

setup_logging()


async def _sync_job() -> None:
    """Задача планировщика: никогда не роняет loop исключением."""
    from .sync import sync_all
    try:
        await sync_all()
    except Exception as e:  # noqa: BLE001 — планировщик обязан пережить всё
        logger.error(f"Фоновая синхронизация упала: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Таблицы (ленивый путь вместо Alembic до первой эволюции схемы),
    демо-сид для разработки и планировщик синхронизации."""
    from .db import Base, engine

    if os.getenv("SKIP_DB_INIT") != "1":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if os.getenv("SEED_DEMO") == "1":
        from .seed import seed_demo
        await seed_demo()
        logger.info("Загружены демо-данные (SEED_DEMO=1)")

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    hours = int(os.getenv("SYNC_INTERVAL_HOURS", "48"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _sync_job, "interval", hours=hours, id="sync",
        coalesce=True, max_instances=1,
    )
    scheduler.start()
    logger.info(f"Планировщик запущен: синхронизация каждые {hours} ч")
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
app.include_router(students.router)
app.include_router(schedule.router)
app.include_router(grades.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка живости сервиса."""
    return {"status": "ok"}
