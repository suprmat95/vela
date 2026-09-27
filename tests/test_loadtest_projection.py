"""Proiezione di un giro misurato a più viaggiatori: modello a coda satura con i quattro gruppi."""
import contextlib
import io
import unittest

from loadtest.projection import main, markdown, paid_within, pay_markdown, project, requests_per_arrival
from loadtest.scenario import Mix


class ProjectionTest(unittest.TestCase):
    def test_saturated_queue_at_fifty_thousand(self):
        p = project(50_000, rate=40)                  # 50/30/18/2 in 5 minuti + 3 di coda
        self.assertEqual(p.groups, {"browse": 25_000, "proposal": 15_000, "link": 9_000, "pay": 1_000})
        self.assertEqual((p.accepts, p.accepts_per_minute), (10_000, 2000))
        self.assertTrue(p.saturated)
        self.assertEqual(p.queue_at_end, 9800)        # (2000 − 40) · 5
        self.assertAlmostEqual(p.wait_at_minute_1, 1960 / 40, places=0)     # Marco: 49 min
        self.assertAlmostEqual(p.wait_at_60_percent, 1960 * 3 / 40, places=0)
        self.assertEqual(p.wait_median, 122.5)                              # accetta al minuto 2,5
        self.assertAlmostEqual(p.wait_at_end, 9800 / 40, places=0)
        self.assertEqual(p.drain_minutes, 250)
        self.assertEqual((p.links_by_end, p.paid_by_end), (320, 32))        # 40 · 8, il 10% paga

    def test_below_saturation_nobody_waits_and_everyone_gets_the_link(self):
        p = project(500, rate=40)                     # 100 accettazioni in 5 min: 20/min
        self.assertFalse(p.saturated)
        self.assertEqual((p.queue_at_end, p.wait_at_60_percent), (0, 0))
        self.assertEqual((p.links_by_end, p.paid_by_end), (100, 10))

    def test_rest_load_counts_only_who_talks_to_vela(self):
        self.assertAlmostEqual(requests_per_arrival(Mix(50, 30, 18)), 0.5 * 2 + 0.2 * 2 + 0.02)
        self.assertEqual(requests_per_arrival(Mix(100, 0, 0)), 0)
        p = project(50_000, rate=40)
        self.assertAlmostEqual(p.rest_rps_at_end, 50_000 / 300 * 1.42 + 9800 / 45, places=0)

    def test_share_of_payers_who_can_pay_within_minutes(self):
        p = project(50_000, rate=40)                  # λ − rate = 1960/min, 5 min di arrivi
        self.assertAlmostEqual(paid_within(p, 49), 0.2)                     # chi accetta al minuto 1
        self.assertEqual(paid_within(p, 245), 1.0)                          # l'ultimo
        self.assertEqual(paid_within(p, 1000), 1.0)
        self.assertEqual(paid_within(project(500, rate=40), 0), 1.0)        # nessuna coda

    def test_pay_table(self):
        table = pay_markdown(40, sizes=(50_000,), within=(49, 245))
        self.assertIn("| 50000 | 1000 | 20% (200) | 100% (1000) |", table)

    def test_rate_must_be_positive(self):
        with self.assertRaises(ValueError):
            project(1000, rate=0)

    def test_markdown_table(self):
        table = markdown(40)
        self.assertIn("| 50000 | 25000 / 15000 / 9000 / 1000 | 2000 | 9800 | 49 / 122.5 / 245 | 250 |", table)
        self.assertEqual(len(table.splitlines()), 4)

    def test_cli_takes_the_groups(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["--rate", "40", "--browse", "0", "--proposal", "0", "--link", "0", "--sizes", "1000"])
        self.assertIn("| 1000 | 0 / 0 / 0 / 1000 |", out.getvalue())


if __name__ == "__main__":
    unittest.main()
