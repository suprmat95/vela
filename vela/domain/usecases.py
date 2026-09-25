"""Orchestratore dei cinque casi d'uso di RF-39, identici su ogni superficie.

Dipende solo dalle porte: repository, HofJ e pagamenti sono iniettati. `now` e `new_id` sono
iniettabili per i test. Ogni risposta porta `say` (RF-42) e mai più di un prodotto (RF-10).
"""
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from vela.domain import geo, say
from vela.domain.chooser import Choice, choose
from vela.domain.intent import parse_intent
from vela.domain.models import (AcceptResponse, Intent, IntentCreated, IntentQuestion,
                                MissingTravelerData, NoMatch, Order, OrderStatus,
                                OrderStatusResponse, Product, ProductSummary, Proposal,
                                ProposalMade, Rejection, TravelerDefaults, TravelerProfile)
from vela.domain.orders import NotFound, OrderService
from vela.domain.refine import refine
from vela.ports.hofj import Customer, HofJPort
from vela.ports.llm import IntentExtractor
from vela.ports.payments import PaymentsPort
from vela.ports.repositories import DuplicateOrder, Repositories

__all__ = ["Vela", "NotFound", "utcnow", "random_id", "summary_of"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def random_id() -> str:
    return str(uuid.uuid4())


def summary_of(product: Product) -> ProductSummary:
    return ProductSummary(product.id, product.title, product.destination, product.hotel)


class Vela:
    def __init__(self, repos: Repositories, hofj: HofJPort, payments: PaymentsPort,
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
        self.orders = OrderService(repos, hofj, self.now)

    # --- RF-01..05 -----------------------------------------------------------

    def create_intent(self, text: str, profile: Optional[TravelerProfile] = None
                      ) -> Union[IntentCreated, IntentQuestion]:
        profile = profile or TravelerProfile()
        result = parse_intent(text, profile, today=self.now().date(), extractor=self.extractor)
        if result.question:
            return IntentQuestion(result.question, result.question)
        intent = Intent(self.new_id(), text, result.criteria, profile, self.now())
        self.repos.intents.add(intent)
        return IntentCreated(intent.id, intent.criteria, say.say_intent_created(intent.criteria))

    # --- RF-06..11 -----------------------------------------------------------

    def get_proposal(self, intent_id: str) -> Union[ProposalMade, NoMatch]:
        intent = self.repos.intents.get(intent_id)
        if intent is None:
            raise NotFound("intent", intent_id)
        return self._propose(intent)

    def reject_proposal(self, proposal_id: str, reason: str) -> Union[ProposalMade, NoMatch]:
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        self.repos.rejections.add(Rejection(intent.id, proposal.id, proposal.product_id,
                                            reason or "", self.now()))
        return self._propose(self._refined(intent, proposal, reason or ""))

    def _refined(self, intent: Intent, proposal: Proposal, reason: str) -> Intent:
        """RF-08: il motivo aggiorna i criteri dell'intento, persistiti prima della nuova scelta."""
        product = self.repos.products.get(proposal.product_id)
        area = geo.area_of_destination(product.destination, product.country) if product else None
        criteria = refine(intent.criteria, reason, proposal, area, self.now().date())
        if criteria == intent.criteria:
            return intent
        self.repos.intents.update_criteria(intent.id, criteria)
        return replace(intent, criteria=criteria)

    def _propose(self, intent: Intent) -> Union[ProposalMade, NoMatch]:
        lang = intent.criteria.language
        rejected_proposals = self.repos.rejections.proposal_ids_for_intent(intent.id)
        open_proposals = [p for p in self.repos.proposals.list_for_intent(intent.id)
                          if p.id not in rejected_proposals]
        if open_proposals:
            return self._made(open_proposals[-1], lang=lang)
        rejected_products = self.repos.rejections.product_ids_for_intent(intent.id)
        result = choose(self.repos.products.list_all(), intent.criteria, rejected_products,
                        today=self.now().date())
        if not isinstance(result, Choice):
            return NoMatch(intent.id, result.failed_criterion,
                           say.say_no_match(result.failed_criterion, intent.criteria))
        proposal = Proposal(self.new_id(), intent.id, result.product.id, result.start_date,
                            result.end_date, intent.criteria.pax or 1, result.product.price,
                            result.product.currency, result.reason, self.now())
        self.repos.proposals.add(proposal)
        return self._made(proposal, result.product, lang)

    def _made(self, proposal: Proposal, product: Optional[Product] = None,
              lang: str = "it") -> ProposalMade:
        product = product or self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        return ProposalMade(proposal, summary, say.say_proposal(summary, proposal, lang))

    # --- RF-12..16, RNF-03 ---------------------------------------------------

    def accept_proposal(self, proposal_id: str, traveler: Optional[TravelerProfile] = None
                        ) -> Union[AcceptResponse, MissingTravelerData]:
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        lang = intent.criteria.language
        existing = self.repos.orders.get_by_proposal(proposal_id)
        if existing is not None:
            return self._accepted(self._ensure_link(existing), lang)
        profile = intent.profile.merged_with(traveler or TravelerProfile())
        missing = profile.missing_fields(proposal.pax)
        if missing:
            return MissingTravelerData(proposal_id, tuple(missing), say.say_missing(missing, lang))
        product = self.repos.products.get(proposal.product_id)
        itinerary = self.hofj.create_itinerary(product, proposal.start_date, proposal.pax, 1,
                                               proposal.currency)
        d = self.defaults
        self.hofj.set_customer(itinerary.id, Customer(
            profile.first_name, profile.last_name, profile.email, profile.phone,
            d.street1, d.postal_code, d.city, d.region, d.country_code))
        names = [(profile.first_name, profile.last_name)] + [
            (p.first_name, p.last_name) for p in profile.participants]
        slots = self.hofj.get_pax(itinerary.id)
        filled = [replace(slot, first_name=names[i][0], last_name=names[i][1])
                  if i < len(names) else slot for i, slot in enumerate(slots)]
        self.hofj.set_pax(itinerary.id, filled)
        now = self.now()
        order = Order(self.new_id(), proposal.id, intent.id, product.id,
                      OrderStatus.AWAITING_PAYMENT, proposal.pax, proposal.price_from,
                      itinerary.total, itinerary.currency, profile, now, now,
                      itinerary_id=itinerary.id)
        try:
            self.repos.orders.add(order)
        except DuplicateOrder:
            return self._accepted(self.repos.orders.get_by_proposal(proposal_id), lang)
        return self._accepted(self._ensure_link(order), lang)

    def _ensure_link(self, order: Order) -> Order:
        """Crea il link di pagamento se manca (RF-18). Se il fornitore fallisce, `PaymentsError`
        risale alla superficie e l'ordine resta senza link: un nuovo accept riprova."""
        if order.payment_url or order.status != OrderStatus.AWAITING_PAYMENT:
            return order
        product = self.repos.products.get(order.product_id)
        link = self.payments.create_payment_link(order, product.title)
        order = replace(order, payment_url=link.url, payment_ref=link.reference,
                        updated_at=self.now())
        self.repos.orders.save(order)
        return order

    def _accepted(self, order: Order, lang: str = "it") -> AcceptResponse:
        estimate = order.price_from * order.pax
        differs = order.total != estimate
        return AcceptResponse(order.id, order.status, order.total, order.currency, estimate,
                              differs, order.payment_url or "",
                              say.say_accept(order.total, estimate, differs, lang))

    # --- RF-25, RF-26 --------------------------------------------------------

    def get_order_status(self, order_id: str) -> OrderStatusResponse:
        order = self.orders.get(order_id)
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        payable = order.status == OrderStatus.AWAITING_PAYMENT
        return OrderStatusResponse(order.id, order.status, order.booking_code, order.total,
                                   order.currency, order.payment_url if payable else None,
                                   say.say_status(order.status, order.booking_code,
                                                  order.failure_reason, lang, order.total))
