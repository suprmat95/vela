import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

ROOT = os.path.join(os.path.dirname(__file__), "..")
INI = os.path.join(ROOT, "alembic.ini")


def alembic_config():
    return Config(INI)


def versions(url):
    engine = create_engine(url)
    with engine.connect() as conn:
        if "alembic_version" not in inspect(conn).get_table_names():
            return None
        return [row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version"))]


class ScriptsTest(unittest.TestCase):
    def test_single_head_is_initial_revision(self):
        heads = ScriptDirectory.from_config(alembic_config()).get_heads()
        self.assertEqual(heads, ["0006"])

    def test_ini_paths_do_not_depend_on_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run([sys.executable, "-m", "alembic", "-c", os.path.abspath(INI), "heads"],
                                 cwd=tmp, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("0006", res.stdout)


class SqliteUpgradeTest(unittest.TestCase):
    def test_upgrade_head_then_downgrade_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                self.assertEqual(versions(url), ["0006"])
                with create_engine(url).connect() as conn:
                    tables = inspect(conn).get_table_names()
                    self.assertIn("orders", tables)
                    self.assertNotIn("stripe_events", tables)   # creata da 0003, tolta da 0004
                    self.assertIn("jobs", tables)
                    self.assertIn("quota_window", tables)
                    order_cols = {c["name"]: c for c in inspect(conn).get_columns("orders")}
                    self.assertIn("enqueued_at", order_cols)
                    self.assertIn("replacement_proposal_id", order_cols)
                    self.assertTrue(order_cols["total"]["nullable"])
                    product_cols = {c["name"]: c for c in inspect(conn).get_columns("products")}
                    self.assertTrue(product_cols["brand"]["nullable"])
                command.downgrade(alembic_config(), "base")
                self.assertEqual(versions(url), [])

    def test_upgrade_keeps_existing_loggers_enabled(self):
        import logging
        logger = logging.getLogger("vela.test_migrations_probe")
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
        self.assertFalse(logger.disabled)

    def test_downgrade_from_0006_removes_products_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0005")
                with create_engine(url).connect() as conn:
                    cols = {c["name"] for c in inspect(conn).get_columns("products")}
                    self.assertNotIn("brand", cols)
                    self.assertIn("provider_id", cols)

    def test_downgrade_from_0005_removes_queue_tables_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0004")
                with create_engine(url).connect() as conn:
                    tables = inspect(conn).get_table_names()
                    self.assertNotIn("jobs", tables)
                    self.assertNotIn("quota_window", tables)
                    cols = {c["name"] for c in inspect(conn).get_columns("orders")}
                    self.assertNotIn("enqueued_at", cols)
                    self.assertNotIn("replacement_proposal_id", cols)

    def test_downgrade_from_0004_restores_stripe_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                command.downgrade(alembic_config(), "0003")
                with create_engine(url).connect() as conn:
                    self.assertIn("stripe_events", inspect(conn).get_table_names())

    def test_upgrade_without_database_url_fails_explicitly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                command.upgrade(alembic_config(), "head")
        self.assertIn("DATABASE_URL", str(ctx.exception))


class PostgresUpgradeTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DATABASE_URL"), "serve DATABASE_URL")
    def test_upgrade_head_is_idempotent(self):
        from vela.config import Settings
        command.upgrade(alembic_config(), "head")
        command.upgrade(alembic_config(), "head")
        self.assertEqual(versions(Settings.from_env().database_url), ["0006"])
