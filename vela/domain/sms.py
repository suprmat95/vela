"""Job degli SMS al viaggiatore (decisione 2026-09-26, RF-19, RF-57): link e conferma.

Il job d'acquisto accoda `sms_link` quando l'ordine diventa `awaiting_payment`; il job di
prenotazione accoda `sms_confirmed` alla conferma. Nessuna chiamata a HofJ, nessuna quota.
Un ordine che non è più nello stato atteso (pagato, annullato, scaduto) chiude il job senza
invio, e così un numero che non si normalizza; proposta o prodotto mancanti lo chiudono `dead`.
Errore temporaneo: nuovo tentativo dopo 30 s, 2 min, 10 min, poi `dead`; errore definitivo:
`dead` subito. L'ordine non cambia mai per colpa
di un SMS. Nei log il numero è mascherato e il testo (che contiene il link) non compare.
"""
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, Sequence

from vela.domain import phone, sms_text
from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus, Proposal
from vela.domain.purchase import JobResult
from vela.ports.notifier import Notifier, NotifierError, NotifierRejected
from vela.ports.repositories import Repositories

log = logging.getLogger(__name__)

EXPECTED = {JobKind.SMS_LINK: OrderStatus.AWAITING_PAYMENT,
            JobKind.SMS_CONFIRMED: OrderStatus.CONFIRMED}


class SmsJob:
    def __init__(self, repos: Repositories, notifier: Notifier, now: Callable[[], datetime],
                 backoff: Sequence[int] = (30, 120, 600)):
        self.repos, self.notifier, self.now = repos, notifier, now
        self.backoff = tuple(backoff)

    def run(self, job: Job, next_window: datetime) -> JobResult:
        order = self.repos.orders.get(job.order_id)
        if order is None or order.status != EXPECTED[job.kind]:
            return self._close(job, JobStatus.DONE)
        to = phone.normalize_it(order.traveler.phone)
        if to is None:
            log.warning("sms %s saltato: numero non valido (ordine %s)", job.kind.value, order.id)
            return self._close(job, JobStatus.DONE)
        proposal = self.repos.proposals.get(order.proposal_id)
        product = self.repos.products.get(order.product_id)
        if proposal is None or product is None:   # mai un job `running` per sempre
            log.warning("sms %s non inviato: proposta o prodotto mancante (ordine %s)",
                        job.kind.value, order.id)
            return self._close(job, JobStatus.DEAD, LookupError("proposta o prodotto mancante"))
        try:
            message_id = self.notifier.send_sms(to, self._body(job.kind, order, proposal,
                                                               product.title))
        except NotifierRejected as exc:
            log.warning("sms %s rifiutato per %s (ordine %s): %s", job.kind.value, phone.mask(to),
                        order.id, exc)
            return self._close(replace(job, attempts=job.attempts + 1), JobStatus.DEAD, exc)
        except NotifierError as exc:
            attempts = job.attempts + 1
            if attempts > len(self.backoff):
                log.warning("sms %s non inviato a %s dopo %d tentativi (ordine %s): %s",
                            job.kind.value, phone.mask(to), attempts, order.id, exc)
                return self._close(replace(job, attempts=attempts), JobStatus.DEAD, exc)
            run_after = self.now() + timedelta(seconds=self.backoff[attempts - 1])
            job = replace(job, status=JobStatus.PENDING, run_after=run_after, locked_at=None,
                          attempts=attempts, last_error=_describe(exc))
            self.repos.jobs.save(job)
            return JobResult(job)
        log.info("sms %s inviato a %s (ordine %s, messaggio %s)", job.kind.value, phone.mask(to),
                 order.id, message_id)
        return self._close(job, JobStatus.DONE)

    def _body(self, kind: JobKind, order: Order, proposal: Proposal, title: str) -> str:
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        if kind == JobKind.SMS_LINK:
            return sms_text.payment_link(title, proposal.start_date, proposal.end_date, order.pax,
                                         order.total, order.payment_url, lang)
        return sms_text.confirmed(title, proposal.start_date, proposal.end_date, order.pax,
                                  order.booking_code, lang)

    def _close(self, job: Job, status: JobStatus, exc: Exception = None) -> JobResult:
        job = replace(job, status=status, locked_at=None,
                      last_error=_describe(exc) if exc is not None else job.last_error)
        self.repos.jobs.save(job)
        return JobResult(job)


def _describe(exc: Exception) -> str:
    return ("%s: %s" % (type(exc).__name__, exc))[:500]
