import unittest
from datetime import date

from app.rules import (
    Priority,
    RuleError,
    Status,
    is_overdue,
    sort_key,
    validate_description,
    validate_due_date,
    validate_priority,
    validate_status,
    validate_title,
    validate_topic,
)


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


class PriorityRuleTest(unittest.TestCase):
    def test_three_values(self):
        for value in ["LOW", "NORMAL", "HIGH"]:
            self.assertEqual(validate_priority(value), Priority(value))

    def test_rejects_null_and_others(self):
        # 우선순위는 지울 수 없으므로 None 도 거부한다.
        for bad in [None, "", "high", "URGENT", 1, ["HIGH"]]:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_priority(bad)


class DueDateRuleTest(unittest.TestCase):
    def test_none_means_no_due_date(self):
        self.assertIsNone(validate_due_date(None))

    def test_accepts_dates_including_past(self):
        for value in ["2026-10-26", "1999-01-01", "2028-02-29"]:
            self.assertEqual(validate_due_date(value), value)

    def test_rejects_other_formats_times_and_impossible_dates(self):
        bad_values = [
            "", " ", "2026-10-26 ", "2026/10/26", "20261026", "26-10-26", "2026-1-5",
            "2026-10-26T10:00", "2026-10-26 10:00", "2026-02-30", "2027-02-29", "2026-13-01",
            "2026-00-10", "٢٠٢٦-١٠-٢٦", 20261026, True, ["2026-10-26"],
        ]
        for bad in bad_values:
            with self.subTest(bad=bad):
                with self.assertRaises(RuleError):
                    validate_due_date(bad)


class OverdueRuleTest(unittest.TestCase):
    # IMPACT-ANALYSIS 6.4 의 판정 예 8개. 오늘은 2026-10-26.
    TODAY = date(2026, 10, 26)

    def test_eight_cases(self):
        cases = [
            ("2026-10-25", "TODO", True),
            ("2026-10-25", "IN_PROGRESS", True),
            ("2026-10-25", "DONE", False),
            ("2026-10-26", "TODO", False),
            ("2026-10-26", "DONE", False),
            ("2026-10-27", "TODO", False),
            ("2026-10-27", "DONE", False),
            (None, "TODO", False),
            (None, "DONE", False),
        ]
        for due, status, expected in cases:
            with self.subTest(due=due, status=status):
                self.assertIs(is_overdue(due, Status(status), self.TODAY), expected)

    def test_month_and_year_boundaries(self):
        self.assertTrue(is_overdue("2025-12-31", "TODO", date(2026, 1, 1)))
        self.assertFalse(is_overdue("2026-01-01", "TODO", date(2026, 1, 1)))
        self.assertTrue(is_overdue("2026-09-30", "TODO", date(2026, 10, 1)))


class SortKeyTest(unittest.TestCase):
    def order(self, items):
        # items: (id, priority, due_date, overdue)
        return [i[0] for i in sorted(items, key=lambda i: sort_key(i[0], i[1], i[2], i[3]))]

    def test_overdue_beats_priority(self):
        self.assertEqual(
            self.order([(1, "HIGH", None, False), (2, "LOW", "2026-10-01", True)]), [2, 1]
        )

    def test_high_before_normal_before_low(self):
        self.assertEqual(
            self.order([(1, "LOW", None, False), (2, "NORMAL", None, False), (3, "HIGH", None, False)]),
            [3, 2, 1],
        )

    def test_priority_beats_due_date(self):
        self.assertEqual(
            self.order([(1, "NORMAL", "2026-10-27", False), (2, "HIGH", "2026-12-01", False)]), [2, 1]
        )

    def test_nearer_due_date_first_and_no_due_date_last(self):
        self.assertEqual(
            self.order(
                [(1, "NORMAL", None, False), (2, "NORMAL", "2026-11-05", False), (3, "NORMAL", "2026-10-30", False)]
            ),
            [3, 2, 1],
        )

    def test_overdue_older_due_date_first(self):
        self.assertEqual(
            self.order([(1, "NORMAL", "2026-10-25", True), (2, "NORMAL", "2026-10-01", True)]), [2, 1]
        )

    def test_ties_go_by_id(self):
        self.assertEqual(self.order([(2, "NORMAL", None, False), (1, "NORMAL", None, False)]), [1, 2])


if __name__ == "__main__":
    unittest.main()
