"""Verifica del pagamento per interrogazione (RF-20): sostituisce il webhook Stripe.

Il job d'acquisto, creato il link, accoda un job `payment_check`. Il job legge lo stato del
link (nessuna chiamata a HofJ, nessuna quota): aperto → riprova dopo `poll_seconds`; pagato →
`settle_payment` (ordine pagato e job di prenotazione, RF-51); scaduto → `expired`. Un errore
del fornitore di pagamento riprova allo stesso ritmo. Un ordine che non è più da pagare (già
pagato, annullato, scaduto) chiude il job senza chiamate.
"""
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from vela.domain.models import Job, JobStatus, OrderStatus
from vela.domain.orders import OrderService
from vela.domain.purchase import JobResult
from vela.ports.payments import PaymentsError, PaymentsPort
from vela.ports.repositories import Repositories


class PaymentCheckJob:
    def __init__(self, repos: Repositories, payments: PaymentsPort, orders: OrderService,
                 now: Callable[[], datetime], poll_seconds: int = 60):
        self.repos, self.payments, self.orders = repos, payments, orders
        self.now, self.poll_seconds = now, poll_seconds

    def run(self, job: Job, next_window: datetime) -> JobResult:
        order = self.repos.orders.get(job.order_id)
        if order is None or order.status != OrderStatus.AWAITING_PAYMENT:
            return self._save(replace(job, status=JobStatus.DONE, locked_at=None))
        try:
            status = self.payments.link_status(order.payment_ref)
        except PaymentsError as exc:
            return self._later(job, "%s: %s" % (type(exc).__name__, exc))
        if status.state == "open":
            return self._later(job, job.last_error)
        self.orders.settle_payment(order.id, status)
        return self._save(replace(job, status=JobStatus.DONE, locked_at=None))

    def _later(self, job: Job, last_error) -> JobResult:
        return self._save(replace(job, status=JobStatus.PENDING, locked_at=None, last_error=last_error,
                                  run_after=self.now() + timedelta(seconds=self.poll_seconds)))

    def _save(self, job: Job) -> JobResult:
        self.repos.jobs.save(job)
        return JobResult(job)
