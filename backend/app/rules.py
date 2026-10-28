import re
from datetime import date
from enum import StrEnum


class Status(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class RuleError(ValueError):
    """제목·상태 규칙 위반 (API-SPEC 2절의 제목 규칙 위반, 상태 값 위반)."""


# 카드 규칙은 한 곳에 두고 등록과 수정이 함께 쓴다. (D-006)
def validate_title(title: object) -> str:
    # 필수이고 공백만 있으면 거부한다. 저장할 때 앞뒤 공백은 지운다. (D-009, D-010)
    if not isinstance(title, str) or not title.strip():
        raise RuleError("제목은 비워 둘 수 없습니다.")
    return title.strip()


def validate_description(description: object) -> str:
    # 선택이다. 없으면 빈 문자열로 저장한다. (D-011)
    if description is None:
        return ""
    if not isinstance(description, str):
        raise RuleError("설명은 문자열이어야 합니다.")
    return description


def validate_status(status: object) -> Status:
    try:
        return Status(status)
    except ValueError:
        raise RuleError("상태는 TODO, IN_PROGRESS, DONE 중 하나여야 합니다.") from None


def validate_priority(priority: object) -> Priority:
    try:
        return Priority(priority)
    except ValueError:
        raise RuleError("우선순위는 LOW, NORMAL, HIGH 중 하나여야 합니다.") from None


_DUE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_due_date(due_date: object) -> str | None:
    # YYYY-MM-DD 이고 실제 있는 날짜이거나 null 이다.
    if due_date is None:
        return None
    if not isinstance(due_date, str) or not _DUE_DATE.match(due_date):
        raise RuleError("마감일은 YYYY-MM-DD 형식이거나 null 이어야 합니다.")
    try:
        date.fromisoformat(due_date)
    except ValueError:
        raise RuleError("마감일은 실제 있는 날짜여야 합니다.") from None
    return due_date


# 계정 규칙. 값 검사는 여기 한 곳에서 한다. (D-006)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128  # 너무 긴 입력으로 해시 계산이 오래 걸리는 것을 막는다.


def validate_username(username: object) -> str:
    # 아이디는 이메일 형식이다. 앞뒤 공백을 지우고 소문자로 맞춰 저장한다.
    if not isinstance(username, str):
        raise RuleError("아이디는 이메일 형식이어야 합니다.")
    value = username.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value):
        raise RuleError("아이디는 이메일 형식이어야 합니다.")
    return value


def validate_password(password: object) -> str:
    if not isinstance(password, str) or not (
        MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH
    ):
        raise RuleError(
            f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상 {MAX_PASSWORD_LENGTH}자 이하여야 합니다."
        )
    return password
