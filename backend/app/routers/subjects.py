"""Предметы: описание по названию (для Drawer в оценках и расписании)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Subject
from ..routers.grades import _parse_description
from ..schemas import SubjectOut
from ..subject_descriptions import norm_key

router = APIRouter(prefix="/subjects", tags=["subjects"])


def _match(subjects: list[Subject], name: str) -> Subject | None:
    """Предмет по свободному названию.

    Точно -> нормализованно -> префикс (subject_text расписания — это
    «название (организация)») -> подстрока. Длинные имена проверяются первыми.
    """
    if not (name or "").strip():
        return None
    want = norm_key(name)
    exact = next((s for s in subjects if s.name == name.strip()), None)
    if exact is not None:
        return exact
    normed = next((s for s in subjects if norm_key(s.name) == want), None)
    if normed is not None:
        return normed
    by_len = sorted(subjects, key=lambda s: len(s.name), reverse=True)
    prefix = next((s for s in by_len
                   if norm_key(s.name) and want.startswith(norm_key(s.name))), None)
    if prefix is not None:
        return prefix
    return next((s for s in by_len if want and want in norm_key(s.name)), None)


@router.get("", response_model=SubjectOut)
async def get_subject(name: str,
                      session: AsyncSession = Depends(get_session)):
    """Описание предмета по названию; 404 — нет в базе/макете."""
    subjects = (await session.execute(select(Subject))).scalars().all()
    found = _match(list(subjects), name)
    if found is None:
        raise HTTPException(status_code=404, detail="subject not found")
    return SubjectOut(id=found.id, name=found.name,
                      description=_parse_description(found.description))
