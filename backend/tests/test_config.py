import os
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigError, get_anthropic_api_key, get_session_secret

# 테스트용 가짜 값이다.
FAKE = "fake-secret-for-test"


class SessionSecretTest(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("SESSION_SECRET", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.env = Path(self._tmp.name) / ".env"

    def tearDown(self):
        os.environ.pop("SESSION_SECRET", None)
        if self._old is not None:
            os.environ["SESSION_SECRET"] = self._old
        self._tmp.cleanup()

    def test_reads_from_env_file(self):
        self.env.write_text(f"# 주석\nSESSION_SECRET={FAKE}\n", encoding="utf-8")
        self.assertEqual(get_session_secret(self.env), FAKE)

    def test_environment_variable_wins(self):
        self.env.write_text("SESSION_SECRET=from-file\n", encoding="utf-8")
        os.environ["SESSION_SECRET"] = FAKE
        self.assertEqual(get_session_secret(self.env), FAKE)

    def test_empty_value_is_refused(self):
        self.env.write_text("SESSION_SECRET=\n", encoding="utf-8")
        with self.assertRaises(ConfigError):
            get_session_secret(self.env)

    def test_blank_value_is_refused(self):
        os.environ["SESSION_SECRET"] = "   "
        with self.assertRaises(ConfigError):
            get_session_secret(self.env)

    def test_missing_file_is_refused(self):
        with self.assertRaises(ConfigError):
            get_session_secret(self.env)

    def test_error_message_does_not_contain_value(self):
        os.environ["SESSION_SECRET"] = " "
        try:
            get_session_secret(self.env)
        except ConfigError as e:
            self.assertNotIn(FAKE, str(e))


class AnthropicKeyTest(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("ANTHROPIC_API_KEY", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.env = Path(self._tmp.name) / ".env"

    def tearDown(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if self._old is not None:
            os.environ["ANTHROPIC_API_KEY"] = self._old
        self._tmp.cleanup()

    def test_reads_from_env_file(self):
        self.env.write_text(f"ANTHROPIC_API_KEY={FAKE}\n", encoding="utf-8")
        self.assertEqual(get_anthropic_api_key(self.env), FAKE)

    def test_environment_variable_wins(self):
        self.env.write_text("ANTHROPIC_API_KEY=from-file\n", encoding="utf-8")
        os.environ["ANTHROPIC_API_KEY"] = FAKE
        self.assertEqual(get_anthropic_api_key(self.env), FAKE)

    def test_missing_or_blank_is_refused(self):
        with self.assertRaises(ConfigError):
            get_anthropic_api_key(self.env)
        os.environ["ANTHROPIC_API_KEY"] = "  "
        with self.assertRaises(ConfigError):
            get_anthropic_api_key(self.env)


if __name__ == "__main__":
    unittest.main()
