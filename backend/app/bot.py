"""Telegram-бот: привязка аккаунта к студенту (long polling).

Сценарий: студент пишет боту /start -> бот проверяет членство в группе
курса (TELEGRAM_GROUP_ID) -> просит «Фамилия Имя» как в ведомости ->
если ФИО есть и ещё ни к кому не привязано, telegram_user_id записывается
в Student. После этого на сайте можно запрашивать временный пароль —
его присылает этот же бот (routers/auth.py).

Привязка — по принципу «кто первый»: перепривязать занятое ФИО может только
администратор (`python -m app.admin unbind "Фамилия Имя"`).

Polling живёт в процессе backend (один инстанс). Вебхук при старте
снимается: с ним getUpdates не работает.
"""

import asyncio
import time

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import telegram
from .db import SessionLocal
from .models import Student
from .sync import norm_name

# Попытки ввода ФИО на один Telegram-аккаунт: бот подтверждает наличие ФИО
# в ведомости, перебирать его без ограничений нельзя.
_BIND_ATTEMPTS = 10
_BIND_WINDOW_S = 3600
_bind_hits: dict[int, list[float]] = {}

ASK_NAME = ("Напишите фамилию и имя так, как они записаны в ведомости, "
            "например: Иванов Иван")
NOT_MEMBER = ("Бот работает только для участников группы курса в Telegram. "
              "Вступите в группу и напишите /start ещё раз.")


def _key(text: str) -> str:
    """Ключ сравнения ФИО: регистр, пробелы, ё->е."""
    return norm_name(text).replace("ё", "е")


def _bind_allowed(user_id: int) -> bool:
    """Лимит попыток ввода ФИО (скользящее окно, monotonic)."""
    now = time.monotonic()
    hits = [t for t in _bind_hits.get(user_id, []) if t > now - _BIND_WINDOW_S]
    if len(hits) >= _BIND_ATTEMPTS:
        _bind_hits[user_id] = hits
        return False
    hits.append(now)
    _bind_hits[user_id] = hits
    return True


def _name(st: Student) -> str:
    return f"{st.last_name} {st.first_name}".strip()


async def handle_message(session: AsyncSession, *, user_id: int,
                         username: str | None, chat_type: str,
                         text: str) -> str | None:
    """Входящее сообщение -> текст ответа (None — молчать).

    Отделено от polling'а, чтобы тестироваться без сети.
    """
    if chat_type != "private":
        return None  # в группе бот молчит
    text = (text or "").strip()
    tg_username = f"@{username}" if username else None

    bound = (await session.execute(
        select(Student).where(Student.telegram_user_id == user_id)
    )).scalars().first()
    if bound is not None:
        if bound.telegram_username != tg_username:
            await _set_username(session, bound, tg_username)
            await session.commit()
        return (f"Ваш Telegram привязан к студенту {_name(bound)}.\n"
                "Чтобы войти, введите на сайте фамилию и имя и нажмите "
                "«Получить пароль» — пароль придёт сюда.")

    if not await telegram.is_group_member(user_id):
        return NOT_MEMBER
    if text.startswith("/"):
        return ASK_NAME  # /start, /help и прочие команды

    parts = text.split()
    if len(parts) < 2:
        return ASK_NAME
    if not _bind_allowed(user_id):
        return "Слишком много попыток. Попробуйте через час."
    want = _key(f"{parts[0]} {parts[1]}")
    student = next(
        (st for st in (await session.execute(select(Student))).scalars()
         if _key(st.code) == want),
        None)
    if student is None:
        return ("Не нашёл такого студента в ведомости. Проверьте написание "
                "(сначала фамилия, потом имя).")
    if student.telegram_user_id is not None:
        logger.warning(f"Попытка занять привязанное ФИО {student.code!r} "
                       f"с tg {user_id}")
        return ("Этот студент уже привязан к другому Telegram-аккаунту. "
                "Если это ошибка — обратитесь к администратору.")
    student.telegram_user_id = user_id
    await _set_username(session, student, tg_username)
    await session.commit()
    logger.info(f"Telegram привязан: {student.code!r} -> {user_id}")
    return (f"Готово: аккаунт привязан к студенту {_name(student)}.\n"
            "Теперь на сайте введите фамилию и имя и нажмите "
            "«Получить пароль» — пароль придёт сюда.")


async def _set_username(session: AsyncSession, student: Student,
                        username: str | None) -> None:
    """username уникален: снимаем его с прежнего владельца (сменил ник)."""
    if username:
        await session.execute(
            update(Student)
            .where(Student.telegram_username == username)
            .where(Student.id != student.id)
            .values(telegram_username=None))
    student.telegram_username = username


_bot_username: str = ""


def bot_username() -> str:
    """@username бота (известен после старта polling'а) — для ссылки на сайте."""
    return _bot_username


async def run_polling() -> None:
    """Бесконечный long polling; отменяется через task.cancel()."""
    global _bot_username
    offset: int | None = None
    started = False
    while True:
        try:
            if not started:
                me = await telegram.call("getMe")
                _bot_username = (me or {}).get("username", "")
                await telegram.call("deleteWebhook")
                started = True
                logger.info(f"Telegram-бот @{_bot_username} запущен (polling)")
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            updates = await telegram.call("getUpdates", http_timeout=40, **params)
            for upd in updates or []:
                offset = upd["update_id"] + 1
                await _process_update(upd)
        except asyncio.CancelledError:
            raise
        except telegram.TelegramError as e:
            logger.warning(f"Telegram polling: {e}")
            await asyncio.sleep(5)
        except Exception:  # noqa: BLE001 — бот обязан пережить всё
            logger.exception("Telegram polling упал, повтор через 5 с")
            await asyncio.sleep(5)


async def _process_update(upd: dict) -> None:
    """Одно обновление: ошибка в нём не должна останавливать polling."""
    msg = upd.get("message") or {}
    sender = msg.get("from") or {}
    chat = msg.get("chat") or {}
    if not sender.get("id") or sender.get("is_bot") or "text" not in msg:
        return
    try:
        async with SessionLocal() as session:
            reply = await handle_message(
                session, user_id=sender["id"], username=sender.get("username"),
                chat_type=chat.get("type", ""), text=msg["text"])
        if reply:
            await telegram.send_message(chat["id"], reply)
    except Exception:  # noqa: BLE001
        logger.exception(f"Ошибка обработки сообщения от tg {sender.get('id')}")
