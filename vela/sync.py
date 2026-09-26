"""Sync incrementale multi-brand del catalogo HofJ (M10, RF-28..31).

Per ogni brand di `HOFJ_BRANDS`: lista paginata, dettaglio esteso solo per i prodotti nuovi, con
`updatedAt` cambiato o archiviati e poi ricomparsi; scrittura per lotti nella tabella `products`
con il brand e lo sport della mappa. I prodotti invariati ricevono solo brand, sport e
`fetched_at` (anche le righe pre-M10 con brand NULL, senza dettaglio). A lista completa i prodotti
spariti si archiviano tra quelli del brand; un brand con errori non archivia nulla e non tocca gli
altri, e una lista senza prodotti attivi è un errore. Un id già presente con un altro brand
ferma quel brand (decisione M10 sulla chiave).

Un solo sync alla volta fra tutte le istanze (advisory lock, RF-30). Ogni chiamata prende uno slot `SYNC` della quota condivisa (§4.8): cede il passo agli acquisti
in attesa e aspetta la finestra successiva; un 429 marca la finestra e non si ripete subito.
"""
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from vela.domain.catalog import product_from_entry, project_detail, strip_media
from vela.domain.models import Product, QuotaClass
from vela.ports.catalog import CatalogSource
from vela.ports.hofj import ConfigError, HofJError, QuotaError

log = logging.getLogger(__name__)

BATCH_SIZE = 25
SYNC_INTERVAL = timedelta(hours=6)     # RF-30: al boot se più vecchio, poi ogni 6 h
RETRY_AFTER = timedelta(minutes=15)    # giro fallito o saltato: si riprova prima


class BrandConflict(Exception):
    """Un id della lista di un brand appartiene già a un altro brand."""


@dataclass
class BrandReport:
    sport: str
    brand: str
    pages: int = 0
    details: int = 0
    written: int = 0
    unchanged: int = 0
    archived: int = 0
    error: Optional[str] = None


@dataclass
class SyncReport:
    brands: List[BrandReport] = field(default_factory=list)
    calls: int = 0
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return not self.skipped and all(b.error is None for b in self.brands)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CatalogSync:
    def __init__(self, source: CatalogSource, repos, brands: Dict[str, str],
                 now: Callable[[], datetime] = _utcnow, sleep: Callable[[float], None] = time.sleep,
                 batch_size: int = BATCH_SIZE):
        self.source, self.repos, self.brands = source, repos, brands
        self.now, self.sleep, self.batch_size = now, sleep, batch_size

    def run(self) -> SyncReport:
        """Un giro su tutti i brand, sotto l'advisory lock: se un altro sync lo tiene, niente."""
        with self.repos.catalog_lock() as acquired:
            if not acquired:
                log.info("sync saltato: un altro sync del catalogo è in corso")
                return SyncReport(skipped=True)
            return self._run()

    def _run(self) -> SyncReport:
        report = SyncReport()
        for sport, brand in self.brands.items():
            brand_report = BrandReport(sport, brand)
            report.brands.append(brand_report)
            try:
                self._sync_brand(brand_report, report)
            except ConfigError as exc:
                brand_report.error = str(exc)
                log.error("sync %s: %s, giro interrotto", brand, exc)
                break
            except (HofJError, BrandConflict) as exc:
                brand_report.error = str(exc)
            log.info("sync %s (%s): pagine=%d dettagli=%d scritti=%d invariati=%d archiviati=%d%s",
                     brand, sport, brand_report.pages, brand_report.details, brand_report.written,
                     brand_report.unchanged, brand_report.archived,
                     " errore=%s" % brand_report.error if brand_report.error else "")
        return report

    # --- un brand --------------------------------------------------------------------------

    def _sync_brand(self, br: BrandReport, report: SyncReport) -> None:
        seen: List[str] = []
        pending: List[Product] = []
        try:
            for items in self._pages(br, report):
                active = [i for i in items if not i.get("archived")]
                state = self.repos.products.sync_state([str(i["id"]) for i in active])
                unchanged = []
                for entry in active:
                    pid = str(entry["id"])
                    known = state.get(pid)
                    if known is not None and known.brand not in (None, br.brand):
                        raise BrandConflict("il prodotto %s del brand %s è già del brand %s"
                                            % (pid, br.brand, known.brand))
                    seen.append(pid)
                    if known is None or known.archived or known.updated_at != entry.get("updatedAt"):
                        pending.append(self._download(br, report, pid))
                        if len(pending) >= self.batch_size:
                            self._write(br, pending)
                    else:
                        unchanged.append(pid)
                self.repos.products.mark_seen(unchanged, br.brand, br.sport, self.now())
                br.unchanged += len(unchanged)
        finally:
            self._write(br, pending)
        if not seen:   # una lista vuota per errore archivierebbe tutto il brand
            raise HofJError("lista %s: nessun prodotto attivo, niente archiviazione" % br.brand)
        br.archived = self.repos.products.archive_missing(seen, brand=br.brand)

    def _pages(self, br: BrandReport, report: SyncReport):
        cursor, cursors = None, set()
        while True:
            items, cursor = self._call(report, lambda c=cursor: self.source.list_page(br.brand, c))
            br.pages += 1
            yield items
            if not cursor:
                return
            if cursor in cursors:
                raise HofJError("lista %s: cursore ripetuto %r" % (br.brand, cursor))
            cursors.add(cursor)

    def _download(self, br: BrandReport, report: SyncReport, pid: str) -> Product:
        detail = self._call(report, lambda: self.source.detail(br.brand, pid))
        br.details += 1
        return product_from_entry(project_detail(detail), archived=False, raw=strip_media(detail),
                                  fetched_at=self.now(), brand=br.brand, sport=br.sport)

    def _write(self, br: BrandReport, pending: List[Product]) -> None:
        if pending:
            self.repos.products.upsert_many(list(pending))
            br.written += len(pending)
            pending.clear()

    # --- quota ----------------------------------------------------------------------------------

    def _call(self, report: SyncReport, fn):
        """Una chiamata HofJ con uno slot `SYNC`: senza slot o dopo un 429 si attende la finestra
        successiva e si riprova."""
        quota = self.repos.quota
        while True:
            now = self.now()
            if not quota.acquire(QuotaClass.SYNC, 1, now,
                                 purchase_waiting=self.repos.jobs.purchase_waiting()):
                self._wait(now)
                continue
            report.calls += 1
            try:
                return fn()
            except QuotaError:
                quota.on_429(now)
                self._wait(now)

    def _wait(self, now: datetime) -> None:
        seconds = (self.repos.quota.next_window_start(now) - now).total_seconds()
        self.sleep(max(seconds, 1.0))


class SyncScheduler:
    """Thread in background del live (RF-30). A ogni `tick`: se il catalogo è vuoto o più
    vecchio di `interval` esegue un giro, poi dice quanti secondi aspettare. Ogni istanza ha il
    suo scheduler; l'advisory lock del sync fa girare una sola istanza alla volta."""

    def __init__(self, sync, repos, now: Callable[[], datetime] = _utcnow,
                 interval: timedelta = SYNC_INTERVAL, retry_after: timedelta = RETRY_AFTER):
        self.sync, self.repos, self.now = sync, repos, now
        self.interval, self.retry_after = interval, retry_after
        self._stop = threading.Event()
        self.wait = self._stop.wait

    def tick(self) -> float:
        last = self.repos.products.last_fetched_at()
        if last is not None:
            age = self.now() - last
            if age < self.interval:
                return (self.interval - age).total_seconds()
        try:
            report = self.sync.run()
        except Exception:   # il thread non deve morire: si logga e si riprova
            log.exception("sync del catalogo fallito")
            return self.retry_after.total_seconds()
        if not report.ok:
            return self.retry_after.total_seconds()
        return self.interval.total_seconds()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            self.wait(self.tick())

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_forever, name="vela-catalog-sync", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()


# --- comando: python -m vela.sync ------------------------------------------------------------

from vela.adapters.hofj_replay import FIXTURES_DIR  # noqa: E402
from vela.config import Settings, live_brands  # noqa: E402

USAGE = """Sync del catalogo HofJ (M10). Senza opzioni: un giro su tutti i brand di HOFJ_BRANDS
nel database di DATABASE_URL. Con --record: una fixture per brand in --out-dir, senza database.
--dry-run stampa le chiamate previste e non ne fa nessuna. La chiave HOFJ_API_KEY non viene mai
stampata."""


class _CountingSource:
    """Conta le chiamate HofJ vere del comando, `/v1/quota` compresa."""

    def __init__(self, source):
        self.source, self.calls = source, 0

    def list_page(self, brand, cursor):
        self.calls += 1
        return self.source.list_page(brand, cursor)

    def detail(self, brand, product_id):
        self.calls += 1
        return self.source.detail(brand, product_id)

    def get_quota(self):
        self.calls += 1
        return self.source.get_quota()


def http_source(settings: Settings, locale: str):
    from vela.adapters.hofj_http import HofJHttp
    brand = next(iter(live_brands(settings).values()))   # il brand vero arriva a ogni chiamata
    return HofJHttp(settings.hofj_base_url, settings.hofj_api_key, brand, locale=locale)


def database_repositories(settings: Settings):
    from vela.adapters.db import make_engine
    from vela.adapters.repo_postgres import PostgresRepositories
    return PostgresRepositories(make_engine(settings.database_url), quota_margin=settings.quota_margin,
                                booking_reserve=settings.booking_reserve,
                                quota_burst=settings.quota_burst, quota_floor=settings.quota_floor)


def _host_fixtures(base_url: str) -> Dict[str, str]:
    from vela.domain.catalog import fixture_meta, select_fixtures
    try:
        paths = select_fixtures(FIXTURES_DIR, base_url)
    except RuntimeError:
        return {}
    return {fixture_meta(path)["brand"]: path for path in paths}


def plan(brands: Dict[str, str], base_url: str) -> List[str]:
    """Chiamate previste per brand, stimate dalla fixture dell'host se c'è: le pagine sono
    esatte a catalogo invariato, i dettagli un tetto (il sync scarica solo nuovi e cambiati)."""
    import json
    fixtures = _host_fixtures(base_url)
    lines = ["1 /v1/quota"]
    for sport, brand in brands.items():
        path = fixtures.get(brand)
        if path is None:
            lines.append("%s (%s): nessuna fixture, pagine e dettagli sconosciuti "
                         "(una pagina ogni 100 prodotti, un dettaglio per prodotto attivo)" % (brand, sport))
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        total, active = len(data.get("products") or []), len(data.get("details") or {})
        lines.append("%s (%s): %d pagine, al più %d dettagli (fixture: %d prodotti, %d attivi)"
                     % (brand, sport, max(1, -(-total // 100)), active, total, active))
    return lines


def _locale(base_url: str, wanted: Optional[str]) -> str:
    if wanted:
        return wanted
    from vela.domain.catalog import fixture_meta
    fixtures = _host_fixtures(base_url)
    return fixture_meta(next(iter(fixtures.values())))["locale"] if fixtures else "it"


def main(argv: Optional[List[str]] = None) -> None:
    import argparse
    import sys
    parser = argparse.ArgumentParser(prog="python -m vela.sync", description=USAGE)
    parser.add_argument("--record", action="store_true", help="registra le fixture invece del database")
    parser.add_argument("--sport", help="solo il brand di questo sport (padel o tennis)")
    parser.add_argument("--out-dir", default=FIXTURES_DIR, help="cartella delle fixture (--record)")
    parser.add_argument("--locale", help="locale delle chiamate (default: quello delle fixture dell'host)")
    parser.add_argument("--dry-run", action="store_true", help="stampa le chiamate previste, nessuna rete")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = Settings.from_env()
    if not settings.hofj_base_url:
        sys.exit("manca HOFJ_BASE_URL")
    try:
        brands = live_brands(settings)
    except ValueError as exc:
        sys.exit(str(exc))
    if args.sport:
        if args.sport not in brands:
            sys.exit("sport %s non presente in HOFJ_BRANDS" % args.sport)
        brands = {args.sport: brands[args.sport]}
    base_url = settings.hofj_base_url.rstrip("/")
    locale = _locale(base_url, args.locale)
    print("%s su %s, locale %s. Chiamate previste:" % ("Registrazione" if args.record else "Sync",
                                                       base_url, locale))
    for line in plan(brands, base_url):
        print("  " + line)
    if args.dry_run:
        return
    if not args.record and not settings.database_url:
        sys.exit("manca DATABASE_URL: il sync scrive nel database (per le fixture usare --record)")
    if not settings.hofj_api_key:
        sys.exit("manca HOFJ_API_KEY")

    source = _CountingSource(http_source(settings, locale))
    if args.record:
        from vela.fixtures import RecordError, record_fixtures
        try:
            paths = record_fixtures(source, brands, base_url, locale, args.out_dir)
        except RecordError as exc:
            print(str(exc))
            print("chiamate HofJ: %d" % source.calls)
            sys.exit(1)
        for path in paths:
            print("scritta %s (%d byte)" % (path, os.path.getsize(path)))
        print("chiamate HofJ: %d" % source.calls)
        return

    repos = database_repositories(settings)
    if repos.quota.acquire(QuotaClass.SYNC, 1, _utcnow()):
        repos.quota.sync_from_snapshot(source.get_quota(), _utcnow())
    report = CatalogSync(source, repos, brands).run()
    for b in report.brands:
        print("%s (%s): pagine %d, dettagli %d, scritti %d, invariati %d, archiviati %d%s"
              % (b.brand, b.sport, b.pages, b.details, b.written, b.unchanged, b.archived,
                 ", errore: %s" % b.error if b.error else ""))
    if report.skipped:
        print("saltato: un altro sync è in corso")
    print("chiamate HofJ: %d" % source.calls)
    if not report.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
