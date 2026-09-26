"""Proiezione dei giri ridotti (M13a): modello a coda satura."""
import unittest

from loadtest.projection import project


class ProjectionTest(unittest.TestCase):
    def test_saturated_queue_at_fifty_thousand(self):
        p = project(50_000, rate=12)
        self.assertEqual(p.accepts_per_minute, 1000)
        self.assertTrue(p.saturated)
        self.assertEqual(p.queue_at_end, round(988 * 10))
        self.assertAlmostEqual(p.wait_at_minute_1, 988 / 12, places=0)     # Marco: ~82 min
        self.assertAlmostEqual(p.wait_last_minutes, 9880 / 12, places=0)
        self.assertAlmostEqual(p.drain_minutes, 10_000 / 12, places=0)

    def test_below_saturation_nobody_waits(self):
        p = project(500, rate=12)       # 10 accettazioni/min
        self.assertFalse(p.saturated)
        self.assertEqual((p.queue_at_end, p.wait_at_60_percent), (0, 0))

    def test_rest_load_grows_with_arrivals_and_queue(self):
        self.assertGreater(project(50_000, 12).rest_rps_at_end, project(10_000, 12).rest_rps_at_end)

    def test_rate_must_be_positive(self):
        with self.assertRaises(ValueError):
            project(1000, rate=0)


if __name__ == "__main__":
    unittest.main()
