"""Worker a thread (RF-50): N thread per istanza chiamano il processore; `drain` per i test."""
import threading
import time
import unittest

from vela.adapters.worker import Worker


class CountingProcessor:
    """Ha `jobs` lavori da fare; ogni giro ne consuma uno."""

    def __init__(self, jobs=0, fail_first=0):
        self.jobs, self.fail_first = jobs, fail_first
        self.calls = 0
        self.lock = threading.Lock()

    def run_once(self):
        with self.lock:
            self.calls += 1
            if self.fail_first:
                self.fail_first -= 1
                raise RuntimeError("guasto inatteso")
            if self.jobs == 0:
                return False
            self.jobs -= 1
            return True


def wait_until(condition, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.005)
    return False


class WorkerTest(unittest.TestCase):
    def test_drain_runs_until_idle(self):
        p = CountingProcessor(jobs=7)
        self.assertEqual(Worker(p, concurrency=0).drain(), 7)
        self.assertEqual(p.jobs, 0)

    def test_drain_stops_at_max_iterations(self):
        p = CountingProcessor(jobs=50)
        self.assertEqual(Worker(p, concurrency=0).drain(max_iterations=10), 10)

    def test_worker_threads_process_jobs_and_stop(self):
        p = CountingProcessor(jobs=30)
        w = Worker(p, concurrency=3, idle_sleep=0.01)
        w.start()
        self.assertTrue(wait_until(lambda: p.jobs == 0))
        self.assertEqual(len([t for t in threading.enumerate() if t.name.startswith("vela-worker-")]), 3)
        w.stop(wait=True)
        self.assertEqual([t for t in threading.enumerate() if t.name.startswith("vela-worker-")], [])

    def test_worker_survives_exception(self):
        p = CountingProcessor(jobs=3, fail_first=2)
        w = Worker(p, concurrency=1, idle_sleep=0.01)
        with self.assertLogs("vela.worker", "ERROR"):
            w.start()
            self.assertTrue(wait_until(lambda: p.jobs == 0))
        w.stop(wait=True)

    def test_zero_concurrency_starts_no_threads(self):
        w = Worker(CountingProcessor(), concurrency=0)
        w.start()
        self.assertEqual([t for t in threading.enumerate() if t.name.startswith("vela-worker-")], [])
        w.stop(wait=True)

    def test_idle_worker_waits_between_polls(self):
        p = CountingProcessor(jobs=0)
        w = Worker(p, concurrency=1, idle_sleep=0.2)
        w.start()
        time.sleep(0.1)
        w.stop(wait=True)
        self.assertEqual(p.calls, 1)


if __name__ == "__main__":
    unittest.main()
