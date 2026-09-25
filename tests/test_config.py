import inspect
import unittest

from vela import config
from vela.config import Settings, normalize_database_url

ALL_VARS = {
    "DATABASE_URL": "postgres://u:p@h:5432/vela",
    "HOFJ_API_KEY": "k",
    "HOFJ_BASE_URL": "https://api.example.test/v1",
    "HOFJ_BRAND": "brand",
    "STRIPE_SECRET_KEY": "sk",
    "STRIPE_WEBHOOK_SECRET": "whsec",
    "VELA_API_TOKEN": "tok",
    "VELA_UPSTREAM_MODE": "live",
    "ANTHROPIC_API_KEY": "ak",
    "VELA_PUBLIC_URL": "https://vela.example.test",
}


class SettingsFromEnvTest(unittest.TestCase):
    def test_empty_environment_gives_none_and_replay_default(self):
        s = Settings.from_env({})
        self.assertIsNone(s.database_url)
        self.assertIsNone(s.hofj_api_key)
        self.assertIsNone(s.hofj_base_url)
        self.assertIsNone(s.hofj_brand)
        self.assertIsNone(s.stripe_secret_key)
        self.assertIsNone(s.stripe_webhook_secret)
        self.assertIsNone(s.vela_api_token)
        self.assertIsNone(s.anthropic_api_key)
        self.assertIsNone(s.vela_public_url)
        self.assertEqual(s.vela_upstream_mode, "replay")

    def test_all_variables_are_read(self):
        s = Settings.from_env(ALL_VARS)
        self.assertEqual(s.hofj_api_key, "k")
        self.assertEqual(s.hofj_base_url, "https://api.example.test/v1")
        self.assertEqual(s.hofj_brand, "brand")
        self.assertEqual(s.stripe_secret_key, "sk")
        self.assertEqual(s.stripe_webhook_secret, "whsec")
        self.assertEqual(s.vela_api_token, "tok")
        self.assertEqual(s.vela_upstream_mode, "live")
        self.assertEqual(s.anthropic_api_key, "ak")
        self.assertEqual(s.vela_public_url, "https://vela.example.test")

    def test_database_url_is_normalized(self):
        s = Settings.from_env(ALL_VARS)
        self.assertEqual(s.database_url, "postgresql+psycopg://u:p@h:5432/vela")

    def test_from_env_defaults_to_process_environment(self):
        self.assertIsInstance(Settings.from_env(), Settings)

    def test_settings_are_immutable(self):
        s = Settings.from_env({})
        with self.assertRaises(Exception):
            s.vela_upstream_mode = "live"


class NormalizeDatabaseUrlTest(unittest.TestCase):
    def test_postgres_scheme_gets_psycopg_driver(self):
        self.assertEqual(normalize_database_url("postgres://u:p@h/db"), "postgresql+psycopg://u:p@h/db")

    def test_postgresql_scheme_gets_psycopg_driver(self):
        self.assertEqual(normalize_database_url("postgresql://u:p@h/db"), "postgresql+psycopg://u:p@h/db")

    def test_explicit_driver_is_unchanged(self):
        self.assertEqual(normalize_database_url("postgresql+psycopg://u:p@h/db"), "postgresql+psycopg://u:p@h/db")

    def test_sqlite_is_unchanged(self):
        self.assertEqual(normalize_database_url("sqlite://"), "sqlite://")
        self.assertEqual(normalize_database_url("sqlite:////tmp/x.db"), "sqlite:////tmp/x.db")

    def test_none_is_none(self):
        self.assertIsNone(normalize_database_url(None))


class NoDotenvTest(unittest.TestCase):
    def test_module_never_reads_files(self):
        source = inspect.getsource(config)
        self.assertNotIn("open(", source)
        self.assertNotIn("dotenv", source)
        self.assertNotIn(".env", source)
