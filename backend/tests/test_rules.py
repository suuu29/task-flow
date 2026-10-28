import unittest

from app.rules import (
    RuleError,
    Status,
    validate_description,
    validate_due_date,
    validate_priority,
    validate_status,
    validate_title,
    validate_topic,
)


class PriorityRuleTest(unittest.TestCase):
    def test_allowed(self):
        for ok in ["LOW", "NORMAL", "HIGH"]:
            self.assertEqual(validate_priority(ok), ok)

    def test_rejects_others(self):
        for bad in ["high", "URGENT", "", None, 1]:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_priority(bad)


class TopicRuleTest(unittest.TestCase):
    def test_trims(self):
        self.assertEqual(validate_topic("  이사 준비  "), "이사 준비")

    def test_length_limit(self):
        self.assertEqual(validate_topic("가" * 200), "가" * 200)
        with self.assertRaises(RuleError):
            validate_topic("가" * 201)

    def test_rejects_empty_and_not_string(self):
        for bad in ["", "   ", None, 3]:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_topic(bad)


class DueDateRuleTest(unittest.TestCase):
    def test_allowed(self):
        self.assertIsNone(validate_due_date(None))
        self.assertEqual(validate_due_date("2026-10-29"), "2026-10-29")

    def test_rejects_bad_format_and_missing_dates(self):
        for bad in ["2026-2-3", "10/29/2026", "2026-02-30", "2026-13-01", "", 20261029]:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_due_date(bad)


class TitleRuleTest(unittest.TestCase):
    def test_rejects_empty_and_blank(self):
        for bad in ["", " ", "   \t\n", None, 3]:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_title(bad)

    def test_trims(self):
        self.assertEqual(validate_title("  할 일  "), "할 일")


class DescriptionRuleTest(unittest.TestCase):
    def test_optional(self):
        self.assertEqual(validate_description(None), "")
        self.assertEqual(validate_description(""), "")
        self.assertEqual(validate_description("메모"), "메모")

    def test_rejects_non_string(self):
        with self.assertRaises(RuleError):
            validate_description(5)


class StatusRuleTest(unittest.TestCase):
    def test_three_values(self):
        for value in ["TODO", "IN_PROGRESS", "DONE"]:
            self.assertEqual(validate_status(value), Status(value))

    def test_rejects_others(self):
        for bad in ["", "todo", "doing", None, 1]:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_status(bad)


if __name__ == "__main__":
    unittest.main()
