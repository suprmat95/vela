"""Job di prenotazione (RF-23, RF-24, RF-51): chiude su HofJ un ordine pagato.

M19: cliente e passeggeri arrivano qui dal job d'acquisto, dopo il pagamento (sonde del
2026-09-27, `docs/api/customer-pax.md`: HofJ li accetta anche su un itinerario pagato e il
totale non cambia). Passi, ognuno salvato prima del successivo (RF-27):

  0 cliente (`set_customer`, dati del viaggiatore e default di RF-13)        1 chiamata HofJ
  1 passeggeri con i `refId` `pax-1..N`, senza leggerli (differenza #36)     1
  2 ripiego: `get_pax` + `set_pax`, solo se il passo 1 riceve un 4xx          2
  3 booking (`POST /v1/bookings`, inoltra l'id del PaymentIntent)            1
  4 fatto

Il passo 1 riuscito salta al 3. Un 4xx al passo 1 porta al 2 e rimette il job in coda subito,
senza contare un tentativo: le due chiamate del ripiego prendono i loro gettoni (RF-47). Rete,
timeout e 5xx: nuovo tentativo dopo 5, 10, 20, 40 secondi, poi `booking_failed`. Un 4xx
(prodotto o configurazione) non si ripete. Un 429 torna nella finestra successiva senza contare
il tentativo (RF-38). Un ordine che non è più `paid_pending_booking` (già confermato da un altro
job) chiude il job senza chiamate. Tutte le chiamate sono della classe di quota `booking`.
"""
import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, List, Sequence

from vela.domain import say
from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus, TravelerDefaults
from vela.domain.notify import enqueue_sms
from vela.domain.purchase import JobResult
from vela.ports.hofj import (Customer, HofJError, HofJRouter, Pax, PaymentProof, ProductError, QuotaError,
                             UpstreamError)
from vela.ports.repositories import Repositories

STEP_CUSTOMER, STEP_PAX, STEP_PAX_READ, STEP_BOOKING, STEP_DONE = range(5)
_CALLS = {STEP_CUSTOMER: 3, STEP_PAX: 2, STEP_PAX_READ: 3, STEP_BOOKING: 1, STEP_DONE: 0}
_NEXT = {STEP_PAX: STEP_BOOKING}


def booking_calls_needed(job: Job) -> int:
    """Chiamate HofJ dei passi che restano: il blocco da prenotare prima di eseguire (RF-47)."""
    return _CALLS[min(job.step, STEP_DONE)]


class _PaxRejected(Exception):
    pass


class BookingJob:
    def __init__(self, repos: Repositories, hofj: HofJRouter, now: Callable[[], datetime],
                 max_attempts: int = 5, backoff: Sequence[int] = (5, 10, 20, 40),
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
                 defaults: TravelerDefaults = TravelerDefaults()):
        self.repos, self.hofj, self.now = repos, hofj, now
        self.max_attempts, self.backoff, self.new_id = max_attempts, tuple(backoff), new_id
        self.defaults = defaults

    def run(self, job: Job, next_window: datetime) -> JobResult:
        order = self.repos.orders.get(job.order_id)
        if order is None or order.status != OrderStatus.PAID_PENDING_BOOKING:
            return self._close(job, JobStatus.DONE)
        try:   # RF-56: brand del prodotto dell'ordine, riletto a ogni esecuzione
            hofj = self.hofj.client_for(self.repos.products.get(order.product_id))
            while job.step < STEP_DONE:
                job = self._step(job, order, hofj)
        except _PaxRejected:
            return JobResult(self._pending(replace(job, step=STEP_PAX_READ), self.now(), None, job.attempts))
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
        return self._close(job, JobStatus.DONE)

    def _step(self, job: Job, order: Order, hofj) -> Job:
        if job.step == STEP_CUSTOMER:
            t, d = order.traveler, self.defaults
            hofj.set_customer(order.itinerary_id, Customer(
                t.first_name, t.last_name, t.email, t.phone,
                d.street1, d.postal_code, d.city, d.region, d.country_code))
        elif job.step == STEP_PAX:
            slots = [Pax("pax-%d" % (i + 1)) for i in range(order.pax)]
            try:
                hofj.set_pax(order.itinerary_id, _named(order, slots))
            except ProductError as exc:   # 4xx: `refId` diversi da quelli attesi
                raise _PaxRejected() from exc
        elif job.step == STEP_PAX_READ:
            hofj.set_pax(order.itinerary_id, _named(order, hofj.get_pax(order.itinerary_id)))
        elif job.step == STEP_BOOKING:
            code = hofj.create_booking(order.itinerary_id, PaymentProof(order.payment_ref or "", "succeeded"))
            self._save(replace(order, status=OrderStatus.CONFIRMED, booking_code=code))
            enqueue_sms(self.repos, JobKind.SMS_CONFIRMED, order.id, self.now(), self.new_id)   # RF-57
        job = replace(job, step=_NEXT.get(job.step, job.step + 1))
        self.repos.jobs.save(job)
        return job

    def _save(self, order: Order) -> None:
        self.repos.orders.save(replace(order, updated_at=self.now()))

    def _fail(self, order: Order, reason: str) -> None:
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent else "it"
        self._save(replace(order, status=OrderStatus.BOOKING_FAILED,
                           failure_reason=say.failure_reason(reason, lang)))

    def _pending(self, job: Job, run_after: datetime, exc, attempts: int) -> Job:
        job = replace(job, status=JobStatus.PENDING, run_after=run_after, locked_at=None,
                      attempts=attempts, last_error=_describe(exc) if exc is not None else job.last_error)
        self.repos.jobs.save(job)
        return job

    def _close(self, job: Job, status: JobStatus, exc: Exception = None) -> JobResult:
        job = replace(job, status=status, locked_at=None,
                      last_error=_describe(exc) if exc is not None else job.last_error)
        self.repos.jobs.save(job)
        return JobResult(job)


def _named(order: Order, slots: List[Pax]) -> List[Pax]:
    """I nomi del viaggiatore e dei partecipanti, in ordine; gli slot in più restano come sono."""
    t = order.traveler
    names = [(t.first_name, t.last_name)] + [(p.first_name, p.last_name) for p in t.participants]
    return [replace(slot, first_name=names[i][0], last_name=names[i][1]) if i < len(names) else slot
            for i, slot in enumerate(slots)]


def _describe(exc: Exception) -> str:
    return ("%s: %s" % (type(exc).__name__, exc))[:500]
