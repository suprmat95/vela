"""Regole pure della quota HofJ (RF-47, RF-48): limite effettivo, token bucket, attesa stimata."""
import unittest
from datetime import timedelta

from support import NOW
from vela.domain.models import QuotaClass
from vela.domain.quota import (BucketRules, QuotaBucket, effective_limit, estimated_wait_seconds,
                               purchases_per_minute, seconds_until, wait_minutes)


class LimitsTest(unittest.TestCase):
    def test_effective_limit_applies_margin(self):
        self.assertEqual(effective_limit(120, 0.10), 108)

    def test_effective_limit_without_margin(self):
        self.assertEqual(effective_limit(120, 0.0), 120)

    def test_percentages_are_exact_not_float(self):
        # 100 × 0,29 in float fa 28,999…: il floor darebbe 28.
        self.assertEqual(effective_limit(100, 0.71), 29)


class BucketRulesTest(unittest.TestCase):
    def test_burst_plus_a_minute_of_rate_is_the_effective_limit(self):
        rules = BucketRules()
        self.assertEqual(rules.burst + 60 * rules.rate(120), 108)
        self.assertAlmostEqual(rules.rate(120), 100 / 60)

    def test_floor_applies_to_purchase_and_sync_only(self):
        rules = BucketRules()
        self.assertEqual([rules.floor_for(c) for c in (QuotaClass.BOOKING, QuotaClass.PURCHASE,
                                                       QuotaClass.SYNC)], [0, 2, 2])

    def test_burst_must_hold_a_purchase_plus_the_floor(self):
        with self.assertRaises(ValueError):
            BucketRules(burst=6, floor=2)

    def test_limit_without_rate_beyond_burst_is_an_error(self):
        with self.assertRaises(ValueError):
            BucketRules().rate(8)

    def test_seconds_until_a_purchase_from_empty(self):
        rules = BucketRules()
        empty = QuotaBucket(0.0, NOW, 120, False, NOW, NOW + timedelta(seconds=60))
        self.assertAlmostEqual(seconds_until(empty, QuotaClass.PURCHASE, 5, NOW, rules), 7 * 60 / 100)
        self.assertAlmostEqual(seconds_until(empty, QuotaClass.BOOKING, 1, NOW, rules), 0.6)


class EstimatedWaitTest(unittest.TestCase):
    def test_purchases_per_minute_counts_80_percent_of_the_rate(self):
        self.assertAlmostEqual(purchases_per_minute(100 / 60, 0.20), 16)

    def test_estimated_wait_formula(self):
        per_minute = purchases_per_minute(100 / 60, 0.20)
        self.assertEqual(estimated_wait_seconds(1, per_minute), 4)        # 3,75 s per eccesso
        self.assertEqual(estimated_wait_seconds(16, per_minute), 60)
        self.assertEqual(estimated_wait_seconds(1000, per_minute), 3750)  # nessun tetto (RF-48)

    def test_wait_minutes_rounds_up_min_one(self):
        self.assertEqual(wait_minutes(4), 1)
        self.assertEqual(wait_minutes(60), 1)
        self.assertEqual(wait_minutes(61), 2)
        self.assertEqual(wait_minutes(0), 1)

    def test_no_rate_for_purchases_is_an_error(self):
        with self.assertRaises(ValueError):
            purchases_per_minute(100 / 60, 1.0)


if __name__ == "__main__":
    unittest.main()
