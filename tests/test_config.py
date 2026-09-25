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



class SettingsDefaultsTest(unittest.TestCase):
    """Parametri di M5 "configurabili" (RF-24, RF-47, RF-50): campi con default, senza env (§6)."""

    def test_m5_defaults(self):
        s = Settings.from_env({})
        self.assertEqual(s.worker_concurrency, 4)
        self.assertEqual(s.quota_margin, 0.10)
        self.assertEqual(s.booking_reserve, 0.20)
        self.assertEqual(s.purchase_max_attempts, 3)
        self.assertEqual(s.booking_max_attempts, 5)
        self.assertEqual(s.booking_backoff, (5, 10, 20, 40))
        self.assertEqual(s.job_lease_seconds, 120)
        self.assertEqual(s.payment_poll_seconds, 60)
        self.assertEqual(s.replay_latency, (0.0, 0.0))
        self.assertIsNone(s.replay_limit)

    def test_m5_parameters_are_not_read_from_environment(self):
        s = Settings.from_env({"VELA_WORKER_CONCURRENCY": "9", "WORKER_CONCURRENCY": "9",
                               "VELA_REPLAY_LIMIT": "120"})
        self.assertEqual(s.worker_concurrency, 4)
        self.assertIsNone(s.replay_limit)

    def test_m5_parameters_can_be_set_in_code(self):
        s = Settings(worker_concurrency=8, replay_limit=120, replay_latency=(2.0, 6.0))
        self.assertEqual((s.worker_concurrency, s.replay_limit, s.replay_latency), (8, 120, (2.0, 6.0)))

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
        for literal in ("'.env", '".env'):  # il nome file come stringa; `env.get` è lecito
            self.assertNotIn(literal, source)
