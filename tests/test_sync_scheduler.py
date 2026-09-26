"""Scheduler del sync (RF-30): al boot se il catalogo è vuoto o più vecchio di 6 h, poi ogni 6 h."""
import threading
import unittest
from dataclasses import replace
from datetime import timedelta

from support import make_product
from test_sync import T0, Clock
from vela.adapters.repo_memory import MemoryRepositories
from vela.sync import SyncReport, SyncScheduler

SIX_HOURS = 6 * 3600


class FakeSync:
    def __init__(self, repos, clock, report=None, error=None):
        self.repos, self.clock, self.runs = repos, clock, 0
        self.report, self.error = report or SyncReport(), error

    def run(self):
        self.runs += 1
        if self.error:
            raise self.error
        self.repos.products.upsert_many([replace(make_product(self.runs), fetched_at=self.clock())])
        return self.report


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.repos, self.clock = MemoryRepositories(), Clock()

    def scheduler(self, sync):
        return SyncScheduler(sync, self.repos, now=self.clock)

    def test_empty_catalog_syncs_at_once_then_waits_six_hours(self):
        sync = FakeSync(self.repos, self.clock)
        self.assertEqual(self.scheduler(sync).tick(), SIX_HOURS)
        self.assertEqual(sync.runs, 1)

    def test_fresh_catalog_waits_until_it_is_six_hours_old(self):
        self.repos.products.upsert_many([replace(make_product(1), fetched_at=T0 - timedelta(hours=2))])
        sync = FakeSync(self.repos, self.clock)
        self.assertEqual(self.scheduler(sync).tick(), 4 * 3600)
        self.assertEqual(sync.runs, 0)

    def test_old_catalog_syncs_at_boot(self):
        self.repos.products.upsert_many([replace(make_product(1), fetched_at=T0 - timedelta(hours=7))])
        sync = FakeSync(self.repos, self.clock)
        self.scheduler(sync).tick()
        self.assertEqual(sync.runs, 1)

    def test_skipped_run_retries_sooner(self):
        sync = FakeSync(self.repos, self.clock, report=SyncReport(skipped=True))
        self.assertEqual(self.scheduler(sync).tick(), 15 * 60)

    def test_crashed_run_is_logged_and_retried_sooner(self):
        sync = FakeSync(self.repos, self.clock, error=RuntimeError("x"))
        with self.assertLogs("vela.sync", level="ERROR") as logs:
            self.assertEqual(self.scheduler(sync).tick(), 15 * 60)
        self.assertIn("sync del catalogo fallito", logs.output[0])

    def test_run_forever_stops_on_request(self):
        sync = FakeSync(self.repos, self.clock)
        scheduler = self.scheduler(sync)
        waits = []

        def wait(seconds):
            waits.append(seconds)
            scheduler.stop()
            return True
        scheduler.wait = wait
        scheduler.run_forever()
        self.assertEqual((sync.runs, waits), (1, [SIX_HOURS]))

    def test_start_runs_in_a_daemon_thread(self):
        sync = FakeSync(self.repos, self.clock)
        scheduler = self.scheduler(sync)
        thread = scheduler.start()
        self.assertTrue(thread.daemon)
        scheduler.stop()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(thread, threading.Thread)


if __name__ == "__main__":
    unittest.main()
