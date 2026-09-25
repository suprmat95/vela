"""Job di prenotazione (RF-23, RF-24, RF-51): chiude su HofJ un ordine pagato.

Una chiamata (`POST /v1/bookings`, classe di quota `booking`) che inoltra l'id del PaymentIntent
e lo stato del pagamento. Rete, timeout e 5xx: nuovo tentativo dopo 5, 10, 20, 40 secondi, poi
`booking_failed`. Un 4xx (prodotto o configurazione) non si ripete. Un 429 torna nella finestra
successiva senza contare il tentativo (RF-38). Un ordine che non è più `paid_pending_booking`
(già confermato da un altro job) chiude il job senza chiamate.
"""
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, Sequence

from vela.domain import say
from vela.domain.models import Job, JobStatus, Order, OrderStatus
from vela.domain.purchase import JobResult
from vela.ports.hofj import HofJPort, PaymentProof, QuotaError, UpstreamError, HofJError
from vela.ports.repositories import Repositories

BOOKING_CALLS = 1


class BookingJob:
    def __init__(self, repos: Repositories, hofj: HofJPort, now: Callable[[], datetime],
                 max_attempts: int = 5, backoff: Sequence[int] = (5, 10, 20, 40)):
        self.repos, self.hofj, self.now = repos, hofj, now
        self.max_attempts, self.backoff = max_attempts, tuple(backoff)

    def run(self, job: Job, next_window: datetime) -> JobResult:
        order = self.repos.orders.get(job.order_id)
        if order is None or order.status != OrderStatus.PAID_PENDING_BOOKING:
            return self._close(job, JobStatus.DONE)
        proof = PaymentProof(order.payment_ref or "", "succeeded")
        try:
            code = self.hofj.create_booking(order.itinerary_id, proof)
        except QuotaError as exc:
            return JobResult(self._pending(job, next_window, exc, job.attempts), hit_429=True)
        except UpstreamError as exc:
            attempts = job.attempts + 1
            if attempts >= self.max_attempts:
                self._fail(order, "booking_upstream")
                return self._close(replace(job, attempts=attempts), JobStatus.DEAD, exc)
            wait = self.backoff[min(attempts, len(self.backoff)) - 1]
            return JobResult(self._pending(job, self.now() + timedelta(seconds=wait), exc, attempts))
        except HofJError as exc:
            self._fail(order, "booking_rejected")
            return self._close(job, JobStatus.DEAD, exc)
        self._save(replace(order, status=OrderStatus.CONFIRMED, booking_code=code))
        return self._close(job, JobStatus.DONE)

    def _save(self, order: Order) -> None:
        self.repos.orders.save(replace(order, updated_at=self.now()))

    def _fail(self, order: Order, reason: str) -> None:
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent else "it"
        self._save(replace(order, status=OrderStatus.BOOKING_FAILED,
                           failure_reason=say.failure_reason(reason, lang)))

    def _pending(self, job: Job, run_after: datetime, exc: Exception, attempts: int) -> Job:
        job = replace(job, status=JobStatus.PENDING, run_after=run_after, locked_at=None,
                      attempts=attempts, last_error=_describe(exc))
        self.repos.jobs.save(job)
        return job

    def _close(self, job: Job, status: JobStatus, exc: Exception = None) -> JobResult:
        job = replace(job, status=status, locked_at=None,
                      last_error=_describe(exc) if exc is not None else job.last_error)
        self.repos.jobs.save(job)
        return JobResult(job)


def _describe(exc: Exception) -> str:
    return ("%s: %s" % (type(exc).__name__, exc))[:500]
