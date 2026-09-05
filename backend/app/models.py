"""Модели БД кабинета студента.

Связей relationship нет осознанно: в async-режиме ленивая загрузка падает,
все выборки делаются явными select/join в роутерах и синхронизации.

Идентификаторов студентов в исходных таблицах нет, поэтому Student.code —
нормализованные «фамилия имя» (без отчества: в ведомостях составов одни
и те же студенты записаны то с отчеством, то без).
"""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Group(Base):
    """Учебная группа (УЦП-25, ЛФТ-25, ...)."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class Student(Base):
    """Студент. Вход — по фамилии+имени (свои данные подсвечиваются)."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    code: Mapped[str] = mapped_column(String(256), unique=True)
    last_name: Mapped[str] = mapped_column(String(128), index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    full_name: Mapped[str] = mapped_column(String(256), default="")
    telegram_username: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, default=None)
    telegram_user_id: Mapped[int | None] = mapped_column(nullable=True, default=None)


class Subject(Base):
    """Предмет (чистое название из шапки блока ведомости)."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True)


class Grade(Base):
    """Итоговая оценка студента по предмету за семестр."""

    __tablename__ = "grades"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "subject_id", "semester",
            name="uq_grade_student_subject_semester",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), index=True
    )
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    semester: Mapped[str] = mapped_column(String(64), index=True)
    attestation: Mapped[str] = mapped_column(String(64), default="")
    value: Mapped[str] = mapped_column(String(32), default="")
    verbal: Mapped[str] = mapped_column(String(32), default="")
    ects: Mapped[str] = mapped_column(String(8), default="")
    score: Mapped[float | None] = mapped_column(default=None)


class ScheduleItem(Base):
    """Занятие/аттестация/событие/дедлайн на конкретную дату.

    kind: lesson | attestation | event | deadline.
    status: active | cancelled | moved.
    """

    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"), index=True
    )
    date: Mapped[str] = mapped_column(index=True)  # ISO YYYY-MM-DD
    time_start: Mapped[str] = mapped_column(String(5), default="")
    time_end: Mapped[str] = mapped_column(String(5), default="")
    subject_text: Mapped[str] = mapped_column(String(512), default="")
    teacher: Mapped[str] = mapped_column(String(256), default="")
    org: Mapped[str] = mapped_column(String(128), default="")
    lesson_no: Mapped[int | None] = mapped_column(default=None)
    kind: Mapped[str] = mapped_column(String(16), default="lesson")
    status: Mapped[str] = mapped_column(String(16), default="active")
    note: Mapped[str] = mapped_column(String(1024), default="")
    link: Mapped[str] = mapped_column(String(1024), default="")
