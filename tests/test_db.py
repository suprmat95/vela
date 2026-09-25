import os
import time
import unittest

from sqlalchemy import MetaData

from vela.adapters.db import check_db, connect_args_for, make_engine, metadata

UNREACHABLE = "postgresql+psycopg://u:p@127.0.0.1:1/x"


class MakeEngineTest(unittest.TestCase):
    def test_sqlite_engine_is_usable(self):
        engine = make_engine("sqlite://")
        self.assertTrue(check_db(engine))

    def test_postgres_engine_uses_psycopg_dialect(self):
        engine = make_engine(UNREACHABLE)
        self.assertEqual(engine.dialect.name, "postgresql")
        self.assertEqual(engine.dialect.driver, "psycopg")

    def test_shared_metadata(self):
        self.assertIsInstance(metadata, MetaData)


class ConnectArgsTest(unittest.TestCase):
    def test_postgres_gets_connect_timeout(self):
        self.assertEqual(connect_args_for(UNREACHABLE), {"connect_timeout": 3})

    def test_sqlite_gets_no_connect_args(self):
        self.assertEqual(connect_args_for("sqlite://"), {})


class CheckDbTest(unittest.TestCase):
    def test_unreachable_postgres_is_false_and_fast(self):
        engine = make_engine(UNREACHABLE)
        start = time.monotonic()
        self.assertFalse(check_db(engine))
        self.assertLess(time.monotonic() - start, 5)

    @unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")
    def test_postgres_roundtrip(self):
        from vela.config import Settings
        self.assertTrue(check_db(make_engine(Settings.from_env().database_url)))
