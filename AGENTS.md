# Электронный кабинет студента — инструкции OpenCode

## Команды разработки (Windows)

**Backend (Python 3.12):**
```powershell
cd backend; py -m venv .venv; .\.venv\Scripts\python -m pip install -e ".[dev]"
$env:DATABASE_URL="sqlite+aiosqlite:///./lk-dev.db"; $env:SEED_DEMO="1"; $env:AUTH_DEV_MODE="1"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload
```

**Frontend (Node.js 24):**
```powershell
cd frontend; npm.cmd install; $env:VITE_API_URL="http://localhost:8001"; npm.cmd run dev
```

> Windows: `npm`/`npx` запускать как `npm.cmd`/`npx.cmd` (ExecutionPolicy), Python через `py -m`.
> Порт 8000 занят — backend всегда на **8001**.

## Проверки

```powershell
# Backend (pytest auto-async: asyncio_mode = "auto" в pyproject.toml)
cd backend; .\.venv\Scripts\python -m pytest tests/ -q

# Frontend типы
cd frontend; npx.cmd --no-install tsc --noEmit

# E2E (нужны запущенные backend с SEED_DEMO=1 AUTH_DEV_MODE=1 + frontend dev-сервер)
cd frontend; npm.cmd run test:e2e
```

- `test_api.py` подменяет сессию на SQLite — **не** требует Postgres.
- `test_sync.py` — чистые функции парсера, без файлов и БД.
- E2E (`e2e/cabinet.spec.ts`): вход → расписание → оценки, desktop + mobile 390px. Playwright не поднимает серверы автоматически (`webServer: undefined`).

## Архитектурные особенности

- **Бэкенд:** FastAPI + asyncpg + APScheduler **3.x** (не 4.x! — на PyPI только альфы). Синхронизация из Яндекс.Таблиц через headless Chromium (URL из edit-страницы, подпись покрывает query целиком).
- **Фронтенд:** React 18 + TypeScript + Atlaskit. `React.StrictMode` **отключён** (`main.tsx:5`) — `@atlaskit/portal` v6 теряет контент popup/drawer при двойном монтировании в dev.
- **Авторизация:** ФИО + временный пароль от Telegram-бота (`bot.py`, привязка через /start) → Bearer-токен; все данные за `current_student`. Локально/E2E: `AUTH_DEV_MODE=1` (пароль в ответе API). `Student.code` = нормализованная "фамилия имя" (без отчества).
- **SQLAlchemy без relationships** — ленивая загрузка падает в async; только FK + явные select.
- **Таблицы через `create_all`** при старте (Aleiambic подключить при первой эволюции схемы).
- **Логирование:** JSON в stderr через `loguru.serialize=True`, middleware логирует каждый HTTP-запрос.

## Данные и синхронизация

- `YANDEX_SCHEDULE_URL` и `YANDEX_GRADES_URL` — edit-ссылки таблиц Яндекс.Диска.
- APScheduler запускает `sync_all()` дважды в сутки — в 09:30 и 11:00 МСК (`SYNC_TIMES`, `SYNC_TIMEZONE`).
- Пустые `YANDEX_*_URL` — пропуск с warning. Недоступные ссылки — ошибка в лог, API отдаёт старые данные.
- `_sync_job` глотает все исключения (планировщик обязан пережить всё).
- Пустая оценка в ведомости = «оценки ещё нет» (`value=""`), не «2».
- Синк не применяется, если данных стало < `SYNC_MIN_RATIO` (0.5) от прежнего; принудительно — `python -m app.admin sync --force`.

## Правила работы

1. **Context7:** перед использованием Atlaskit/FastAPI/SQLAlchemy — `npx ctx7@latest docs <id> "<что искать>"`
2. **Playwright MCP:** после UI-компонентов — E2E-тесты с эмуляцией мобильного (390px)
3. **Язык:** вся документация (README, ARCHITECTURE, API, docstrings) — на русском

## Структура проекта

```
backend/
  app/main.py       — точка входа, lifespan (таблицы, сид, планировщик)
  app/db.py         — AsyncEngine + get_session (зависимость FastAPI)
  app/models.py     — Group, Student, Subject, Grade, ScheduleItem
  app/sync.py       — скачивание XLSX + парсинг + upsert
  app/routers/      — auth, schedule, grades, subjects
  app/bot.py        — Telegram-бот (привязка), app/admin.py — CLI привязок
  tests/            — pytest: test_sync.py, test_api.py (sqlite)
frontend/
  src/              — App, api-клиент, экраны Login/Schedule/Grades
  e2e/cabinet.spec.ts — Playwright E2E
docker-compose.yml  — PostgreSQL 16 (для продакшена)
```

---

> При завершении всех задач напечатать `\a` (системный звуковой сигнал)
