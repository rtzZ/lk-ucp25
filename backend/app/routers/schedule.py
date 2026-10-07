"""Расписание группы текущего студента с фильтрами по дате и типу."""

import datetime as _dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Group, ScheduleItem
from ..schemas import ScheduleItemOut, StudentOut
from ..tz import local_tz
from .auth import current_student

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _now() -> _dt.datetime:
    """Текущее время в поясе кабинета (SYNC_TIMEZONE), naive.

    Не время сервера: в Docker оно UTC, и live/completed съезжали бы на 3 ч.
    """
    return _dt.datetime.now(local_tz()).replace(microsecond=0, tzinfo=None)


def _is_in_progress(date: str, time_start: str, time_end: str,
                    now: _dt.datetime) -> bool:
    """Сейчас идёт ли пара: дата сегодня + time_start <= now < time_end."""
    if date != now.strftime("%Y-%m-%d"):
        return False
    start, end = time_start.strip(), time_end.strip()
    if not start or not end:
        return False
    hhmm = now.strftime("%H:%M")
    return start <= hhmm < end


def _display_status(item: ScheduleItem, now: _dt.datetime) -> str:
    """Статус для выдачи: live/completed вычисляются на лету, БД не трогаем.

    Персистентный перевод в completed делает фоновый джоб (`main._expire_job`);
    чтение записью не занимается (иначе каждый GET — UPDATE+commit: гонки
    с синком, нагрузка, несовместимость с read-only репликами).
    """
    if item.status != "active":
        return item.status
    if _is_in_progress(item.date, item.time_start, item.time_end, now):
        return "live"
    today = now.strftime("%Y-%m-%d")
    if item.date < today:
        return "completed"
    if item.date == today:
        end = (item.time_end or "").strip() or (item.time_start or "").strip()
        if end and end <= now.strftime("%H:%M"):
            return "completed"
    return "active"


async def _expire_past_items(session: AsyncSession,
                             now: _dt.datetime | None = None) -> int:
    """Переводит прошедшие пары (status='active') → 'completed'.

    Логика: дата раньше сегодня ИЛИ (дата сегодня + время окончания <= сейчас).
    Если time_end не заполнен — используется time_start; если оба пусты —
    сравнивается только дата.
    """
    now = now or _now()
    today = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")

    # 1) Дата строго до сегодня — безусловно completed.
    r1 = (await session.execute(
        update(ScheduleItem)
        .where(ScheduleItem.status == "active")
        .where(ScheduleItem.date < today)
        .values(status="completed")
    )).rowcount

    # 2) Сегодня: time_end <= сейчас (fallback на time_start).
    effective = func.coalesce(
        func.nullif(ScheduleItem.time_end, ""),
        func.nullif(ScheduleItem.time_start, ""),
        "",
    )
    r2 = (await session.execute(
        update(ScheduleItem)
        .where(ScheduleItem.status == "active")
        .where(ScheduleItem.date == today)
        .where(effective != "")
        .where(effective <= hhmm)
        .values(status="completed")
    )).rowcount

    if r1 + r2:
        await session.commit()
    return r1 + r2


@router.get("", response_model=list[ScheduleItemOut])
async def list_schedule(date_from: str = "", date_to: str = "",
                        kind: str = "",
                        me: StudentOut = Depends(current_student),
                        session: AsyncSession = Depends(get_session)):
    """Записи группы студента по датам (ISO). kind: lesson|attestation|event|deadline.

    Только чтение: статусы live/completed вычисляются на лету
    (`_display_status`), персистентный перевод делает фоновый джоб.
    """
    now = _now()
    stmt = (select(ScheduleItem, Group.name)
            .join(Group, ScheduleItem.group_id == Group.id)
            .where(Group.name == me.group))
    if date_from:
        stmt = stmt.where(ScheduleItem.date >= date_from)
    if date_to:
        stmt = stmt.where(ScheduleItem.date <= date_to)
    if kind:
        stmt = stmt.where(ScheduleItem.kind == kind)
    stmt = stmt.order_by(ScheduleItem.date, ScheduleItem.time_start,
                         ScheduleItem.id)
    rows = (await session.execute(stmt)).all()
    out = []
    for i, g in rows:
        status = _display_status(i, now)
        out.append(ScheduleItemOut(id=i.id, group=g, date=i.date,
                                   time_start=i.time_start, time_end=i.time_end,
                                   subject_text=i.subject_text, teacher=i.teacher,
                                   org=i.org, lesson_no=i.lesson_no, kind=i.kind,
                                   status=status, note=i.note, link=i.link))
    return out
