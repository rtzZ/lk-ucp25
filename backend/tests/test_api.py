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
    os.environ["SKIP_SCHEDULER"] = "1"  # фоновые задачи в тестах не нужны

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


def test_grades_include_description(client):
    """Оценки отдают описание предмета (пустое, если нет в макете)."""
    import asyncio
    import json

    async def run():
        from app.subject_descriptions import to_json
        async with TestSession() as s:
            subj = (await s.execute(select(Subject))).scalar_one()
            subj.description = to_json("Маркетинг")
            await s.commit()

    asyncio.run(run())
    try:
        grades = client.get(f"/grades?student_id={client.ids[0]}").json()
        d = grades[0]["description"]
        assert d["about"].startswith("Дисциплина учит проводить исследования")
        assert d["content_title"] == "Содержание дисциплины"
        assert "Рыночная ориентация" in d["content"]
    finally:
        async def cleanup():
            async with TestSession() as s:
                subj = (await s.execute(select(Subject))).scalar_one()
                subj.description = ""
                await s.commit()
        asyncio.run(cleanup())


def test_subjects_endpoint(client):
    """GET /subjects: точное, нормализованное («по выбору») и 404."""
    r = client.get("/subjects", params={"name": "Математика"})
    assert r.status_code == 200
    assert r.json()["description"]["about"] == ""
    assert client.get("/subjects", params={"name": "Нет такого"}).status_code == 404
    assert client.get("/subjects", params={"name": ""}).status_code == 404


def test_subjects_match_prefix_org_suffix(client):
    """subject_text расписания «Название (Организация)» матчится на предмет."""
    r = client.get("/subjects", params={
        "name": "Математика (Нетология)"})
    assert r.status_code == 200
    assert r.json()["name"] == "Математика"


def test_subjects_match_normalized(client):
    """Скобки «(по выбору)» и регистр не мешают матчингу."""
    import asyncio

    async def run():
        async with TestSession() as s:
            s.add(Subject(name="Управление проектами в консалтинге (по выбору)",
                          description=""))
            await s.commit()

    asyncio.run(run())
    try:
        r = client.get("/subjects", params={
            "name": "управление проектами В КОНСАЛТИНГЕ (по выбору)"})
        assert r.status_code == 200
        assert r.json()["name"] == "Управление проектами в консалтинге (по выбору)"
    finally:
        async def cleanup():
            async with TestSession() as s:
                await s.execute(Subject.__table__.delete().where(
                    Subject.name == "Управление проектами в консалтинге (по выбору)"))
                await s.commit()
        asyncio.run(cleanup())


def test_fill_descriptions_no_overwrite():
    """fill проставляет описания пустым и не трогает заполненные."""
    import asyncio
    from app.subject_descriptions import fill_subject_descriptions
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def run():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with S() as s:
            s.add_all([
                Subject(name="Маркетинг", description=""),
                Subject(name="Физика", description=""),
                Subject(name="Математика", description='{"about": "ручное"}'),
            ])
            await s.commit()
        async with S() as s:
            n = await fill_subject_descriptions(s)
            rows = {r.name: r.description for r in
                    (await s.execute(select(Subject))).scalars()}
        assert n == 1  # только Маркетинг (Физика не в макете)
        assert "исследования" in rows["Маркетинг"]
        assert rows["Физика"] == ""
        assert rows["Математика"] == '{"about": "ручное"}'  # ручное не затёрто
        await eng.dispose()

    asyncio.run(run())


def test_expire_past_items():
    """Прошедшие active-пары становятся completed; будущие не трогаются."""
    import asyncio
    import datetime
    from app.routers.schedule import _expire_past_items

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def run():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with S() as s:
            s.add(Group(name="G"))
            await s.flush()
            gid = (await s.execute(select(Group))).scalar_one().id
            s.add_all([
                ScheduleItem(group_id=gid, date="2026-09-10",
                             time_start="08:00", time_end="09:00",
                             subject_text="past-today", status="active"),
                ScheduleItem(group_id=gid, date="2026-09-10",
                             time_start="23:00", time_end="23:30",
                             subject_text="future-today", status="active"),
                ScheduleItem(group_id=gid, date="2026-09-09",
                             time_start="", time_end="",
                             subject_text="past-day", status="active"),
                ScheduleItem(group_id=gid, date="2026-09-11",
                             time_start="08:00", time_end="09:00",
                             subject_text="future", status="active"),
                ScheduleItem(group_id=gid, date="2026-09-10",
                             time_start="20:30", time_end="21:30",
                             subject_text="live-now", status="active"),
            ])
            await s.commit()

        now = datetime.datetime(2026, 9, 10, 21, 0)
        async with S() as s:
            n = await _expire_past_items(s, now=now)
            rows = {r.subject_text: r.status for r in
                    (await s.execute(select(ScheduleItem))).scalars()}
        assert n == 2  # past-today (21:00 > 09:00) + past-day
        assert rows["past-today"] == "completed"
        assert rows["past-day"] == "completed"
        assert rows["live-now"] == "active"   # идёт сейчас — не прошедшая
        assert rows["future-today"] == "active"  # 23:00 ещё впереди
        assert rows["future"] == "active"
        await eng.dispose()

    asyncio.run(run())


def test_is_in_progress():
    """Отсечки live: внутри [start, end) — true, на границах и вне — false."""
    import datetime
    from app.routers.schedule import _is_in_progress

    now = datetime.datetime(2026, 9, 10, 21, 0)
    assert _is_in_progress("2026-09-10", "20:30", "21:30", now)
    assert _is_in_progress("2026-09-10", "21:00", "22:00", now)  # только началась
    assert not _is_in_progress("2026-09-10", "19:00", "20:00", now)  # прошла
    assert not _is_in_progress("2026-09-10", "22:00", "23:00", now)  # будущая
    assert not _is_in_progress("2026-09-11", "20:30", "21:30", now)  # другой день
    assert not _is_in_progress("2026-09-10", "", "21:30", now)  # нет времени начала
    assert not _is_in_progress("2026-09-10", "20:30", "", now)  # нет времени конца


def test_live_status_in_api(client):
    """Идущая сейчас пара возвращается API со статусом 'live'."""
    import asyncio
    import datetime

    async def run():
        now = datetime.datetime.now()
        today = now.strftime("%Y-%m-%d")
        start = (now - datetime.timedelta(minutes=5)).strftime("%H:%M")
        end = (now + datetime.timedelta(minutes=10)).strftime("%H:%M")
        async with TestSession() as s:
            gid = (await s.execute(select(Group).where(
                Group.name == "УЦП-25"))).scalar_one().id
            it = ScheduleItem(group_id=gid, date=today,
                              time_start=start, time_end=end,
                              subject_text="ЖИВАЯ ПАРА", kind="lesson",
                              status="active")
            s.add(it)
            await s.commit()
        try:
            rows = client.get("/schedule?group=УЦП-25").json()
            live = [r for r in rows if r["subject_text"] == "ЖИВАЯ ПАРА"]
            assert len(live) == 1 and live[0]["status"] == "live"
        finally:
            async with TestSession() as s:
                await s.execute(ScheduleItem.__table__.delete().where(
                    ScheduleItem.subject_text == "ЖИВАЯ ПАРА"))
                await s.commit()

    asyncio.run(run())


def test_upsert_grades_keeps_telegram():
    """Синхронизация не затирает telegram-привязки студентов."""
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.sync import upsert_grades

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def run():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with S() as s:
            s.add(Group(name="УЦП-25"))
            await s.flush()
            gid = (await s.execute(select(Group))).scalar_one().id
            s.add(Student(group_id=gid, code="иванов иван",
                          last_name="Иванов", first_name="Иван",
                          full_name="Иванов Иван Иванович",
                          telegram_username="@ivanov_ivan",
                          telegram_user_id=10001))
            await s.commit()
        students = [{"group": "УЦП-25", "code": "иванов иван",
                     "last_name": "Иванов", "first_name": "Иван",
                     "full_name": "Иванов Иван Иванович"}]
        grades = [{"student_code": "иванов иван", "subject": "Математика",
                   "semester": "1 семестр 25-26", "attestation": "экзамен",
                   "value": "5", "verbal": "Отлично", "ects": "A",
                   "score": 92.0}]
        async with S() as s:
            assert await upsert_grades(students, grades, s) == 1
            st = (await s.execute(select(Student).where(
                Student.code == "иванов иван"))).scalar_one()
            assert st.telegram_username == "@ivanov_ivan"
            assert st.telegram_user_id == 10001
        await eng.dispose()

    asyncio.run(run())


def test_upsert_empty_keeps_data():
    """Пустой результат парсинга не вайпает БД."""
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.sync import upsert_grades, upsert_schedule

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def run():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with S() as s:
            s.add(Group(name="УЦП-25"))
            await s.flush()
            gid = (await s.execute(select(Group))).scalar_one().id
            s.add_all([
                Student(group_id=gid, code="иванов иван",
                        last_name="Иванов", first_name="Иван",
                        full_name="Иванов Иван Иванович"),
                ScheduleItem(group_id=gid, date="2026-02-09",
                             time_start="19:00", time_end="20:20",
                             subject_text="Математика", kind="lesson"),
            ])
            await s.commit()
        async with S() as s:
            assert await upsert_schedule([], s) == 0
            assert await upsert_grades([], [], s) == 0
            assert (await s.execute(select(Student))).scalar_one() is not None
            assert (await s.execute(select(ScheduleItem))).scalar_one() is not None
        await eng.dispose()

    asyncio.run(run())


def test_lesson_link_keeps_only_http():
    """В link проходят только http(s)-ссылки (защита от javascript: XSS)."""
    from app.sync import parse_lesson_cell

    good = parse_lesson_cell("Математика\nНетология\nhttps://video.example.com/1")
    assert good and good["link"] == "https://video.example.com/1"
    bad = parse_lesson_cell("Математика\nНетология\njavascript:alert(1)")
    assert bad and bad["link"] == ""
    bad2 = parse_lesson_cell("Математика", hyperlink="JaVaScRiPt:alert(1)")
    assert bad2 and bad2["link"] == ""
    assert parse_lesson_cell("Математика", hyperlink="http://a.b/c")["link"] == "http://a.b/c"


def test_rate_limit_blocks():
    """Лимитер: сверх лимита — 429, у других IP — свой счётчик."""
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app import ratelimit

    ratelimit.reset()
    dep = ratelimit.rate_limit("test-auth", limit=2, window_s=60)

    async def run():
        req = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"))
        await dep(req)
        await dep(req)
        try:
            await dep(req)
        except HTTPException as e:
            assert e.status_code == 429
        else:
            raise AssertionError("ожидался 429")
        other = SimpleNamespace(client=SimpleNamespace(host="5.6.7.8"))
        await dep(other)  # другой IP не затронут

    asyncio.run(run())
    ratelimit.reset()


def test_telegram_not_configured(client, monkeypatch):
    """Без TELEGRAM_BOT_TOKEN — понятная ошибка вместо падения."""
    import app.routers.auth as auth_mod

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_GROUP_ID", raising=False)
    assert not auth_mod._telegram_configured()
    r = client.post("/auth/telegram_request_code",
                    json={"telegram_username": "@ivanov_ivan", "code": ""})
    assert r.status_code == 200
    assert "не настроен" in r.json()["error"]
    r = client.post("/auth/telegram_login",
                    json={"telegram_username": "@ivanov_ivan", "code": "000000"})
    assert r.status_code == 503


def test_parse_sync_times():
    """SYNC_TIMES: валидные пары проходят, мусор пропускается."""
    from app.main import _parse_sync_times

    assert _parse_sync_times("09:30,11:00") == [(9, 30), (11, 0)]
    assert _parse_sync_times(" 9:5 , 23:59 ") == [(9, 5), (23, 59)]
    assert _parse_sync_times("25:00,12:60,abc,,10:00") == [(10, 0)]
    assert _parse_sync_times("") == []
    assert _parse_sync_times("мусор") == []


def test_resolve_tz_fallback(monkeypatch):
    """Неизвестный SYNC_TIMEZONE — warning + Москва."""
    import os
    from zoneinfo import ZoneInfo

    from app.main import _resolve_tz

    monkeypatch.delenv("SYNC_TIMEZONE", raising=False)
    assert _resolve_tz() == ZoneInfo("Europe/Moscow")
    monkeypatch.setenv("SYNC_TIMEZONE", "Mars/Olympus")
    assert _resolve_tz() == ZoneInfo("Europe/Moscow")
    monkeypatch.setenv("SYNC_TIMEZONE", "Europe/London")
    assert _resolve_tz() == ZoneInfo("Europe/London")
    monkeypatch.delenv("SYNC_TIMEZONE", raising=False)
    assert os.getenv("SYNC_TIMEZONE") is None


def test_display_status():
    """Статусы на выдаче: прошлое active -> completed, будущее -> active."""
    import datetime
    from app.models import ScheduleItem
    from app.routers.schedule import _display_status

    now = datetime.datetime(2026, 9, 10, 21, 0)
    past = ScheduleItem(group_id=1, date="2026-09-09", time_start="",
                        time_end="", subject_text="x", status="active")
    assert _display_status(past, now) == "completed"
    past_today = ScheduleItem(group_id=1, date="2026-09-10",
                              time_start="08:00", time_end="09:00",
                              subject_text="x", status="active")
    assert _display_status(past_today, now) == "completed"
    future = ScheduleItem(group_id=1, date="2026-09-11", time_start="08:00",
                          time_end="09:00", subject_text="x", status="active")
    assert _display_status(future, now) == "active"
    live = ScheduleItem(group_id=1, date="2026-09-10", time_start="20:30",
                        time_end="21:30", subject_text="x", status="active")
    assert _display_status(live, now) == "live"
    cancelled = ScheduleItem(group_id=1, date="2026-09-09", time_start="",
                             time_end="", subject_text="x",
                             status="cancelled")
    assert _display_status(cancelled, now) == "cancelled"


def test_schedule_read_does_not_write(client):
    """GET /schedule показывает completed, но БД не меняет."""
    import asyncio

    rows = client.get("/schedule?group=УЦП-25").json()
    past = next(r for r in rows if r["date"] == "2026-02-09")
    assert past["status"] == "completed"  # посчитано на лету

    async def run():
        async with TestSession() as s:
            it = (await s.execute(select(ScheduleItem).where(
                ScheduleItem.date == "2026-02-09"))).scalar_one()
            return it.status

    assert asyncio.run(run()) == "active"  # в БД — без изменений


def test_upsert_grades_dedupes():
    """Дубли (студент, предмет, семестр) не роняют синк IntegrityError."""
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.sync import upsert_grades

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def run():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with S() as s:
            s.add(Group(name="УЦП-25"))
            await s.flush()
            gid = (await s.execute(select(Group))).scalar_one().id
            s.add(Student(group_id=gid, code="иванов иван",
                          last_name="Иванов", first_name="Иван",
                          full_name="Иванов Иван Иванович"))
            await s.commit()
        one = {"student_code": "иванов иван", "subject": "Математика",
               "semester": "1 семестр 25-26", "attestation": "экзамен",
               "value": "5", "verbal": "Отлично", "ects": "A", "score": 92.0}
        students = [{"group": "УЦП-25", "code": "иванов иван",
                     "last_name": "Иванов", "first_name": "Иван",
                     "full_name": "Иванов Иван Иванович"}]
        async with S() as s:
            assert await upsert_grades(students, [one, dict(one)], s) == 1
            grades = (await s.execute(select(Grade))).scalars().all()
            assert len(grades) == 1
        await eng.dispose()

    asyncio.run(run())
