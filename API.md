# API

База: `http://localhost:8001`. Все ответы — JSON. Ошибки: `{"detail": ...}`.
Интерактивная документация: `/docs`.

## `POST /auth/login` — вход

Вход — идентификация себя (пароля нет, данные общие).

Тело: `{"last_name": "Иванов", "first_name": "Иван"}` (имя опционально).

- `200` → `{"student": {...}, "suggestions": []}`.
- Точного совпадения нет, но фамилия единственная → `200` с этим студентом.
- `404` → `{"detail": {"message": "Студент не найден, уточните имя",
  "suggestions": [...]}}` — однофамильцы кнопками.

`Student`: `id, group, code, last_name, first_name, full_name`.

## `GET /students` — список группы

`?group=УЦП-25` (по умолчанию `УЦП-25`). Сортировка по фамилии/имени.
Используется экраном входа.

## `GET /students/{id}` — карточка

`404` — `{"detail": "Студент не найден"}`.

## `GET /schedule/groups` — группы

Имена групп, у которых есть записи расписания. `["УЦП-25", "ЛФТ-25"]`.

## `GET /schedule` — расписание

Параметры: `group` (по умолчанию `УЦП-25`), `date_from`/`date_to` (ISO
`YYYY-MM-DD`), `kind` (`lesson | attestation | event | deadline`).
Сортировка: дата, время, id.

Запись: `id, group, date, time_start, time_end, subject_text, teacher, org,
lesson_no (nullable), kind, status (active|cancelled|moved), note,
link (URL подключения, "" если нет)`.

Пример: `/schedule?group=УЦП-25&date_from=2026-02-09&date_to=2026-02-15`.

## `GET /grades` — оценки студента

Параметры: `student_id` (обязателен), `semester` (опционален, точное имя
листа, например `1 семестр 25-26`). Сортировка: семестр, предмет.

Оценка: `id, subject, semester, attestation (экзамен|зачет|зачет с оценкой|""),
value (как в ведомости: "5", "зачтено", баллы), verbal, ects, score (nullable)`.

## `GET /health`

`{"status": "ok"}`.

## Логирование

Каждый запрос пишется в stderr одной JSON-строкой (`loguru serialize=True`):

```json
{"text": "... | INFO | app.main:log_requests:54 - http_request\n",
 "record": {"extra": {"method": "GET", "path": "/health", "status": 200,
  "elapsed_ms": 35.6}, ...}}
```

Ошибки парсинга (`sync.py`) и запуски/падения фоновых задач — тем же логгером
с контекстом (`[оценки]`, `[расписание]`).
