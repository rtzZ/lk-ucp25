"""CLI администратора: привязки Telegram.

  python -m app.admin bindings                  — список привязок
  python -m app.admin unbind "Фамилия Имя"      — снять привязку и сессии

Снятие нужно, если ФИО занял чужой аккаунт или студент сменил Telegram:
после него студент заново пишет боту /start.
"""

import asyncio
import sys

from sqlalchemy import delete, select

from .db import SessionLocal
from .models import AuthSession, Student
from .sync import norm_name


async def bindings() -> None:
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Student).where(Student.telegram_user_id.is_not(None))
            .order_by(Student.last_name, Student.first_name)
        )).scalars().all()
    for st in rows:
        print(f"{st.last_name} {st.first_name}\t{st.telegram_username or '-'}"
              f"\t{st.telegram_user_id}")
    print(f"Всего: {len(rows)}")


async def unbind(name: str) -> int:
    want = norm_name(name).replace("ё", "е")
    async with SessionLocal() as session:
        student = next(
            (st for st in (await session.execute(select(Student))).scalars()
             if st.code.replace("ё", "е") == want), None)
        if student is None:
            print(f"Студент {name!r} не найден", file=sys.stderr)
            return 1
        student.telegram_user_id = None
        student.telegram_username = None
        await session.execute(
            delete(AuthSession).where(AuthSession.student_id == student.id))
        await session.commit()
    print(f"Привязка снята: {student.last_name} {student.first_name}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] == "bindings":
        asyncio.run(bindings())
        return 0
    if len(argv) == 2 and argv[0] == "unbind":
        return asyncio.run(unbind(argv[1]))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
