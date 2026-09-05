"""Pydantic-схемы ответов API."""

from pydantic import BaseModel


class StudentOut(BaseModel):
    """Студент с именем группы."""

    id: int
    group: str
    code: str
    last_name: str
    first_name: str
    full_name: str


class LoginIn(BaseModel):
    """Вход — по фамилии (+имя для точности). Пароля нет: данные общие,
    вход нужен лишь чтобы подсветить свои оценки и расписание."""

    last_name: str
    first_name: str = ""


class LoginOut(BaseModel):
    """Успешный вход либо подсказки-однофамильцы при неточном вводе."""

    student: StudentOut | None = None
    suggestions: list[StudentOut] = []


class GradeOut(BaseModel):
    """Итоговая оценка с названием предмета."""

    id: int
    subject: str
    semester: str
    attestation: str
    value: str
    verbal: str
    ects: str
    score: float | None


class ScheduleItemOut(BaseModel):
    """Запись расписания на конкретную дату."""

    id: int
    group: str
    date: str
    time_start: str
    time_end: str
    subject_text: str
    teacher: str
    org: str
    lesson_no: int | None
    kind: str
    status: str
    note: str
    link: str
