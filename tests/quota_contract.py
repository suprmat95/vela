"""Contratto del contatore di quota (RF-36..38, RF-47), eseguito in memoria e su Postgres.

Limite 120, margine 10% e riserva 20%: limite effettivo 108, riserva booking 21, tetto 87 per
purchase e sync. `now` è passato esplicitamente: nessun orologio reale.
"""
from datetime import timedelta

from support import NOW
from vela.domain.models import QuotaClass
from vela.ports.hofj import QuotaSnapshot

B, P, S = QuotaClass.BOOKING, QuotaClass.PURCHASE, QuotaClass.SYNC


def fill(store, cls, calls, now=NOW):
    for _ in range(calls):
        assert store.acquire(cls, 1, now)


class QuotaContract:
    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.store = self.make_store()

    def used(self, now=NOW):
        return self.store.snapshot(now)["used"]

    def test_acquire_within_cap(self):
        self.assertTrue(self.store.acquire(P, 5, NOW))
        self.assertTrue(self.store.acquire(B, 1, NOW))
        self.assertEqual(self.used(), 6)

    def test_purchase_blocked_at_cap(self):
        fill(self.store, P, 87)
        self.assertFalse(self.store.acquire(P, 1, NOW))
        self.assertEqual(self.used(), 87)

    def test_booking_reserve_survives_full_purchase_window(self):
        fill(self.store, P, 87)
        fill(self.store, B, 21)
        self.assertFalse(self.store.acquire(B, 1, NOW))
        self.assertEqual(self.used(), 108)

    def test_block_is_atomic_all_or_nothing(self):
        fill(self.store, P, 86)
        self.assertFalse(self.store.acquire(P, 5, NOW))
        self.assertEqual(self.used(), 86)
        self.assertTrue(self.store.acquire(P, 1, NOW))

    def test_window_rolls_after_60s(self):
        fill(self.store, P, 87)
        self.assertFalse(self.store.acquire(P, 1, NOW + timedelta(seconds=59)))
        self.assertTrue(self.store.acquire(P, 5, NOW + timedelta(seconds=60)))
        self.assertEqual(self.used(NOW + timedelta(seconds=60)), 5)
        self.assertEqual(self.store.next_window_start(NOW + timedelta(seconds=61)),
                         NOW + timedelta(seconds=120))

    def test_window_stays_on_the_60s_grid_after_a_gap(self):
        self.store.acquire(P, 1, NOW)
        later = NOW + timedelta(seconds=150)
        self.assertTrue(self.store.acquire(P, 1, later))
        snap = self.store.snapshot(later)
        self.assertEqual(snap["window_start"], NOW + timedelta(seconds=120))
        self.assertEqual(snap["window_end"], NOW + timedelta(seconds=180))

    def test_sync_only_without_waiting_purchase(self):
        self.assertFalse(self.store.acquire(S, 1, NOW, purchase_waiting=True))
        self.assertTrue(self.store.acquire(S, 1, NOW, purchase_waiting=False))
        fill(self.store, P, 86)
        self.assertFalse(self.store.acquire(S, 1, NOW))   # tetto 87 come purchase

    def test_429_zeroes_remaining_budget(self):
        self.store.acquire(P, 5, NOW)
        self.store.on_429(NOW + timedelta(seconds=10))
        self.assertFalse(self.store.acquire(B, 1, NOW + timedelta(seconds=11)))
        self.assertFalse(self.store.acquire(P, 1, NOW + timedelta(seconds=11)))
        self.assertTrue(self.store.acquire(B, 1, NOW + timedelta(seconds=60)))

    def test_sync_from_snapshot_aligns_window(self):
        start = NOW - timedelta(seconds=20)
        self.store.sync_from_snapshot(QuotaSnapshot(100, 30, start, start + timedelta(seconds=60)))
        snap = self.store.snapshot(NOW)
        self.assertEqual((snap["limit_per_minute"], snap["effective_limit"], snap["reserve"]), (100, 90, 18))
        self.assertEqual(snap["used"], 30)
        self.assertEqual(snap["window_end"], NOW + timedelta(seconds=40))
        fill(self.store, P, 42)                          # 30 + 42 = 72 = 90 − 18
        self.assertFalse(self.store.acquire(P, 1, NOW))
        self.assertEqual(self.store.next_window_start(NOW), NOW + timedelta(seconds=40))

    def test_needs_refresh_before_first_sync_and_after_429(self):
        self.assertTrue(self.store.needs_refresh(NOW))
        self.store.sync_from_snapshot(QuotaSnapshot(120, 1, NOW, NOW + timedelta(seconds=60)))
        self.assertFalse(self.store.needs_refresh(NOW))
        self.store.acquire(P, 5, NOW)
        self.assertFalse(self.store.needs_refresh(NOW))
        self.store.on_429(NOW)
        self.assertTrue(self.store.needs_refresh(NOW))

    def test_snapshot_reports_remaining_and_rolls_without_writing(self):
        self.store.acquire(P, 10, NOW)
        snap = self.store.snapshot(NOW)
        self.assertEqual(snap["remaining"], 98)
        self.assertEqual(self.store.snapshot(NOW + timedelta(seconds=61))["used"], 0)
        self.assertEqual(self.used(NOW), 10)
