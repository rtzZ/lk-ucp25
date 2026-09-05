"""Расписание: группы и записи с фильтрами по дате и типу."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Group, ScheduleItem
from ..schemas import ScheduleItemOut

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/groups", response_model=list[str])
async def list_groups(session: AsyncSession = Depends(get_session)):
    """Имена групп, у которых есть расписание."""
    rows = (await session.execute(
        select(Group.name).join(ScheduleItem,
                                ScheduleItem.group_id == Group.id)
        .distinct().order_by(Group.name)
    )).all()
    return [r[0] for r in rows]


@router.get("", response_model=list[ScheduleItemOut])
async def list_schedule(group: str = "УЦП-25",
                        date_from: str = "", date_to: str = "",
                        kind: str = "",
                        session: AsyncSession = Depends(get_session)):
    """Записи группы по датам (ISO). kind: lesson|attestation|event|deadline."""
    stmt = (select(ScheduleItem, Group.name)
            .join(Group, ScheduleItem.group_id == Group.id)
            .where(Group.name == group))
    if date_from:
        stmt = stmt.where(ScheduleItem.date >= date_from)
    if date_to:
        stmt = stmt.where(ScheduleItem.date <= date_to)
    if kind:
        stmt = stmt.where(ScheduleItem.kind == kind)
    stmt = stmt.order_by(ScheduleItem.date, ScheduleItem.time_start,
                         ScheduleItem.id)
    rows = (await session.execute(stmt)).all()
    return [ScheduleItemOut(id=i.id, group=g, date=i.date,
                            time_start=i.time_start, time_end=i.time_end,
                            subject_text=i.subject_text, teacher=i.teacher,
                            org=i.org, lesson_no=i.lesson_no, kind=i.kind,
                            status=i.status, note=i.note, link=i.link)
            for i, g in rows]
