"""Демо-данные для разработки и E2E (SEED_DEMO=1)."""

from sqlalchemy import select

from .db import SessionLocal
from .models import Grade, Group, ScheduleItem, Student, Subject


async def seed_demo() -> None:
    """Минимальный детерминированный набор: группа, 2 студента, пары, оценки."""
    async with SessionLocal() as session:
        exists = (await session.execute(select(Group))).first()
        if exists:
            return
        session.add(Group(name="УЦП-25"))
        await session.flush()
        group_id = (await session.execute(select(Group))).scalar_one().id
        session.add_all([
            Student(group_id=group_id, code="иванов иван",
                    last_name="Иванов", first_name="Иван",
                    full_name="Иванов Иван Иванович",
                    telegram_username="@ivanov_ivan"),
            Student(group_id=group_id, code="петрова анна",
                    last_name="Петрова", first_name="Анна",
                    full_name="Петрова Анна Сергеевна",
                    telegram_username="@petрова_анна"),
        ])
        session.add_all([
            Subject(name="Математика"),
            Subject(name="Физика"),
        ])
        await session.flush()
        st = {s.code: s.id for s in
              (await session.execute(select(Student))).scalars()}
        subj = {s.name: s.id for s in
                (await session.execute(select(Subject))).scalars()}
        session.add_all([
            Grade(student_id=st["иванов иван"], subject_id=subj["Математика"],
                  semester="1 семестр 25-26", attestation="экзамен",
                  value="5", verbal="Отлично", ects="A", score=92.0),
            Grade(student_id=st["иванов иван"], subject_id=subj["Физика"],
                  semester="1 семестр 25-26", attestation="зачет",
                  value="зачтено", verbal="", ects="Passed", score=75.0),
            ScheduleItem(group_id=group_id, date="2026-02-09",
                         time_start="19:00", time_end="20:20",
                         subject_text="Математика", teacher="Сидоров",
                         org="РАНХиГС", lesson_no=1, kind="lesson",
                         link="https://video.example.com/math-1"),
            ScheduleItem(group_id=group_id, date="2026-02-10",
                         time_start="19:00", time_end="20:20",
                         subject_text="Физика", teacher="Козлова",
                         org="Нетология", lesson_no=2, kind="lesson"),
        ])
        await session.commit()
