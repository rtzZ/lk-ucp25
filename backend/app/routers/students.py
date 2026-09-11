"""Студенты: список группы (экран входа) и карточка."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Group, Student
from ..schemas import StudentOut

router = APIRouter(prefix="/students", tags=["students"])


@router.get("", response_model=list[StudentOut])
async def list_students(group: str = "УЦП-25",
                        session: AsyncSession = Depends(get_session)):
    """Все студенты группы для экрана входа."""
    rows = (await session.execute(
        select(Student, Group.name)
        .join(Group, Student.group_id == Group.id)
        .where(Group.name == group)
        .order_by(Student.last_name, Student.first_name)
    )).all()
    return [StudentOut(id=s.id, group=g, code=s.code, last_name=s.last_name,
                       first_name=s.first_name, full_name=s.full_name)
            for s, g in rows]


@router.get("/{student_id}", response_model=StudentOut)
async def get_student(student_id: int,
                      session: AsyncSession = Depends(get_session)):
    """Карточка студента."""
    row = (await session.execute(
        select(Student, Group.name)
        .join(Group, Student.group_id == Group.id)
        .where(Student.id == student_id)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Студент не найден")
    student, group_name = row
    return StudentOut(id=student.id, group=group_name, code=student.code,
                      last_name=student.last_name,
                      first_name=student.first_name,
                      full_name=student.full_name)
