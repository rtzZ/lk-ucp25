"""Оценки конкретного студента (все данные общие, свои подсвечиваются)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Grade, Subject
from ..schemas import GradeOut

router = APIRouter(prefix="/grades", tags=["grades"])


@router.get("", response_model=list[GradeOut])
async def list_grades(student_id: int, semester: str = "",
                      session: AsyncSession = Depends(get_session)):
    """Итоговые оценки студента, опционально за семестр."""
    stmt = (select(Grade, Subject.name)
            .join(Subject, Grade.subject_id == Subject.id)
            .where(Grade.student_id == student_id))
    if semester:
        stmt = stmt.where(Grade.semester == semester)
    stmt = stmt.order_by(Grade.semester, Subject.name)
    rows = (await session.execute(stmt)).all()
    return [GradeOut(id=g.id, subject=name, semester=g.semester,
                     attestation=g.attestation, value=g.value,
                     verbal=g.verbal, ects=g.ects, score=g.score)
            for g, name in rows]
