"""Вход: идентификация себя по фамилии+имени (без пароля) или Telegram."""

import secrets
import time
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
    """Запрос временного кода: проверяем, что username в БД, генерируем 6-значный код."""
    username = body.telegram_username.strip()
    if not username.startswith("@"):
        return TelegramLoginOut(error="Username должен начинаться с @")
    
    # Проверяем, есть ли такой пользователь в БД
    result = await session.execute(select(Student).where(Student.telegram_username == username))
    student = result.scalar_one_or_none()
    if not student:
        # Если username не в БД, всё равно генерируем код (для демо/отладки)
        # В продакшене можно убрать эту ветку и возвращать error="User not found"
        pass
    
    code = f"{secrets.randbelow(10_000_000):06d}"
    _temp_codes[username] = (code, time.time() + 60)  # 60 секунд TTL
    # В реальном боте здесь был бы вызов Telegram API для отправки кода пользователю
    return TelegramLoginOut(code_sent=True)


@router.post("/telegram_login", response_model=LoginOut)
async def telegram_login(body: TelegramLoginIn, session: AsyncSession = Depends(get_session)):
    """Вход по username + коду. Проверяем код и возвращаем студента."""
    username = body.telegram_username.strip()
    if not username.startswith("@"):
        raise HTTPException(status_code=400, detail="Username должен начинаться с @")
    
    # Проверяем код
    if username not in _temp_codes:
        raise HTTPException(status_code=400, detail="Код не найден. Запросите новый.")
    
    stored_code, expires_at = _temp_codes[username]
    if time.time() > expires_at:
        del _temp_codes[username]
        raise HTTPException(status_code=400, detail="Код истёк. Запросите новый.")
    
    if body.code != stored_code:
        raise HTTPException(status_code=400, detail="Неверный код.")
    
    del _temp_codes[username]
    
    # Находим студента
    result = await session.execute(select(Student, Group.name).join(Group, Student.group_id == Group.id)
                                   .where(Student.telegram_username == username))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Студент не найден.")
    
    student, group_name = row
    return LoginOut(student=_out(student, group_name))
