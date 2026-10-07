"""Вход: ФИО + временный пароль от Telegram-бота -> токен сессии.

1. POST /auth/request_password — бот присылает 6-значный пароль студенту,
   чей Telegram привязан (bot.py) и кто состоит в группе курса.
2. POST /auth/login — пароль -> токен (Bearer), сессия в БД (sha256 токена).
3. Остальные эндпоинты требуют `current_student` (Authorization: Bearer).

Ответ на запрос пароля одинаковый для всех ФИО (нет/не привязан/привязан),
чтобы по нему нельзя было выяснить состав группы.

AUTH_DEV_MODE=1 (только без TELEGRAM_BOT_TOKEN) — пароль возвращается
в ответе вместо Telegram: для локальной разработки и E2E.
"""

import datetime
import hashlib
import hmac
import os
import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import bot, telegram
from ..db import get_session
from ..models import AuthSession, Group, Student
from ..ratelimit import rate_limit
from ..schemas import (
    AuthConfigOut,
    LoginIn,
    PasswordLoginIn,
    RequestPasswordOut,
    StudentOut,
    TokenOut,
)
from ..sync import norm_name

router = APIRouter(prefix="/auth", tags=["auth"])


# Временные пароли: student_id -> [пароль, expires, неверных попыток, sent_at].
# Процесс локальный — при рестарте пароли сгорают, для мультиинстанса нужен Redis.
_passwords: dict[int, list] = {}
_PASSWORD_TTL_S = 300
_PASSWORD_MAX_ATTEMPTS = 5  # дальше пароль сгорает, нужен новый
_RESEND_COOLDOWN_S = 30  # не спамить студенту в Telegram

GENERIC_SENT = True
BAD_PASSWORD = "Неверный или истёкший пароль. Запросите новый."


def dev_mode() -> bool:
    """Пароль в ответе вместо Telegram. Никогда — при настроенном боте."""
    return os.getenv("AUTH_DEV_MODE") == "1" and not telegram.bot_token()


# В dev-режиме лимиты не нужны (пароль и так в ответе), а E2E логинится часто.
request_limit = rate_limit("auth-request-password", limit=5, window_s=60,
                           skip=lambda: dev_mode())
login_limit = rate_limit("auth-login", limit=10, window_s=60,
                         skip=lambda: dev_mode())


def _session_ttl() -> datetime.timedelta:
    try:
        days = int(os.getenv("SESSION_TTL_DAYS", "30"))
    except ValueError:
        days = 30
    return datetime.timedelta(days=max(days, 1))


def _utcnow() -> datetime.datetime:
    """Naive UTC (так хранится AuthSession.expires_at)."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _out(student: Student, group_name: str) -> StudentOut:
    return StudentOut(
        id=student.id, group=group_name, code=student.code,
        last_name=student.last_name, first_name=student.first_name,
        full_name=student.full_name,
    )


async def _find_student(session: AsyncSession, last_name: str,
                        first_name: str) -> tuple[Student, str] | None:
    """Студент по «фамилия имя» (регистр/пробелы/ё не важны)."""
    if not last_name.strip() or not first_name.strip():
        return None
    want = norm_name(f"{last_name} {first_name}").replace("ё", "е")
    rows = (await session.execute(
        select(Student, Group.name).join(Group, Student.group_id == Group.id)
    )).all()
    return next(((s, g) for s, g in rows
                 if s.code.replace("ё", "е") == want), None)


def _purge_passwords(now: float) -> None:
    for key in [k for k, v in _passwords.items() if v[1] <= now]:
        del _passwords[key]


def _new_password(student_id: int) -> str:
    now = time.monotonic()
    _purge_passwords(now)
    password = f"{secrets.randbelow(1_000_000):06d}"
    _passwords[student_id] = [password, now + _PASSWORD_TTL_S, 0, now]
    return password


@router.get("/config", response_model=AuthConfigOut)
async def auth_config():
    """Что показать на экране входа: ссылку на бота, dev-режим."""
    return AuthConfigOut(telegram=telegram.configured(),
                         bot_username=bot.bot_username(),
                         dev_mode=dev_mode())


@router.post("/request_password", response_model=RequestPasswordOut)
async def request_password(body: LoginIn,
                           _rl: None = Depends(request_limit),
                           session: AsyncSession = Depends(get_session)):
    """Отправка временного пароля в Telegram. Ответ не раскрывает, есть ли студент."""
    if not dev_mode() and not telegram.configured():
        raise HTTPException(status_code=503,
                            detail="Вход не настроен. Обратитесь к администратору.")
    found = await _find_student(session, body.last_name, body.first_name)
    if found is None:
        return RequestPasswordOut(sent=GENERIC_SENT)
    student, _ = found

    if dev_mode():
        return RequestPasswordOut(sent=True,
                                  dev_password=_new_password(student.id))

    if student.telegram_user_id is None:
        return RequestPasswordOut(sent=GENERIC_SENT)
    prev = _passwords.get(student.id)
    if prev and time.monotonic() - prev[3] < _RESEND_COOLDOWN_S:
        return RequestPasswordOut(sent=GENERIC_SENT)  # прошлый ещё в пути
    try:
        if not await telegram.is_group_member(student.telegram_user_id):
            logger.info(f"Пароль не выдан: {student.code!r} не в группе курса")
            return RequestPasswordOut(sent=GENERIC_SENT)
        password = _new_password(student.id)
        await telegram.send_message(
            student.telegram_user_id,
            f"Пароль для входа в кабинет студента: {password}\n"
            f"Действует {_PASSWORD_TTL_S // 60} минут. "
            "Никому его не сообщайте.")
    except telegram.TelegramError as e:
        _passwords.pop(student.id, None)
        logger.error(f"Не удалось отправить пароль {student.code!r}: {e}")
        raise HTTPException(status_code=502,
                            detail="Telegram недоступен, попробуйте позже.") from None
    return RequestPasswordOut(sent=GENERIC_SENT)


@router.post("/login", response_model=TokenOut)
async def login(body: PasswordLoginIn,
                _rl: None = Depends(login_limit),
                session: AsyncSession = Depends(get_session)):
    """ФИО + временный пароль -> токен сессии."""
    found = await _find_student(session, body.last_name, body.first_name)
    if found is None:
        raise HTTPException(status_code=400, detail=BAD_PASSWORD)
    student, group_name = found
    entry = _passwords.get(student.id)
    if entry is None or time.monotonic() > entry[1]:
        _passwords.pop(student.id, None)
        raise HTTPException(status_code=400, detail=BAD_PASSWORD)
    if not hmac.compare_digest(body.password.strip().encode(), entry[0].encode()):
        entry[2] += 1
        if entry[2] >= _PASSWORD_MAX_ATTEMPTS:
            del _passwords[student.id]
        raise HTTPException(status_code=400, detail=BAD_PASSWORD)
    del _passwords[student.id]

    token = secrets.token_urlsafe(32)
    session.add(AuthSession(token_hash=_hash(token), student_id=student.id,
                            expires_at=_utcnow() + _session_ttl()))
    await session.commit()
    logger.info(f"Вход: {student.code!r}")
    return TokenOut(token=token, student=_out(student, group_name))


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Требуется вход",
                            headers={"WWW-Authenticate": "Bearer"})
    return token.strip()


async def current_student(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> StudentOut:
    """Зависимость: студент по Bearer-токену, иначе 401."""
    token = _bearer(authorization)
    row = (await session.execute(
        select(Student, Group.name)
        .join(AuthSession, AuthSession.student_id == Student.id)
        .join(Group, Student.group_id == Group.id)
        .where(AuthSession.token_hash == _hash(token))
        .where(AuthSession.expires_at > _utcnow())
    )).first()
    if row is None:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите снова",
                            headers={"WWW-Authenticate": "Bearer"})
    return _out(*row)


@router.get("/me", response_model=StudentOut)
async def me(student: StudentOut = Depends(current_student)):
    """Текущий студент (клиент проверяет сохранённый токен)."""
    return student


@router.post("/logout", status_code=204)
async def logout(authorization: str | None = Header(default=None),
                 session: AsyncSession = Depends(get_session)):
    """Отзыв текущего токена. Невалидный токен — тоже 204."""
    token = _bearer(authorization)
    await session.execute(
        delete(AuthSession).where(AuthSession.token_hash == _hash(token)))
    await session.commit()
    return Response(status_code=204)


async def purge_expired_sessions(session: AsyncSession) -> int:
    """Удаление истёкших сессий (фоновый джоб)."""
    n = (await session.execute(
        delete(AuthSession).where(AuthSession.expires_at <= _utcnow())
    )).rowcount
    await session.commit()
    return n or 0
