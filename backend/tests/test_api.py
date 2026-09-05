"""API-тесты: auth, students, schedule, grades (sqlite, без Postgres)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.models import Grade, Group, ScheduleItem, Student, Subject

engine = create_async_engine("sqlite+aiosqlite://")
TestSession = async_sessionmaker(engine, expire_on_commit=False)


async def _seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as s:
        s.add(Group(name="УЦП-25"))
        await s.flush()
        group_id = (await s.execute(select(Group))).scalar_one().id
        s.add_all([
            Student(group_id=group_id, code="иванов иван",
                    last_name="Иванов", first_name="Иван",
                    full_name="Иванов Иван Иванович"),
            Student(group_id=group_id, code="петров петр",
                    last_name="Петров", first_name="Петр",
                    full_name="Петров Петр"),
        ])
        s.add(Subject(name="Математика"))
        await s.flush()
        st1 = (await s.execute(select(Student).where(
            Student.code == "иванов иван"))).scalar_one()
        st2 = (await s.execute(select(Student).where(
            Student.code == "петров петр"))).scalar_one()
        subj = (await s.execute(select(Subject))).scalar_one()
        s.add_all([
            Grade(student_id=st1.id, subject_id=subj.id,
                  semester="1 семестр 25-26", attestation="экзамен",
                  value="5", verbal="Отлично", ects="A", score=92.0),
            Grade(student_id=st2.id, subject_id=subj.id,
                  semester="1 семестр 25-26", attestation="экзамен",
                  value="4", verbal="Хорошо", ects="C", score=78.0),
            ScheduleItem(group_id=group_id, date="2026-02-09",
                         time_start="19:00", time_end="20:20",
                         subject_text="Математика", teacher="Сидоров",
                         org="РАНХиГС", lesson_no=1, kind="lesson",
                         status="active",
                         link="https://video.example.com/math-1"),
            ScheduleItem(group_id=group_id, date="2026-02-10",
                         time_start="19:00", time_end="20:20",
                         subject_text="Математика", kind="lesson",
                         status="cancelled"),
            ScheduleItem(group_id=group_id, date="2026-02-11",
                         time_start="", time_end="",
                         subject_text="Дедлайн ДЗ-1", kind="deadline",
                         status="active"),
        ])
        await s.commit()
        return st1.id, st2.id


@pytest.fixture(scope="module")
def client():
    import asyncio
    import os
    ids = asyncio.run(_seed())
    os.environ["SKIP_DB_INIT"] = "1"

    async def override():
        async with TestSession() as s:
            yield s

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        c.ids = ids
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_exact(client):
    r = client.post("/auth/login",
                    json={"last_name": "Иванов", "first_name": "Иван"})
    assert r.status_code == 200
    assert r.json()["student"]["code"] == "иванов иван"
    assert r.json()["student"]["group"] == "УЦП-25"


def test_login_last_name_only_single_match(client):
    r = client.post("/auth/login", json={"last_name": "Петров"})
    assert r.status_code == 200
    assert r.json()["student"]["first_name"] == "Петр"


def test_login_unknown_with_suggestions(client):
    r = client.post("/auth/login",
                    json={"last_name": "Иванов", "first_name": "Сергей"})
    assert r.status_code == 404
    suggestions = r.json()["detail"]["suggestions"]
    assert any(s["first_name"] == "Иван" for s in suggestions)


def test_login_unknown_no_suggestions(client):
    r = client.post("/auth/login", json={"last_name": "Несуществующий"})
    assert r.status_code == 404
    assert r.json()["detail"]["suggestions"] == []


def test_students_list_and_card(client):
    students = client.get("/students?group=УЦП-25").json()
    assert len(students) == 2
    card = client.get(f"/students/{client.ids[0]}").json()
    assert card["full_name"] == "Иванов Иван Иванович"
    assert client.get("/students/9999").status_code == 404


def test_schedule_filters(client):
    all_items = client.get("/schedule?group=УЦП-25").json()
    assert len(all_items) == 3
    assert all_items[0]["date"] == "2026-02-09"  # порядок по дате/времени
    lessons = client.get("/schedule?group=УЦП-25&kind=lesson").json()
    assert len(lessons) == 2
    day = client.get("/schedule?group=УЦП-25&date_from=2026-02-10"
                     "&date_to=2026-02-10").json()
    assert len(day) == 1 and day[0]["status"] == "cancelled"
    assert all_items[0]["link"] == "https://video.example.com/math-1"
    assert client.get("/schedule/groups").json() == ["УЦП-25"]


def test_grades(client):
    grades = client.get(f"/grades?student_id={client.ids[0]}").json()
    assert len(grades) == 1
    g = grades[0]
    assert (g["subject"], g["value"], g["score"]) == ("Математика", "5", 92.0)
    assert client.get(
        f"/grades?student_id={client.ids[0]}&semester=2 семестр").json() == []
    other = client.get(f"/grades?student_id={client.ids[1]}").json()
    assert other[0]["value"] == "4"
