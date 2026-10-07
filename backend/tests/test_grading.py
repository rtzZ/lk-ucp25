"""Официальная шкала оценивания: границы, разбор ведомости, статусы, расхождения."""

import pytest

from app.grading import BANDS, band, interpret, mismatch, parse_value


@pytest.mark.parametrize("score,ects,five,passed", [
    (100, "A", 5, True), (95, "A", 5, True), (94, "B", 5, True), (85, "B", 5, True),
    (84, "C", 4, True), (75, "C", 4, True), (74, "D", 4, True), (65, "D", 4, True),
    (64, "E", 3, True), (55, "E", 3, True), (54, "F", 2, False), (0, "F", 2, False),
    (92.5, "B", 5, True), (54.9, "F", 2, False),
])
def test_band_edges(score, ects, five, passed):
    b = band(score)
    assert (b.ects, b.five, b.passed) == (ects, five, passed)


def test_band_out_of_range():
    assert band(None) is None and band(-1) is None and band(100.5) is None


def test_bands_cover_0_100_without_gaps():
    covered = sorted(x for b in BANDS for x in range(b.lo, b.hi + 1))
    assert covered == list(range(0, 101))


@pytest.mark.parametrize("raw,expected", [
    ("5", (5, True)), ("Отлично", (5, True)), ("отл.", (5, True)),
    ("4", (4, True)), ("хорошо", (4, True)),
    ("удов-но", (3, True)), ("Удовлетворительно", (3, True)),
    ("2", (2, False)), ("неудов-но", (2, False)),
    ("зачтено", (None, True)), ("Зачтено", (None, True)),
    ("не зачтено", (None, False)), ("незачтено", (None, False)),
    ("", (None, None)), ("88", (None, None)),
])
def test_parse_value(raw, expected):
    assert parse_value(raw) == expected


def test_interpret_final_word_grade_counts_as_five():
    r = interpret("Отлично", "B", 89.0, semester_closed=True)
    assert (r["status"], r["five"], r["label"], r["ects_letter"], r["ects_source"]) == (
        "final", 5, "Отлично", "B", "sheet")
    assert r["mismatch"] == ""


def test_interpret_pass_gets_ects_from_score():
    r = interpret("зачтено", "Passed", 70.0, semester_closed=True)
    assert (r["passed"], r["label"], r["ects_letter"], r["ects_source"]) == (
        True, "Зачтено", "D", "score")


def test_interpret_provisional_and_in_progress():
    p = interpret("", "", 89.0, semester_closed=True)
    assert (p["status"], p["five"], p["label"], p["ects_letter"]) == (
        "provisional", 5, "Отлично", "B")
    g = interpret("", "", 20.0, semester_closed=False)
    assert (g["status"], g["five"], g["ects_letter"]) == ("in_progress", None, "")
    assert interpret("", "", None, semester_closed=True)["status"] == "none"


@pytest.mark.parametrize("value,ects,score,expect", [
    ("4", "", 0.0, "по шкале — 2"),          # реальный случай из ведомости
    ("5", "A", 55.0, "по шкале — 3"),
    ("Отлично", "A", 92.0, "ECTS «A», а 92 баллов по шкале — B"),
    ("зачтено", "", 40.0, "не зачтено"),
    ("5", "A", 96.0, ""),                     # согласовано
    ("зачтено", "Passed", 55.0, ""),
    ("5", "A", None, ""),                     # без баллов не проверить
])
def test_mismatch(value, ects, score, expect):
    m = mismatch(value, ects, score)
    assert (expect in m) if expect else m == ""
