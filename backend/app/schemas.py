from typing import Any

from pydantic import BaseModel

from app.rules import Priority, Status


class TaskCreate(BaseModel):
    # 값 검사는 rules.py 한 곳에서 한다. (D-006) 여기서는 받기만 한다.
    title: Any = None
    description: Any = None


class TaskUpdate(BaseModel):
    # 보낸 필드만 고친다. 상태는 받지 않는다. (상태 변경은 별도 요청)
    title: Any = None
    description: Any = None


class StatusChange(BaseModel):
    status: Any = None


class Task(BaseModel):
    id: int
    title: str
    description: str
    status: Status


class SuggestRequest(BaseModel):
    # 값 검사는 rules.py 한 곳에서 한다. (D-006)
    title: Any = None
    description: Any = None


class Suggestion(BaseModel):
    priority: Priority
    due_date: str | None
    reason: str


class Credentials(BaseModel):
    # 값 검사는 rules.py 한 곳에서 한다. 여기서는 받기만 한다.
    username: Any = None
    password: Any = None


class User(BaseModel):
    # 응답에는 비밀번호와 해시를 담지 않는다.
    id: int
    username: str
