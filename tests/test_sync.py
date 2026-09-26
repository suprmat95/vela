"""Sync incrementale multi-brand del catalogo (M10, RF-28..31) con sorgente finta: mai la rete."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from hofj_samples import detail_of, item
from support import make_product
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.models import Job, JobKind, JobStatus, QuotaClass
from vela.ports.hofj import ConfigError, QuotaError, UpstreamError
from vela.sync import CatalogSync

T0 = datetime(2026, 9, 26, 12, 0, 30, tzinfo=timezone.utc)
BRANDS = {"padel": "weebora.com", "tennis": "terrarossa.com"}


class Clock:
    """Orologio finto: `sleep` lo fa avanzare, così le attese della quota non bloccano i test."""

    def __init__(self, start=T0):
        self.t, self.slept = start, []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += timedelta(seconds=seconds)


class FakeSource:
    """`CatalogSource` finto: pagine per brand, dettagli per id, guasti programmati."""

    def __init__(self, pages, details=None):
        self.pages = pages                        # {brand: [[item, ...], [item, ...]]}
        self.details = details or {}
        self.calls = []
        self.fail = {}                            # {("detail", id) | ("list", brand): errore}

    def list_page(self, brand, cursor):
        self.calls.append(("list", brand, cursor))
        if ("list", brand) in self.fail:
            raise self.fail[("list", brand)]
        pages = self.pages[brand]
        n = int(cursor) if cursor else 0
        return pages[n], (str(n + 1) if n + 1 < len(pages) else None)

    def detail(self, brand, product_id):
        self.calls.append(("detail", brand, product_id))
        error = self.fail.get(("detail", product_id))
        if error is not None:
            raise error
        return self.details.get(product_id) or detail_of(self._listed(brand, product_id))

    def _listed(self, brand, product_id):
        return next(i for page in self.pages[brand] for i in page if i["id"] == product_id)

    def detail_calls(self):
        return [c[2] for c in self.calls if c[0] == "detail"]


class CountingProducts:
    """Avvolge il repository dei prodotti e conta i lotti scritti."""

    def __init__(self, inner):
        self.inner, self.batches = inner, []

    def upsert_many(self, products):
        products = list(products)
        self.batches.append([p.id for p in products])
        self.inner.upsert_many(products)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def two_brands():
    return FakeSource({"weebora.com": [[item(1), item(2), item(3, archived=True)]],
                       "terrarossa.com": [[item(11, title="Rafa Nadal Academy"), item(12)]]})


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.repos = MemoryRepositories()
        self.clock = Clock()

    def sync(self, source, brands=BRANDS, **kw):
        return CatalogSync(source, self.repos, brands, now=self.clock, sleep=self.clock.sleep, **kw)

    def products(self):
        return {p.id: p for p in self.repos.products.list_all()}

    # --- lock --------------------------------------------------------------------------------

    def test_skips_when_another_sync_holds_the_lock(self):
        source = two_brands()
        with self.repos.catalog_lock():
            report = self.sync(source).run()
        self.assertTrue(report.skipped)
        self.assertFalse(report.ok)
        self.assertEqual((source.calls, self.products()), ([], {}))

    def test_releases_the_lock_after_a_run(self):
        self.sync(two_brands()).run()
        with self.repos.catalog_lock() as free:
            self.assertTrue(free)

    # --- scrittura --------------------------------------------------------------------------

    def test_writes_both_brands_with_brand_and_sport_from_the_map(self):
        report = self.sync(two_brands()).run()
        got = {pid: (p.brand, p.sport, p.archived) for pid, p in self.products().items()}
        self.assertEqual(got, {"1": ("weebora.com", "padel", False), "2": ("weebora.com", "padel", False),
                               "11": ("terrarossa.com", "tennis", False),
                               "12": ("terrarossa.com", "tennis", False)})
        self.assertEqual([(b.brand, b.written, b.error) for b in report.brands],
                         [("weebora.com", 2, None), ("terrarossa.com", 2, None)])

    def test_details_only_for_active_products(self):
        source = two_brands()
        self.sync(source).run()
        self.assertEqual(source.detail_calls(), ["1", "2", "11", "12"])

    def test_written_product_comes_from_the_extended_detail(self):
        self.sync(two_brands()).run()
        p = self.products()["1"]
        self.assertEqual((p.destination, p.hotel, p.fetched_at), ("Sinalunga", "Hotel Uno", T0))
        self.assertNotIn("gallery", p.raw)

    def test_follows_the_cursor_across_pages(self):
        source = FakeSource({"weebora.com": [[item(1)], [item(2)], [item(3)]]})
        report = self.sync(source, {"padel": "weebora.com"}).run()
        self.assertEqual([c for c in source.calls if c[0] == "list"],
                         [("list", "weebora.com", None), ("list", "weebora.com", "1"),
                          ("list", "weebora.com", "2")])
        self.assertEqual(report.brands[0].pages, 3)
        self.assertEqual(sorted(self.products()), ["1", "2", "3"])

    def test_writes_in_batches(self):
        products = CountingProducts(self.repos.products)
        self.repos.products = products
        source = FakeSource({"weebora.com": [[item(n) for n in range(1, 6)]]})
        self.sync(source, {"padel": "weebora.com"}, batch_size=2).run()
        self.assertEqual(products.batches, [["1", "2"], ["3", "4"], ["5"]])

    # --- incrementale -----------------------------------------------------------------------

    def test_second_run_downloads_only_new_or_changed_products(self):
        first = FakeSource({"weebora.com": [[item(1), item(2)]]})
        self.sync(first, {"padel": "weebora.com"}).run()
        self.clock.t += timedelta(hours=6)
        second = FakeSource({"weebora.com": [[item(1), item(2, updatedAt="2026-09-26T08:00:00.000Z"),
                                               item(4)]]})
        report = self.sync(second, {"padel": "weebora.com"}).run()
        self.assertEqual(second.detail_calls(), ["2", "4"])
        self.assertEqual(report.brands[0].unchanged, 1)
        self.assertEqual({pid: p.fetched_at for pid, p in self.products().items()},
                         {"1": self.clock.t, "2": self.clock.t, "4": self.clock.t})

    def test_pre_m10_row_is_relabelled_without_a_detail(self):
        self.repos.products.upsert_many([make_product(11, sport="padel",
                                                      updated_at="2026-09-25T09:20:18.757Z")])
        source = FakeSource({"terrarossa.com": [[item(11)]]})
        self.sync(source, {"tennis": "terrarossa.com"}).run()
        self.assertEqual(source.detail_calls(), [])
        p = self.products()["11"]
        self.assertEqual((p.brand, p.sport, p.fetched_at), ("terrarossa.com", "tennis", T0))

    def test_archived_product_that_comes_back_is_downloaded_again(self):
        self.repos.products.upsert_many([make_product(1, brand="weebora.com", archived=True,
                                                      updated_at="2026-09-25T09:20:18.757Z")])
        source = FakeSource({"weebora.com": [[item(1)]]})
        self.sync(source, {"padel": "weebora.com"}).run()
        self.assertEqual(source.detail_calls(), ["1"])
        self.assertFalse(self.products()["1"].archived)

    # --- archiviazione per brand ------------------------------------------------------------

    def test_product_missing_from_its_brand_is_archived_only_there(self):
        self.repos.products.upsert_many([make_product(9, brand="weebora.com"),
                                         make_product(19, brand="terrarossa.com")])
        report = self.sync(FakeSource({"weebora.com": [[item(1)]], "terrarossa.com": [[item(19)]]})).run()
        archived = {pid: p.archived for pid, p in self.products().items()}
        self.assertEqual(archived, {"1": False, "9": True, "19": False})
        self.assertEqual([b.archived for b in report.brands], [1, 0])

    def test_archived_in_the_list_is_archived_in_the_catalog(self):
        self.repos.products.upsert_many([make_product(3, brand="weebora.com")])
        self.sync(FakeSource({"weebora.com": [[item(1), item(3, archived=True)]]}),
                  {"padel": "weebora.com"}).run()
        self.assertTrue(self.products()["3"].archived)

    def test_failing_brand_archives_nothing_and_leaves_the_other_brand_alone(self):
        self.repos.products.upsert_many([make_product(9, brand="weebora.com")])
        source = FakeSource({"weebora.com": [[item(1), item(2)]], "terrarossa.com": [[item(11)]]})
        source.fail[("detail", "2")] = UpstreamError("HofJ GET /v1/products/2: 503")
        report = self.sync(source).run()
        products = self.products()
        self.assertFalse(products["9"].archived)                       # niente archiviazione
        self.assertEqual(products["11"].brand, "terrarossa.com")       # l'altro brand va avanti
        self.assertIn("503", report.brands[0].error)
        self.assertIsNone(report.brands[1].error)
        self.assertFalse(report.ok)

    def test_interruption_midway_leaves_written_batches_and_a_coherent_catalog(self):
        source = FakeSource({"weebora.com": [[item(n) for n in range(1, 6)]]})
        source.fail[("detail", "4")] = UpstreamError("rete")
        self.sync(source, {"padel": "weebora.com"}, batch_size=2).run()
        products = self.products()
        self.assertEqual(sorted(products), ["1", "2", "3"])    # lotto 1-2 e lotto parziale 3
        self.assertTrue(all(p.brand == "weebora.com" and not p.archived for p in products.values()))

    def test_empty_list_archives_nothing(self):
        self.repos.products.upsert_many([make_product(9, brand="weebora.com")])
        report = self.sync(FakeSource({"weebora.com": [[item(3, archived=True)]]}),
                           {"padel": "weebora.com"}).run()
        self.assertFalse(self.products()["9"].archived)
        self.assertIn("nessun prodotto attivo", report.brands[0].error)

    def test_failing_list_is_a_brand_error(self):
        source = two_brands()
        source.fail[("list", "weebora.com")] = UpstreamError("down")
        report = self.sync(source).run()
        self.assertEqual([b.error is None for b in report.brands], [False, True])

    # --- id fra brand -------------------------------------------------------------------------

    def test_id_already_owned_by_another_brand_stops_that_brand(self):
        self.repos.products.upsert_many([make_product(2, brand="weebora.com")])
        self.repos.products.upsert_many([make_product(7, brand="terrarossa.com")])
        source = FakeSource({"terrarossa.com": [[item(11), item(2), item(12)]]})
        report = self.sync(source, {"tennis": "terrarossa.com"}).run()
        self.assertIn("2", report.brands[0].error)
        self.assertIn("weebora.com", report.brands[0].error)
        products = self.products()
        self.assertEqual(products["2"].brand, "weebora.com")
        self.assertFalse(products["7"].archived)
        self.assertNotIn("12", products)

    # --- quota -----------------------------------------------------------------------------

    def test_every_call_takes_a_sync_quota_slot(self):
        calls = []
        acquire = self.repos.quota.acquire
        self.repos.quota.acquire = lambda cls, n, now, purchase_waiting=False: (
            calls.append((cls, n, purchase_waiting)) or acquire(cls, n, now, purchase_waiting))
        source = two_brands()
        self.sync(source).run()
        self.assertEqual(len(calls), len(source.calls))
        self.assertEqual(set(calls), {(QuotaClass.SYNC, 1, False)})

    def test_waits_for_the_next_window_when_the_quota_refuses(self):
        source = FakeSource({"weebora.com": [[item(n) for n in range(1, 90)]]})
        report = self.sync(source, {"padel": "weebora.com"}).run()
        self.assertEqual(report.brands[0].written, 89)
        self.assertTrue(self.clock.slept)                        # oltre 86 chiamate di sync: attesa
        self.assertEqual(report.calls, 90)

    def test_yields_to_waiting_purchases(self):
        self.repos.jobs.enqueue(Job("j1", JobKind.PURCHASE, "o1", JobStatus.PENDING, T0, T0))
        waiting = {"n": 0}
        purchase_waiting = self.repos.jobs.purchase_waiting

        def once_then_free():
            waiting["n"] += 1
            return purchase_waiting() if waiting["n"] == 1 else False
        self.repos.jobs.purchase_waiting = once_then_free
        self.sync(FakeSource({"weebora.com": [[item(1)]]}), {"padel": "weebora.com"}).run()
        self.assertEqual(len(self.clock.slept), 1)
        self.assertIn("1", self.products())

    def test_429_marks_the_quota_and_retries_after_waiting(self):
        source = FakeSource({"weebora.com": [[item(1)]]})
        source.fail[("detail", "1")] = QuotaError("429", retry_after=10)
        marked = []
        on_429 = self.repos.quota.on_429
        self.repos.quota.on_429 = lambda now: (marked.append(now), on_429(now))

        original = source.detail

        def detail(brand, pid):
            if len(source.detail_calls()) == 1:
                source.fail.pop(("detail", "1"), None)
            return original(brand, pid)
        source.detail = detail
        report = self.sync(source, {"padel": "weebora.com"}).run()
        self.assertEqual(marked, [T0])
        self.assertTrue(self.clock.slept)
        self.assertIsNone(report.brands[0].error)
        self.assertIn("1", self.products())

    def test_config_error_stops_the_whole_run(self):
        source = two_brands()
        source.fail[("list", "weebora.com")] = ConfigError("401")
        with self.assertLogs("vela.sync", level="ERROR"):
            report = self.sync(source).run()
        self.assertEqual(len(report.brands), 1)
        self.assertIn("401", report.brands[0].error)
        self.assertEqual(self.products(), {})


if __name__ == "__main__":
    unittest.main()
