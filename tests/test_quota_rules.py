"""Regole pure della quota HofJ (RF-47, RF-48) con i numeri decisi nell'intervista M5."""
import unittest

from vela.domain.models import QuotaClass
from vela.domain.quota import (booking_reserve, cap_for, effective_limit, estimated_wait_seconds,
                               purchases_per_window, wait_minutes)


class LimitsTest(unittest.TestCase):
    def test_effective_limit_applies_margin(self):
        self.assertEqual(effective_limit(120, 0.10), 108)

    def test_effective_limit_without_margin(self):
        self.assertEqual(effective_limit(120, 0.0), 120)

    def test_booking_reserve_rounds_down(self):
        self.assertEqual(booking_reserve(108, 0.20), 21)     # 21,6

    def test_percentages_are_exact_not_float(self):
        # 100 × 0,29 in float fa 28,999…: il floor darebbe 28.
        self.assertEqual(booking_reserve(100, 0.29), 29)
        self.assertEqual(effective_limit(100, 0.71), 29)

    def test_caps_per_class(self):
        self.assertEqual(cap_for(QuotaClass.BOOKING, 108, 21), 108)
        self.assertEqual(cap_for(QuotaClass.PURCHASE, 108, 21), 87)
        self.assertEqual(cap_for(QuotaClass.SYNC, 108, 21), 87)

    def test_purchases_per_window(self):
        self.assertAlmostEqual(purchases_per_window(108, 21), 17.4)
        self.assertAlmostEqual(purchases_per_window(120, 24), 19.2)   # numeri della spec senza margine


class EstimatedWaitTest(unittest.TestCase):
    def test_estimated_wait_formula(self):
        per_window = purchases_per_window(108, 21)
        self.assertEqual(estimated_wait_seconds(1, per_window), 4)       # 3,45 s per eccesso
        self.assertEqual(estimated_wait_seconds(18, per_window), 63)
        self.assertEqual(estimated_wait_seconds(1000, per_window), 3449)  # nessun tetto (RF-48)

    def test_wait_minutes_rounds_up_min_one(self):
        self.assertEqual(wait_minutes(4), 1)
        self.assertEqual(wait_minutes(60), 1)
        self.assertEqual(wait_minutes(61), 2)
        self.assertEqual(wait_minutes(0), 1)

    def test_no_budget_for_purchases_is_an_error(self):
        with self.assertRaises(ValueError):
            purchases_per_window(21, 21)


if __name__ == "__main__":
    unittest.main()
