# Электронный кабинет студента

Адаптивное веб-приложение (mobile-first): расписание занятий и оценки.
Данные не вводятся вручную — каждые 2 дня синхронизируются из двух
публичных таблиц Яндекс.Диска. Подробности: [ARCHITECTURE.md](ARCHITECTURE.md),
эндпоинты: [API.md](API.md).

## Структура

```
backend/            FastAPI (Python 3.12): API, парсер таблиц, планировщик
  app/
    main.py         точка входа, lifespan (таблицы, сид, планировщик)
    db.py           AsyncEngine (asyncpg) + сессии
    models.py       Group, Student, Subject, Grade, ScheduleItem
    sync.py         скачивание XLSX + парсинг + upsert
    seed.py         демо-данные (SEED_DEMO=1)
    schemas.py      Pydantic-схемы ответов
    routers/        auth, students, schedule, grades
    logging.py      JSON-логирование (loguru)
  tests/            pytest: test_sync.py, test_api.py
frontend/           Vite + React 18 + TypeScript + Atlassian Design System
  src/              App, api-клиент, экраны Login/Schedule/Grades
  e2e/              Playwright-тесты (cabinet.spec.ts)
docker-compose.yml  PostgreSQL 16 для продакшена
.env.example        переменные окружения (включая публичные ссылки на таблицы)
```

## Быстрый старт (Windows)

Нужны: Python 3.12 (`py`), Node.js 24. Важно: команды `npm`/`npx`
запускать как `npm.cmd`/`npx.cmd` (иначе блокирует ExecutionPolicy),
Python — через `py -m`.

```powershell
# Backend
cd backend
py -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
$env:DATABASE_URL = "sqlite+aiosqlite:///./lk-dev.db"
$env:SEED_DEMO = "1"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8001
# -> http://localhost:8001/health, документация: /docs

# Frontend (второе окно)
cd frontend
npm.cmd install
$env:VITE_API_URL = "http://localhost:8001"
npm.cmd run dev
# -> http://localhost:5173 (демо-вход: Иванов / Иван)
```

> Порт 8000 на dev-машине занят другим сервисом — backend поднимаем на **8001**.
> Без `SEED_DEMO=1` база пустая (Postgres поднимается через `docker-compose up -d`,
> синхронизация наполнит данными при наличии ссылок в окружении).

## Проверки

```powershell
cd backend; .\.venv\Scripts\python -m pytest tests/ -q   # 30 тестов
cd frontend; npx.cmd --no-install tsc --noEmit           # типы
npx.cmd --no-install vite build                          # сборка
npm.cmd run test:e2e   # E2E (нужны запущенные backend SEED_DEMO=1 + frontend dev)
```

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://lk:lk@localhost:5432/lk` | Строка подключения (sqlite для разработки) |
| `YANDEX_SCHEDULE_URL` | — | Edit-ссылка таблицы расписания |
| `YANDEX_GRADES_URL` | — | Edit-ссылка таблицы успеваемости |
| `SYNC_INTERVAL_HOURS` | `48` | Период фоновой синхронизации |
| `SEED_DEMO` | — | `1` — загрузить демо-данные при старте |
| `SKIP_DB_INIT` | — | `1` — пропустить create_all (нужно тестам) |
| `FRONTEND_URL` | `http://localhost:5173` | CORS-origin фронтенда |
| `VITE_API_URL` | `http://localhost:8000` | Адрес API для фронтенда |
| `LOG_LEVEL` | `INFO` | Уровень логов |
