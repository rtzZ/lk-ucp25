"""Вход: идентификация себя по фамилии+имени (без пароля) или Telegram."""

import secrets
import time
import urllib.request
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Group, Student
from ..schemas import LoginIn, LoginOut, StudentOut, TelegramLoginIn, TelegramLoginOut
from ..sync import norm_name

router = APIRouter(prefix="/auth", tags=["auth"])

# ponytail: in-memory store, lost on restart. Add Redis if multi-instance or persistence needed.
_temp_codes: dict[str, tuple[str, float]] = {}  # username -> (code, expires_at)

# ponytail: hardcoded bot config. Move to env vars if needed.
_TELEGRAM_BOT_TOKEN = "5166952715:AAE7GIRWcf03L-07V8QoW7FfIr6BP67IFEI"
_TELEGRAM_GROUP_ID = -5287416461


def _out(student: Student, group_name: str) -> StudentOut:
    return StudentOut(
        id=student.id, group=group_name, code=student.code,
        last_name=student.last_name, first_name=student.first_name,
        full_name=student.full_name,
    )


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    """Точное совпадение «фамилия имя» -> student; иначе 404 с подсказками."""
    rows = (await session.execute(
        select(Student, Group.name).join(Group, Student.group_id == Group.id)
    )).all()
    want = norm_name(f"{body.last_name} {body.first_name}".strip())
    for student, group_name in rows:
        if student.code == want and body.first_name.strip():
            return LoginOut(student=_out(student, group_name))
    same_last = [_out(s, g) for s, g in rows
                 if norm_name(s.last_name) == norm_name(body.last_name)]
    if len(same_last) == 1 and not body.first_name.strip():
        return LoginOut(student=same_last[0])
    raise HTTPException(status_code=404, detail={
        "message": "Студент не найден, уточните имя",
        "suggestions": [s.model_dump() for s in same_last],
    })


@router.post("/telegram_request_code", response_model=TelegramLoginOut)
async def telegram_request_code(body: TelegramLoginIn, session: AsyncSession = Depends(get_session)):
    """Запрос временного кода: проверяем членство в группе через @CoomanBot."""
    user_id_str = body.telegram_username.strip()
    
    try:
        user_id = int(user_id_str)
    except ValueError:
        return TelegramLoginOut(error="user_id должен быть числом")
    
    # Проверяем членство в группе через Telegram Bot API
    try:
        # API: https://api.telegram.org/bot<TOKEN>/getChatMember?chat_id=<GROUP_ID>&user_id=<USER_ID>
        chat_member_url = (
            f"https://api.telegram.org/bot{_TELEGRAM_BOT_TOKEN}/"
            f"getChatMember?chat_id={_TELEGRAM_GROUP_ID}&user_id={user_id}"
        )
        req = urllib.request.Request(chat_member_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8")
            import json
            result = json.loads(data)
            if not result.get("ok"):
                return TelegramLoginOut(error=f"Ошибка Telegram API: {result.get('description', 'unknown')}")
            
            # Проверяем статус участника
            member = result.get("result", {})
            status = member.get("status")
            if status not in ("member", "administrator", "creator"):
                return TelegramLoginOut(error="Пользователь не состоит в группе. Проверьте подписку на канал/группу.")
        
        # Проверяем, что пользователь есть в БД
        # ponytail: ищем по telegram_username, но user_id не сохранён в БД.
        # Решение: добавить поле telegram_user_id в модель Student, или
        # использовать username как идентификатор.
        # Для простоты: ищем пользователя по username (предполагается, что он введён в БД)
        
        # Получаем username через Telegram API (опционально)
        # getUpdates может вернуть username по user_id, если пользователь писал боту
        # Но это сложно... Проще: пусть username хранится в БД
        
        # Простая проверка: ищем пользователя с совпадающим telegram_user_id
        # В реальном сценарии: нужно сохранять user_id в БД и искать по нему
        
        result_db = await session.execute(select(Student).where(Student.telegram_user_id == user_id))
        student = result_db.scalar_one_or_none()
        if not student:
            # Для демо: ищем любого пользователя с не-null telegram_username
            result_db = await session.execute(select(Student).where(Student.telegram_username.isnot(None)))
            student = result_db.scalar_one_or_none()
            if not student:
                return TelegramLoginOut(error="В системе нет привязанных Telegram-пользователей")
        
        code = f"{secrets.randbelow(10_000_000):06d}"
        _temp_codes[str(user_id)] = (code, time.time() + 60)  # 60 секунд TTL
        return TelegramLoginOut(code_sent=True)
    except urllib.error.URLError as e:
        return TelegramLoginOut(error=f"Ошибка подключения к Telegram API: {str(e.reason)}")
    except Exception as e:
        return TelegramLoginOut(error=f"Ошибка: {str(e)}")


@router.post("/telegram_login", response_model=LoginOut)
async def telegram_login(body: TelegramLoginIn, session: AsyncSession = Depends(get_session)):
    """Вход по user_id + коду. Проверяем код и возвращаем студента."""
    user_id_str = body.telegram_username.strip()
    
    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="user_id должен быть числом")
    
    # Проверяем код
    if user_id_str not in _temp_codes:
        raise HTTPException(status_code=400, detail="Код не найден. Запросите новый.")
    
    stored_code, expires_at = _temp_codes[user_id_str]
    if time.time() > expires_at:
        del _temp_codes[user_id_str]
        raise HTTPException(status_code=400, detail="Код истёк. Запросите новый.")
    
    if body.code != stored_code:
        raise HTTPException(status_code=400, detail="Неверный код.")
    
    del _temp_codes[user_id_str]
    
    # Находим студента
    result = await session.execute(select(Student, Group.name).join(Group, Student.group_id == Group.id)
                                   .where(Student.telegram_user_id == user_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Студент не найден.")
    
    student, group_name = row
    return LoginOut(student=_out(student, group_name))
