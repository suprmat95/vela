"""Comando di un giro: attesa del sync, gruppi, comando Locust."""
import argparse
import contextlib
import io
import unittest

from loadtest.run import describe, durations, expected_products, locust_command, main, wait_for_catalog
from loadtest.scenario import Mix


class RunTest(unittest.TestCase):
    def test_expected_products_are_the_active_ones_of_the_brands(self):
        self.assertEqual(expected_products(["weebora.com", "terrarossa.com"]), 77 + 49)
        self.assertEqual(expected_products(["staging.weebora.com"]), 56)

    def test_waits_until_the_catalog_is_complete(self):
        answers = [RuntimeError, {"catalog": None}, {"catalog": {"products": 40}},
                   {"catalog": {"products": 126}}]
        slept = []

        def get(path):
            a = answers.pop(0)
            if a is RuntimeError:
                raise ValueError("non JSON")
            return a

        health = wait_for_catalog(get, 126, sleep=slept.append, say=lambda m: None)
        self.assertEqual(health["catalog"]["products"], 126)
        self.assertEqual(len(slept), 3)

    def test_gives_up_after_the_timeout(self):
        t = [0.0]
        with self.assertRaises(RuntimeError):
            wait_for_catalog(lambda p: {"catalog": {"products": 1}}, 126, timeout=30,
                             sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0],
                             say=lambda m: None)

    def test_locust_command(self):
        args = argparse.Namespace(arrival_minutes=10.0, tail_minutes=5.0, vela="http://vela:8000",
                                  travelers=50000, seed=13, browse=50.0, proposal=30.0, link=18.0)
        cmd = locust_command(args, "/out/50k")
        self.assertEqual([cmd[cmd.index(o) + 1] for o in ("--browse", "--proposal", "--link")],
                         ["50.0", "30.0", "18.0"])
        self.assertEqual(cmd[cmd.index("--run-time") + 1], "960s")   # giro + 60 s per chiudere
        self.assertEqual(cmd[cmd.index("--travelers") + 1], "50000")
        self.assertIn("--headless", cmd)
        self.assertEqual(cmd[cmd.index("--events-out") + 1], "/out/50k/travelers.jsonl")

    def test_describe_the_groups(self):
        self.assertEqual(describe(10_000, Mix()),
                         "10000 viaggiatori: browse 50% (5000), proposal 30% (3000), link 18% (1800), pay 2% (200)")

    def test_percentages_over_one_hundred_are_refused_before_the_run(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            main(["--browse", "50", "--proposal", "40", "--link", "18"])
        self.assertIn("somma ≤ 100", err.getvalue())



class DurationTest(unittest.TestCase):
    def test_default_is_ten_minutes_two_thirds_arrivals(self):
        self.assertEqual(durations(10, None, None), (20 / 3, 10 / 3))

    def test_one_part_given_the_other_fills_the_duration(self):
        self.assertEqual(durations(10, 7, None), (7, 3))
        self.assertEqual(durations(8, None, 3), (5, 3))

    def test_both_parts_must_fit_the_duration(self):
        self.assertEqual(durations(10, 5, 3), (5, 3))
        with self.assertRaises(ValueError):
            durations(10, 8, 3)

    def test_invalid_values(self):
        for args in ((0, None, None), (10, 0, None), (10, None, 10), (10, None, -1)):
            with self.subTest(args), self.assertRaises(ValueError):
                durations(*args)


if __name__ == "__main__":
    unittest.main()
