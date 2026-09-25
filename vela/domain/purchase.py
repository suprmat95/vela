"""Job d'acquisto (RF-46): prepara su HofJ il carrello di un ordine `queued` e il link di pagamento.

Passi, ognuno salvato prima del successivo così una ripresa (RF-27) non rifà ciò che è già fatto:

  0 itinerario (`create_itinerary`, salva `itinerary_id`)       1 chiamata HofJ
  1 cliente (`set_customer`)                                    1
  2 passeggeri (`get_pax` + `set_pax`, un'unica unità di ripresa) 2
  3 importo da pagare (`get_itinerary`, salva `total`)          1
  4 link di pagamento (porta dei pagamenti)                     0
  5 fatto: l'ordine è `awaiting_payment`

Prima di ogni passo l'ordine viene riletto: se non è più `queued` (rinuncia, RF-49) il job si
ferma senza altre chiamate. Esiti degli errori:
- rete, timeout, 5xx, errore del fornitore di pagamento: nuovo tentativo nella finestra
  successiva, al terzo l'ordine è `failed` con un motivo leggibile;
- 429: nuovo tentativo nella finestra successiva, senza contare il tentativo (RF-38);
- errore del prodotto sulla creazione dell'itinerario: prodotto non prenotabile (RF-33), la
  proposta è chiusa come rifiutata e l'ordine è `replaced` con la proposta successiva (RF-17);
- 401/403: `failed` senza toccare il prodotto.
"""
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Union

from vela.domain import say
from vela.domain.models import (Job, JobStatus, NoMatch, Order, OrderStatus, ProposalMade,
                                Rejection, TravelerDefaults)
from vela.ports.hofj import (ConfigError, Customer, HofJError, HofJPort, ProductError, QuotaError)
from vela.ports.payments import PaymentsError, PaymentsPort
from vela.ports.repositories import Repositories

STEP_ITINERARY, STEP_CUSTOMER, STEP_PAX, STEP_TOTAL, STEP_LINK, STEP_DONE = range(6)
_CALLS = {STEP_ITINERARY: 5, STEP_CUSTOMER: 4, STEP_PAX: 3, STEP_TOTAL: 1, STEP_LINK: 0, STEP_DONE: 0}
UNBOOKABLE_REASON = "prodotto non prenotabile"


def calls_needed(job: Job) -> int:
    """Chiamate HofJ dei passi che restano: il blocco da prenotare prima di eseguire (RF-47)."""
    return _CALLS[min(job.step, STEP_DONE)]


@dataclass(frozen=True)
class JobResult:
    job: Job
    hit_429: bool = False


class PurchaseJob:
    def __init__(self, repos: Repositories, hofj: HofJPort, payments: PaymentsPort,
                 propose: Callable[..., Union[ProposalMade, NoMatch]], defaults: TravelerDefaults,
                 now: Callable[[], datetime], max_attempts: int = 3):
        self.repos, self.hofj, self.payments = repos, hofj, payments
        self.propose, self.defaults, self.now = propose, defaults, now
        self.max_attempts = max_attempts

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
        except HofJError as exc:
            return self._retry(job, next_window, exc, "upstream")

    # --- passi -------------------------------------------------------------------------

    def _step(self, job: Job, order: Order) -> Job:
        if job.step == STEP_ITINERARY:
            product = self.repos.products.get(order.product_id)
            proposal = self.repos.proposals.get(order.proposal_id)
            itinerary_id = self.hofj.create_itinerary(product, proposal.start_date, order.pax, 1,
                                                      order.currency)
            if not product.bookable:
                self.repos.products.set_bookable(product.id, True, self.now())   # RF-34
            self._save_order(replace(order, itinerary_id=itinerary_id))
        elif job.step == STEP_CUSTOMER:
            t, d = order.traveler, self.defaults
            self.hofj.set_customer(order.itinerary_id, Customer(
                t.first_name, t.last_name, t.email, t.phone,
                d.street1, d.postal_code, d.city, d.region, d.country_code))
        elif job.step == STEP_PAX:
            t = order.traveler
            names = [(t.first_name, t.last_name)] + [(p.first_name, p.last_name) for p in t.participants]
            slots = self.hofj.get_pax(order.itinerary_id)
            filled = [replace(slot, first_name=names[i][0], last_name=names[i][1])
                      if i < len(names) else slot for i, slot in enumerate(slots)]
            self.hofj.set_pax(order.itinerary_id, filled)
        elif job.step == STEP_TOTAL:
            itinerary = self.hofj.get_itinerary(order.itinerary_id)
            self._save_order(replace(order, total=itinerary.total, currency=itinerary.currency))
        elif job.step == STEP_LINK:
            product = self.repos.products.get(order.product_id)
            link = self.payments.create_payment_link(order, product.title)
            self._save_order(replace(order, status=OrderStatus.AWAITING_PAYMENT,
                                     payment_url=link.url, payment_ref=link.reference))
        job = replace(job, step=job.step + 1)
        self.repos.jobs.save(job)
        return job

    # --- esiti ---------------------------------------------------------------------------

    def _save_order(self, order: Order) -> None:
        self.repos.orders.save(replace(order, updated_at=self.now()))

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
        return self._close(job, JobStatus.DONE, exc)


def _describe(exc: Exception) -> str:
    return ("%s: %s" % (type(exc).__name__, exc))[:500]
