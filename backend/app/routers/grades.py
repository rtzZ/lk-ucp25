"""Оценки: только свои (студент — из токена сессии)."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Grade, Subject
from ..grading import BANDS, interpret
from ..schemas import GradeOut, ScaleBandOut, StudentOut, SubjectDescription
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


# Семестр закрыт, если итоговая оценка есть хотя бы у этой доли записей
# (по всей группе): тогда баллы без оценки — «предварительно», иначе — «идёт».
CLOSED_SHARE = 0.5


async def _closed_semesters(session: AsyncSession) -> set[str]:
    rows = (await session.execute(
        select(Grade.semester, func.count(),
               func.sum(case((Grade.value != "", 1), else_=0)))
        .group_by(Grade.semester))).all()
    return {sem for sem, total, filled in rows
            if total and (filled or 0) / total >= CLOSED_SHARE}


@router.get("/scale", response_model=list[ScaleBandOut])
async def grading_scale(_me: StudentOut = Depends(current_student)):
    """Официальная шкала оценивания (для легенды на фронте)."""
    return [ScaleBandOut(**b.__dict__) for b in BANDS]


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
    closed = await _closed_semesters(session)
    return [GradeOut(id=g.id, subject=name, semester=g.semester,
                     attestation=g.attestation, value=g.value,
                     verbal=g.verbal, ects=g.ects, score=g.score,
                     description=_parse_description(desc),
                     **interpret(g.value, g.ects, g.score,
                                 semester_closed=g.semester in closed))
            for g, name, desc in rows]
