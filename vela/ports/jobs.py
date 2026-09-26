"""Porta verso la coda dei job del worker (RF-27, RF-50).

`claim` preleva un job alla volta: prima i `booking` (RF-51), poi le verifiche di pagamento,
poi gli acquisti in ordine di arrivo (`enqueued_at`, RF-47). Un job `running` il cui lease è
scaduto (istanza morta a metà) torna prelevabile e riparte dal passo salvato (RF-27).
"""
from datetime import datetime
from typing import Optional, Protocol

from vela.domain.models import Job, JobKind


class DuplicateJob(Exception):
    """L'ordine ha già un job `booking` attivo (RF-51); il database lo garantisce con un indice
    unico parziale (migrazione 0009)."""


class JobRepository(Protocol):
    def enqueue(self, job: Job) -> None:
        """Solleva `DuplicateJob` se l'ordine ha già un job `booking` `pending` o `running`."""
    def get(self, job_id: str) -> Optional[Job]: ...
    def save(self, job: Job) -> None: ...
    def claim(self, now: datetime, lease_seconds: int) -> Optional[Job]: ...
    def active_for_order(self, order_id: str, kind: JobKind) -> Optional[Job]: ...
    def queued_purchase_position(self, order_id: str) -> Optional[int]: ...
    def purchase_waiting(self) -> bool: ...
    def oldest_purchase_enqueued_at(self) -> Optional[datetime]:
        """`enqueued_at` del più vecchio acquisto attivo: l'età della coda in `/health` (M18)."""
