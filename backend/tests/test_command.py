import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx2 as httpx
from fastapi import HTTPException

from app import ai as ai_module
from app import command as command_module
from app import tasks as tasks_module
from app.auth import current_user
from app.db import connect, init_db
from app.main import app
from app.schemas import CommandRequest, User

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


def add(title="새 일", priority="HIGH", due="2030-01-02"):
    return {"kind": "add", "id": None, "title": title, "priority": priority, "due_date": due}


def done(task_id):
    return {"kind": "done", "id": task_id, "title": None, "priority": None, "due_date": None}


def due(task_id, due_date="2030-01-02"):
    return {"kind": "due", "id": task_id, "title": None, "priority": None, "due_date": due_date}


class CommandTest(unittest.TestCase):
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

    def add_task(self, owner, title, status="TODO", priority="NORMAL", due_date=None, description=""):
        conn = connect()
        try:
            with conn:
                return conn.execute(
                    "INSERT INTO tasks (title, description, status, owner_id, priority, due_date)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (title, description, status, owner.id, priority, due_date),
                ).lastrowid
        finally:
            conn.close()

    def call(self, result, text="아무 문장", user=None):
        client = FakeClient(result)
        with mock.patch.object(ai_module, "make_client", return_value=client):
            try:
                out = command_module.command(CommandRequest(text=text), user=user or self.me)
                return out, None, client
            except HTTPException as e:
                return None, e, client

    def answer(self, actions, ask=None):
        return reply({"actions": actions, "ask": ask})

    def test_success_mixed(self):
        a = self.add_task(self.me, "A")
        b = self.add_task(self.me, "B")
        out, err, _ = self.call(self.answer([add(), due(a), done(b)]))
        self.assertIsNone(err)
        self.assertIsNone(out.ask)
        self.assertEqual([x.kind for x in out.actions], ["add", "due", "done"])
        self.assertEqual(
            (out.actions[0].id, out.actions[0].title, out.actions[0].priority, out.actions[0].due_date),
            (None, "새 일", "HIGH", "2030-01-02"),
        )
        self.assertEqual((out.actions[1].id, out.actions[1].due_date), (a, "2030-01-02"))
        self.assertEqual(out.actions[2].id, b)

    def test_add_without_priority_is_normal(self):
        out, _, _ = self.call(self.answer([add(priority=None, due=None)]))
        self.assertEqual(out.actions[0].priority, "NORMAL")
        self.assertIsNone(out.actions[0].due_date)

    def test_sends_only_my_open_tasks_without_description(self):
        a = self.add_task(self.me, "내 일", priority="HIGH", due_date="2030-05-05", description="비밀설명")
        self.add_task(self.me, "끝난 일", status="DONE")
        self.add_task(self.other, "남의 일")
        _, _, client = self.call(self.answer([done(a)]), text="내 일 끝냈어")
        kw = client.calls[0]
        content = kw["messages"][0]["content"]
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        self.assertEqual(kw["system"], command_module.SYSTEM_PROMPT)
        self.assertIn(f"오늘 날짜: {date.today().isoformat()}", content)
        self.assertIn("<text>\n내 일 끝냈어\n</text>", content)
        block = content.split("<tasks>\n")[1].split("\n</tasks>")[0]
        lines = [json.loads(x) for x in block.split("\n")]
        self.assertEqual([i["id"] for i in lines], [a])
        self.assertEqual(set(lines[0]), {"id", "title", "priority", "due_date"})
        for hidden in ("비밀설명", "끝난 일", "남의 일"):
            self.assertNotIn(hidden, content)

    def test_empty_list_still_calls_model(self):
        out, err, client = self.call(self.answer([add()]))
        self.assertIsNone(err)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(out.actions[0].kind, "add")

    def test_unknown_ids_are_dropped(self):
        a = self.add_task(self.me, "A")
        other_id = self.add_task(self.other, "남의 일")
        finished = self.add_task(self.me, "끝난 일", status="DONE")
        out, _, _ = self.call(
            self.answer([done(9999), done(other_id), due(finished), done("1"), done(True), done(a)])
        )
        self.assertEqual([(x.kind, x.id) for x in out.actions], [("done", a)])

    def test_bad_dates_drop_the_action(self):
        a = self.add_task(self.me, "A")
        out, _, _ = self.call(
            self.answer(
                [
                    due(a, "2030-02-31"),
                    due(a, "내일"),
                    due(a, "2030-1-2"),
                    due(a, None),
                    add(due="2030/01/02"),
                    add(due=20300102),
                    done(a),
                ]
            )
        )
        self.assertEqual([(x.kind, x.id) for x in out.actions], [("done", a)])

    def test_past_date_is_allowed(self):
        a = self.add_task(self.me, "A")
        out, _, _ = self.call(self.answer([due(a, "2001-01-01")]))
        self.assertEqual(out.actions[0].due_date, "2001-01-01")

    def test_invalid_add_is_dropped(self):
        for bad in (add(title="  "), add(title=3), add(priority="URGENT"), {"kind": "add"}):
            with self.subTest(bad=bad):
                out, _, _ = self.call(self.answer([bad]))
                self.assertEqual(out.actions, [])
                self.assertEqual(out.ask, command_module.NOT_UNDERSTOOD)

    def test_unknown_kind_is_dropped_and_delete_does_not_exist(self):
        a = self.add_task(self.me, "A")
        out, _, _ = self.call(self.answer([{"kind": "delete", "id": a}, {"kind": "status", "id": a}]))
        self.assertEqual(out.actions, [])
        self.assertTrue(out.ask)

    def test_no_actions_left_uses_model_ask_or_default(self):
        out, _, _ = self.call(self.answer([done(9999)], ask="어느 카드인가요?"))
        self.assertEqual((out.actions, out.ask), ([], "어느 카드인가요?"))
        out, _, _ = self.call(self.answer([], ask=None))
        self.assertEqual(out.ask, command_module.NOT_UNDERSTOOD)
        out, _, _ = self.call(self.answer([], ask="  "))
        self.assertEqual(out.ask, command_module.NOT_UNDERSTOOD)

    def test_ask_is_null_when_actions_remain(self):
        a = self.add_task(self.me, "A")
        out, _, _ = self.call(self.answer([done(a)], ask="무시될 말"))
        self.assertIsNone(out.ask)

    def test_duplicates_merged_and_capped(self):
        a = self.add_task(self.me, "A")
        out, _, _ = self.call(self.answer([done(a), done(a), due(a), due(a)]))
        self.assertEqual([(x.kind, x.id) for x in out.actions], [("done", a), ("due", a)])
        out, _, _ = self.call(self.answer([add(title=f"T{i}") for i in range(15)]))
        self.assertEqual(len(out.actions), command_module.MAX_ACTIONS)

    def test_code_fence_is_stripped(self):
        body = json.dumps({"actions": [add()], "ask": None})
        out, err, _ = self.call(reply(f"```json\n{body}\n```"))
        self.assertIsNone(err)
        self.assertEqual(out.actions[0].kind, "add")

    def test_text_rule_is_422_and_model_not_called(self):
        for bad in ("", "   ", None, 3, "가" * 201):
            with self.subTest(bad=bad):
                _, err, client = self.call(self.answer([add()]), text=bad)
                self.assertEqual(err.status_code, 422)
                self.assertTrue(err.detail)
                self.assertEqual(client.calls, [])
        out, err, _ = self.call(self.answer([add()]), text="가" * 200)
        self.assertIsNone(err)

    def test_bad_answers_are_502(self):
        bad = [
            "JSON 아님",
            "[1, 2]",
            {"actions": []},  # ask 없음
            {"ask": None},  # actions 없음
            {"actions": "x", "ask": None},
            {"actions": [], "ask": 3},
            {"actions": [3], "ask": None},  # 항목이 객체 아님
        ]
        for data in bad:
            with self.subTest(data=data):
                _, err, _ = self.call(reply(data))
                self.assertEqual(err.status_code, 502)
                self.assertEqual(err.detail, "제안 실패")

    def test_truncated_and_empty_answers_are_502(self):
        _, err, _ = self.call(reply({"actions": [add()], "ask": None}, stop_reason="max_tokens"))
        self.assertEqual(err.status_code, 502)
        _, err, _ = self.call(SimpleNamespace(content=[], stop_reason="end_turn"))
        self.assertEqual(err.status_code, 502)

    def test_missing_key_is_503(self):
        with mock.patch.object(ai_module, "get_anthropic_api_key") as get_key:
            from app.config import ConfigError

            get_key.side_effect = ConfigError("x")
            _, err, client = self.call(reply("x"))
        self.assertEqual(err.status_code, 503)
        self.assertEqual(err.detail, "AI 기능 꺼짐")
        self.assertEqual(client.calls, [])

    def test_limit_and_busy_are_503(self):
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
        _, err, _ = self.call(status_error(anthropic.BadRequestError, 400))
        self.assertEqual(err.status_code, 502)

    def test_db_is_never_changed(self):
        a = self.add_task(self.me, "A")
        self.add_task(self.me, "B", status="DONE")
        before = task_rows()
        for result in (
            self.answer([add(), due(a), done(a)]),
            reply("깨짐"),
            status_error(anthropic.RateLimitError, 429),
        ):
            self.call(result)
        self.assertEqual(task_rows(), before)

    def test_requires_login_and_route_comes_before_task_id(self):
        deps = [d.dependency for d in command_module.router.dependencies]
        self.assertIn(current_user, deps)
        routers = [r.original_router for r in app.routes if hasattr(r, "original_router")]
        self.assertLess(routers.index(command_module.router), routers.index(tasks_module.router))
        self.assertEqual([r.path for r in command_module.router.routes], ["/tasks/command"])


if __name__ == "__main__":
    unittest.main()
