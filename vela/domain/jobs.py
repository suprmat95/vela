"""Processore dei job (RF-47, RF-50): un giro preleva un job, prende i gettoni e lo esegue.

Nessuna chiamata a HofJ parte senza gettoni presi dal token bucket condiviso (RF-37, M18): un
acquisto prende i gettoni dei passi che restano, una prenotazione un gettone della classe
`booking` (che non lascia la soglia agli acquisti). Senza gettoni il job torna in coda
all'istante in cui un acquisto potrà partire, senza contare un tentativo. Un 429 svuota il
bucket (RF-38) e il job non si ripete subito.

`GET /v1/quota` (RF-36) si chiama al boot e dopo un 429, mai in ciclo. Dopo un 429 la rilettura
è una sola per il cluster (`claim_refresh` prende il gettone e spegne la richiesta nello stesso
passo). Se la rilettura riceve un 429 il bucket resta fermo una finestra intera; se fallisce
altrimenti si riprova dopo una finestra e intanto si lavora con il bucket che si ha.
I gettoni presi e non usati (job interrotto a metà) non tornano nel bucket.
"""
from dataclasses import replace
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple

from vela.domain.models import Job, JobKind, JobStatus, QuotaClass
from vela.domain.purchase import calls_needed
from vela.domain.quota import WINDOW
from vela.ports.hofj import HofJError, HofJRouter, QuotaError
from vela.ports.repositories import Repositories


def quota_needs(job: Job) -> Tuple[Optional[QuotaClass], int]:
    if job.kind == JobKind.PURCHASE:
        return QuotaClass.PURCHASE, calls_needed(job)
    if job.kind == JobKind.BOOKING:
        return QuotaClass.BOOKING, 1
    return None, 0      # verifica del pagamento e SMS: nessuna chiamata HofJ


class JobProcessor:
    def __init__(self, repos: Repositories, hofj: HofJRouter, handlers: Dict[JobKind, object],
                 now: Callable[[], datetime], lease_seconds: int = 180):
        self.repos, self.hofj, self.handlers = repos, hofj, handlers
        self.now, self.lease_seconds = now, lease_seconds
        self._refresh_after: Optional[datetime] = None

    def refresh_quota(self) -> bool:
        """Al boot: legge `/v1/quota` prendendo un gettone `booking`; allinea il bucket condiviso."""
        quota, now = self.repos.quota, self.now()
        if not quota.acquire(QuotaClass.BOOKING, 1, now):
            quota.mark_refresh_needed(now)
            return False
        return self._read_quota(now)

    def _refresh_if_needed(self, now: datetime) -> None:
        """Dopo un 429: una sola rilettura per il cluster, quando c'è un gettone `booking`."""
        quota = self.repos.quota
        if not quota.needs_refresh(now) or (self._refresh_after is not None and now < self._refresh_after):
            return
        if quota.claim_refresh(now):
            self._read_quota(now)

    def _read_quota(self, now: datetime) -> bool:
        quota = self.repos.quota
        try:
            snapshot = self.hofj.get_quota()
        except QuotaError:
            quota.on_429(now, hold_seconds=WINDOW.total_seconds())
            self._refresh_after = now + WINDOW
            return False
        except HofJError:
            quota.mark_refresh_needed(now)
            self._refresh_after = now + WINDOW
            return False
        quota.sync_from_snapshot(snapshot, self.now())
        self._refresh_after = None
        return True

    def run_once(self) -> bool:
        """Un giro del worker. False se non c'era nulla da fare."""
        now = self.now()
        quota = self.repos.quota
        self._refresh_if_needed(now)
        job = self.repos.jobs.claim(now, self.lease_seconds)
        if job is None:
            return False
        cls, needed = quota_needs(job)
        if needed and not quota.acquire(cls, needed, now):
            self.repos.jobs.save(replace(job, status=JobStatus.PENDING, locked_at=None,
                                         run_after=quota.next_window_start(now, cls, needed)))
            return True
        # un errore di rete o un 5xx si ripete non prima di una finestra (RF-46)
        retry_at = max(quota.next_window_start(now), now + WINDOW)
        result = self.handlers[job.kind].run(job, retry_at)
        if result.hit_429:   # RF-38: bucket svuotato; il job riparte quando il bucket lo consente
            later = self.now()
            quota.on_429(later)
            self.repos.jobs.save(replace(result.job, run_after=quota.next_window_start(later, cls, needed)))
        return True
