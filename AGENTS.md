# Электронный кабинет студента — инструкции OpenCode

## Команды разработки (Windows)

**Backend (Python 3.12):**
```powershell
cd backend; py -m venv .venv; .\.venv\Scripts\python -m pip install -e ".[dev]"
$env:DATABASE_URL="sqlite+aiosqlite:///./lk-dev.db"; $env:SEED_DEMO="1"
.\.venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload
```

**Frontend (Node.js 24):**
```powershell
cd frontend; npm.cmd install; $env:VITE_API_URL="http://localhost:8001"; npm.cmd run dev
```

**Проверки:** `pytest tests/ -q` (backend), `npx.cmd --no-install tsc --noEmit` (frontend типы), `npm.cmd run test:e2e` (Playwright)

## Архитектурные особенности

- **Бэкенд:** FastAPI + asyncpg + APScheduler 3.x (не 4.x!), синхронизация из Яндекс.Таблиц через headless Chromium (URL извлекается из HTML edit-страницы)
- **Фронтенд:** React 18 + TypeScript + Atlaskit. StrictMode отключён (`main.tsx:5`) — иначе `@atlaskit/portal` теряет контент popup/drawer
- **Без аутентификации:** вход по ФИО (данные общие), `Student.code` = нормализованная "фамилия имя"
- **Логирование:** JSON в stderr через `loguru.serialize=True`, middleware логирует каждый HTTP-запрос
- **Порты:** backend на **8001** (8000 занят), frontend на 5173

## Данные и синхронизация

- `YANDEX_SCHEDULE_URL` и `YANDEX_GRADES_URL` в `.env` (ссылки из `.env.example`)
- APScheduler запускает `sync_all()` каждые 48 часов (`SYNC_INTERVAL_HOURS`)
- При недоступности ссылок ошибка логируется, API продолжает отдавать старые данные из БД

## Правила работы

1. **Ponytail:** перед сложной логикой (парсер, схема БД) вызывать `/ponytail`
2. **Context7:** перед использованием Atlaskit/FastAPI/SQLAlchemy — `npx ctx7@latest docs <id> "<что искать>"`
3. **Playwright MCP:** после UI-компонентов — E2E-тесты с эмуляцией мобильного (390px)
4. **Ralph Loop:** итеративно по чек-листу — не переходить к следующему шагу пока текущий не закоммичен
5. **Язык:** вся документация (README, ARCHITECTURE, API, docstrings) — на русском

## Структура проекта

```
backend/     — FastAPI (app/main.py, app/models.py, app/sync.py, app/routers/)
frontend/    — Vite + React (src/, e2e/cabinet.spec.ts)
docker-compose.yml — PostgreSQL 16
```

---

> При завершении всех задач напечатать `\a` (системный звуковой сигнал)
