import unittest
from datetime import date
from decision_dashboard_v2.analytics import previous_month_comparison

class PreviousMonthComparisonTest(unittest.TestCase):
    def test_caps_at_previous_month_end_and_handles_leap_year(self):
        for start, end, expected in [
            (date(2026, 10, 1), date(2026, 10, 31), (date(2026, 9, 1), date(2026, 9, 30))),
            (date(2027, 3, 1), date(2027, 3, 31), (date(2027, 2, 1), date(2027, 2, 28))),
            (date(2028, 3, 1), date(2028, 3, 31), (date(2028, 2, 1), date(2028, 2, 29))),
            (date(2027, 1, 1), date(2027, 1, 15), (date(2026, 12, 1), date(2026, 12, 15))),
        ]:
            with self.subTest(end=end):
                self.assertEqual(previous_month_comparison(start, end), expected)
