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
    """Запрос временного пароля: фамилия + имя как в ведомости."""

    last_name: str
    first_name: str


class PasswordLoginIn(LoginIn):
    """Вход: ФИО + временный пароль из Telegram."""

    password: str


class RequestPasswordOut(BaseModel):
    """Ответ одинаков для всех ФИО (не раскрывает состав группы).

    dev_password — только в AUTH_DEV_MODE (разработка/E2E).
    """

    sent: bool
    dev_password: str | None = None


class TokenOut(BaseModel):
    """Токен сессии (Authorization: Bearer) и студент."""

    token: str
    student: StudentOut


class AuthConfigOut(BaseModel):
    """Настройки экрана входа."""

    telegram: bool
    bot_username: str
    dev_mode: bool
    group: str  # подпись экрана входа (LK_GROUP)


class SubjectDescription(BaseModel):
    """Описание предмета из Figma-макета: абзац + списки навыков и содержания."""

    about: str = ""
    skills_title: str | None = None
    skills: list[str] = []
    content_title: str | None = None
    content: list[str] = []


class SubjectOut(BaseModel):
    """Предмет с описанием (пустое — нет в макете)."""

    id: int
    name: str
    description: SubjectDescription = SubjectDescription()


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
    description: SubjectDescription = SubjectDescription()


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
