import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import MigrationRequired, connect, init_db


def add_user(conn, name="a@test.com"):
    with conn:
        cur = conn.execute("INSERT INTO users (username) VALUES (?)", (name,))
    return cur.lastrowid


class DbPersistenceTest(unittest.TestCase):
    def test_row_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            init_db(path)

            conn = connect(path)
            uid = add_user(conn)
            with conn:
                conn.execute(
                    "INSERT INTO tasks (title, description, status, owner_id) VALUES (?, ?, ?, ?)",
                    ("제목", "설명", "TODO", uid),
                )
            conn.close()

            conn = connect(path)
            rows = conn.execute("SELECT title, description, status, owner_id FROM tasks").fetchall()
            conn.close()
            self.assertEqual([tuple(r) for r in rows], [("제목", "설명", "TODO", uid)])

    def test_init_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            init_db(path)
            conn = connect(path)
            uid = add_user(conn)
            with conn:
                conn.execute(
                    "INSERT INTO tasks (title, status, owner_id) VALUES (?, ?, ?)", ("a", "TODO", uid)
                )
            conn.close()

            init_db(path)  # 다시 불러도 기존 카드를 지우지 않는다

            conn = connect(path)
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            conn.close()
            self.assertEqual(count, 1)


class PriorityDueColumnsTest(unittest.TestCase):
    # priority(NOT NULL, 기본 NORMAL)와 due_date(비울 수 있음). 값 제한은 저장소에 없다. (D-018, #19)
    def test_defaults_and_values_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            init_db(path)
            conn = connect(path)
            uid = add_user(conn)
            with conn:
                conn.execute(
                    "INSERT INTO tasks (title, status, owner_id) VALUES ('기본', 'TODO', ?)", (uid,)
                )
                conn.execute(
                    "INSERT INTO tasks (title, status, owner_id, priority, due_date)"
                    " VALUES ('지정', 'TODO', ?, 'HIGH', '2026-10-25')",
                    (uid,),
                )
            conn.close()

            init_db(path)  # 다시 불러도 값이 그대로다
            conn = connect(path)
            rows = conn.execute("SELECT title, priority, due_date FROM tasks ORDER BY id").fetchall()
            conn.close()
            self.assertEqual(
                [tuple(r) for r in rows], [("기본", "NORMAL", None), ("지정", "HIGH", "2026-10-25")]
            )

    def test_priority_cannot_be_null_but_due_date_can(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.db"
            init_db(path)
            conn = connect(path)
            uid = add_user(conn)
            with self.assertRaises(sqlite3.IntegrityError):
                with conn:
                    conn.execute(
                        "INSERT INTO tasks (title, status, owner_id, priority) VALUES ('a', 'TODO', ?, NULL)",
                        (uid,),
                    )
            with conn:
                conn.execute(
                    "INSERT INTO tasks (title, status, owner_id, due_date) VALUES ('b', 'TODO', ?, NULL)",
                    (uid,),
                )
            conn.close()


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "test.db"
        init_db(self.path)
        self.conn = connect(self.path)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def test_tables_and_index_exist(self):
        names = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master")}
        self.assertTrue({"users", "sessions", "tasks", "idx_tasks_owner_id"} <= names)

    def test_foreign_keys_are_on(self):
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_task_with_unknown_owner_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute(
                    "INSERT INTO tasks (title, status, owner_id) VALUES ('a', 'TODO', 999)"
                )

    def test_task_without_owner_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute("INSERT INTO tasks (title, status) VALUES ('a', 'TODO')")

    def test_session_with_unknown_user_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.conn:
                self.conn.execute(
                    "INSERT INTO sessions (id, user_id, expires_at) VALUES ('s', 999, 1)"
                )

    def test_username_is_unique(self):
        add_user(self.conn, "dup@test.com")
        with self.assertRaises(sqlite3.IntegrityError):
            add_user(self.conn, "dup@test.com")


class LegacyDbTest(unittest.TestCase):
    def test_old_tasks_table_stops_without_changing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            raw = sqlite3.connect(path)
            with raw:
                raw.execute(
                    "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                    " description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL)"
                )
                raw.execute("INSERT INTO tasks (title, status) VALUES ('옛 카드', 'TODO')")
            raw.close()

            with self.assertRaises(MigrationRequired):
                init_db(path)

            raw = sqlite3.connect(path)
            tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows = raw.execute("SELECT title FROM tasks").fetchall()
            cols = [r[1] for r in raw.execute("PRAGMA table_info(tasks)")]
            raw.close()
            self.assertNotIn("users", tables)
            self.assertEqual(rows, [("옛 카드",)])
            self.assertNotIn("owner_id", cols)

    def test_tasks_table_without_priority_and_due_date_stops_without_changing_it(self):
        # 0004 까지 끝난 구조(owner_id 있음, priority · due_date 없음)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m2.db"
            raw = sqlite3.connect(path)
            with raw:
                raw.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT)")
                raw.execute("INSERT INTO users (username) VALUES ('a@test.com')")
                raw.execute(
                    "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                    " description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,"
                    " owner_id INTEGER NOT NULL REFERENCES users(id))"
                )
                raw.execute("INSERT INTO tasks (title, status, owner_id) VALUES ('카드', 'TODO', 1)")
            raw.close()

            with self.assertRaises(MigrationRequired) as cm:
                init_db(path)
            self.assertIn("priority", str(cm.exception))

            raw = sqlite3.connect(path)
            cols = [r[1] for r in raw.execute("PRAGMA table_info(tasks)")]
            tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows = raw.execute("SELECT title FROM tasks").fetchall()
            raw.close()
            self.assertEqual(cols, ["id", "title", "description", "status", "owner_id"])
            self.assertNotIn("sessions", tables)
            self.assertEqual(rows, [("카드",)])


if __name__ == "__main__":
    unittest.main()
