"""Regole di quota del finto HofJ (M13a): finestra ancorata come la sonda, scorrevole come opzione."""
import unittest

from loadtest.fake_hofj.rules import AnchoredWindow, Background, RollingWindow, make_window

T0 = 1_000_000.0


class AnchoredWindowTest(unittest.TestCase):
    def test_first_call_opens_the_window_at_its_instant(self):
        w = AnchoredWindow(limit=3)
        a = w.admit("k", T0 + 0.769)
        self.assertTrue(a.ok)
        self.assertEqual((a.used, a.window_start, a.window_end), (1, T0 + 0.769, T0 + 60.769))

    def test_last_instant_before_the_end_is_in_the_same_window(self):
        w = AnchoredWindow(limit=2)
        w.admit("k", T0)
        self.assertTrue(w.admit("k", T0 + 59.999).ok)
        refused = w.admit("k", T0 + 59.9995)
        self.assertFalse(refused.ok)
        self.assertAlmostEqual(refused.retry_after, 0.0005, places=6)

    def test_after_a_pause_the_new_window_starts_at_the_call_not_on_a_grid(self):
        # esempio della sonda: finestra 06.769 → 66.769, pausa di 3,8 s, la successiva a 70.532
        w = AnchoredWindow(limit=120)
        w.admit("k", T0 + 6.769)
        a = w.admit("k", T0 + 70.532)
        self.assertEqual((a.used, a.window_start, a.window_end), (1, T0 + 70.532, T0 + 130.532))
        # a 126.769 (dove una griglia azzererebbe) la finestra di HofJ è ancora aperta
        self.assertEqual(w.admit("k", T0 + 126.769).used, 2)

    def test_refused_calls_count(self):
        w = AnchoredWindow(limit=1)
        w.admit("k", T0)
        w.admit("k", T0 + 1)
        a = w.admit("k", T0 + 2)
        self.assertFalse(a.ok)
        self.assertEqual(a.used, 3)

    def test_keys_are_independent(self):
        w = AnchoredWindow(limit=1)
        w.admit("a", T0)
        self.assertTrue(w.admit("b", T0 + 1).ok)

    def test_peek_does_not_consume(self):
        w = AnchoredWindow(limit=5)
        w.admit("k", T0)
        self.assertEqual(w.peek("k", T0 + 1).used, 1)
        self.assertEqual(w.admit("k", T0 + 2).used, 2)


class RollingWindowTest(unittest.TestCase):
    def test_calls_older_than_sixty_seconds_leave_the_window(self):
        w = RollingWindow(limit=2)
        w.admit("k", T0)
        w.admit("k", T0 + 30)
        self.assertFalse(w.admit("k", T0 + 59.999).ok)
        # a T0 + 60 la chiamata di T0 esce; restano 30 e 59.999 (respinta ma contata)
        self.assertFalse(w.admit("k", T0 + 60).ok)
        self.assertTrue(w.admit("k", T0 + 120.0).ok)

    def test_retry_after_is_when_the_oldest_call_leaves(self):
        w = RollingWindow(limit=1)
        w.admit("k", T0)
        a = w.admit("k", T0 + 10)
        self.assertFalse(a.ok)
        self.assertAlmostEqual(a.retry_after, 50)
        self.assertEqual((a.window_start, a.window_end), (T0, T0 + 60))


class BackgroundTest(unittest.TestCase):
    def test_spreads_calls_evenly(self):
        b = Background(rpm=12, start=T0)
        self.assertEqual(b.due(T0), 1)
        self.assertEqual(b.due(T0 + 4.9), 0)
        self.assertEqual(b.due(T0 + 5), 1)
        self.assertEqual(b.due(T0 + 60), 11)

    def test_zero_rpm_never_calls(self):
        self.assertEqual(Background(rpm=0, start=T0).due(T0 + 600), 0)


class FactoryTest(unittest.TestCase):
    def test_make_window(self):
        self.assertIsInstance(make_window("anchored", 120), AnchoredWindow)
        self.assertIsInstance(make_window("rolling", 120), RollingWindow)
        with self.assertRaises(ValueError):
            make_window("grid", 120)


if __name__ == "__main__":
    unittest.main()
