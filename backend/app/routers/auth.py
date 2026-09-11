"""Вход: идентификация себя по фамилии+имени (без пароля) или Telegram."""

import hmac
import os
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Group, Student
from ..ratelimit import rate_limit
from ..schemas import LoginIn, LoginOut, StudentOut, TelegramLoginIn, TelegramLoginOut
from ..sync import norm_name

router = APIRouter(prefix="/auth", tags=["auth"])

# Лимиты: ФИО перебирается легко (публичные данные), коды — 6 цифр.
login_limit = rate_limit("auth-login", limit=30, window_s=60)
code_request_limit = rate_limit("auth-code-request", limit=5, window_s=60)
code_login_limit = rate_limit("auth-code-login", limit=10, window_s=60)

# Временные коды Telegram: user_id -> (code, expires_monotonic).
# Процесс локальный — при рестарте коды сгорают, для мультиинстанса нужен Redis.
_temp_codes: dict[str, tuple[str, float]] = {}
_CODE_TTL_S = 60


def _bot_token() -> str:
    """Токен читается лениво, чтобы тесты могли подменять окружение."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _group_id() -> int:
    try:
        return int(os.getenv("TELEGRAM_GROUP_ID", "0"))
    except ValueError:
        return 0


def _telegram_configured() -> bool:
    return bool(_bot_token()) and _group_id() != 0


def _purge_codes(now: float) -> None:
    """Удаляет истёкшие коды, чтобы словарь не рос бесконечно."""
    for key in [k for k, v in _temp_codes.items() if v[1] <= now]:
        del _temp_codes[key]


def _out(student: Student, group_name: str) -> StudentOut:
    return StudentOut(
        id=student.id, group=group_name, code=student.code,
        last_name=student.last_name, first_name=student.first_name,
        full_name=student.full_name,
    )


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request,
                _rl: None = Depends(login_limit),
                session: AsyncSession = Depends(get_session)):
    """Точное совпадение «фамилия имя» -> student; иначе 404 с подсказками."""
    want = norm_name(f"{body.last_name} {body.first_name}".strip())
    row = (await session.execute(
        select(Student, Group.name).join(Group, Student.group_id == Group.id)
        .where(Student.code == want)
    )).first()
    if row is not None and body.first_name.strip():
        student, group_name = row
        return LoginOut(student=_out(student, group_name))
    # Fallback-подсказки — редкий путь (опечатка/нет имени): полный скан.
    # WHERE по lower(last_name) здесь нельзя: SQLite lower() — только ASCII,
    # кириллицу не свернёт, а точное поведение матчинга важнее микрооптимизации.
    rows = (await session.execute(
        select(Student, Group.name).join(Group, Student.group_id == Group.id)
    )).all()
    same_last = [_out(s, g) for s, g in rows
                 if norm_name(s.last_name) == norm_name(body.last_name)]
    if len(same_last) == 1 and not body.first_name.strip():
        return LoginOut(student=same_last[0])
    raise HTTPException(status_code=404, detail={
        "message": "Студент не найден, уточните имя",
        "suggestions": [s.model_dump() for s in same_last],
    })


@router.post("/telegram_request_code", response_model=TelegramLoginOut)
async def telegram_request_code(body: TelegramLoginIn, request: Request,
                                _rl: None = Depends(code_request_limit),
                                session: AsyncSession = Depends(get_session)):
    """Запрос временного кода: проверяем членство в группе и шлём код в ЛС бота."""
    if not _telegram_configured():
        return TelegramLoginOut(error="Вход через Telegram не настроен. Обратитесь к администратору.")
    username = body.telegram_username.strip()
    if not username.startswith("@"):
        return TelegramLoginOut(error="Username должен начинаться с @")

    # Ищем пользователя по username в БД
    result = await session.execute(select(Student).where(Student.telegram_username == username))
    student = result.scalar_one_or_none()
    if not student:
        return TelegramLoginOut(error="Пользователь не найден в системе. Обратитесь к администратору.")
    if not student.telegram_user_id:
        return TelegramLoginOut(error="Для входа через Telegram требуется user_id. Свяжитесь с администратором.")

    token = _bot_token()
    group_id = _group_id()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Проверяем, что пользователь состоит в группе через Bot API
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getChatMember",
                params={"chat_id": group_id, "user_id": student.telegram_user_id},
            )
            data = resp.json()
            if not data.get("ok"):
                return TelegramLoginOut(error=f"Ошибка Telegram API: {data.get('description', 'unknown')}")
            status = data.get("result", {}).get("status")
            if status not in ("member", "administrator", "creator"):
                return TelegramLoginOut(error="Пользователь не состоит в группе. Проверьте подписку на канал/группу.")

            # Генерируем код и отправляем в личные сообщения
            code = f"{secrets.randbelow(10_000_000):06d}"
            send = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": student.telegram_user_id,
                      "text": f"Ваш код для входа в кабинет студента: {code}\nДействует 60 секунд."},
            )
            send_data = send.json()
            if not send_data.get("ok"):
                return TelegramLoginOut(
                    error="Не удалось отправить код. Напишите боту /start и попробуйте снова.")
    except (httpx.HTTPError, ValueError) as e:
        return TelegramLoginOut(error=f"Ошибка подключения к Telegram API: {e}")

    now = time.monotonic()
    _purge_codes(now)
    _temp_codes[str(student.telegram_user_id)] = (code, now + _CODE_TTL_S)
    return TelegramLoginOut(code_sent=True)


@router.post("/telegram_login", response_model=LoginOut)
async def telegram_login(body: TelegramLoginIn, request: Request,
                         _rl: None = Depends(code_login_limit),
                         session: AsyncSession = Depends(get_session)):
    """Вход по username + коду. Проверяем код и возвращаем студента."""
    if not _telegram_configured():
        raise HTTPException(status_code=503, detail="Вход через Telegram не настроен.")
    username = body.telegram_username.strip()
    if not username.startswith("@"):
        raise HTTPException(status_code=400, detail="Username должен начинаться с @")

    # Ищем пользователя по username в БД
    result = await session.execute(select(Student, Group.name).join(Group, Student.group_id == Group.id)
                                   .where(Student.telegram_username == username))
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Студент не найден.")

    student, group_name = row

    if not student.telegram_user_id:
        raise HTTPException(status_code=400, detail="Для входа через Telegram требуется user_id. Свяжитесь с администратором.")

    # Проверяем код (сравнение за константное время, без утечки по времени)
    user_id_str = str(student.telegram_user_id)
    entry = _temp_codes.get(user_id_str)
    if entry is None:
        raise HTTPException(status_code=400, detail="Код не найден. Запросите новый.")

    stored_code, expires_at = entry
    if time.monotonic() > expires_at:
        del _temp_codes[user_id_str]
        raise HTTPException(status_code=400, detail="Код истёк. Запросите новый.")

    if not hmac.compare_digest(body.code, stored_code):
        raise HTTPException(status_code=400, detail="Неверный код.")

    del _temp_codes[user_id_str]

    return LoginOut(student=_out(student, group_name))
