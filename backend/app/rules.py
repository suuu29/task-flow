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
    """제목·상태·우선순위·마감일 규칙 위반 (API-SPEC 2절, API-SPEC-CHANGE 7.6)."""


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
    # 세 값 중 하나여야 한다. 지울 수 없으므로 None 도 거부한다. (R-009)
    try:
        return Priority(priority)
    except ValueError:
        raise RuleError("우선순위는 LOW, NORMAL, HIGH 중 하나여야 합니다.") from None


MAX_TOPIC_LENGTH = 200  # 너무 긴 입력으로 모델 호출 비용이 커지는 것을 막는다.


def validate_topic(topic: object) -> str:
    # 필수이고 공백만 있으면 거부한다. 앞뒤 공백은 지운다.
    if not isinstance(topic, str) or not topic.strip():
        raise RuleError("주제는 비워 둘 수 없습니다.")
    value = topic.strip()
    if len(value) > MAX_TOPIC_LENGTH:
        raise RuleError(f"주제는 {MAX_TOPIC_LENGTH}자 이하여야 합니다.")
    return value


MAX_COMMAND_LENGTH = 200  # 너무 긴 입력으로 모델 호출 비용이 커지는 것을 막는다.


def validate_command(text: object) -> str:
    # 필수이고 공백만 있으면 거부한다. 앞뒤 공백은 지운다.
    if not isinstance(text, str) or not text.strip():
        raise RuleError("문장은 비워 둘 수 없습니다.")
    value = text.strip()
    if len(value) > MAX_COMMAND_LENGTH:
        raise RuleError(f"문장은 {MAX_COMMAND_LENGTH}자 이하여야 합니다.")
    return value


_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def validate_due_date(due_date: object) -> str | None:
    # 선택이다. None 은 마감일 없음이다. 값이 있으면 실제로 있는 YYYY-MM-DD 날짜여야 한다. (R-010)
    # 지난 날짜도 쓸 수 있다. 시각은 받지 않는다.
    if due_date is None:
        return None
    if not isinstance(due_date, str) or not _DATE.fullmatch(due_date):
        raise RuleError("마감일은 YYYY-MM-DD 형식의 날짜여야 합니다.")
    try:
        date.fromisoformat(due_date)
    except ValueError:
        raise RuleError("마감일은 YYYY-MM-DD 형식의 날짜여야 합니다.") from None
    return due_date


def today() -> date:
    # 기한 초과의 "오늘"은 서버를 실행하는 컴퓨터의 날짜이다. (#19 결정)
    return date.today()


def is_overdue(due_date: str | None, status: object, today_: date) -> bool:
    # 마감일이 오늘보다 이전이고 완료가 아니면 기한 초과이다. 마감일이 없으면 아니다. (R-011)
    # 저장된 마감일은 YYYY-MM-DD 이므로 문자열 비교가 날짜 비교와 같다.
    return due_date is not None and status != Status.DONE and due_date < today_.isoformat()


_PRIORITY_ORDER = {Priority.HIGH: 0, Priority.NORMAL: 1, Priority.LOW: 2}


def sort_key(task_id: int, priority: object, due_date: str | None, overdue: bool) -> tuple:
    # 기한 초과 → 우선순위(HIGH 먼저) → 마감일(없으면 맨 뒤, 오래된 마감 먼저) → 만든 순서(id). (R-012)
    return (not overdue, _PRIORITY_ORDER[priority], due_date is None, due_date or "", task_id)


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
