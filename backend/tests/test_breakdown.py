import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import anthropic
import httpx2 as httpx
from fastapi import HTTPException

from app import ai as ai_module
from app import breakdown as breakdown_module
from app import tasks as tasks_module
from app.auth import current_user
from app.db import connect, init_db
from app.main import app
from app.schemas import BreakdownRequest
from tests.test_suggest import FakeClient, reply, status_error, task_count

# 테스트용 가짜 값이다. 실제 API는 호출하지 않는다.
FAKE_KEY = "fake-key-for-test"


def item(title="일", priority="NORMAL", due_date=None):
    return {"title": title, "priority": priority, "due_date": due_date}


def answer(*items):
    return json.dumps({"tasks": list(items)}, ensure_ascii=False)


THREE = answer(item("자료 조사", "HIGH", "2026-10-29"), item("초안 쓰기"), item("검토", "LOW"))


class BreakdownTest(unittest.TestCase):
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

    def call(self, result, topic="발표 준비"):
        client = FakeClient(result)
        with mock.patch.object(ai_module, "make_client", return_value=client):
            try:
                out = breakdown_module.breakdown(BreakdownRequest(topic=topic))
                return out, None, client
            except HTTPException as e:
                return None, e, client

    def test_success_three_to_five(self):
        for n in (3, 4, 5):
            with self.subTest(n=n):
                out, err, _ = self.call(reply(answer(*[item(f"일{i}") for i in range(n)])))
                self.assertIsNone(err)
                self.assertEqual(len(out.tasks), n)

    def test_values(self):
        out, _, _ = self.call(reply(THREE))
        self.assertEqual(out.tasks[0].title, "자료 조사")
        self.assertEqual(out.tasks[0].priority, "HIGH")
        self.assertEqual(out.tasks[0].due_date, "2026-10-29")
        self.assertIsNone(out.tasks[1].due_date)

    def test_code_fence_is_stripped(self):
        for text in (f"```json\n{THREE}\n```", f"```\n{THREE}\n```"):
            out, err, _ = self.call(reply(text))
            self.assertIsNone(err)
            self.assertEqual(len(out.tasks), 3)

    def test_bad_answers_are_502(self):
        bad = {
            "2개": answer(item(), item()),
            "6개": answer(*[item() for _ in range(6)]),
            "0개": answer(),
            "tasks 없음": '{"items": []}',
            "리스트 아님": '{"tasks": "x"}',
            "배열만": "[1, 2, 3]",
            "JSON 아님": "나눠 드릴게요",
            "title 없음": answer(item(), item(), {"priority": "LOW", "due_date": None}),
            "title 빈 값": answer(item(), item(), item(title="  ")),
            "priority 밖": answer(item(), item(), item(priority="URGENT")),
            "due_date 형식": answer(item(), item(), item(due_date="내일")),
            "due_date 없는 날짜": answer(item(), item(), item(due_date="2026-02-30")),
            "due_date 키 빠짐": answer(item(), item(), {"title": "a", "priority": "LOW"}),
            "항목이 객체 아님": answer(item(), item(), "일"),
        }
        for name, text in bad.items():
            with self.subTest(name=name):
                _, err, _ = self.call(reply(text))
                self.assertEqual(err.status_code, 502)
                self.assertEqual(err.detail, "제안 실패")

    def test_truncated_and_empty_are_502(self):
        _, err, _ = self.call(reply(THREE, stop_reason="max_tokens"))
        self.assertEqual(err.status_code, 502)
        _, err, _ = self.call(reply(THREE).__class__(content=[], stop_reason="end_turn"))
        self.assertEqual(err.status_code, 502)

    def test_missing_key_is_503(self):
        from app.config import ConfigError

        with mock.patch.object(ai_module, "get_anthropic_api_key", side_effect=ConfigError("x")):
            _, err, client = self.call(reply(THREE))
        self.assertEqual(err.status_code, 503)
        self.assertEqual(err.detail, "AI 기능 꺼짐")
        self.assertEqual(client.calls, [])

    def test_limit_and_busy_are_503_and_other_errors_502(self):
        for exc in (
            status_error(anthropic.RateLimitError, 429),
            status_error(anthropic.OverloadedError, 529),
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid")),
        ):
            with self.subTest(exc=type(exc).__name__):
                _, err, _ = self.call(exc)
                self.assertEqual(err.status_code, 503)
                self.assertNotIn(FAKE_KEY, str(err.detail))
        _, err, _ = self.call(status_error(anthropic.BadRequestError, 400))
        self.assertEqual(err.status_code, 502)

    def test_invalid_topic_is_422_without_calling_model(self):
        for topic in ("  ", None, "가" * 201):
            with self.subTest(topic=topic):
                _, err, client = self.call(reply(THREE), topic=topic)
                self.assertEqual(err.status_code, 422)
                self.assertEqual(client.calls, [])

    def test_request_options(self):
        _, _, client = self.call(reply(THREE), topic="이사 준비")
        kw = client.calls[0]
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        self.assertEqual(kw["thinking"], {"type": "disabled"})
        content = kw["messages"][0]["content"]
        self.assertIn(date.today().isoformat(), content)  # 오늘 날짜는 서버가 넣는다.
        self.assertIn("이사 준비", content)
        self.assertEqual(kw["system"], breakdown_module.SYSTEM_PROMPT)

    def test_key_value_is_not_in_prompts(self):
        self.assertNotIn(FAKE_KEY, breakdown_module.SYSTEM_PROMPT)
        _, _, client = self.call(reply(THREE))
        self.assertNotIn(FAKE_KEY, json.dumps(client.calls[0], ensure_ascii=False, default=str))

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
        for result in (reply(THREE), reply("깨짐"), status_error(anthropic.RateLimitError, 429)):
            self.call(result)
        self.assertEqual(task_count(), before)

    def test_requires_login_and_route_comes_before_task_id(self):
        deps = [d.dependency for d in breakdown_module.router.dependencies]
        self.assertIn(current_user, deps)
        routers = [r.original_router for r in app.routes if hasattr(r, "original_router")]
        # 먼저 등록되어야 /tasks/{task_id} 에 가려지지 않는다.
        self.assertLess(
            routers.index(breakdown_module.router), routers.index(tasks_module.router)
        )
        paths = [r.path for r in breakdown_module.router.routes]
        self.assertEqual(paths, ["/tasks/breakdown"])


if __name__ == "__main__":
    unittest.main()
