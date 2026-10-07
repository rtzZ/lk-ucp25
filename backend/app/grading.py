"""Официальная шкала оценивания — единственный источник правды.

Таблица (100-балльная -> традиционная / бинарная / ECTS):

    95-100  Отлично              Зачтено     A/passed
    85-94   Отлично              Зачтено     B/passed
    75-84   Хорошо               Зачтено     C/passed
    65-74   Хорошо               Зачтено     D/passed
    55-64   Удовлетворительно    Зачтено     E/passed
    0-54    Неудовлетворительно  Не зачтено  F/failed

Ведомость — официальный документ: её значение показывается как есть,
шкала лишь достраивает недостающее (буква ECTS по баллам, предварительная
оценка) и подсвечивает противоречия (`mismatch`), ничего не исправляя.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """Строка шкалы: баллы [lo, hi] -> оценки во всех системах."""

    lo: int
    hi: int
    traditional: str
    five: int
    passed: bool
    ects: str


BANDS: tuple[Band, ...] = (
    Band(95, 100, "Отлично", 5, True, "A"),
    Band(85, 94, "Отлично", 5, True, "B"),
    Band(75, 84, "Хорошо", 4, True, "C"),
    Band(65, 74, "Хорошо", 4, True, "D"),
    Band(55, 64, "Удовлетворительно", 3, True, "E"),
    Band(0, 54, "Неудовлетворительно", 2, False, "F"),
)

TRADITIONAL = {5: "Отлично", 4: "Хорошо", 3: "Удовлетворительно", 2: "Неудовлетворительно"}

# Как пятибалльные оценки записаны в ведомостях (цифрой, словом, сокращением).
_FIVE_WORDS = {
    "5": 5, "отлично": 5, "отл": 5,
    "4": 4, "хорошо": 4, "хор": 4,
    "3": 3, "удовлетворительно": 3, "удов-но": 3, "удовл": 3, "удовлетв": 3, "уд": 3,
    "2": 2, "неудовлетворительно": 2, "неудов-но": 2, "неуд": 2, "неудовл": 2,
}
_BINARY_WORDS = {"зачтено": True, "зачет": True, "зачёт": True,
                 "не зачтено": False, "незачтено": False, "не зачет": False}


def band(score: float | None) -> Band | None:
    """Строка шкалы по баллам; None — баллов нет или они вне 0-100.

    Границы целые, дробные баллы (92.5) округляются вниз: 54.9 — ещё F.
    """
    if score is None or not 0 <= score <= 100:
        return None
    s = int(score)
    return next(b for b in BANDS if b.lo <= s <= b.hi)


def _key(text: str) -> str:
    return re.sub(r"[.\s]+$", "", " ".join(str(text or "").split()).lower())


def parse_value(value: str) -> tuple[int | None, bool | None]:
    """Оценка из ведомости -> (пятибалльная, зачтено).

    «Отлично»/«5»/«отл.» -> (5, True); «удов-но» -> (3, True);
    «не зачтено» -> (None, False); пусто/непонятно -> (None, None).
    Пятибалльная тоже даёт «зачтено» (>= 3) — как в таблице.
    """
    k = _key(value)
    if k in _FIVE_WORDS:
        five = _FIVE_WORDS[k]
        return five, five >= 3
    if k in _BINARY_WORDS:
        return None, _BINARY_WORDS[k]
    return None, None


def _sheet_letter(ects: str) -> str:
    """Буква ECTS из ведомости: «B», «b/passed» -> «B»; «Passed»/пусто -> ""."""
    m = re.match(r"^\s*([a-fA-F])\b", str(ects or ""))
    return m.group(1).upper() if m else ""


def interpret(value: str, ects: str, score: float | None,
              semester_closed: bool) -> dict:
    """Оценка из ведомости -> разобранная по официальной шкале.

    status: final (оценка есть) | provisional (семестр закрыт, оценки нет,
    но есть баллы — оценка по шкале, помечается «предварительно») |
    in_progress (семестр идёт, баллы копятся) | none.
    """
    five, passed = parse_value(value)
    b = band(score)
    letter = _sheet_letter(ects)
    ects_source = "sheet" if letter else ""
    if not letter and b is not None:
        letter, ects_source = b.ects, "score"

    if str(value or "").strip():
        status = "final"
    elif b is None:
        status = "none"
    elif semester_closed:
        status = "provisional"
        five, passed = b.five, b.passed
    else:
        status = "in_progress"

    label = TRADITIONAL.get(five, "") if five is not None else (
        "Зачтено" if passed else "Не зачтено" if passed is False else "")

    return {
        "five": five,
        "passed": passed,
        "label": label,
        "ects_letter": letter if status != "in_progress" else "",
        "ects_source": ects_source if status != "in_progress" else "",
        "status": status,
        "mismatch": mismatch(value, ects, score) if status == "final" else "",
    }


def mismatch(value: str, ects: str, score: float | None) -> str:
    """Противоречие ведомости и шкалы — текстом; "" — согласовано/не проверить."""
    b = band(score)
    if b is None:
        return ""
    s = f"{score:g}"
    five, passed = parse_value(value)
    if five is not None and five != b.five:
        return (f"В ведомости «{str(value).strip()}», а {s} баллов по шкале — "
                f"{b.five} ({b.traditional.lower()})")
    if five is None and passed is not None and passed != b.passed:
        want = "зачтено" if b.passed else "не зачтено"
        return f"В ведомости «{str(value).strip()}», а {s} баллов по шкале — {want}"
    letter = _sheet_letter(ects)
    if letter and letter != b.ects:
        return f"В ведомости ECTS «{letter}», а {s} баллов по шкале — {b.ects}"
    return ""
