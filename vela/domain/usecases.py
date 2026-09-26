"""Orchestratore dei cinque casi d'uso di RF-39, identici su ogni superficie.

Dipende solo dalle porte: repository, HofJ e pagamenti sono iniettati. `now` e `new_id` sono
iniettabili per i test. Ogni risposta porta `say` (RF-42) e mai più di un prodotto (RF-10).
"""
import logging
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional, Tuple, Union

from vela.domain import geo, say
from vela.domain.chooser import Choice, choose
from vela.domain.intent import parse_intent
from vela.domain.models import (Intent, IntentCreated, IntentQuestion, Job, JobKind, JobStatus,
                                MissingTravelerData, NoMatch, Order, OrderQueued, OrderStatus,
                                OrderStatusResponse, Product, ProductSummary, Proposal,
                                ProposalMade, Rejection, StructuredFields, TravelerDefaults,
                                TravelerProfile)
from vela.domain.orders import NotFound, OrderService
from vela.domain.quota import estimated_wait_seconds, wait_minutes
from vela.domain.refine import Refinement, is_price_reason, refine
from vela.ports.hofj import HofJRouter
from vela.ports.llm import IntentExtractor
from vela.ports.payments import PaymentsPort
from vela.ports.repositories import DuplicateOrder, Repositories

__all__ = ["Vela", "NotFound", "utcnow", "random_id", "summary_of"]

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def random_id() -> str:
    return str(uuid.uuid4())


def summary_of(product: Product) -> ProductSummary:
    return ProductSummary(product.id, product.title, product.destination, product.hotel)


class Vela:
    def __init__(self, repos: Repositories, hofj: HofJRouter, payments: PaymentsPort,
                 defaults=None, now: Optional[Callable[[], datetime]] = None,
                 new_id: Optional[Callable[[], str]] = None,
                 extractor: Optional[IntentExtractor] = None):
        self.repos = repos
        self.hofj = hofj
        self.payments = payments
        self.now = now or utcnow
        self.new_id = new_id or random_id
        self.extractor = extractor
        self.defaults = defaults or TravelerDefaults()
        self.orders = OrderService(repos, hofj, self.now, self.new_id)

    # --- RF-01..05 -----------------------------------------------------------

    def create_intent(self, text: str, profile: Optional[TravelerProfile] = None,
                      fields: Optional[StructuredFields] = None
                      ) -> Union[IntentCreated, IntentQuestion]:
        """RF-01..04, RF-52..54: campi strutturati > parser > fallback; i campi invalidi sono
        scartati e detti nel `say`, i conflitti con il testo vanno nei log."""
        profile = profile or TravelerProfile()
        result = parse_intent(text, profile, today=self.now().date(), extractor=self.extractor,
                              fields=fields)
        lang = result.criteria.language
        if result.question:
            return IntentQuestion(result.question, say.prefixed(
                say.say_discarded(result.discarded, lang), result.question))
        intent = Intent(self.new_id(), text, result.criteria, profile, self.now())
        self.repos.intents.add(intent)
        _log_conflicts(intent.id, result.conflicts)
        return IntentCreated(intent.id, intent.criteria,
                             say.say_intent_created(intent.criteria, result.discarded))

    # --- RF-06..11 -----------------------------------------------------------

    def get_proposal(self, intent_id: str) -> Union[ProposalMade, NoMatch]:
        intent = self.repos.intents.get(intent_id)
        if intent is None:
            raise NotFound("intent", intent_id)
        return self._propose(intent)

    def reject_proposal(self, proposal_id: str, reason: str,
                        fields: Optional[StructuredFields] = None) -> Union[ProposalMade, NoMatch]:
        """RF-08, RF-53..55. Un secondo rifiuto della stessa proposta (dopo un "niente di
        compatibile") aggiorna i criteri senza registrare un nuovo rifiuto: il repository ignora
        il duplicato (`uq_rejections_proposal_id`)."""
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        cancelled = self._cancel_unpaid_order(proposal.id)
        self.repos.rejections.add(Rejection(intent.id, proposal.id, proposal.product_id,
                                            reason or "", self.now()))
        intent, refinement = self._refined(intent, proposal, reason or "", fields)
        _log_conflicts(intent.id, refinement.conflicts)
        result = self._propose(intent)
        if isinstance(result, NoMatch):
            result = replace(result, rejected_proposal_id=proposal.id)
        lang = intent.criteria.language
        lead = [say.say_discarded(refinement.discarded, lang)]
        if (reason or "").strip() and not refinement.understood:
            lead.append(say.say_untranslatable(lang))
        lead.append(say.say_understood(intent.criteria))
        sentence = say.prefixed(" ".join(p for p in lead if p), result.say)
        if cancelled:   # RF-49
            sentence = say.say_cancelled_then(sentence, lang)
        return replace(result, say=sentence)

    def _cancel_unpaid_order(self, proposal_id: str) -> bool:
        """RF-49: un ordine in coda, in lavorazione o da pagare diventa `cancelled`; il job si
        ferma al passo successivo. Dopo il pagamento l'ordine non si tocca."""
        order = self.repos.orders.get_by_proposal(proposal_id)
        if order is None or order.status not in (OrderStatus.QUEUED, OrderStatus.AWAITING_PAYMENT):
            return False
        self.repos.orders.save(replace(order, status=OrderStatus.CANCELLED, updated_at=self.now()))
        return True

    def _refined(self, intent: Intent, proposal: Proposal, reason: str,
                 fields: Optional[StructuredFields]) -> Tuple[Intent, Refinement]:
        """RF-08: motivo e campi aggiornano i criteri dell'intento, persistiti prima della nuova
        scelta."""
        product = self.repos.products.get(proposal.product_id)
        area = geo.area_of_destination(product.destination, product.country) if product else None
        refinement = refine(intent.criteria, reason, proposal, area, self.now().date(), fields)
        if refinement.criteria == intent.criteria:
            return intent, refinement
        self.repos.intents.update_criteria(intent.id, refinement.criteria)
        return replace(intent, criteria=refinement.criteria), refinement

    def _propose(self, intent: Intent) -> Union[ProposalMade, NoMatch]:
        lang = intent.criteria.language
        rejected_proposals = self.repos.rejections.proposal_ids_for_intent(intent.id)
        open_proposals = [p for p in self.repos.proposals.list_for_intent(intent.id)
                          if p.id not in rejected_proposals]
        if open_proposals:
            return self._made(open_proposals[-1], lang=lang)
        rejected_products = self.repos.rejections.product_ids_for_intent(intent.id)
        now = self.now()
        result = choose(self.repos.products.list_all(), intent.criteria, rejected_products,
                        today=now.date(), now=now, max_total=self._price_ceiling(intent.id))
        if not isinstance(result, Choice):
            return NoMatch(intent.id, result.failed_criterion,
                           say.say_no_match(result.failed_criterion, intent.criteria))
        proposal = Proposal(self.new_id(), intent.id, result.product.id, result.start_date,
                            result.end_date, intent.criteria.pax or 1, result.product.price,
                            result.product.currency, result.reason, self.now())
        self.repos.proposals.add(proposal)
        return self._made(proposal, result.product, lang)

    def _price_ceiling(self, intent_id: str) -> Optional[Decimal]:
        """Decisione M7 (§10.1): dopo un rifiuto per prezzo si propone solo qualcosa che costa
        meno; il tetto è il totale più basso tra le proposte rifiutate per prezzo."""
        by_price = {r.proposal_id for r in self.repos.rejections.list_for_intent(intent_id)
                    if is_price_reason(r.reason)}
        totals = [p.total_from for p in self.repos.proposals.list_for_intent(intent_id)
                  if p.id in by_price]
        return min(totals) if totals else None

    def _made(self, proposal: Proposal, product: Optional[Product] = None,
              lang: str = "it") -> ProposalMade:
        product = product or self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        return ProposalMade(proposal, summary, say.say_proposal(summary, proposal, lang))

    # --- RF-12, RF-13, RF-17, RF-19, RF-45, RNF-03 ------------------------------

    def accept_proposal(self, proposal_id: str, traveler: Optional[TravelerProfile] = None
                        ) -> Union[OrderQueued, OrderStatusResponse, MissingTravelerData]:
        """RF-45: mette l'ordine in coda e risponde subito, senza chiamare HofJ né il pagamento.
        Il carrello e il link li prepara il job d'acquisto (RF-46)."""
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        lang = intent.criteria.language
        existing = self.repos.orders.get_by_proposal(proposal_id)
        if existing is not None:
            return self.get_order_status(existing.id)
        replaced = self.repos.orders.get_by_replacement(proposal_id)
        known = intent.profile if replaced is None else intent.profile.merged_with(replaced.traveler)
        profile = known.merged_with(traveler or TravelerProfile())   # RF-17: dati già dati
        missing = profile.missing_fields(proposal.pax)
        if missing:
            return MissingTravelerData(proposal_id, tuple(missing), say.say_missing(missing, lang))
        now = self.now()
        enqueued_at = replaced.enqueued_at if replaced and replaced.enqueued_at else now   # RF-17
        order = Order(self.new_id(), proposal.id, intent.id, proposal.product_id, OrderStatus.QUEUED,
                      proposal.pax, proposal.price_from, None, proposal.currency, profile, now, now,
                      enqueued_at=enqueued_at)
        try:
            self.repos.orders.add(order)
        except DuplicateOrder:
            return self.get_order_status(self.repos.orders.get_by_proposal(proposal_id).id)
        self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PURCHASE, order.id, JobStatus.PENDING,
                                    enqueued_at, now))
        position, wait = self._queue_position(order.id)
        return OrderQueued(order.id, OrderStatus.QUEUED, position, wait,
                           say.say_queued(wait_minutes(wait or 0), lang))

    def _queue_position(self, order_id: str) -> Tuple[Optional[int], Optional[int]]:
        """RF-48: posizione tra gli acquisti in attesa e attesa stimata in secondi."""
        position = self.repos.jobs.queued_purchase_position(order_id)
        if position is None:
            return None, None
        snap = self.repos.quota.snapshot(self.now())
        return position, estimated_wait_seconds(position, snap["purchases_per_minute"])

    # --- RF-25, RF-26 --------------------------------------------------------

    def get_order_status(self, order_id: str) -> OrderStatusResponse:
        order = self.orders.get(order_id)
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        status = order.status
        if status == OrderStatus.QUEUED:
            position, wait = self._queue_position(order.id)
            minutes = None if wait is None else wait_minutes(wait)
            return OrderStatusResponse(order.id, status, say.say_status(status, None, None, lang,
                                                                        minutes=minutes),
                                       position=position, wait_seconds=wait)
        if status == OrderStatus.REPLACED and order.replacement_proposal_id:
            proposal = self._made(self.repos.proposals.get(order.replacement_proposal_id), lang=lang)
            return OrderStatusResponse(order.id, status,
                                       say.say_replaced(proposal.product, proposal.proposal, lang),
                                       proposal=proposal)
        estimate = order.price_from * order.pax
        payable = status == OrderStatus.AWAITING_PAYMENT
        if payable:
            self._check_payment_now(order.id)
        differs = None if order.total is None else order.total != estimate
        return OrderStatusResponse(
            order.id, status,
            say.say_status(status, order.booking_code, order.failure_reason, lang, order.total,
                           price_from_total=estimate),
            total=order.total, currency=order.currency if order.total is not None else None,
            price_from_total=estimate if order.total is not None else None, total_differs=differs,
            payment_url=order.payment_url if payable else None, booking_code=order.booking_code,
            failure_reason=order.failure_reason
            if status in (OrderStatus.FAILED, OrderStatus.BOOKING_FAILED) else None)

    def _check_payment_now(self, order_id: str) -> None:
        """RF-20: chi chiede lo stato anticipa la verifica del pagamento (nessuna chiamata qui)."""
        job = self.repos.jobs.active_for_order(order_id, JobKind.PAYMENT_CHECK)
        now = self.now()
        if job is not None and job.status == JobStatus.PENDING and job.run_after > now:
            self.repos.jobs.save(replace(job, run_after=now))


def _log_conflicts(intent_id: str, conflicts: tuple) -> None:
    """RF-53, RNF-06: campo e testo in contrasto; vince il campo. Mai il testo dell'intento."""
    for name, from_text, from_field in conflicts:
        log.info("conflitto testo/campo intent=%s campo=%s testo=%r campo_strutturato=%r",
                 intent_id, name, from_text, from_field)
