"""Orchestratore dei cinque casi d'uso di RF-39, identici su ogni superficie.

Dipende solo dalle porte: repository, HofJ e pagamenti sono iniettati. `now` e `new_id` sono
iniettabili per i test. Ogni risposta porta `say` (RF-42) e mai più di un prodotto (RF-10).
"""
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional, Union

from vela.domain import say
from vela.domain.chooser import Choice, choose
from vela.domain.intent import parse_intent
from vela.domain.models import (Intent, IntentCreated, IntentQuestion, NoMatch, Product,
                                ProductSummary, Proposal, ProposalMade, Rejection, TravelerProfile)
from vela.ports.hofj import HofJPort
from vela.ports.payments import PaymentsPort
from vela.ports.repositories import Repositories


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def random_id() -> str:
    return str(uuid.uuid4())


class NotFound(Exception):
    def __init__(self, kind: str, id: str):
        super().__init__("%s %s non trovato" % (kind, id))
        self.kind = kind
        self.id = id


def summary_of(product: Product) -> ProductSummary:
    return ProductSummary(product.id, product.title, product.destination, product.hotel)


class Vela:
    def __init__(self, repos: Repositories, hofj: HofJPort, payments: PaymentsPort,
                 defaults=None, now: Optional[Callable[[], datetime]] = None,
                 new_id: Optional[Callable[[], str]] = None):
        self.repos = repos
        self.hofj = hofj
        self.payments = payments
        self.defaults = defaults
        self.now = now or utcnow
        self.new_id = new_id or random_id

    # --- RF-01..05 -----------------------------------------------------------

    def create_intent(self, text: str, profile: Optional[TravelerProfile] = None
                      ) -> Union[IntentCreated, IntentQuestion]:
        profile = profile or TravelerProfile()
        result = parse_intent(text, profile, today=self.now().date())
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
        return self._propose(intent)

    def _propose(self, intent: Intent) -> Union[ProposalMade, NoMatch]:
        rejected_proposals = self.repos.rejections.proposal_ids_for_intent(intent.id)
        open_proposals = [p for p in self.repos.proposals.list_for_intent(intent.id)
                          if p.id not in rejected_proposals]
        if open_proposals:
            return self._made(open_proposals[-1])
        rejected_products = self.repos.rejections.product_ids_for_intent(intent.id)
        result = choose(self.repos.products.list_all(), intent.criteria, rejected_products,
                        today=self.now().date())
        if not isinstance(result, Choice):
            return NoMatch(intent.id, result.failed_criterion, say.say_no_match(result.failed_criterion))
        proposal = Proposal(self.new_id(), intent.id, result.product.id, result.start_date,
                            result.end_date, intent.criteria.pax or 1, result.product.price,
                            result.product.currency, result.reason, self.now())
        self.repos.proposals.add(proposal)
        return self._made(proposal, result.product)

    def _made(self, proposal: Proposal, product: Optional[Product] = None) -> ProposalMade:
        product = product or self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        return ProposalMade(proposal, summary, say.say_proposal(summary, proposal))
