"""Вход: идентификация себя по фамилии+имени (без пароля)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Group, Student
from ..schemas import LoginIn, LoginOut, StudentOut
from ..sync import norm_name

router = APIRouter(prefix="/auth", tags=["auth"])


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
