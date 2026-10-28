"""alembic 이전(0001~0005)을 임시 복사본 DB 로 연습한다. 실제 taskflow.db 는 건드리지 않는다.

DATA-MIGRATION-PLAN.md 6절 B(복사본에서 연습)와 C(수량 비교)를 자동으로 확인한다.
테스트에 쓰는 사용자와 비밀번호는 가짜 값이다.
"""
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.auth import current_user, login, signup
from app.db import MigrationRequired, connect, init_db
from app.schemas import Credentials, TaskCreate, User
from app.tasks import create_task, list_tasks
from starlette.requests import Request
from fastapi import HTTPException, Response

BACKEND = Path(__file__).resolve().parent.parent
PW = "fake-password-1"

LEGACY_TASKS = """
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL
    )
"""
LEGACY_ROWS = [
    ("첫 카드", "설명 있음", "TODO"),
    ("둘째", "", "IN_PROGRESS"),
    ("셋째 'quote' \"x\"", "줄\n바꿈", "DONE"),
    ("지울 카드", "", "TODO"),  # 마지막 id 를 지워 AUTOINCREMENT 기록이 최대 id 보다 크게 만든다
]


def make_legacy_db(path: Path, rows=LEGACY_ROWS, delete_last=True) -> list[tuple]:
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(LEGACY_TASKS)
        for r in rows:
            conn.execute("INSERT INTO tasks (title, description, status) VALUES (?, ?, ?)", r)
        if delete_last and rows:
            conn.execute("DELETE FROM tasks WHERE id = (SELECT MAX(id) FROM tasks)")
    snap = [tuple(r) for r in conn.execute("SELECT id, title, description, status FROM tasks ORDER BY id")]
    conn.close()
    return snap


def structure(path: Path) -> dict:
    # 최종 구조 비교용: 컬럼 · 외래 키 · 인덱스 이름
    conn = sqlite3.connect(path)
    try:
        out = {}
        for t in ("users", "sessions", "tasks"):
            out[t] = (
                [tuple(r[1:]) for r in conn.execute(f"PRAGMA table_info({t})")],
                [tuple(r[2:]) for r in conn.execute(f"PRAGMA foreign_key_list({t})")],
            )
        out["indexes"] = sorted(r[1] for r in conn.execute("PRAGMA index_list(tasks)") if "autoindex" not in r[1])
        return out
    finally:
        conn.close()


class MigrationBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.db = self.dir / "copy.db"
        self._old = {k: os.environ.get(k) for k in ("TASKFLOW_DB", "SESSION_SECRET")}
        os.environ["TASKFLOW_DB"] = str(self.db)
        os.environ["SESSION_SECRET"] = "fake-secret-for-test"

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def cfg(self) -> Config:
        return Config(str(BACKEND / "alembic.ini"))

    def upgrade(self, target="head"):
        with redirect_stderr(io.StringIO()):
            command.upgrade(self.cfg(), target)

    def rows(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return [tuple(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()

    def version(self):
        return self.rows("SELECT version_num FROM alembic_version")


class FullMigrationTest(MigrationBase):
    def setUp(self):
        super().setUp()
        self.before = make_legacy_db(self.db)
        self.upgrade()

    def test_version_is_head(self):
        self.assertEqual(self.version(), [("0005",)])

    def test_tasks_count_ids_and_values_unchanged(self):
        after = self.rows("SELECT id, title, description, status FROM tasks ORDER BY id")
        self.assertEqual(after, self.before)

    def test_only_migrated_account_exists_without_password(self):
        self.assertEqual(self.rows("SELECT username, password_hash FROM users"), [("migrated@test.com", None)])

    def test_all_tasks_belong_to_migrated_account(self):
        owners = self.rows(
            "SELECT DISTINCT u.username FROM tasks t JOIN users u ON u.id = t.owner_id"
        )
        self.assertEqual(owners, [("migrated@test.com",)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM tasks WHERE owner_id IS NULL"), [(0,)])

    def test_foreign_key_check_is_clean(self):
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])

    def test_final_structure_matches_a_fresh_database(self):
        fresh = self.dir / "fresh.db"
        init_db(fresh)
        self.assertEqual(structure(self.db), structure(fresh))

    def test_deleted_ids_are_not_reused(self):
        # 마지막 id(4)를 지운 DB 였다. 이전 뒤 새 Task 는 5 부터여야 한다.
        conn = connect(self.db)
        try:
            with conn:
                new_id = conn.execute(
                    "INSERT INTO tasks (title, status, owner_id) VALUES ('new', 'TODO', "
                    "(SELECT id FROM users LIMIT 1))"
                ).lastrowid
        finally:
            conn.close()
        self.assertEqual(new_id, 5)

    def test_running_again_changes_nothing(self):
        snap = self.rows("SELECT * FROM tasks ORDER BY id")
        self.upgrade()
        self.assertEqual(self.rows("SELECT * FROM tasks ORDER BY id"), snap)
        self.assertEqual(self.version(), [("0005",)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM users"), [(1,)])

    def test_app_starts_on_migrated_database(self):
        init_db()  # MigrationRequired 없이 통과하고 아무것도 바꾸지 않는다
        self.assertEqual(self.rows("SELECT COUNT(*) FROM tasks"), [(len(self.before),)])


class ClaimAfterMigrationTest(MigrationBase):
    # 6절 B: 복사본에서 가짜 비밀번호로 가입해 받고, 다른 가짜 사용자에게는 보이지 않는지 확인한다.
    def setUp(self):
        super().setUp()
        self.before = make_legacy_db(self.db)
        self.upgrade()

    def req(self, resp: Response) -> Request:
        cookie = resp.headers.getlist("set-cookie")[0].split(";")[0]
        return Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})

    def test_migrated_account_cannot_login_before_claim(self):
        with self.assertRaises(HTTPException) as cm:
            login(Credentials(username="migrated@test.com", password=PW), Response())
        self.assertEqual(cm.exception.status_code, 401)

    def test_first_signup_receives_all_existing_tasks_and_others_see_none(self):
        signup(Credentials(username="migrated@test.com", password=PW))
        resp = Response()
        login(Credentials(username="migrated@test.com", password=PW), resp)
        owner = current_user(self.req(resp))
        self.assertEqual([t.id for t in list_tasks(user=owner)], [r[0] for r in self.before])

        other = signup(Credentials(username="other@test.com", password="fake-password-2"))
        self.assertEqual(list_tasks(user=User(id=other.id, username=other.username)), [])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM tasks"), [(len(self.before),)])

    def test_new_task_after_claim_gets_next_id(self):
        user = signup(Credentials(username="migrated@test.com", password=PW))
        task = create_task(TaskCreate(title="x"), user=user)
        self.assertEqual(task.id, 5)


class StepwiseAndFailureTest(MigrationBase):
    def test_each_step_can_run_alone(self):
        before = make_legacy_db(self.db)
        for rev, expected_owners in [("0001", [(None,)]), ("0002", [(None,)]), ("0003", None)]:
            self.upgrade(rev)
            self.assertEqual(self.version(), [(rev,)])
            if expected_owners is not None:
                self.assertEqual(self.rows("SELECT DISTINCT owner_id FROM tasks"), expected_owners)
            self.assertEqual(
                self.rows("SELECT id, title, description, status FROM tasks ORDER BY id"), before
            )
        self.upgrade("0004")
        self.assertEqual(self.version(), [("0004",)])
        self.upgrade("0005")
        self.assertEqual(self.version(), [("0005",)])
        self.assertEqual(
            self.rows("SELECT id, title, description, status FROM tasks ORDER BY id"), before
        )

    def test_failed_step_changes_nothing_and_stays_at_previous_version(self):
        before = make_legacy_db(self.db)
        self.upgrade("0002")
        # 이전용 계정이 아닌 주인의 Task 가 있으면 D3 는 UPDATE 를 한 뒤 확인에서 멈춘다.
        conn = sqlite3.connect(self.db)
        with conn:
            conn.execute("INSERT INTO users (username) VALUES ('stranger@test.com')")
            conn.execute("UPDATE tasks SET owner_id = 2 WHERE id = 1")
        conn.close()
        owners_before = self.rows("SELECT id, owner_id FROM tasks ORDER BY id")

        with self.assertRaises(RuntimeError):
            self.upgrade("0003")

        # D3 의 UPDATE 가 취소되어 주인 없는 Task 도 그대로 NULL 이다.
        self.assertEqual(self.rows("SELECT id, owner_id FROM tasks ORDER BY id"), owners_before)
        self.assertEqual(self.version(), [("0002",)])
        self.assertEqual(
            self.rows("SELECT id, title, description, status FROM tasks ORDER BY id"), before
        )

    def test_d2_stops_when_a_user_already_exists(self):
        make_legacy_db(self.db)
        self.upgrade("0001")
        conn = sqlite3.connect(self.db)
        with conn:
            conn.execute("INSERT INTO users (username) VALUES ('migrated@test.com')")
        conn.close()
        with self.assertRaises(RuntimeError):
            self.upgrade("0002")
        self.assertEqual(self.rows("SELECT COUNT(*) FROM users"), [(1,)])
        self.assertEqual(self.version(), [("0001",)])

    def test_empty_legacy_database_migrates(self):
        make_legacy_db(self.db, rows=[], delete_last=False)
        self.upgrade()
        self.assertEqual(self.version(), [("0005",)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM tasks"), [(0,)])
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])

    def test_already_new_structure_is_refused_and_unchanged(self):
        init_db(self.db)
        snap = structure(self.db)
        with self.assertRaises(RuntimeError):
            self.upgrade()
        self.assertEqual(structure(self.db), snap)

    def test_database_without_tasks_is_refused(self):
        sqlite3.connect(self.db).close()
        with self.assertRaises(RuntimeError):
            self.upgrade()

    def test_app_refuses_unmigrated_database(self):
        make_legacy_db(self.db)
        with self.assertRaises(MigrationRequired):
            init_db()

    def test_downgrade_is_not_supported(self):
        make_legacy_db(self.db)
        self.upgrade()
        with self.assertRaises(NotImplementedError):
            with redirect_stderr(io.StringIO()):
                command.downgrade(self.cfg(), "0003")
        self.assertEqual(self.version(), [("0005",)])


class PriorityDueMigrationTest(MigrationBase):
    # 0005: priority(NOT NULL, 기본 NORMAL)와 due_date(비울 수 있음)를 더한다. (#19)
    def setUp(self):
        super().setUp()
        self.before = make_legacy_db(self.db)
        self.upgrade("0004")

    def test_existing_rows_get_normal_and_no_due_date_and_keep_values(self):
        old = self.rows("SELECT id, title, description, status, owner_id FROM tasks ORDER BY id")
        self.upgrade("0005")
        new = self.rows(
            "SELECT id, title, description, status, owner_id, priority, due_date FROM tasks ORDER BY id"
        )
        self.assertEqual([r[:5] for r in new], old)
        self.assertEqual({r[5] for r in new}, {"NORMAL"})
        self.assertEqual({r[6] for r in new}, {None})
        self.assertEqual(len(new), len(self.before))

    def test_new_columns_and_kept_constraints(self):
        self.upgrade("0005")
        conn = sqlite3.connect(self.db)
        try:
            cols = {r[1]: (r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info(tasks)")}
            fks = [tuple(r[2:4]) for r in conn.execute("PRAGMA foreign_key_list(tasks)")]
        finally:
            conn.close()
        self.assertEqual(cols["priority"], ("TEXT", 1, "'NORMAL'"))
        self.assertEqual(cols["due_date"], ("TEXT", 0, None))
        self.assertEqual(cols["owner_id"][1], 1)
        self.assertEqual(fks, [("users", "owner_id")])
        self.assertEqual(self.rows("PRAGMA foreign_key_check"), [])

    def test_task_without_owner_is_still_rejected(self):
        self.upgrade("0005")
        conn = connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                with conn:
                    conn.execute("INSERT INTO tasks (title, status) VALUES ('a', 'TODO')")
        finally:
            conn.close()

    def test_running_again_changes_nothing(self):
        self.upgrade("0005")
        snap = self.rows("SELECT * FROM tasks ORDER BY id")
        self.upgrade("head")
        self.assertEqual(self.rows("SELECT * FROM tasks ORDER BY id"), snap)
        self.assertEqual(self.version(), [("0005",)])

    def test_stops_when_columns_already_exist_and_changes_nothing(self):
        conn = sqlite3.connect(self.db)
        with conn:
            conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'NORMAL'")
        conn.close()
        snap = structure(self.db)
        rows = self.rows("SELECT * FROM tasks ORDER BY id")
        with self.assertRaises(RuntimeError):
            self.upgrade("0005")
        self.assertEqual(structure(self.db), snap)
        self.assertEqual(self.rows("SELECT * FROM tasks ORDER BY id"), rows)
        self.assertEqual(self.version(), [("0004",)])

    def test_app_refuses_database_without_new_columns_and_leaves_it_unchanged(self):
        snap = structure(self.db)
        with self.assertRaises(MigrationRequired):
            init_db()
        self.assertEqual(structure(self.db), snap)
        self.assertEqual(self.version(), [("0004",)])

    def test_app_starts_after_0005_and_keeps_rows(self):
        self.upgrade("0005")
        init_db()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM tasks"), [(len(self.before),)])


if __name__ == "__main__":
    unittest.main()
