"""Contratto della quota su Postgres e concorrenza reale (RF-47). Solo con DATABASE_URL."""
import os
import threading
import unittest
from unittest.mock import patch

from quota_contract import QuotaContract
from support import NOW
from test_repo_postgres import INI, TEST_SCHEMA, test_url
from vela.domain.models import QuotaClass


@unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")
class PostgresQuotaTest(QuotaContract, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import text
        from vela.adapters.db import make_engine
        from vela.config import Settings
        with make_engine(Settings.from_env().database_url).begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS %s" % TEST_SCHEMA))
        with patch.dict(os.environ, {"DATABASE_URL": test_url()}):
            command.upgrade(Config(INI), "head")
        cls.engine = make_engine(test_url())

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def make_store(self):
        from sqlalchemy import delete
        from vela.adapters.repo_postgres import PostgresQuota
        from vela.adapters.schema import quota_window_t
        with self.engine.begin() as conn:
            conn.execute(delete(quota_window_t))
        return PostgresQuota(self.engine, margin=0.10, reserve=0.20)

    def test_concurrent_acquire_never_exceeds_limit(self):
        """8 worker × 25 tentativi (200 > 87) sulla stessa finestra: concessi esattamente 87 purchase."""
        granted = []
        lock = threading.Lock()

        def worker():
            mine = sum(1 for _ in range(25) if self.store.acquire(QuotaClass.PURCHASE, 1, NOW))
            with lock:
                granted.append(mine)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(granted), 87)
        self.assertEqual(self.store.snapshot(NOW)["used"], 87)


if __name__ == "__main__":
    unittest.main()
