import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx2 as httpx
from fastapi import HTTPException

from app import ai as ai_module
from app import tasks as tasks_module
from app import weekplan as weekplan_module
from app.auth import current_user
from app.db import connect, init_db
from app.main import app
from app.schemas import User

# 테스트용 가짜 값이다. 실제 API는 호출하지 않는다.
FAKE_KEY = "fake-key-for-test"


def reply(data, stop_reason="end_turn"):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return SimpleNamespace(content=[SimpleNamespace(text=text)], stop_reason=stop_reason)


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def status_error(cls, status):
    req = httpx.Request("POST", "https://example.invalid")
    res = httpx.Response(status, request=req)
    return cls("x", response=res, body=None)


def task_rows():
    conn = connect()
    try:
        return [tuple(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()]
    finally:
        conn.close()


def day(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


class WeekPlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = os.environ.get("TASKFLOW_DB")
        self._old_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["TASKFLOW_DB"] = str(Path(self._tmp.name) / "test.db")
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
        init_db()
        self.me = self.add_user("me@test.com")
        self.other = self.add_user("other@test.com")

    def tearDown(self):
        for name, old in (("TASKFLOW_DB", self._old_db), ("ANTHROPIC_API_KEY", self._old_key)):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        self._tmp.cleanup()

    def add_user(self, username):
        conn = connect()
        try:
            with conn:
                uid = conn.execute("INSERT INTO users (username) VALUES (?)", (username,)).lastrowid
        finally:
            conn.close()
        return User(id=uid, username=username)

    def add_task(self, owner, title, status="TODO", priority="NORMAL", due=None, description=""):
        conn = connect()
        try:
            with conn:
                return conn.execute(
                    "INSERT INTO tasks (title, description, status, owner_id, priority, due_date)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (title, description, status, owner.id, priority, due),
                ).lastrowid
        finally:
            conn.close()

    def call(self, result, user=None):
        client = FakeClient(result)
        with mock.patch.object(ai_module, "make_client", return_value=client):
            try:
                return weekplan_module.weekplan(user=user or self.me), None, client
            except HTTPException as e:
                return None, e, client

    def test_success(self):
        a = self.add_task(self.me, "A")
        b = self.add_task(self.me, "B")
        c = self.add_task(self.me, "C")
        out, err, _ = self.call(
            reply(
                {
                    "days": [
                        {"date": day(2), "task_ids": [c]},
                        {"date": day(0), "task_ids": [a, b]},
                    ],
                    "note": ["  무리하지 마세요  "],
                }
            )
        )
        self.assertIsNone(err)
        self.assertEqual([(d.date, d.task_ids) for d in out.days], [(day(0), [a, b]), (day(2), [c])])
        self.assertEqual(out.note, ["무리하지 마세요"])

    def test_sends_only_my_open_tasks_without_description_or_title(self):
        a = self.add_task(self.me, "기한 지남", priority="HIGH", due=day(-1), description="비밀설명")
        b = self.add_task(self.me, "진행 중", status="IN_PROGRESS")
        self.add_task(self.me, "끝난 일", status="DONE")
        self.add_task(self.other, "남의 일")
        _, _, client = self.call(reply({"days": [{"date": day(0), "task_ids": [a, b]}], "note": []}))
        kw = client.calls[0]
        content = kw["messages"][0]["content"]
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        self.assertEqual(kw["system"], weekplan_module.SYSTEM_PROMPT)
        self.assertIn(f"오늘 날짜: {date.today().isoformat()}", content)
        block = content.split("<tasks>\n")[1].split("\n</tasks>")[0]
        lines = [json.loads(x) for x in block.split("\n")]
        self.assertEqual([i["id"] for i in lines], [a, b])  # 기한 초과가 먼저
        self.assertEqual(set(lines[0]), {"id", "priority", "due_date", "overdue"})
        self.assertTrue(lines[0]["overdue"])
        self.assertFalse(lines[1]["overdue"])
        for hidden in ("비밀설명", "기한 지남", "진행 중", "끝난 일", "남의 일"):
            self.assertNotIn(hidden, content)

    def test_no_open_tasks_skips_model(self):
        for label, make in (
            ("없음", lambda: None),
            ("DONE과 남의 것만", lambda: (self.add_task(self.me, "끝", status="DONE"), self.add_task(self.other, "남"))),
        ):
            with self.subTest(label):
                make()
                out, err, client = self.call(reply("안 쓰임"))
                self.assertIsNone(err)
                self.assertEqual(client.calls, [])
                self.assertEqual(out.days, [])
                self.assertEqual(out.note, ["이번 주는 비어 있어요"])

    def test_out_of_range_dates_are_dropped(self):
        a = self.add_task(self.me, "A")
        b = self.add_task(self.me, "B")
        c = self.add_task(self.me, "C")
        out, err, _ = self.call(
            reply(
                {
                    "days": [
                        {"date": day(-1), "task_ids": [a]},
                        {"date": day(7), "task_ids": [a]},
                        {"date": "2026-02-30", "task_ids": [a]},
                        {"date": "내일", "task_ids": [a]},
                        {"date": day(6), "task_ids": [b]},
                        {"date": day(0), "task_ids": [c]},
                    ],
                    "note": [],
                }
            )
        )
        self.assertIsNone(err)
        self.assertEqual([(d.date, d.task_ids) for d in out.days], [(day(0), [c]), (day(6), [b])])

    def test_unknown_and_other_users_ids_are_dropped(self):
        a = self.add_task(self.me, "A")
        other_id = self.add_task(self.other, "남의 일")
        out, err, _ = self.call(
            reply({"days": [{"date": day(1), "task_ids": [9999, other_id, a]}], "note": []})
        )
        self.assertIsNone(err)
        self.assertEqual([(d.date, d.task_ids) for d in out.days], [(day(1), [a])])

    def test_one_id_only_on_one_day_and_same_date_is_merged(self):
        a = self.add_task(self.me, "A")
        b = self.add_task(self.me, "B")
        out, err, _ = self.call(
            reply(
                {
                    "days": [
                        {"date": day(1), "task_ids": [a, a]},
                        {"date": day(3), "task_ids": [a]},  # 이미 놓임 → 비어서 빠짐
                        {"date": day(1), "task_ids": [b]},
                    ],
                    "note": [],
                }
            )
        )
        self.assertIsNone(err)
        self.assertEqual([(d.date, d.task_ids) for d in out.days], [(day(1), [a, b])])

    def test_nothing_left_is_502(self):
        a = self.add_task(self.me, "A")
        other_id = self.add_task(self.other, "남의 일")
        for data in (
            {"days": [], "note": []},
            {"days": [{"date": day(8), "task_ids": [a]}], "note": []},
            {"days": [{"date": day(0), "task_ids": [9999, other_id]}], "note": []},
            {"days": [{"date": day(0), "task_ids": []}], "note": []},
        ):
            with self.subTest(data=data):
                _, err, _ = self.call(reply(data))
                self.assertEqual(err.status_code, 502)
                self.assertEqual(err.detail, "제안 실패")

    def test_bad_answers_are_502(self):
        a = self.add_task(self.me, "A")
        ok = {"date": day(0), "task_ids": [a]}
        bad = [
            "JSON 아님",
            "[1, 2]",
            {"days": [ok]},  # note 없음
            {"note": []},  # days 없음
            {"days": "x", "note": []},
            {"days": [ok], "note": "x"},
            {"days": [ok], "note": [1]},
            {"days": [a], "note": []},  # 항목이 객체 아님
            {"days": [{"date": day(0)}], "note": []},  # task_ids 없음
            {"days": [{"task_ids": [a]}], "note": []},  # date 없음
            {"days": [{"date": 3, "task_ids": [a]}], "note": []},
            {"days": [{"date": day(0), "task_ids": "x"}], "note": []},
            {"days": [{"date": day(0), "task_ids": [str(a)]}], "note": []},
            {"days": [{"date": day(0), "task_ids": [True]}], "note": []},
        ]
        for data in bad:
            with self.subTest(data=data):
                _, err, _ = self.call(reply(data))
                self.assertEqual(err.status_code, 502)
                self.assertEqual(err.detail, "제안 실패")

    def test_code_fence_is_stripped(self):
        a = self.add_task(self.me, "A")
        body = json.dumps({"days": [{"date": day(0), "task_ids": [a]}], "note": ["c"]})
        out, err, _ = self.call(reply(f"```json\n{body}\n```"))
        self.assertIsNone(err)
        self.assertEqual(out.days[0].task_ids, [a])

    def test_truncated_and_empty_answers_are_502(self):
        a = self.add_task(self.me, "A")
        good = {"days": [{"date": day(0), "task_ids": [a]}], "note": []}
        _, err, _ = self.call(reply(good, stop_reason="max_tokens"))
        self.assertEqual(err.status_code, 502)
        _, err, _ = self.call(SimpleNamespace(content=[], stop_reason="end_turn"))
        self.assertEqual(err.status_code, 502)

    def test_missing_key_is_503(self):
        self.add_task(self.me, "A")
        with mock.patch.object(ai_module, "get_anthropic_api_key") as get_key:
            from app.config import ConfigError

            get_key.side_effect = ConfigError("x")
            _, err, client = self.call(reply("x"))
        self.assertEqual(err.status_code, 503)
        self.assertEqual(err.detail, "AI 기능 꺼짐")
        self.assertEqual(client.calls, [])

    def test_limit_and_busy_are_503(self):
        self.add_task(self.me, "A")
        for exc in (
            status_error(anthropic.RateLimitError, 429),
            status_error(anthropic.OverloadedError, 529),
            status_error(anthropic.ServiceUnavailableError, 503),
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid")),
        ):
            with self.subTest(exc=type(exc).__name__):
                _, err, _ = self.call(exc)
                self.assertEqual(err.status_code, 503)
                self.assertNotIn(FAKE_KEY, str(err.detail))

    def test_other_sdk_error_is_502(self):
        self.add_task(self.me, "A")
        _, err, _ = self.call(status_error(anthropic.BadRequestError, 400))
        self.assertEqual(err.status_code, 502)

    def test_db_is_never_changed(self):
        a = self.add_task(self.me, "A")
        self.add_task(self.me, "B", status="DONE")
        before = task_rows()
        good = {"days": [{"date": day(0), "task_ids": [a]}], "note": []}
        for result in (reply(good), reply("깨짐"), status_error(anthropic.RateLimitError, 429)):
            self.call(result)
        self.assertEqual(task_rows(), before)

    def test_requires_login_and_route_comes_before_task_id(self):
        deps = [d.dependency for d in weekplan_module.router.dependencies]
        self.assertIn(current_user, deps)
        routers = [r.original_router for r in app.routes if hasattr(r, "original_router")]
        self.assertLess(routers.index(weekplan_module.router), routers.index(tasks_module.router))
        self.assertEqual([r.path for r in weekplan_module.router.routes], ["/tasks/weekplan"])


if __name__ == "__main__":
    unittest.main()
