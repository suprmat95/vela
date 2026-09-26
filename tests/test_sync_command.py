"""`python -m vela.sync` (M10, RF-30, RF-32): sync forzato, registrazione delle fixture, dry-run."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from hofj_samples import item
from test_fixtures_record import QuotaSource
from vela import sync as sync_module
from vela.adapters.repo_memory import MemoryRepositories

KEY = "hofj-chiave-segreta"
ENV = {"HOFJ_API_KEY": KEY, "HOFJ_BASE_URL": "https://api.hofj.com",
       "HOFJ_BRANDS": "padel=weebora.com,tennis=terrarossa.com", "DATABASE_URL": "sqlite://"}


def fixtures_dir():
    """Una fixture padel di produzione (3 prodotti, 2 attivi); nessuna fixture tennis."""
    folder = tempfile.mkdtemp()
    items = [item(1), item(2), item(3, archived=True)]
    with open(os.path.join(folder, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump({"base_url": "https://api.hofj.com", "locale": "it", "brand": "weebora.com",
                   "sport": "padel", "products": items,
                   "details": {i["id"]: {"catalog": i, "raw": i} for i in items[:2]}}, fh)
    return folder


def run_main(argv, env=ENV, source=None, repos=None):
    out, err = io.StringIO(), io.StringIO()
    folder = fixtures_dir()
    source = source or QuotaSource({"weebora.com": [[item(1)]], "terrarossa.com": [[item(11)]]})
    code = 0
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(sync_module, "FIXTURES_DIR", folder), \
            mock.patch.object(sync_module, "http_source", lambda settings, locale: source), \
            mock.patch.object(sync_module, "database_repositories",
                              lambda settings: repos or MemoryRepositories()), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            sync_module.main(argv)
        except SystemExit as exc:   # sys.exit("…") stampa il messaggio solo all'uscita vera
            code = 1 if isinstance(exc.code, str) else exc.code
            if isinstance(exc.code, str):
                err.write(exc.code)
    return code, out.getvalue() + err.getvalue(), source, folder


class DryRunTest(unittest.TestCase):
    def test_prints_the_plan_per_brand_without_calls(self):
        code, text, source, _ = run_main(["--dry-run"], env=dict(ENV, HOFJ_API_KEY=""))
        self.assertIn(code, (0, None))
        self.assertEqual(source.calls, [])
        self.assertIn("weebora.com (padel): 1 pagine, al più 2 dettagli", text)
        self.assertIn("terrarossa.com (tennis): nessuna fixture", text)
        self.assertIn("1 /v1/quota", text)

    def test_record_dry_run_is_limited_to_the_chosen_sport(self):
        _, text, source, _ = run_main(["--record", "--sport", "tennis", "--dry-run"])
        self.assertEqual(source.calls, [])
        self.assertIn("terrarossa.com", text)
        self.assertNotIn("weebora.com", text)


class ConfigErrorsTest(unittest.TestCase):
    def test_missing_key_exits_before_any_call(self):
        code, text, source, _ = run_main([], env=dict(ENV, HOFJ_API_KEY=""))
        self.assertNotIn(code, (0, None))
        self.assertIn("HOFJ_API_KEY", text)
        self.assertEqual(source.calls, [])

    def test_invalid_brand_map_or_old_variable(self):
        for env in (dict(ENV, HOFJ_BRANDS="golf=golf.com"),
                    {k: v for k, v in dict(ENV, HOFJ_BRAND="weebora.com").items() if k != "HOFJ_BRANDS"}):
            with self.subTest(env=env.get("HOFJ_BRANDS")):
                code, text, source, _ = run_main([], env=env)
                self.assertNotIn(code, (0, None))
                self.assertIn("HOFJ_BRAND", text)
                self.assertNotIn(KEY, text)
                self.assertEqual(source.calls, [])

    def test_unknown_sport_for_record(self):
        code, text, _, _ = run_main(["--record", "--sport", "golf"])
        self.assertNotIn(code, (0, None))
        self.assertIn("golf", text)

    def test_sync_needs_a_database(self):
        env = {k: v for k, v in ENV.items() if k != "DATABASE_URL"}
        code, text, source, _ = run_main([], env=env)
        self.assertNotIn(code, (0, None))
        self.assertIn("DATABASE_URL", text)
        self.assertEqual(source.calls, [])


class RunTest(unittest.TestCase):
    def test_sync_writes_both_brands_and_prints_the_report(self):
        repos = MemoryRepositories()
        code, text, source, _ = run_main([], repos=repos)
        self.assertIn(code, (0, None))
        self.assertEqual(sorted((p.id, p.brand) for p in repos.products.list_all()),
                         [("1", "weebora.com"), ("11", "terrarossa.com")])
        self.assertEqual(source.calls[0], ("quota",))
        self.assertIn("chiamate HofJ: 5", text)          # quota + 2 liste + 2 dettagli
        self.assertNotIn(KEY, text)

    def test_failed_brand_exits_with_an_error(self):
        source = QuotaSource({"weebora.com": [[item(1)]], "terrarossa.com": [[item(11)]]})
        from vela.ports.hofj import UpstreamError
        source.fail[("detail", "11")] = UpstreamError("503")
        code, text, _, _ = run_main([], source=source)
        self.assertEqual(code, 1)
        self.assertIn("terrarossa.com", text)

    def test_record_writes_the_fixture_of_the_chosen_sport(self):
        out = tempfile.mkdtemp()
        code, text, source, _ = run_main(["--record", "--sport", "tennis", "--out-dir", out])
        self.assertIn(code, (0, None))
        self.assertEqual(os.listdir(out), ["catalog-tennis.json"])
        self.assertNotIn(("list", "weebora.com", None), source.calls)
        self.assertIn("catalog-tennis.json", text)


if __name__ == "__main__":
    unittest.main()
