"""Processore dei job (RF-47, RF-50): un giro preleva un job, prenota la quota e lo esegue.

Nessuna chiamata a HofJ parte senza un blocco di budget prenotato nella finestra corrente
(RF-37): un acquisto prenota le chiamate dei passi che restano, una prenotazione una chiamata
della classe `booking` (che ha la riserva). Senza budget il job torna in coda per la finestra
successiva, senza contare un tentativo. Un 429 azzera il budget della finestra (RF-38).

`GET /v1/quota` (RF-36) si chiama al boot e dopo un 429, mai in ciclo: se la lettura fallisce
si riprova solo nella finestra successiva e intanto si lavora con la finestra che si ha.
Le chiamate prenotate e non usate (job interrotto a metà) non tornano nel budget.
"""
from dataclasses import replace
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple

from vela.domain.models import Job, JobKind, JobStatus, QuotaClass
from vela.domain.purchase import calls_needed
from vela.ports.hofj import HofJError, HofJPort, QuotaError
from vela.ports.repositories import Repositories


def quota_needs(job: Job) -> Tuple[Optional[QuotaClass], int]:
    if job.kind == JobKind.PURCHASE:
        return QuotaClass.PURCHASE, calls_needed(job)
    if job.kind == JobKind.BOOKING:
        return QuotaClass.BOOKING, 1
    return None, 0      # verifica del pagamento: nessuna chiamata HofJ


class JobProcessor:
    def __init__(self, repos: Repositories, hofj: HofJPort, handlers: Dict[JobKind, object],
                 now: Callable[[], datetime], lease_seconds: int = 120):
        self.repos, self.hofj, self.handlers = repos, hofj, handlers
        self.now, self.lease_seconds = now, lease_seconds
        self._refresh_after: Optional[datetime] = None

    def refresh_quota(self) -> bool:
        """Legge `/v1/quota` prenotando una chiamata `booking`; allinea la finestra condivisa."""
        quota, now = self.repos.quota, self.now()
        if not quota.acquire(QuotaClass.BOOKING, 1, now):
            self._refresh_after = quota.next_window_start(now)
            return False
        try:
            snapshot = self.hofj.get_quota()
        except QuotaError:
            quota.on_429(now)
            self._refresh_after = quota.next_window_start(now)
            return False
        except HofJError:
            self._refresh_after = quota.next_window_start(now)
            return False
        quota.sync_from_snapshot(snapshot)
        self._refresh_after = None
        return True

    def run_once(self) -> bool:
        """Un giro del worker. False se non c'era nulla da fare."""
        now = self.now()
        quota = self.repos.quota
        if quota.needs_refresh(now) and (self._refresh_after is None or now >= self._refresh_after):
            self.refresh_quota()
        job = self.repos.jobs.claim(now, self.lease_seconds)
        if job is None:
            return False
        cls, needed = quota_needs(job)
        next_window = quota.next_window_start(now)
        if needed and not quota.acquire(cls, needed, now):
            self.repos.jobs.save(replace(job, status=JobStatus.PENDING, run_after=next_window,
                                         locked_at=None))
            return True
        result = self.handlers[job.kind].run(job, next_window)
        if result.hit_429:
            quota.on_429(self.now())
        return True
