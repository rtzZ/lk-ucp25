"""Подключение к БД: AsyncEngine (asyncpg) + фабрика сессий."""

import os

from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс всех моделей."""


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://lk:lk@localhost:5432/lk"
)

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    """Зависимость FastAPI: сессия на запрос."""
    async with SessionLocal() as session:
        yield session
