"""Accodamento degli SMS (decisione 2026-09-26): un solo job attivo per ordine e tipo.

Separato da `vela.domain.sms` perché lo usano il job d'acquisto e quello di prenotazione, e
`sms` importa `JobResult` da `purchase`.
"""
from datetime import datetime
from typing import Callable

from vela.domain.models import Job, JobKind, JobStatus
from vela.ports.repositories import Repositories


def enqueue_sms(repos: Repositories, kind: JobKind, order_id: str, now: datetime,
                new_id: Callable[[], str]) -> bool:
    """Accoda `kind` per l'ordine, se non ce n'è già uno attivo. False se c'era già."""
    if repos.jobs.active_for_order(order_id, kind) is not None:
        return False
    repos.jobs.enqueue(Job(new_id(), kind, order_id, JobStatus.PENDING, now, now))
    return True
