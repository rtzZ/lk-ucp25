"""API-тесты: auth, students, schedule, grades (sqlite, без Postgres)."""

import datetime
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app
from app.models import AuthSession, Grade, Group, ScheduleItem, Student, Subject
from app.routers.auth import _hash

FAR_FUTURE = datetime.datetime(2100, 1, 1)
IVANOV = {"Authorization": "Bearer tok-ivanov"}
PETROV = {"Authorization": "Bearer tok-petrov"}

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
        s.add_all([
            AuthSession(token_hash=_hash("tok-ivanov"), student_id=st1.id,
                        expires_at=FAR_FUTURE),
            AuthSession(token_hash=_hash("tok-petrov"), student_id=st2.id,
                        expires_at=FAR_FUTURE),
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
    with TestClient(app, headers=IVANOV) as c:
        c.ids = ids
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_schedule_filters(client):
    all_items = client.get("/schedule").json()
    assert len(all_items) == 3
    assert all_items[0]["date"] == "2026-02-09"  # порядок по дате/времени
    lessons = client.get("/schedule?kind=lesson").json()
    assert len(lessons) == 2
    day = client.get("/schedule?date_from=2026-02-10"
                     "&date_to=2026-02-10").json()
    assert len(day) == 1 and day[0]["status"] == "cancelled"
    assert all_items[0]["link"] == "https://video.example.com/math-1"


def test_grades(client):
    """Оценки — только свои: студент берётся из токена, не из запроса."""
    grades = client.get("/grades").json()
    assert len(grades) == 1
    g = grades[0]
    assert (g["subject"], g["value"], g["score"]) == ("Математика", "5", 92.0)
    assert client.get("/grades?semester=2 семестр").json() == []
    other = client.get("/grades", headers=PETROV).json()
    assert other[0]["value"] == "4"
    # чужой student_id в query игнорируется
    assert client.get(f"/grades?student_id={client.ids[1]}").json()[0]["value"] == "5"


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
        grades = client.get("/grades").json()
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

    from app.routers.schedule import _now

    async def run():
        now = _now()
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
            rows = client.get("/schedule").json()
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

    rows = client.get("/schedule").json()
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


def test_now_uses_cabinet_timezone(monkeypatch):
    """_now() — время пояса кабинета, а не сервера (в Docker там UTC)."""
    import datetime
    from zoneinfo import ZoneInfo

    from app.routers.schedule import _now

    monkeypatch.setenv("SYNC_TIMEZONE", "Asia/Vladivostok")
    want = datetime.datetime.now(ZoneInfo("Asia/Vladivostok")).replace(tzinfo=None)
    assert _now().tzinfo is None
    assert abs((_now() - want).total_seconds()) < 5


def test_upsert_grades_keeps_student_ids():
    """Повторный синк не меняет Student.id; ушедшие удаляются, новые — добавляются."""
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.sync import upsert_grades

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    def st(code, last, first):
        return {"group": "УЦП-25", "code": code, "last_name": last,
                "first_name": first, "full_name": f"{last} {first}"}

    def gr(code):
        return {"student_code": code, "subject": "Математика",
                "semester": "1 семестр 25-26", "attestation": "экзамен",
                "value": "5", "verbal": "Отлично", "ects": "A", "score": 92.0}

    async def ids(s):
        return {x.code: x.id for x in (await s.execute(select(Student))).scalars()}

    async def run():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        first = [st("иванов иван", "Иванов", "Иван"),
                 st("петров петр", "Петров", "Петр")]
        async with S() as s:
            await upsert_grades(first, [gr("иванов иван"), gr("петров петр")], s)
            before = await ids(s)
            s.add(AuthSession(token_hash="h", student_id=before["иванов иван"],
                              expires_at=FAR_FUTURE))
            await s.commit()
        second = [st("петров петр", "Петров", "Петр"),
                  st("сидоров сидор", "Сидоров", "Сидор")]
        async with S() as s:
            assert await upsert_grades(
                second, [gr("петров петр"), gr("сидоров сидор")], s) == 2
            after = await ids(s)
            assert after["петров петр"] == before["петров петр"]
            assert "иванов иван" not in after
            assert (await s.execute(select(AuthSession))).first() is None
            assert set(after) == {"петров петр", "сидоров сидор"}
            owners = {g.student_id for g in
                      (await s.execute(select(Grade))).scalars()}
            assert owners == set(after.values())
        await eng.dispose()

    asyncio.run(run())






# --- Авторизация: временный пароль от Telegram-бота -> токен сессии ---

NO_AUTH = {"Authorization": ""}


@pytest.fixture
def auth_env(monkeypatch):
    """Чистое состояние лимитов/паролей; бот «настроен» без сети."""
    import app.routers.auth as auth_mod
    from app import ratelimit

    ratelimit.reset()
    auth_mod._passwords.clear()
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_GROUP_ID", "-100")
    yield auth_mod
    ratelimit.reset()
    auth_mod._passwords.clear()


def _set_tg(student_id: int, user_id: int | None) -> None:
    import asyncio

    async def run():
        async with TestSession() as s:
            st = await s.get(Student, student_id)
            st.telegram_user_id = user_id
            await s.commit()

    asyncio.run(run())


def test_endpoints_require_token(client):
    """Без токена/с чужим токеном — 401 везде, кроме /health и входа."""
    for path in ("/grades", "/schedule", "/subjects?name=Математика", "/auth/me"):
        assert client.get(path, headers=NO_AUTH).status_code == 401, path
        assert client.get(path, headers={"Authorization": "Bearer nope"}
                          ).status_code == 401, path
    assert client.get("/health", headers=NO_AUTH).status_code == 200
    assert client.get("/auth/config", headers=NO_AUTH).status_code == 200
    # публичного списка студентов больше нет
    assert client.get("/students", headers=NO_AUTH).status_code == 404


def test_me(client):
    me = client.get("/auth/me").json()
    assert me["code"] == "иванов иван" and me["group"] == "УЦП-25"
    assert client.get("/auth/me", headers=PETROV).json()["code"] == "петров петр"


def test_expired_session_rejected(client):
    import asyncio

    async def run():
        async with TestSession() as s:
            s.add(AuthSession(token_hash=_hash("tok-old"), student_id=client.ids[0],
                              expires_at=datetime.datetime(2000, 1, 1)))
            await s.commit()

    asyncio.run(run())
    r = client.get("/auth/me", headers={"Authorization": "Bearer tok-old"})
    assert r.status_code == 401


def test_request_password_not_configured(client, auth_env, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    r = client.post("/auth/request_password", headers=NO_AUTH,
                    json={"last_name": "Иванов", "first_name": "Иван"})
    assert r.status_code == 503


def test_password_via_telegram(client, auth_env, monkeypatch):
    """Пароль уходит боту привязанного участника группы; вход -> токен; выход."""
    from app import telegram

    sent: list[tuple[int, str]] = []
    member = {"ok": True}

    async def fake_member(uid):
        return member["ok"]

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(telegram, "is_group_member", fake_member)
    monkeypatch.setattr(telegram, "send_message", fake_send)
    _set_tg(client.ids[0], 555)
    try:
        body = {"last_name": "иванов", "first_name": " Иван "}
        r = client.post("/auth/request_password", json=body, headers=NO_AUTH)
        assert r.json() == {"sent": True, "dev_password": None}
        assert len(sent) == 1 and sent[0][0] == 555
        password = re.search(r"\b(\d{6})\b", sent[0][1]).group(1)

        # повтор в пределах cooldown — без второго сообщения
        client.post("/auth/request_password", json=body, headers=NO_AUTH)
        assert len(sent) == 1

        r = client.post("/auth/login", headers=NO_AUTH,
                        json={**body, "password": password})
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["student"]["code"] == "иванов иван"
        hdr = {"Authorization": f"Bearer {token}"}
        assert client.get("/grades", headers=hdr).json()[0]["value"] == "5"

        # пароль одноразовый
        r = client.post("/auth/login", headers=NO_AUTH,
                        json={**body, "password": password})
        assert r.status_code == 400

        assert client.post("/auth/logout", headers=hdr).status_code == 204
        assert client.get("/auth/me", headers=hdr).status_code == 401
    finally:
        _set_tg(client.ids[0], None)


def test_request_password_does_not_leak(client, auth_env, monkeypatch):
    """Неизвестное ФИО / не привязан / не в группе — одинаковый ответ, без отправки."""
    from app import telegram

    sent = []

    async def not_member(uid):
        return False

    async def fake_send(chat_id, text):
        sent.append(chat_id)

    monkeypatch.setattr(telegram, "is_group_member", not_member)
    monkeypatch.setattr(telegram, "send_message", fake_send)
    _set_tg(client.ids[0], 555)
    try:
        for body in ({"last_name": "Нет", "first_name": "Такого"},
                     {"last_name": "Петров", "first_name": "Петр"},  # не привязан
                     {"last_name": "Иванов", "first_name": "Иван"}):  # не в группе
            r = client.post("/auth/request_password", json=body, headers=NO_AUTH)
            assert r.json() == {"sent": True, "dev_password": None}
        assert sent == []
    finally:
        _set_tg(client.ids[0], None)


def test_request_password_telegram_down(client, auth_env, monkeypatch):
    from app import telegram

    async def boom(uid):
        raise telegram.TelegramError("сеть: ConnectError")

    monkeypatch.setattr(telegram, "is_group_member", boom)
    _set_tg(client.ids[0], 555)
    try:
        r = client.post("/auth/request_password", headers=NO_AUTH,
                        json={"last_name": "Иванов", "first_name": "Иван"})
        assert r.status_code == 502
        assert "t" not in r.json()["detail"].split()  # токен не утекает
    finally:
        _set_tg(client.ids[0], None)


def test_dev_mode_flow_and_attempt_limit(client, auth_env, monkeypatch):
    """AUTH_DEV_MODE: пароль в ответе; 5 неверных вводов сжигают пароль."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    assert client.get("/auth/config", headers=NO_AUTH).json()["dev_mode"] is True
    body = {"last_name": "Петров", "first_name": "Петр"}
    r = client.post("/auth/request_password", json=body, headers=NO_AUTH)
    password = r.json()["dev_password"]
    assert len(password) == 6 and password.isdigit()
    wrong = "000000" if password != "000000" else "111111"
    for _ in range(auth_env._PASSWORD_MAX_ATTEMPTS):
        assert client.post("/auth/login", headers=NO_AUTH,
                           json={**body, "password": wrong}).status_code == 400
    # даже верный пароль уже сгорел
    assert client.post("/auth/login", headers=NO_AUTH,
                       json={**body, "password": password}).status_code == 400
    r = client.post("/auth/request_password", json=body, headers=NO_AUTH)
    r = client.post("/auth/login", headers=NO_AUTH,
                    json={**body, "password": r.json()["dev_password"]})
    assert r.status_code == 200 and r.json()["student"]["code"] == "петров петр"


def test_dev_mode_off_when_bot_configured(auth_env, monkeypatch):
    """AUTH_DEV_MODE игнорируется при настоящем боте (пароль не утечёт в ответ)."""
    monkeypatch.setenv("AUTH_DEV_MODE", "1")
    assert not auth_env.dev_mode()


# --- Бот: привязка Telegram-аккаунта к студенту ---

def _bot_db():
    """Отдельная БД: Иванов (свободен), Петров (привязан к tg 900)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    eng = create_async_engine("sqlite+aiosqlite://")
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def init():
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with S() as s:
            s.add(Group(name="УЦП-25"))
            await s.flush()
            gid = (await s.execute(select(Group))).scalar_one().id
            s.add_all([
                Student(group_id=gid, code="иванов иван", last_name="Иванов",
                        first_name="Иван", full_name="Иванов Иван"),
                Student(group_id=gid, code="петров пётр", last_name="Петров",
                        first_name="Пётр", full_name="Петров Пётр",
                        telegram_user_id=900, telegram_username="@petrov"),
            ])
            await s.commit()

    return eng, S, init


def test_bot_binding(monkeypatch):
    import asyncio

    from app import bot, telegram

    members = {100, 200, 900}

    async def fake_member(uid):
        return uid in members

    monkeypatch.setattr(telegram, "is_group_member", fake_member)
    bot._bind_hits.clear()
    eng, S, init = _bot_db()

    async def say(uid, text, chat="private", username="nick"):
        async with S() as s:
            return await bot.handle_message(s, user_id=uid, username=username,
                                            chat_type=chat, text=text)

    async def run():
        await init()
        assert await say(100, "Иванов Иван", chat="supergroup") is None
        assert await say(300, "/start") == bot.NOT_MEMBER
        assert await say(100, "/start") == bot.ASK_NAME
        assert await say(100, "Иванов") == bot.ASK_NAME
        assert "Не нашёл" in await say(100, "Сидоров Сидор")
        # занятое ФИО (ё/е не важны) — отказ
        assert "уже привязан" in await say(200, "петров петр")
        # привязка, регистр и пробелы не важны
        assert "Готово" in await say(100, "  иванов   ИВАН ")
        async with S() as s:
            st = (await s.execute(select(Student).where(
                Student.code == "иванов иван"))).scalar_one()
            assert (st.telegram_user_id, st.telegram_username) == (100, "@nick")
        # привязанный аккаунт второе ФИО не занимает
        assert "привязан к студенту Иванов Иван" in await say(100, "Петров Пётр")
        # смена ника обновляется
        await say(100, "/start", username="newnick")
        async with S() as s:
            st = (await s.execute(select(Student).where(
                Student.telegram_user_id == 100))).scalar_one()
            assert st.telegram_username == "@newnick"
        await eng.dispose()

    asyncio.run(run())


def test_bot_bind_attempt_limit(monkeypatch):
    import asyncio

    from app import bot, telegram

    async def member(uid):
        return True

    monkeypatch.setattr(telegram, "is_group_member", member)
    bot._bind_hits.clear()
    eng, S, init = _bot_db()

    async def run():
        await init()
        async with S() as s:
            for _ in range(bot._BIND_ATTEMPTS):
                await bot.handle_message(s, user_id=1, username=None,
                                         chat_type="private", text="Нет Такого")
            r = await bot.handle_message(s, user_id=1, username=None,
                                         chat_type="private", text="Иванов Иван")
        assert "Слишком много" in r
        await eng.dispose()

    asyncio.run(run())
    bot._bind_hits.clear()


def test_admin_unbind(monkeypatch):
    import asyncio

    from app import admin

    eng, S, init = _bot_db()
    monkeypatch.setattr(admin, "SessionLocal", S)

    async def run():
        await init()
        async with S() as s:
            pid = (await s.execute(select(Student).where(
                Student.telegram_user_id == 900))).scalar_one().id
            s.add(AuthSession(token_hash="h", student_id=pid, expires_at=FAR_FUTURE))
            await s.commit()
        assert await admin.unbind("Петров Петр") == 0
        assert await admin.unbind("Нет Такого") == 1
        async with S() as s:
            st = await s.get(Student, pid)
            assert st.telegram_user_id is None and st.telegram_username is None
            assert (await s.execute(select(AuthSession))).first() is None
        await eng.dispose()

    asyncio.run(run())


def test_is_group_member_errors(monkeypatch):
    """«user not found» — не участник; «chat not found» — ошибка конфигурации."""
    import asyncio

    from app import telegram

    def fake(desc):
        async def call(method, **kw):
            raise telegram.TelegramError(desc)
        return call

    monkeypatch.setattr(telegram, "call", fake("Bad Request: user not found"))
    assert asyncio.run(telegram.is_group_member(1)) is False
    monkeypatch.setattr(telegram, "call", fake("Bad Request: chat not found"))
    with pytest.raises(telegram.TelegramError):
        asyncio.run(telegram.is_group_member(1))

    async def left(method, **kw):
        return {"status": "left"}

    async def restricted(method, **kw):
        return {"status": "restricted", "is_member": True}

    monkeypatch.setattr(telegram, "call", left)
    assert asyncio.run(telegram.is_group_member(1)) is False
    monkeypatch.setattr(telegram, "call", restricted)
    assert asyncio.run(telegram.is_group_member(1)) is True
