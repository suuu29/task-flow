import os
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db
from app.schemas import TaskCreate, User
from app.tasks import create_task, list_tasks


def add_user(name: str) -> User:
    conn = connect()
    try:
        with conn:
            uid = conn.execute("INSERT INTO users (username) VALUES (?)", (name,)).lastrowid
    finally:
        conn.close()
    return User(id=uid, username=name)


def add_raw_task(owner: User, title: str, priority: str) -> int:
    # API 검증을 거치지 않고 DB에 직접 넣는다. 규칙 밖 값이 든 행을 만들기 위해서이다.
    conn = connect()
    try:
        with conn:
            return conn.execute(
                "INSERT INTO tasks (title, description, status, owner_id, priority, due_date)"
                " VALUES (?, '', 'TODO', ?, ?, NULL)",
                (title, owner.id, priority),
            ).lastrowid
    finally:
        conn.close()


class PriorityReadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("TASKFLOW_DB")
        os.environ["TASKFLOW_DB"] = str(Path(self._tmp.name) / "test.db")
        init_db()
        self.me = add_user("me@test.com")
        self.other = add_user("other@test.com")

    def tearDown(self):
        if self._old is None:
            del os.environ["TASKFLOW_DB"]
        else:
            os.environ["TASKFLOW_DB"] = self._old
        self._tmp.cleanup()

    def test_list_survives_bad_priority_row(self):
        create_task(TaskCreate(title="보통"), user=self.me)
        create_task(TaskCreate(title="급한 일", priority="HIGH"), user=self.me)
        add_raw_task(self.me, "규칙 밖", "URGENT")
        add_raw_task(self.other, "남의 일", "NORMAL")

        tasks = list_tasks(user=self.me)

        self.assertEqual([t.title for t in tasks], ["급한 일", "보통"])

    def test_bad_row_is_skipped_not_deleted(self):
        bad_id = add_raw_task(self.me, "규칙 밖", "URGENT")

        self.assertEqual(list_tasks(user=self.me), [])

        conn = connect()
        try:
            row = conn.execute("SELECT priority FROM tasks WHERE id = ?", (bad_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["priority"], "URGENT")


if __name__ == "__main__":
    unittest.main()
