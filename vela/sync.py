"""Sync incrementale multi-brand del catalogo HofJ (M10, RF-28..31).

Per ogni brand di `HOFJ_BRANDS`: lista paginata, dettaglio esteso solo per i prodotti nuovi, con
`updatedAt` cambiato o archiviati e poi ricomparsi; scrittura per lotti nella tabella `products`
con il brand e lo sport della mappa. I prodotti invariati ricevono solo brand, sport e
`fetched_at` (anche le righe pre-M10 con brand NULL, senza dettaglio). A lista completa i prodotti
spariti si archiviano tra quelli del brand; un brand con errori non archivia nulla e non tocca gli
altri, e una lista senza prodotti attivi è un errore. Un id già presente con un altro brand
ferma quel brand (decisione M10 sulla chiave).

Ogni chiamata prende uno slot `SYNC` della quota condivisa (§4.8): cede il passo agli acquisti
in attesa e aspetta la finestra successiva; un 429 marca la finestra e non si ripete subito.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from vela.domain.catalog import product_from_entry, project_detail, strip_media
from vela.domain.models import Product, QuotaClass
from vela.ports.catalog import CatalogSource
from vela.ports.hofj import ConfigError, HofJError, QuotaError

log = logging.getLogger(__name__)

BATCH_SIZE = 25


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
