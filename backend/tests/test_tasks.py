import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.auth import current_user
from app.db import connect, init_db
from app.schemas import StatusChange, TaskCreate, TaskUpdate, User
from app.tasks import (
    change_status,
    create_task,
    delete_task,
    list_tasks,
    router,
    update_task,
)


def add_user(name: str) -> User:
    conn = connect()
    try:
        with conn:
            uid = conn.execute("INSERT INTO users (username) VALUES (?)", (name,)).lastrowid
    finally:
        conn.close()
    return User(id=uid, username=name)


class TasksBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("TASKFLOW_DB")
        os.environ["TASKFLOW_DB"] = str(Path(self._tmp.name) / "test.db")
        init_db()
        self.me = add_user("me@test.com")

    def tearDown(self):
        if self._old is None:
            del os.environ["TASKFLOW_DB"]
        else:
            os.environ["TASKFLOW_DB"] = self._old
        self._tmp.cleanup()

    # 핸들러를 직접 부르므로 로그인한 사용자를 user 로 넘긴다.
    def create(self, **kw):
        return create_task(TaskCreate(**kw), user=self.me)

    def list(self):
        return list_tasks(user=self.me)


class TasksApiTest(TasksBase):
    def test_empty_list_is_success(self):
        self.assertEqual(self.list(), [])

    def test_create_starts_as_todo_and_description_optional(self):
        task = self.create(title="  첫 카드 ")
        self.assertEqual(task.title, "첫 카드")
        self.assertEqual(task.description, "")
        self.assertEqual(task.status, "TODO")

    def test_list_in_id_order(self):
        self.create(title="a", description="x")
        self.create(title="b")
        self.assertEqual([t.title for t in self.list()], ["a", "b"])

    def test_blank_title_rejected_and_not_saved(self):
        for bad in [None, "", "   "]:
            with self.subTest(bad=bad):
                with self.assertRaises(HTTPException) as cm:
                    self.create(title=bad)
                self.assertEqual(cm.exception.status_code, 422)
        self.assertEqual(self.list(), [])


class TaskChangeTest(TasksApiTest):
    def _code(self, fn, *args, **kw):
        with self.assertRaises(HTTPException) as cm:
            fn(*args, user=self.me, **kw)
        return cm.exception.status_code

    def test_every_status_transition(self):
        states = ["TODO", "IN_PROGRESS", "DONE"]
        for src in states:
            for dst in states:
                with self.subTest(src=src, dst=dst):
                    t = self.create(title="x")
                    change_status(t.id, StatusChange(status=src), user=self.me)
                    self.assertEqual(
                        change_status(t.id, StatusChange(status=dst), user=self.me).status, dst
                    )
                    self.assertEqual([x.status for x in self.list() if x.id == t.id], [dst])

    def test_invalid_status_rejected_and_unchanged(self):
        t = self.create(title="x")
        for bad in [None, "", "done", "DOING"]:
            with self.subTest(bad=bad):
                self.assertEqual(self._code(change_status, t.id, StatusChange(status=bad)), 422)
        self.assertEqual(self.list()[0].status, "TODO")

    def test_update_title_and_description_keeps_status(self):
        t = self.create(title="a", description="d")
        change_status(t.id, StatusChange(status="DONE"), user=self.me)
        u = update_task(t.id, TaskUpdate(title=" b ", description="e"), user=self.me)
        self.assertEqual((u.title, u.description, u.status), ("b", "e", "DONE"))

    def test_update_only_sent_fields(self):
        t = self.create(title="a", description="d")
        self.assertEqual(update_task(t.id, TaskUpdate(description="e"), user=self.me).title, "a")
        self.assertEqual(update_task(t.id, TaskUpdate(title="b"), user=self.me).description, "e")

    def test_update_blank_title_rejected_and_unchanged(self):
        t = self.create(title="a", description="d")
        for bad in [None, "", "  "]:
            with self.subTest(bad=bad):
                self.assertEqual(self._code(update_task, t.id, TaskUpdate(title=bad)), 422)
        self.assertEqual((self.list()[0].title, self.list()[0].description), ("a", "d"))

    def test_missing_card_rejected(self):
        self.assertEqual(self._code(update_task, 999, TaskUpdate(title="x")), 404)
        self.assertEqual(self._code(change_status, 999, StatusChange(status="DONE")), 404)
        self.assertEqual(self._code(delete_task, 999), 404)

    def test_delete_removes_card(self):
        a = self.create(title="a")
        b = self.create(title="b")
        delete_task(a.id, user=self.me)
        self.assertEqual([t.id for t in self.list()], [b.id])
        self.assertEqual(self._code(delete_task, a.id), 404)


class OwnershipTest(TasksBase):
    # R-008: 로그인한 사람은 자기 Task만 보고 바꾼다. 남의 Task는 없는 Task와 같은 404이다.
    def setUp(self):
        super().setUp()
        self.other = add_user("other@test.com")
        self.mine = self.create(title="내 것", description="d")
        self.theirs = create_task(TaskCreate(title="남의 것", description="d"), user=self.other)

    def _error(self, fn, *args):
        with self.assertRaises(HTTPException) as cm:
            fn(*args, user=self.me)
        return cm.exception

    def _snapshot(self):
        conn = connect()
        try:
            return [tuple(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id")]
        finally:
            conn.close()

    def test_list_shows_only_own_tasks(self):
        self.assertEqual([t.id for t in self.list()], [self.mine.id])
        self.assertEqual([t.id for t in list_tasks(user=self.other)], [self.theirs.id])

    def test_new_task_belongs_to_logged_in_user(self):
        conn = connect()
        owner = conn.execute("SELECT owner_id FROM tasks WHERE id = ?", (self.mine.id,)).fetchone()[0]
        conn.close()
        self.assertEqual(owner, self.me.id)

    def test_request_cannot_choose_owner(self):
        # 본문에 owner_id 를 실어도 무시하고 로그인한 사용자가 소유자가 된다.
        body = TaskCreate.model_validate({"title": "x", "owner_id": self.other.id})
        task = create_task(body, user=self.me)
        self.assertEqual([t.id for t in list_tasks(user=self.me)][-1], task.id)
        self.assertNotIn(task.id, [t.id for t in list_tasks(user=self.other)])

    def test_other_users_task_is_404_for_update_status_delete_and_unchanged(self):
        before = self._snapshot()
        errors = [
            self._error(update_task, self.theirs.id, TaskUpdate(title="해킹")),
            self._error(change_status, self.theirs.id, StatusChange(status="DONE")),
            self._error(delete_task, self.theirs.id),
        ]
        self.assertEqual([e.status_code for e in errors], [404, 404, 404])
        self.assertEqual(self._snapshot(), before)

    def test_other_users_task_looks_the_same_as_missing(self):
        theirs = self._error(update_task, self.theirs.id, TaskUpdate(title="x"))
        missing = self._error(update_task, 9999, TaskUpdate(title="x"))
        self.assertEqual((theirs.status_code, theirs.detail), (missing.status_code, missing.detail))

    def test_invalid_input_on_other_users_task_is_404_not_422(self):
        # 남의 Task가 있는지 알려 주지 않는다.
        self.assertEqual(self._error(update_task, self.theirs.id, TaskUpdate(title="")).status_code, 404)
        self.assertEqual(
            self._error(change_status, self.theirs.id, StatusChange(status="x")).status_code, 404
        )


class PriorityDueApiTest(TasksBase):
    # R-009~R-012. "오늘"은 2026-10-26 으로 고정한다.
    TODAY = date(2026, 10, 26)

    def setUp(self):
        super().setUp()
        patcher = patch("app.tasks.today", return_value=self.TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _code(self, fn, *args, **kw):
        with self.assertRaises(HTTPException) as cm:
            fn(*args, user=self.me, **kw)
        return cm.exception.status_code

    def _row(self, task_id):
        conn = connect()
        try:
            return tuple(
                conn.execute(
                    "SELECT title, description, status, priority, due_date FROM tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()
            )
        finally:
            conn.close()

    def _count(self):
        conn = connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        finally:
            conn.close()

    # 등록
    def test_create_without_new_values_is_normal_and_no_due_date(self):
        t = self.create(title="a")
        self.assertEqual((t.priority, t.due_date, t.is_overdue), ("NORMAL", None, False))

    def test_create_with_values_saves_and_lists_them(self):
        t = self.create(title="a", priority="HIGH", due_date="2026-10-30")
        self.assertEqual((t.priority, t.due_date), ("HIGH", "2026-10-30"))
        listed = self.list()[0]
        self.assertEqual((listed.priority, listed.due_date), ("HIGH", "2026-10-30"))

    def test_create_accepts_past_due_date_and_marks_it_overdue(self):
        t = self.create(title="a", due_date="2026-10-25")
        self.assertEqual((t.due_date, t.is_overdue), ("2026-10-25", True))

    def test_create_with_null_due_date_means_none_but_null_priority_is_rejected(self):
        self.assertIsNone(self.create(title="a", due_date=None).due_date)
        self.assertEqual(self._code(create_task, TaskCreate(title="b", priority=None)), 422)
        self.assertEqual(self._count(), 1)

    def test_create_invalid_values_rejected_and_not_saved(self):
        bad_bodies = [
            {"priority": "URGENT"}, {"priority": "high"}, {"priority": 1},
            {"due_date": "2026-02-30"}, {"due_date": "2026/10/26"}, {"due_date": "2026-10-26T10:00"},
            {"due_date": 20261026}, {"due_date": ""},
        ]
        for extra in bad_bodies:
            with self.subTest(extra=extra):
                self.assertEqual(self._code(create_task, TaskCreate(title="x", **extra)), 422)
        self.assertEqual(self._count(), 0)

    def test_create_and_update_use_the_same_rules(self):
        t = self.create(title="a")
        for field, bad in [("priority", "x"), ("priority", None), ("due_date", "2026-13-01")]:
            with self.subTest(field=field, bad=bad):
                self.assertEqual(self._code(create_task, TaskCreate(title="n", **{field: bad})), 422)
                self.assertEqual(self._code(update_task, t.id, TaskUpdate(**{field: bad})), 422)

    # 수정
    def test_update_omitted_fields_stay(self):
        t = self.create(title="a", priority="HIGH", due_date="2026-10-30")
        u = update_task(t.id, TaskUpdate(title="b"), user=self.me)
        self.assertEqual((u.title, u.priority, u.due_date), ("b", "HIGH", "2026-10-30"))

    def test_update_priority_and_due_date_separately(self):
        t = self.create(title="a")
        u = update_task(t.id, TaskUpdate(priority="LOW"), user=self.me)
        self.assertEqual((u.priority, u.due_date), ("LOW", None))
        u = update_task(t.id, TaskUpdate(due_date="2026-11-01"), user=self.me)
        self.assertEqual((u.priority, u.due_date), ("LOW", "2026-11-01"))

    def test_update_due_date_null_clears_it(self):
        t = self.create(title="a", due_date="2026-10-25")
        u = update_task(t.id, TaskUpdate(due_date=None), user=self.me)
        self.assertEqual((u.due_date, u.is_overdue), (None, False))
        self.assertEqual(self._row(t.id)[4], None)

    def test_update_priority_null_rejected_and_unchanged(self):
        t = self.create(title="a", priority="HIGH", due_date="2026-10-30")
        before = self._row(t.id)
        self.assertEqual(self._code(update_task, t.id, TaskUpdate(priority=None)), 422)
        self.assertEqual(self._row(t.id), before)

    def test_update_invalid_values_rejected_and_unchanged(self):
        t = self.create(title="a", description="d", priority="HIGH", due_date="2026-10-30")
        before = self._row(t.id)
        for bad in [{"priority": "x"}, {"due_date": "2026-02-30"}, {"due_date": "10/30"}, {"due_date": 5}]:
            with self.subTest(bad=bad):
                self.assertEqual(self._code(update_task, t.id, TaskUpdate(title="바뀜", **bad)), 422)
                self.assertEqual(self._row(t.id), before)

    def test_update_due_date_to_past_becomes_overdue_and_to_future_clears_it(self):
        t = self.create(title="a", due_date="2026-10-30")
        self.assertTrue(update_task(t.id, TaskUpdate(due_date="2026-10-01"), user=self.me).is_overdue)
        self.assertFalse(update_task(t.id, TaskUpdate(due_date="2026-10-27"), user=self.me).is_overdue)

    # 상태 변경은 우선순위와 마감일을 바꾸지 않는다
    def test_status_change_keeps_priority_and_due_date_and_done_is_not_overdue(self):
        t = self.create(title="a", priority="HIGH", due_date="2026-10-25")
        self.assertTrue(t.is_overdue)
        done = change_status(t.id, StatusChange(status="DONE"), user=self.me)
        self.assertEqual((done.priority, done.due_date, done.is_overdue), ("HIGH", "2026-10-25", False))
        back = change_status(t.id, StatusChange(status="IN_PROGRESS"), user=self.me)
        self.assertEqual((back.priority, back.due_date, back.is_overdue), ("HIGH", "2026-10-25", True))

    def test_overdue_never_changes_status_or_priority(self):
        t = self.create(title="a", priority="LOW", due_date="2026-10-01")
        row = self._row(t.id)
        self.assertEqual((row[2], row[3]), ("TODO", "LOW"))

    # 기한 초과 판정 8개 (IMPACT-ANALYSIS 6.4)
    def test_overdue_judgement_examples(self):
        cases = [
            ("2026-10-25", "TODO", True), ("2026-10-25", "DONE", False),
            ("2026-10-26", "TODO", False), ("2026-10-26", "DONE", False),
            ("2026-10-27", "TODO", False), ("2026-10-27", "DONE", False),
            (None, "TODO", False), (None, "DONE", False),
        ]
        for due, status, expected in cases:
            with self.subTest(due=due, status=status):
                t = self.create(title="x", due_date=due)
                change_status(t.id, StatusChange(status=status), user=self.me)
                listed = next(x for x in self.list() if x.id == t.id)
                self.assertIs(listed.is_overdue, expected)

    def test_overdue_is_computed_at_request_time(self):
        self.create(title="a", due_date="2026-10-27")
        self.assertFalse(self.list()[0].is_overdue)
        with patch("app.tasks.today", return_value=date(2026, 10, 28)):
            self.assertTrue(self.list()[0].is_overdue)

    # 정렬
    def test_list_sorted_by_overdue_priority_due_date_then_id(self):
        def add(title, priority="NORMAL", due=None, status="TODO"):
            t = self.create(title=title, priority=priority, due_date=due)
            if status != "TODO":
                change_status(t.id, StatusChange(status=status), user=self.me)

        add("a")
        add("b", "LOW", "2026-10-20")
        add("c", "HIGH")
        add("d", "NORMAL", "2026-10-30")
        add("e", "HIGH", "2026-10-25")
        add("f", "HIGH", "2026-10-20")
        add("g", "HIGH", "2026-10-28")
        add("h", "HIGH", "2026-10-27")
        add("i")
        add("j", "LOW", "2026-10-01", "DONE")
        self.assertEqual([t.title for t in self.list()], list("febhgcdaij"))

    def test_without_new_values_list_stays_in_id_order(self):
        for name in "cab":
            self.create(title=name)
        self.assertEqual([t.title for t in self.list()], ["c", "a", "b"])

    def test_status_change_resorts_the_list(self):
        a = self.create(title="a", due_date="2026-10-01")
        self.create(title="b", priority="HIGH")
        self.assertEqual([t.title for t in self.list()], ["a", "b"])
        change_status(a.id, StatusChange(status="DONE"), user=self.me)
        self.assertEqual([t.title for t in self.list()], ["b", "a"])

    # 응답 모양과 사용자 분리
    def test_response_has_new_fields_and_no_owner(self):
        t = self.create(title="a", priority="LOW", due_date="2026-10-30")
        for task in (t, self.list()[0], update_task(t.id, TaskUpdate(title="b"), user=self.me)):
            self.assertEqual(
                set(task.model_dump()),
                {"id", "title", "description", "status", "priority", "due_date", "is_overdue"},
            )

    def test_request_owner_value_is_still_ignored(self):
        other = add_user("other@test.com")
        body = TaskCreate.model_validate({"title": "x", "priority": "HIGH", "owner_id": other.id})
        task = create_task(body, user=self.me)
        self.assertEqual([t.id for t in list_tasks(user=self.me)], [task.id])
        self.assertEqual(list_tasks(user=other), [])

    def test_two_users_keep_their_own_values_and_order(self):
        other = add_user("other@test.com")
        create_task(TaskCreate(title="내 것", priority="LOW", due_date="2026-10-01"), user=self.me)
        create_task(TaskCreate(title="남의 것", priority="HIGH", due_date="2026-12-31"), user=other)
        mine, theirs = list_tasks(user=self.me), list_tasks(user=other)
        self.assertEqual([(t.title, t.priority, t.due_date, t.is_overdue) for t in mine],
                         [("내 것", "LOW", "2026-10-01", True)])
        self.assertEqual([(t.title, t.priority, t.due_date, t.is_overdue) for t in theirs],
                         [("남의 것", "HIGH", "2026-12-31", False)])

    def test_other_users_task_is_404_even_with_invalid_new_values_and_unchanged(self):
        other = add_user("other@test.com")
        theirs = create_task(TaskCreate(title="남의 것", priority="HIGH", due_date="2026-12-31"), user=other)
        before = self._row(theirs.id)
        for body in [
            TaskUpdate(priority="x"), TaskUpdate(priority=None), TaskUpdate(due_date="2026-02-30"),
            TaskUpdate(priority="LOW", due_date=None),
        ]:
            with self.subTest(body=body):
                self.assertEqual(self._code(update_task, theirs.id, body), 404)
                self.assertEqual(self._row(theirs.id), before)


class ProtectionTest(unittest.TestCase):
    def test_every_route_requires_login(self):
        # 라우터 전체에 걸린 로그인 확인이 있다. 이 라우터에 더하는 API도 기본으로 보호된다.
        self.assertIn(current_user, [d.dependency for d in router.dependencies])
        self.assertEqual(
            sorted((r.path, sorted(r.methods)[0]) for r in router.routes),
            sorted(
                [
                    ("/tasks", "GET"),
                    ("/tasks", "POST"),
                    ("/tasks/{task_id}", "PATCH"),
                    ("/tasks/{task_id}/status", "PATCH"),
                    ("/tasks/{task_id}", "DELETE"),
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
