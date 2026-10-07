"""Оценки: только свои (студент — из токена сессии)."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Grade, Subject
from ..schemas import GradeOut, StudentOut, SubjectDescription
from .auth import current_student

router = APIRouter(prefix="/grades", tags=["grades"])


def _parse_description(raw: str | None) -> SubjectDescription:
    """JSON из Subject.description -> схема, битый/пустой -> пустая схема."""
    if not raw:
        return SubjectDescription()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return SubjectDescription()
    if not isinstance(data, dict):
        return SubjectDescription()
    try:
        return SubjectDescription(**{k: data.get(k) for k in
                                     ("about", "skills_title", "skills",
                                      "content_title", "content")
                                     if k in data})
    except Exception:  # noqa: BLE001 — битый JSON не должен ронять API
        return SubjectDescription()


@router.get("", response_model=list[GradeOut])
async def list_grades(semester: str = "",
                      me: StudentOut = Depends(current_student),
                      session: AsyncSession = Depends(get_session)):
    """Итоговые оценки текущего студента, опционально за семестр."""
    stmt = (select(Grade, Subject.name, Subject.description)
            .join(Subject, Grade.subject_id == Subject.id)
            .where(Grade.student_id == me.id))
    if semester:
        stmt = stmt.where(Grade.semester == semester)
    stmt = stmt.order_by(Grade.semester, Subject.name)
    rows = (await session.execute(stmt)).all()
    return [GradeOut(id=g.id, subject=name, semester=g.semester,
                     attestation=g.attestation, value=g.value,
                     verbal=g.verbal, ects=g.ects, score=g.score,
                     description=_parse_description(desc))
            for g, name, desc in rows]
