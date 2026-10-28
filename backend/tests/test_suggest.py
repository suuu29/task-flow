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

from app import suggest as suggest_module
from app import tasks as tasks_module
from app.auth import current_user
from app.db import connect, init_db
from app.main import app
from app.schemas import SuggestRequest

# 테스트용 가짜 값이다. 실제 API는 호출하지 않는다.
FAKE_KEY = "fake-key-for-test"
GOOD = '{"priority": "HIGH", "due_date": "2026-10-29", "reason": "내일까지라고 했습니다."}'


def reply(text, stop_reason="end_turn"):
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


def task_count():
    conn = connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


class SuggestTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = os.environ.get("TASKFLOW_DB")
        self._old_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["TASKFLOW_DB"] = str(Path(self._tmp.name) / "test.db")
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
        init_db()

    def tearDown(self):
        for name, old in (("TASKFLOW_DB", self._old_db), ("ANTHROPIC_API_KEY", self._old_key)):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        self._tmp.cleanup()

    def call(self, result, title="보고서 제출", description="내일까지"):
        client = FakeClient(result)
        with mock.patch.object(suggest_module, "make_client", return_value=client):
            try:
                out = suggest_module.suggest(SuggestRequest(title=title, description=description))
                return out, None, client
            except HTTPException as e:
                return None, e, client

    def test_success(self):
        out, err, _ = self.call(reply(GOOD))
        self.assertIsNone(err)
        self.assertEqual(out.priority, "HIGH")
        self.assertEqual(out.due_date, "2026-10-29")

    def test_null_due_date(self):
        out, err, _ = self.call(reply('{"priority": "LOW", "due_date": null, "reason": "r"}'))
        self.assertIsNone(err)
        self.assertIsNone(out.due_date)

    def test_code_fence_is_stripped(self):
        for text in (f"```json\n{GOOD}\n```", f"```\n{GOOD}\n```", f"설명\n```json\n{GOOD}\n```"):
            with self.subTest(text=text[:12]):
                out, err, _ = self.call(reply(text))
                self.assertIsNone(err)
                self.assertEqual(out.priority, "HIGH")

    def test_request_options(self):
        _, _, client = self.call(reply(GOOD), title="제목X", description="")
        kw = client.calls[0]
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        self.assertEqual(kw["thinking"], {"type": "disabled"})
        content = kw["messages"][0]["content"]
        self.assertIn(date.today().isoformat(), content)  # 오늘 날짜는 서버가 넣는다.
        self.assertIn("제목X", content)
        self.assertIn("(없음)", content)
        self.assertEqual(kw["system"], suggest_module.SYSTEM_PROMPT)

    def test_bad_answers_are_502(self):
        bad = [
            "JSON 아님",
            '{"priority": "URGENT", "due_date": null, "reason": "r"}',
            '{"priority": "HIGH", "due_date": "2026-02-30", "reason": "r"}',
            '{"priority": "HIGH", "due_date": "내일", "reason": "r"}',
            '{"priority": "HIGH", "due_date": null}',
            '{"priority": "HIGH", "due_date": null, "reason": 3}',
            "[1, 2]",
        ]
        for text in bad:
            with self.subTest(text=text):
                _, err, _ = self.call(reply(text))
                self.assertEqual(err.status_code, 502)
                self.assertEqual(err.detail, "제안 실패")

    def test_truncated_answer_is_502(self):
        _, err, _ = self.call(reply(GOOD, stop_reason="max_tokens"))
        self.assertEqual(err.status_code, 502)

    def test_empty_content_is_502(self):
        _, err, _ = self.call(SimpleNamespace(content=[], stop_reason="end_turn"))
        self.assertEqual(err.status_code, 502)

    def test_missing_key_is_503(self):
        os.environ.pop("ANTHROPIC_API_KEY")
        with mock.patch.object(suggest_module, "get_anthropic_api_key") as get_key:
            from app.config import ConfigError

            get_key.side_effect = ConfigError("x")
            _, err, client = self.call(reply(GOOD))
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

    def test_invalid_title_is_422(self):
        _, err, client = self.call(reply(GOOD), title="  ")
        self.assertEqual(err.status_code, 422)
        self.assertEqual(client.calls, [])

    def test_db_is_never_changed(self):
        conn = connect()
        try:
            with conn:
                uid = conn.execute("INSERT INTO users (username) VALUES ('a@test.com')").lastrowid
                conn.execute(
                    "INSERT INTO tasks (title, description, status, owner_id) VALUES ('t','','TODO',?)",
                    (uid,),
                )
        finally:
            conn.close()
        before = task_count()
        for result in (reply(GOOD), reply("깨짐"), status_error(anthropic.RateLimitError, 429)):
            self.call(result)
        self.assertEqual(task_count(), before)

    def test_requires_login_and_route_comes_before_task_id(self):
        deps = [d.dependency for d in suggest_module.router.dependencies]
        self.assertIn(current_user, deps)
        routers = [r.original_router for r in app.routes if hasattr(r, "original_router")]
        # 먼저 등록되어야 /tasks/{task_id} 에 가려지지 않는다.
        self.assertLess(
            routers.index(suggest_module.router), routers.index(tasks_module.router)
        )


if __name__ == "__main__":
    unittest.main()
