"""Comando di un giro (M13a): attesa del sync, comando Locust."""
import argparse
import unittest

from loadtest.run import durations, expected_products, locust_command, wait_for_catalog


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
                                  travelers=50000, seed=13, pay=0.02)
        cmd = locust_command(args, "/out/50k")
        self.assertEqual(cmd[cmd.index("--pay") + 1], "0.02")               # M19
        self.assertEqual(cmd[cmd.index("--run-time") + 1], "960s")   # giro + 60 s per chiudere
        self.assertEqual(cmd[cmd.index("--travelers") + 1], "50000")
        self.assertIn("--headless", cmd)
        self.assertEqual(cmd[cmd.index("--events-out") + 1], "/out/50k/travelers.jsonl")



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
