"""Job d'acquisto (RF-46): prepara su HofJ il carrello di un ordine `queued` e il link di pagamento.

Passi, ognuno salvato prima del successivo così una ripresa (RF-27) non rifà ciò che è già fatto.
M19: cliente e passeggeri passano nel job di prenotazione (`vela.domain.booking`), dopo il
pagamento; il totale non dipende da loro (sonda del 2026-09-27, `docs/api/customer-pax.md`).
I numeri dei passi restano quelli di prima: dopo l'itinerario si salta al 3, e un job salvato
dal codice di prima al passo 1 o 2 salta al 3 senza chiamate.

  0 itinerario (`create_itinerary`, salva `itinerary_id`)       1 chiamata HofJ
  3 importo da pagare (`get_itinerary`, salva `total`, pubblica il prezzo in cache, RF-84)  1
    → l'ordine passa a `awaiting_confirmation` e il job si chiude qui (decisione 2026-09-26):
      il viaggiatore sente il prezzo effettivo e solo la sua conferma accoda un nuovo job
      d'acquisto che riparte dal passo 4
      (RF-84: se l'ordine ha già un `confirmed_total` uguale, si prosegue al link senza fermarsi)
  4 link di pagamento (porta dei pagamenti), job di verifica e SMS    0
  5 fatto: l'ordine è `awaiting_payment`

Prima di ogni passo l'ordine viene riletto: se non è più `queued` (rinuncia, RF-49) il job si
ferma senza altre chiamate. Esiti degli errori:
- rete, timeout, 5xx, errore del fornitore di pagamento: nuovo tentativo nella finestra
  successiva, al terzo l'ordine è `failed` con un motivo leggibile;
- timeout sulla creazione dell'itinerario (M18): esito incerto, HofJ può averlo creato e
  `POST /v1/itineraries` non è idempotente. Il nuovo tentativo ne crea un altro; il primo resta
  orfano, contato in `orphan_itineraries` e nel log. La chiamata è già nel budget;
- 429: nuovo tentativo nella finestra successiva, senza contare il tentativo (RF-38);
- errore del prodotto sulla creazione dell'itinerario: prodotto non prenotabile (RF-33), la
  proposta è chiusa come rifiutata e l'ordine è `replaced` con la proposta successiva (RF-17);
- 401/403: `failed` senza toccare il prodotto.
"""
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable, Union

from vela.domain import say
from vela.domain.models import (Job, JobKind, JobStatus, NoMatch, Order, OrderStatus, ProposalMade,
                                Rejection)
from vela.domain.notify import enqueue_sms
from vela.domain.quotes import quote_key, release_quote
from vela.ports.hofj import ConfigError, HofJError, HofJRouter, ProductError, QuotaError, UpstreamTimeout
from vela.ports.payments import PaymentsError, PaymentsPort
from vela.ports.repositories import Repositories

STEP_ITINERARY, STEP_CUSTOMER, STEP_PAX, STEP_TOTAL, STEP_LINK, STEP_DONE = range(6)
_CALLS = {STEP_ITINERARY: 2, STEP_CUSTOMER: 1, STEP_PAX: 1, STEP_TOTAL: 1, STEP_LINK: 0, STEP_DONE: 0}
_NEXT = {STEP_ITINERARY: STEP_TOTAL, STEP_CUSTOMER: STEP_TOTAL, STEP_PAX: STEP_TOTAL}   # M19
UNBOOKABLE_REASON = "prodotto non prenotabile"

log = logging.getLogger("vela.purchase")


def calls_needed(job: Job) -> int:
    """Chiamate HofJ dei passi che restano: il blocco da prenotare prima di eseguire (RF-47)."""
    return _CALLS[min(job.step, STEP_DONE)]


@dataclass(frozen=True)
class JobResult:
    job: Job
    hit_429: bool = False


class PurchaseJob:
    def __init__(self, repos: Repositories, hofj: HofJRouter, payments: PaymentsPort,
                 propose: Callable[..., Union[ProposalMade, NoMatch]], now: Callable[[], datetime],
                 max_attempts: int = 3, new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
                 poll_seconds: int = 60):
        self.repos, self.hofj, self.payments = repos, hofj, payments
        self.propose, self.now = propose, now
        self.max_attempts, self.new_id, self.poll_seconds = max_attempts, new_id, poll_seconds

    def run(self, job: Job, next_window: datetime) -> JobResult:
        try:
            while job.step < STEP_DONE:
                order = self.repos.orders.get(job.order_id)
                if order is None or order.status != OrderStatus.QUEUED:
                    break
                job = self._step(job, order)
            return self._close(job, JobStatus.DONE)
        except QuotaError as exc:
            return JobResult(self._reschedule(job, next_window, exc, count=False), hit_429=True)
        except ConfigError as exc:
            self._fail_order(job, "config")
            return self._close(job, JobStatus.DEAD, exc)
        except ProductError as exc:
            if job.step == STEP_ITINERARY:
                return self._replace(job, exc)
            return self._retry(job, next_window, exc, "upstream")
        except PaymentsError as exc:
            return self._retry(job, next_window, exc, "payments")
        except UpstreamTimeout as exc:
            if job.step == STEP_ITINERARY:
                self._count_orphan(job)
            return self._retry(job, next_window, exc, "upstream")
        except HofJError as exc:
            return self._retry(job, next_window, exc, "upstream")

    # --- passi -------------------------------------------------------------------------

    def _step(self, job: Job, order: Order) -> Job:
        # RF-56: il brand del prodotto, riletto dal DB a ogni passo (riavvii e retry compresi)
        product = self.repos.products.get(order.product_id)
        hofj = self.hofj.client_for(product) if job.step < STEP_LINK else None
        if job.step == STEP_ITINERARY:
            proposal = self.repos.proposals.get(order.proposal_id)
            itinerary_id = hofj.create_itinerary(product, proposal.start_date, order.pax,
                                                 order.rooms, order.currency)   # RF-67
            if not product.bookable:
                self.repos.products.set_bookable(product.id, True, self.now())   # RF-34
            self._save_order(replace(order, itinerary_id=itinerary_id))
        elif job.step == STEP_TOTAL:
            itinerary = hofj.get_itinerary(order.itinerary_id)
            self._publish(order, itinerary.total)   # RF-84: prima che l'ordine lasci `queued`
            priced = replace(order, total=itinerary.total, currency=itinerary.currency)
            if order.confirmed_total == itinerary.total and order.currency == itinerary.currency:
                self._save_order(priced)   # RF-84: il viaggiatore ha già detto sì a questo importo
            else:
                if order.confirmed_total is not None:
                    log.info("quote_price_changed order_id=%s confirmed=%s total=%s",
                             order.id, order.confirmed_total, itinerary.total)
                self._save_order(replace(priced, status=OrderStatus.AWAITING_CONFIRMATION))
        elif job.step == STEP_LINK:
            link = self.payments.create_payment_link(order, product.title)
            self._save_order(replace(order, status=OrderStatus.AWAITING_PAYMENT,
                                     payment_url=link.url, payment_ref=link.reference))
            now = self.now()   # RF-20: da qui la verifica del pagamento per interrogazione
            self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PAYMENT_CHECK, order.id, JobStatus.PENDING,
                                        now, now + timedelta(seconds=self.poll_seconds)))
            enqueue_sms(self.repos, JobKind.SMS_LINK, order.id, now, self.new_id)   # RF-19
        job = replace(job, step=_NEXT.get(job.step, job.step + 1))
        self.repos.jobs.save(job)
        return job

    # --- esiti ---------------------------------------------------------------------------

    def _save_order(self, order: Order) -> None:
        self.repos.orders.save(replace(order, updated_at=self.now()))

    def _publish(self, order: Order, total) -> None:
        """RF-84: se la chiave è in cache (la riga esiste solo con la cache accesa), il prezzo letto
        la aggiorna e sblocca gli agganciati. Va chiamata prima di salvare il nuovo stato: finché
        il leader è `queued` nessun agganciato lo crede uscito e lo rilascia."""
        key = quote_key(order, self.repos.proposals.get(order.proposal_id).start_date)
        if self.repos.quotes.get(key) is None:
            return
        ids = self.repos.quotes.publish(key, order.id, total, self.now())
        if ids:
            log.info("quote_fanout order_id=%s followers=%d", order.id, len(ids))

    def _count_orphan(self, job: Job) -> None:
        order = self.repos.orders.get(job.order_id)
        if order is None:
            return
        self._save_order(replace(order, orphan_itineraries=order.orphan_itineraries + 1))
        log.warning("orphan_itinerary order_id=%s attempt=%d", order.id, job.attempts + 1)

    def _close(self, job: Job, status: JobStatus, exc: Exception = None) -> JobResult:
        job = replace(job, status=status, locked_at=None,
                      last_error=_describe(exc) if exc is not None else job.last_error)
        self.repos.jobs.save(job)
        return JobResult(job)

    def _reschedule(self, job: Job, next_window: datetime, exc: Exception, count: bool) -> Job:
        job = replace(job, status=JobStatus.PENDING, run_after=next_window, locked_at=None,
                      attempts=job.attempts + (1 if count else 0), last_error=_describe(exc))
        self.repos.jobs.save(job)
        return job

    def _retry(self, job: Job, next_window: datetime, exc: Exception, reason: str) -> JobResult:
        if job.attempts + 1 >= self.max_attempts:
            self._fail_order(job, reason)
            return self._close(replace(job, attempts=job.attempts + 1), JobStatus.DEAD, exc)
        return JobResult(self._reschedule(job, next_window, exc, count=True))

    def _lang(self, order: Order) -> str:
        intent = self.repos.intents.get(order.intent_id)
        return intent.criteria.language if intent else "it"

    def _fail_order(self, job: Job, reason: str) -> None:
        order = self.repos.orders.get(job.order_id)
        if order is not None and order.status == OrderStatus.QUEUED:
            self._save_order(replace(order, status=OrderStatus.FAILED,
                                     failure_reason=say.failure_reason(reason, self._lang(order))))
        if order is not None:
            release_quote(self.repos, order, self.now(), self.new_id)   # RF-84: ripiego

    def _replace(self, job: Job, exc: Exception) -> JobResult:
        """RF-17, RF-33: prodotto non prenotabile per tutti; proposta successiva per questo intento."""
        order = self.repos.orders.get(job.order_id)
        now = self.now()
        self.repos.products.set_bookable(order.product_id, False, now)
        self.repos.rejections.add(Rejection(order.intent_id, order.proposal_id, order.product_id,
                                            UNBOOKABLE_REASON, now))
        result = self.propose(self.repos.intents.get(order.intent_id))
        if isinstance(result, ProposalMade):
            self._save_order(replace(order, status=OrderStatus.REPLACED,
                                     replacement_proposal_id=result.proposal.id))
        else:
            self._fail_order(job, "no_alternative")
        release_quote(self.repos, order, now, self.new_id)   # RF-84: ripiego
        return self._close(job, JobStatus.DONE, exc)


def _describe(exc: Exception) -> str:
    return ("%s: %s" % (type(exc).__name__, exc))[:500]
