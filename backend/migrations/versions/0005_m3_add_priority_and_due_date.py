"""m3 add priority and due_date to tasks

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27 10:00:00.000000

BUSINESS-RULES.md 1~2절, DATA-MODEL.md 2.7~2.8 (#19, R-009 · R-010).
tasks 에 priority(NOT NULL, 기본값 NORMAL)와 due_date(비울 수 있음)를 더한다.
이미 있는 Task 는 NORMAL, 마감일 없음이 된다.
SQLite 의 ADD COLUMN 은 기존 행과 owner_id 의 NOT NULL · 외래 키 · AUTOINCREMENT 를 그대로 둔다.
값 제한은 두지 않는다. API 검증(rules.py)만으로 막는다. (D-018)
"""
from typing import Sequence, Union

from alembic import op

from migrations.m2_common import DOWNGRADE_MESSAGE, columns, require, snapshot

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 0004 까지 끝난 구조(owner_id 있음)에서만 실행한다. 이미 새 열이 있으면 멈춘다.
    before_cols = columns(conn, "tasks")
    require("owner_id" in before_cols, "owner_id 가 없는 구조다. 0004 까지 먼저 이전해야 한다.")
    require(
        "priority" not in before_cols and "due_date" not in before_cols,
        "priority 또는 due_date 열이 이미 있다.",
    )

    before = snapshot(conn)
    before_owners = conn.exec_driver_sql("SELECT id, owner_id FROM tasks ORDER BY id").fetchall()

    # app/db.py 의 init_db 와 같은 정의이다. (test_migrations 가 최종 구조가 같은지 비교한다)
    conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'NORMAL'")
    conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN due_date TEXT")

    # 확인: 기존 값 보존, 새 열의 기본값, 구조, 외래 키 검사 0건.
    require(snapshot(conn) == before, "0005 뒤 Task 의 수 · id · 값이 달라졌다.")
    after_owners = conn.exec_driver_sql("SELECT id, owner_id FROM tasks ORDER BY id").fetchall()
    require(after_owners == before_owners, "0005 뒤 Task 의 주인이 달라졌다.")
    not_normal = conn.exec_driver_sql("SELECT COUNT(*) FROM tasks WHERE priority != 'NORMAL'").scalar()
    require(not_normal == 0, "기존 Task 의 priority 가 NORMAL 이 아니다.")
    has_due = conn.exec_driver_sql("SELECT COUNT(*) FROM tasks WHERE due_date IS NOT NULL").scalar()
    require(has_due == 0, "기존 Task 에 마감일이 생겼다.")
    after_cols = columns(conn, "tasks")
    require(after_cols["owner_id"][1] == 1, "0005 뒤 owner_id 가 NOT NULL 이 아니다.")
    require(after_cols["priority"][1] == 1, "priority 가 NOT NULL 이 아니다.")
    require(after_cols["due_date"][1] == 0, "due_date 가 비울 수 있는 열이 아니다.")
    violations = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    require(not violations, f"외래 키 검사에서 위반 {len(violations)}건이 나왔다.")


def downgrade() -> None:
    raise NotImplementedError(DOWNGRADE_MESSAGE)
