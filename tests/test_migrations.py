import os
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
    cfg = Config(INI)
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    return cfg


def versions(url):
    engine = create_engine(url)
    with engine.connect() as conn:
        if "alembic_version" not in inspect(conn).get_table_names():
            return None
        return [row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version"))]


class ScriptsTest(unittest.TestCase):
    def test_single_head_is_initial_revision(self):
        heads = ScriptDirectory.from_config(alembic_config()).get_heads()
        self.assertEqual(heads, ["0001"])


class SqliteUpgradeTest(unittest.TestCase):
    def test_upgrade_head_then_downgrade_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "sqlite:///" + os.path.join(tmp, "vela.db")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(alembic_config(), "head")
                self.assertEqual(versions(url), ["0001"])
                command.downgrade(alembic_config(), "base")
                self.assertEqual(versions(url), [])

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
        self.assertEqual(versions(Settings.from_env().database_url), ["0001"])
