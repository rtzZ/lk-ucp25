"""Тонкий клиент Telegram Bot API.

Токен бота входит в URL запроса, поэтому наружу (в логи, в ответы API)
не уходят ни URL, ни текст исключений httpx — только TelegramError
с безопасным описанием.
"""

import os

import httpx

API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    """Ошибка Bot API или сети (без токена в тексте)."""


def bot_token() -> str:
    """Токен читается лениво, чтобы тесты могли подменять окружение."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def group_id() -> int:
    """ID группы курса: членство в ней — условие привязки и входа."""
    try:
        return int(os.getenv("TELEGRAM_GROUP_ID", "0"))
    except ValueError:
        return 0


def configured() -> bool:
    """Бот настроен: есть токен и группа курса."""
    return bool(bot_token()) and group_id() != 0


async def call(method: str, http_timeout: float = 10, **params):
    """Вызов метода Bot API -> поле result. Ошибки — TelegramError.

    http_timeout — таймаут HTTP (у getUpdates свой параметр `timeout`).
    """
    url = f"{API_BASE}/bot{bot_token()}/{method}"
    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            resp = await client.post(url, json=params)
            data = resp.json()
    except httpx.HTTPError as e:
        raise TelegramError(f"сеть: {type(e).__name__}") from None
    except ValueError:
        raise TelegramError("невалидный ответ Bot API") from None
    if not data.get("ok"):
        raise TelegramError(str(data.get("description", "unknown")))
    return data.get("result")


async def is_group_member(user_id: int) -> bool:
    """Состоит ли пользователь в группе курса (ушедшие/кикнутые — нет)."""
    try:
        member = await call("getChatMember", chat_id=group_id(), user_id=user_id)
    except TelegramError as e:
        # «user not found» — не участник. «chat not found» (неверный
        # TELEGRAM_GROUP_ID / бота нет в группе) — ошибка конфигурации,
        # пробрасываем: иначе всем молча отказывали бы как не-участникам.
        text = str(e).lower()
        if "user not found" in text or "participant_id_invalid" in text:
            return False
        raise
    status = (member or {}).get("status")
    if status == "restricted":
        return bool(member.get("is_member"))
    return status in ("member", "administrator", "creator")


async def send_message(chat_id: int, text: str) -> None:
    """Личное сообщение (бот может писать только тем, кто нажал /start)."""
    await call("sendMessage", chat_id=chat_id, text=text)
