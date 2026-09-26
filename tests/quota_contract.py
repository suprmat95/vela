"""Contratto del token bucket della quota (RF-36..38, RF-47, M18), in memoria e su Postgres.

Limite 120, margine 10%: 108 effettive. Capienza B = 8, ritmo r = (108 − 8)/60 = 100/60
gettoni al secondo, soglia 2 per `purchase` e `sync`. `now` è passato esplicitamente: nessun
orologio reale.
"""
import random
from datetime import timedelta

from support import NOW
from vela.domain.models import QuotaClass
from vela.ports.hofj import QuotaSnapshot

B, P, S = QuotaClass.BOOKING, QuotaClass.PURCHASE, QuotaClass.SYNC
RATE = 100 / 60                      # gettoni al secondo


def at(seconds):
    return NOW + timedelta(seconds=seconds)


def fill(store, cls, calls, now=NOW):
    for _ in range(calls):
        assert store.acquire(cls, 1, now)


def max_in_any_60s(times):
    """Massimo di chiamate in un intervallo chiuso di 60 s qualsiasi (finestra scorrevole)."""
    best, lo = 0, 0
    for hi, t in enumerate(times):
        while t - times[lo] > 60:
            lo += 1
        best = max(best, hi - lo + 1)
    return best


def max_in_anchored_windows(times, offset):
    """Finestra di HofJ misurata: 60 s ancorati alla prima chiamata dopo la scadenza; la prima
    finestra è già aperta da `offset` secondi quando arriva la nostra prima chiamata."""
    start, count, best = (times[0] - offset if times else 0), 0, 0
    for t in times:
        if t >= start + 60:
            start, count = t, 0
        count += 1
        best = max(best, count)
    return best


class QuotaContract:
    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.store = self.make_store()

    def tokens(self, now=NOW):
        return self.store.snapshot(now)["tokens"]

    # --- prelievo ---------------------------------------------------------------------------

    def test_fresh_bucket_is_full(self):
        snap = self.store.snapshot(NOW)
        self.assertEqual((snap["tokens"], snap["burst"], snap["effective_limit"]), (8, 8, 108))
        self.assertAlmostEqual(snap["rate_per_minute"], 100)

    def test_acquire_takes_tokens(self):
        self.assertTrue(self.store.acquire(P, 5, NOW))
        self.assertTrue(self.store.acquire(B, 1, NOW))
        self.assertEqual(self.tokens(), 2)

    def test_purchase_leaves_the_floor_to_bookings(self):
        self.assertTrue(self.store.acquire(P, 6, NOW))
        self.assertFalse(self.store.acquire(P, 1, NOW))
        self.assertEqual(self.tokens(), 2)

    def test_booking_takes_the_floor_down_to_zero(self):
        fill(self.store, P, 6)
        fill(self.store, B, 2)
        self.assertFalse(self.store.acquire(B, 1, NOW))
        self.assertEqual(self.tokens(), 0)

    def test_block_is_atomic_all_or_nothing(self):
        self.assertFalse(self.store.acquire(P, 7, NOW))
        self.assertEqual(self.tokens(), 8)
        self.assertTrue(self.store.acquire(P, 6, NOW))

    def test_sync_only_without_waiting_purchase(self):
        self.assertFalse(self.store.acquire(S, 1, NOW, purchase_waiting=True))
        self.assertTrue(self.store.acquire(S, 1, NOW, purchase_waiting=False))
        fill(self.store, S, 5)
        self.assertFalse(self.store.acquire(S, 1, NOW))   # soglia come purchase

    # --- ritmo ------------------------------------------------------------------------------

    def test_tokens_refill_at_constant_rate(self):
        fill(self.store, P, 6)
        fill(self.store, B, 2)
        self.assertAlmostEqual(self.tokens(at(3)), 5, places=3)
        self.assertFalse(self.store.acquire(P, 5, at(3)))     # servono 5 + soglia 2
        self.assertTrue(self.store.acquire(P, 5, at(4.2)))

    def test_refill_stops_at_burst(self):
        self.store.acquire(P, 5, NOW)
        self.assertEqual(self.tokens(at(600)), 8)

    def test_clock_behind_does_not_add_tokens(self):
        fill(self.store, P, 6)
        self.assertEqual(self.tokens(at(-30)), 2)
        self.assertFalse(self.store.acquire(P, 1, at(-30)))

    def test_next_window_start_is_when_a_whole_purchase_fits(self):
        fill(self.store, P, 6)
        fill(self.store, B, 2)
        self.assertEqual(self.store.next_window_start(NOW), at(7 / RATE))
        self.assertEqual(self.store.next_window_start(at(600)), at(600))

    def test_never_more_than_108_in_any_60s_whatever_hofj_window(self):
        """Prelievi avidi ogni 0,25 s per 3 minuti, blocchi da 1 a 5, tre classi: mai più di 108
        chiamate in un intervallo di 60 s, né con la finestra ancorata di HofJ aperta da istanti
        diversi, né a griglia."""
        rnd = random.Random(18)
        taken = []
        for step in range(3 * 60 * 4):
            t = step / 4
            for _ in range(4):
                cls, n = rnd.choice([(P, 5), (P, 3), (B, 1), (S, 1)])
                if self.store.acquire(cls, n, at(t)):
                    taken.extend([t] * n)
        self.assertGreater(len(taken), 250)                      # il ritmo c'è: ~8 + 100/min
        self.assertLessEqual(max_in_any_60s(taken), 108)
        for offset in (0, 3.8, 30, 59.9):
            with self.subTest(anchored_offset=offset):
                self.assertLessEqual(max_in_anchored_windows(taken, offset), 108)
        for grid in (0, 17.5):
            with self.subTest(grid=grid):
                per_window = {}
                for t in taken:
                    k = (t + grid) // 60
                    per_window[k] = per_window.get(k, 0) + 1
                self.assertLessEqual(max(per_window.values()), 108)

    # --- 429 e rilettura --------------------------------------------------------------------

    def test_429_empties_the_bucket(self):
        self.store.acquire(P, 5, NOW)
        self.store.on_429(at(10))
        self.assertTrue(self.store.needs_refresh(at(10)))
        self.assertFalse(self.store.acquire(B, 1, at(10)))
        self.assertTrue(self.store.acquire(B, 1, at(10 + 1 / RATE)))
        self.assertGreater(self.store.next_window_start(at(10)), at(14))

    def test_429_with_hold_blocks_a_whole_window(self):
        self.store.on_429(NOW, hold_seconds=60)
        self.assertFalse(self.store.acquire(B, 1, at(60)))
        self.assertTrue(self.store.acquire(B, 1, at(60 + 1 / RATE)))

    def test_claim_refresh_is_single_flight(self):
        self.assertTrue(self.store.needs_refresh(NOW))
        self.assertTrue(self.store.claim_refresh(NOW))
        self.assertFalse(self.store.needs_refresh(NOW))
        self.assertFalse(self.store.claim_refresh(NOW))
        self.assertEqual(self.tokens(), 7)

    def test_claim_refresh_needs_a_booking_token(self):
        self.store.on_429(NOW)
        self.assertFalse(self.store.claim_refresh(NOW))
        self.assertTrue(self.store.needs_refresh(NOW))
        self.assertTrue(self.store.claim_refresh(at(1 / RATE)))

    def test_mark_refresh_needed(self):
        self.store.claim_refresh(NOW)
        self.store.mark_refresh_needed(NOW)
        self.assertTrue(self.store.needs_refresh(NOW))

    def test_snapshot_sets_the_limit_and_the_rate(self):
        start = NOW - timedelta(seconds=20)
        self.store.sync_from_snapshot(QuotaSnapshot(100, 30, start, start + timedelta(seconds=60)), NOW)
        snap = self.store.snapshot(NOW)
        self.assertEqual((snap["limit_per_minute"], snap["effective_limit"], snap["tokens"]), (100, 90, 8))
        self.assertAlmostEqual(snap["rate_per_minute"], 82)
        self.assertEqual(snap["hofj_window_end"], NOW + timedelta(seconds=40))
        self.assertFalse(snap["needs_refresh"])

    def test_snapshot_never_gives_more_than_hofj_leaves(self):
        self.store.sync_from_snapshot(QuotaSnapshot(120, 105, NOW, at(60)), NOW)
        self.assertEqual(self.tokens(), 3)

    def test_exhausted_snapshot_blocks_until_hofj_window_ends(self):
        self.store.sync_from_snapshot(QuotaSnapshot(120, 110, at(-40), at(20)), NOW)
        self.assertFalse(self.store.acquire(B, 1, at(20)))
        self.assertTrue(self.store.acquire(B, 1, at(20 + 1 / RATE)))

    def test_snapshot_view_does_not_write(self):
        fill(self.store, P, 6)
        self.assertEqual(self.tokens(at(600)), 8)
        self.assertFalse(self.store.acquire(P, 1, NOW))
