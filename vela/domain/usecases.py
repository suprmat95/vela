"""Orchestratore dei casi d'uso di RF-39 e di RF-83 (dettagli), identici su ogni superficie.

Dipende solo dalle porte: repository, HofJ e pagamenti sono iniettati. `now` e `new_id` sono
iniettabili per i test. Ogni risposta porta `say` (RF-42) e mai più di un prodotto (RF-10).
"""
import functools
import logging
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional, Tuple, Union

from vela.domain import geo, phone, say
from vela.domain.chooser import Choice, cheapest_total, choose, rooms_needed
from vela.domain.details import details_of
from vela.domain.intent import parse_intent, question_rooms, validate_fields
from vela.domain.models import (Intent, IntentCreated, IntentQuestion, Job, JobKind, JobStatus,
                                MissingTravelerData, NoMatch, Order, OrderQueued, OrderStatus,
                                OrderStatusResponse, Product, ProductSummary, Proposal,
                                ProposalDetails, ProposalMade, QuoteKey, QuoteStatus, Rejection,
                                StructuredFields, TravelerDefaults, TravelerProfile)
from vela.domain.orders import NotFound, OrderService
from vela.domain.purchase import STEP_ITINERARY, STEP_LINK
from vela.domain.quota import estimated_wait_seconds, wait_minutes
from vela.domain.quotes import quote_key, release_quote, unstick
from vela.domain.refine import Refinement, is_hotel_rejection, is_price_reason, refine
from vela.ports.hofj import HofJRouter
from vela.ports.llm import IntentExtractor
from vela.ports.payments import PaymentsPort
from vela.ports.repositories import DuplicateOrder, Repositories

__all__ = ["Vela", "NotFound", "utcnow", "random_id", "summary_of"]

log = logging.getLogger(__name__)
SIGN_OF_LIFE_EVERY = timedelta(seconds=60)   # M19: al massimo una scrittura di `last_seen_at` al minuto


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
                 extractor: Optional[IntentExtractor] = None, sms_enabled: bool = False,
                 accept_wait_seconds: float = 0, accept_poll_seconds: float = 1.0,
                 sleep: Optional[Callable[[float], None]] = None, price_quote_ttl_seconds: int = 0):
        self.repos = repos
        # RF-84: vita del prezzo in cache; 0 = cache e fanout spenti (accettazione come prima)
        self.price_quote_ttl = timedelta(seconds=price_quote_ttl_seconds)
        # Decisione 2026-09-26: `accept_proposal` aspetta il prezzo effettivo (e dopo la conferma
        # il link) fino a questo tetto, rileggendo l'ordine; 0 = risponde subito `queued`
        self.accept_wait_seconds = accept_wait_seconds
        self.accept_poll_seconds = accept_poll_seconds
        self.sleep = sleep or time.sleep
        # RF-19, RF-57: le frasi annunciano gli SMS solo se partono davvero (Twilio configurato)
        self.sms_enabled = sms_enabled
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
        now = self.now()
        result = parse_intent(text, profile, today=now.date(), extractor=self.extractor,
                              fields=fields, cheapest_total=self._cheapest_total(now))
        lang = result.criteria.language
        if result.question:
            return IntentQuestion(result.question, say.prefixed(
                say.say_discarded(result.discarded, lang), result.question))
        intent = Intent(self.new_id(), text, result.criteria, profile, self.now())
        self.repos.intents.add(intent)
        _log_conflicts(intent.id, result.conflicts)
        return IntentCreated(intent.id, intent.criteria,
                             say.say_intent_created(intent.criteria, result.discarded))

    def _cheapest_total(self, now: datetime, products: Optional[Callable[[], list]] = None):
        """RF-69, regola 4: il catalogo si legge solo se la regola serve (decisione M21-E:
        nessuna query in più per gli altri intenti); `products` è la lettura condivisa del
        rifiuto."""
        read = products or self.repos.products.list_all

        def cheapest(criteria):
            return cheapest_total(read(), criteria, now.date(), now)
        return cheapest

    # --- RF-06..11 -----------------------------------------------------------

    def get_proposal(self, intent_id: str) -> Union[ProposalMade, NoMatch]:
        intent = self.repos.intents.get(intent_id)
        if intent is None:
            raise NotFound("intent", intent_id)
        return self._propose(intent)

    def reject_proposal(self, proposal_id: str, reason: str, fields: Optional[StructuredFields] = None
                        ) -> Union[ProposalMade, NoMatch, IntentQuestion]:
        """RF-08, RF-53..55, RF-71..75. Prima si capisce il rifiuto, poi si scrive: un motivo senza
        tipo (RF-75), o più di 2 persone senza camere (da M21-D), è una domanda chiusa con l'id della
        proposta, senza rifiuto, criteri né ordine toccati (RF-49). Altrimenti l'ordine non pagato si
        cancella e il rifiuto si registra con tipo e `keep_product`. Un secondo rifiuto della stessa
        proposta (dopo un "niente di compatibile") non ne registra un altro: aggiorna tipo e
        `keep_product` di quello esistente (RF-55) e non chiede più il motivo."""
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        lang = intent.criteria.language
        existing = next((r for r in self.repos.rejections.list_for_intent(intent.id)
                         if r.proposal_id == proposal.id), None)
        # una sola lettura del catalogo per regola 4 e scelta (decisione M21-E)
        products = functools.cache(self.repos.products.list_all)
        product = self.repos.products.get(proposal.product_id)
        refinement = self._refinement(intent, proposal, product, reason or "", fields, products)
        if refinement.ask == "rooms" or (refinement.ask == "reason" and existing is None):
            question = question_rooms(lang) if refinement.ask == "rooms" else say.question_reason(lang)
            return IntentQuestion(question, say.prefixed(say.say_discarded(refinement.discarded, lang),
                                                         question), proposal.id)
        kind = refinement.kind or (existing.kind if existing is not None else None)
        keep = refinement.keep_product
        cancelled = self._cancel_unpaid_order(proposal.id)
        rejection = Rejection(intent.id, proposal.id, proposal.product_id, reason or "", self.now(),
                              kind, keep)
        if existing is None:
            self.repos.rejections.add(rejection)
        elif (existing.kind, existing.keep_product) != (kind, keep):
            self.repos.rejections.update(rejection)
        if refinement.criteria != intent.criteria:
            self.repos.intents.update_criteria(intent.id, refinement.criteria)
            intent = replace(intent, criteria=refinement.criteria)
        _log_conflicts(intent.id, refinement.conflicts)
        result = self._propose(intent, products, same_trip=proposal.product_id if keep else None)
        if isinstance(result, NoMatch):
            result = replace(result, rejected_proposal_id=proposal.id)
        lead = [say.say_discarded(refinement.discarded, lang)]
        if is_hotel_rejection(kind, reason):   # RF-72
            lead.append(say.say_hotel_excluded(product.hotel if product else None, lang))
        if kind == "other" and (reason or "").strip() and not refinement.understood:   # RF-54
            lead.append(say.say_untranslatable(lang))
        lead.append(say.say_understood(intent.criteria))
        if keep and isinstance(result, ProposalMade):   # RF-74
            lead.append(say.say_same_trip(lang))
        sentence = say.prefixed(" ".join(p for p in lead if p), result.say)
        if cancelled:   # RF-49
            sentence = say.say_cancelled_then(sentence, lang)
        return replace(result, say=sentence)

    def _cancel_unpaid_order(self, proposal_id: str) -> bool:
        """RF-49: un ordine in coda, in lavorazione o da pagare diventa `cancelled`; il job si
        ferma al passo successivo. Dopo il pagamento l'ordine non si tocca."""
        order = self.repos.orders.get_by_proposal(proposal_id)
        if order is None or order.status not in (OrderStatus.QUEUED, OrderStatus.AWAITING_CONFIRMATION,
                                                 OrderStatus.AWAITING_PAYMENT):
            return False
        self.repos.orders.save(replace(order, status=OrderStatus.CANCELLED, updated_at=self.now()))
        release_quote(self.repos, order, self.now(), self.new_id)   # RF-84: ripiego
        return True

    def _refinement(self, intent: Intent, proposal: Proposal, product: Optional[Product], reason: str,
                    fields: Optional[StructuredFields], products: Callable[[], list]) -> Refinement:
        """RF-08, RF-71: motivo e campi → criteri aggiornati e tipo; niente si scrive qui."""
        area = geo.area_of_destination(product.destination, product.country) if product else None
        now = self.now()
        return refine(intent.criteria, reason, proposal, area, now.date(), fields,
                      cheapest_total=self._cheapest_total(now, products),
                      product_levels=product.levels if product else frozenset())

    def _propose(self, intent: Intent, products: Optional[Callable[[], list]] = None,
                 same_trip: Optional[str] = None) -> Union[ProposalMade, NoMatch]:
        """`same_trip` (RF-74): subito dopo un rifiuto con `keep_product` si sceglie solo tra le
        altre partenze di quel prodotto."""
        lang = intent.criteria.language
        rejections = self.repos.rejections.list_for_intent(intent.id)
        rejected_proposals = {r.proposal_id for r in rejections}
        proposals = self.repos.proposals.list_for_intent(intent.id)
        open_proposals = [p for p in proposals if p.id not in rejected_proposals]
        rooms = intent.criteria.rooms or 1   # None solo negli intenti salvati prima di M21-D
        if open_proposals:
            return self._made(open_proposals[-1], lang=lang, rooms=rooms)
        # M21-F: un rifiuto con `keep_product` esclude solo le sue date (RF-74); uno `hotel` anche
        # i prodotti dello stesso hotel (RF-72)
        rejected_products = {r.product_id for r in rejections if not r.keep_product}
        dates_of = {p.id: (p.start_date, p.end_date) for p in proposals}
        kept_windows = {}
        for r in rejections:
            if r.keep_product and r.proposal_id in dates_of:
                kept_windows[r.product_id] = kept_windows.get(r.product_id, ()) + (dates_of[r.proposal_id],)
        hotel_rejected = {r.product_id for r in rejections if is_hotel_rejection(r.kind, r.reason)}
        catalog = (products or self.repos.products.list_all)()
        if same_trip is not None:
            catalog = [p for p in catalog if p.id == same_trip]
        now = self.now()
        result = choose(catalog, intent.criteria, rejected_products, today=now.date(), now=now,
                        max_total=self._price_ceiling(rejections, proposals),
                        hotel_rejected=hotel_rejected, kept_windows=kept_windows)
        if not isinstance(result, Choice):
            return NoMatch(intent.id, result.failed_criterion,
                           say.say_no_match(result.failed_criterion, intent.criteria,
                                            result.rooms_needed, result.max_pax_per_room,
                                            result.levels, same_trip=same_trip is not None))
        proposal = Proposal(self.new_id(), intent.id, result.product.id, result.start_date,
                            result.end_date, intent.criteria.pax or 1, result.product.price,
                            result.product.currency, result.reason, self.now())
        self.repos.proposals.add(proposal)
        return self._made(proposal, result.product, lang, rooms)

    def _price_ceiling(self, rejections: list, proposals: list) -> Optional[Decimal]:
        """Decisione M7 (§10.1): dopo un rifiuto per prezzo si propone solo qualcosa che costa
        meno; il tetto è il totale più basso tra le proposte rifiutate per prezzo. Se l'ordine
        aveva già il prezzo effettivo, il rifiuto è su quello (decisione 2026-09-26). Per prezzo:
        tipo `price` (M21-F) o un motivo di prezzo, come prima."""
        by_price = {r.proposal_id for r in rejections if r.kind == "price" or is_price_reason(r.reason)}
        totals = [self._rejected_total(p) for p in proposals if p.id in by_price]
        return min(totals) if totals else None

    def _rejected_total(self, proposal: Proposal) -> Decimal:
        order = self.repos.orders.get_by_proposal(proposal.id)
        return order.total if order is not None and order.total is not None else proposal.total_from

    def _made(self, proposal: Proposal, product: Optional[Product] = None,
              lang: str = "it", rooms: int = 1) -> ProposalMade:
        product = product or self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        return ProposalMade(proposal, summary, say.say_proposal(summary, proposal, lang, rooms),
                            rooms=rooms)

    # --- RF-83 ----------------------------------------------------------------

    def get_proposal_details(self, proposal_id: str) -> ProposalDetails:
        """Programma e dettagli del prodotto proposto, dal `raw` salvato dal sync: nessuna
        chiamata a HofJ e nessun cambio di stato, anche su una proposta rifiutata."""
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        product = self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        details = details_of(product.raw)
        return ProposalDetails(proposal.id, summary, details,
                               say.say_details(summary, details["program"] is not None, lang))

    # --- RF-12, RF-13, RF-17, RF-19, RF-45, RNF-03 ------------------------------

    def accept_proposal(self, proposal_id: str, traveler: Optional[TravelerProfile] = None,
                        rooms: Optional[int] = None
                        ) -> Union[OrderQueued, OrderStatusResponse, MissingTravelerData, IntentQuestion]:
        """RF-45: mette l'ordine in coda, senza chiamare HofJ né il pagamento: il carrello e il
        link li prepara il job d'acquisto (RF-46). Decisione 2026-09-26: il job si ferma al
        prezzo effettivo (`awaiting_confirmation`); una nuova chiamata sulla stessa proposta è
        la conferma e accoda il link. In entrambi i casi aspetta l'esito fino al tetto.
        `rooms` (M21-D, RF-65): correzione facoltativa delle camere, entro 1..pax (altrimenti
        scartata e detta) e non sotto il minimo del prodotto (RF-66: domanda, nessun ordine);
        aggiorna anche i criteri dell'intento (decisione M21-D, 3). Ignorata sulla conferma."""
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        lang = intent.criteria.language
        existing = self.repos.orders.get_by_proposal(proposal_id)
        if existing is not None and existing.status == OrderStatus.AWAITING_CONFIRMATION:
            return self._confirm(existing)
        if existing is not None:
            return self.get_order_status(existing.id)
        replaced = self.repos.orders.get_by_replacement(proposal_id)
        known = intent.profile if replaced is None else intent.profile.merged_with(replaced.traveler)
        profile = known.merged_with(traveler or TravelerProfile())   # RF-17: dati già dati
        missing = profile.missing_fields(proposal.pax)
        if missing:
            return MissingTravelerData(proposal_id, tuple(missing), say.say_missing(missing, lang))
        corrected, discarded = self._rooms_correction(proposal, rooms)
        chosen = corrected if corrected is not None else (intent.criteria.rooms or 1)
        product = self.repos.products.get(proposal.product_id)
        needed = rooms_needed(product, proposal.pax) if product else 1
        prefix = say.say_discarded(discarded, lang)
        if chosen < needed:   # M21-F: con l'id della proposta, come la domanda di RF-75
            return IntentQuestion(question_rooms(lang), say.prefixed(prefix, say.say_rooms_below_minimum(
                product.max_pax_per_room, proposal.pax, needed, lang)), proposal.id)
        if corrected is not None and corrected != intent.criteria.rooms:
            self.repos.intents.update_criteria(intent.id, replace(intent.criteria, rooms=corrected))
        now = self.now()
        enqueued_at = replaced.enqueued_at if replaced and replaced.enqueued_at else now   # RF-17
        quotes_on = self.price_quote_ttl > timedelta(0)
        order = Order(self.new_id(), proposal.id, intent.id, proposal.product_id, OrderStatus.QUEUED,
                      proposal.pax, proposal.price_from, None, proposal.currency, profile, now, now,
                      enqueued_at=enqueued_at, rooms=chosen, follows_quote=quotes_on,
                      last_seen_at=now)   # M19: l'accettazione è un segno di vita
        cached = self._cached_total(order, proposal, product, now) if quotes_on else None
        if cached is not None:   # RF-84: hit, nessun job e nessuna chiamata
            order = replace(order, status=OrderStatus.AWAITING_CONFIRMATION, total=cached,
                            follows_quote=False)
        try:
            self.repos.orders.add(order)
        except DuplicateOrder:
            return self.get_order_status(self.repos.orders.get_by_proposal(proposal_id).id)
        if cached is not None:
            result = self.get_order_status(order.id)
        else:
            if not quotes_on or self._lead(order, proposal, product, now):
                self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PURCHASE, order.id, JobStatus.PENDING,
                                            enqueued_at, now))
            result = self._await_progress(order.id)
        return replace(result, say=say.prefixed(prefix, result.say)) if prefix else result

    def _rooms_correction(self, proposal: Proposal, rooms: Optional[int]) -> Tuple[Optional[int], tuple]:
        """RF-53 per `rooms` su `accept_proposal`: intero in 1..pax, altrimenti scartato."""
        if rooms is None:
            return None, ()
        valid, discarded = validate_fields({"rooms": rooms}, self.now().date())
        value = valid.get("rooms")
        if value is not None and value > proposal.pax:
            return None, (("rooms", rooms),)
        return value, discarded

    # --- RF-84: cache del prezzo --------------------------------------------

    def _quote_key(self, order: Order) -> QuoteKey:
        return quote_key(order, self.repos.proposals.get(order.proposal_id).start_date)

    def _cached_total(self, order: Order, proposal: Proposal, product: Optional[Product],
                      now: datetime) -> Optional[Decimal]:
        """Il totale in cache se è `ready`, più giovane del TTL e il prodotto è ancora prenotabile."""
        quote = self.repos.quotes.get(quote_key(order, proposal.start_date))
        if (quote is None or quote.status != QuoteStatus.READY or product is None
                or not product.bookable or quote.priced_at < now - self.price_quote_ttl):
            return None
        return quote.total

    def _lead(self, order: Order, proposal: Proposal, product: Optional[Product], now: datetime) -> bool:
        """L'ordine, nato agganciato, prova a diventare leader. Se perde e intanto un leader ha
        pubblicato prende subito quel prezzo; altrimenti resta agganciato. Con il prodotto non
        prenotabile nessun prezzo in cache vale: la riga `ready` si prende comunque e il carrello
        vero dirà se il prodotto è tornato prenotabile (RF-34)."""
        key = quote_key(order, proposal.start_date)
        bookable = product is not None and product.bookable
        fresh_after = now - self.price_quote_ttl if bookable else now
        # `detach` e non `save_if_status`: se un rilascio ha già sganciato l'ordine (e gli ha dato
        # un job) non si accoda un secondo job né si prende il prezzo in cache
        if self.repos.quotes.claim(key, order.id, now, fresh_after):
            return self.repos.quotes.detach(replace(order, follows_quote=False))
        quote = self.repos.quotes.get(key)
        if quote is not None and quote.status == QuoteStatus.READY:
            self.repos.quotes.detach(replace(order, status=OrderStatus.AWAITING_CONFIRMATION,
                                             total=quote.total, follows_quote=False, updated_at=now))
        return False

    def _confirm(self, order: Order) -> Union[OrderQueued, OrderStatusResponse]:
        """Il sì al prezzo effettivo: l'ordine torna in coda. Con il carrello il job riparte dal
        link; senza (RF-84, prezzo dalla cache) riparte dal carrello e al passo 3 confronta il
        totale con quello confermato qui."""
        now = self.now()
        self.repos.orders.touch(order.id, now, SIGN_OF_LIFE_EVERY)   # M19
        cart = order.itinerary_id is not None
        confirmed = order if cart else replace(order, confirmed_total=order.total)
        self.repos.orders.save(replace(confirmed, status=OrderStatus.QUEUED, updated_at=now))
        if self.repos.jobs.active_for_order(order.id, JobKind.PURCHASE) is None:
            self.repos.jobs.enqueue(Job(self.new_id(), JobKind.PURCHASE, order.id, JobStatus.PENDING,
                                        now, now, step=STEP_LINK if cart else STEP_ITINERARY))
        return self._await_progress(order.id)

    def _await_progress(self, order_id: str) -> Union[OrderQueued, OrderStatusResponse]:
        """Rilegge l'ordine finché esce da `queued` o scade il tetto: nessuna chiamata a HofJ,
        il lavoro lo fa il worker."""
        waited = 0.0
        while waited < self.accept_wait_seconds:
            self.sleep(self.accept_poll_seconds)
            waited += self.accept_poll_seconds
            current = self.repos.orders.get(order_id)
            if current.status != OrderStatus.QUEUED:
                return self.get_order_status(order_id)
            unstick(self.repos, current, self.now(), self.new_id, self.now() - self.price_quote_ttl)   # RF-84
        order = self.repos.orders.get(order_id)
        if order.status != OrderStatus.QUEUED:
            return self.get_order_status(order_id)
        lang = self._lang(order)
        position, wait = self._queue_position(order.id)
        minutes = wait_minutes(wait or 0)
        sentence = (say.say_queued(minutes, lang, self._phone_tail(order)) if order.total is not None
                    else say.say_queued_for_price(minutes, lang))
        return OrderQueued(order.id, OrderStatus.QUEUED, position, wait, sentence)

    def _lang(self, order: Order) -> str:
        intent = self.repos.intents.get(order.intent_id)
        return intent.criteria.language if intent is not None else "it"

    def _phone_tail(self, order: Order) -> Optional[str]:
        """Ultime cifre da dire solo se l'SMS parte davvero; `None` lascia le frasi senza SMS."""
        return phone.tail(order.traveler.phone) if self.sms_enabled else None

    def _queue_position(self, order_id: str) -> Tuple[Optional[int], Optional[int]]:
        """RF-48: posizione tra gli acquisti in attesa e attesa stimata in secondi."""
        order = self.repos.orders.get(order_id)
        if order is not None and order.follows_quote:   # RF-84: la posizione del leader
            quote = self.repos.quotes.get(self._quote_key(order))
            if quote is not None and quote.status == QuoteStatus.PENDING:
                order_id = quote.leader_order_id
        position = self.repos.jobs.queued_purchase_position(order_id)
        if position is None:
            return None, None
        snap = self.repos.quota.snapshot(self.now())
        return position, estimated_wait_seconds(position, snap["purchases_per_minute"])

    # --- RF-25, RF-26 --------------------------------------------------------

    def get_order_status(self, order_id: str) -> OrderStatusResponse:
        order = self.orders.get(order_id)
        self.repos.orders.touch(order.id, self.now(), SIGN_OF_LIFE_EVERY)   # M19: segno di vita
        if order.follows_quote:   # RF-84: un leader uscito senza rilascio non blocca nessuno
            unstick(self.repos, order, self.now(), self.new_id, self.now() - self.price_quote_ttl)
            order = self.orders.get(order_id)
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        status = order.status
        tail = self._phone_tail(order)
        if status == OrderStatus.QUEUED:
            position, wait = self._queue_position(order.id)
            minutes = None if wait is None else wait_minutes(wait)
            return OrderStatusResponse(order.id, status, say.say_status(status, None, None, lang,
                                                                        total=order.total,
                                                                        minutes=minutes, phone_tail=tail),
                                       position=position, wait_seconds=wait)
        if status == OrderStatus.REPLACED and order.replacement_proposal_id:
            rooms = (intent.criteria.rooms or 1) if intent is not None else order.rooms
            proposal = self._made(self.repos.proposals.get(order.replacement_proposal_id), lang=lang,
                                  rooms=rooms)
            return OrderStatusResponse(order.id, status,
                                       say.say_replaced(proposal.product, proposal.proposal, lang, rooms),
                                       proposal=proposal)
        estimate = order.price_from * order.pax
        if status == OrderStatus.EXPIRED and order.payment_url is None:   # M19: scaduto in coda
            return OrderStatusResponse(order.id, status, say.say_expired_silent(lang))
        payable = status == OrderStatus.AWAITING_PAYMENT
        if payable:
            self._check_payment_now(order.id)
        differs = None if order.total is None else order.total != estimate
        sentence = say.say_status(status, order.booking_code, order.failure_reason, lang, order.total,
                                  price_from_total=estimate, phone_tail=tail, pax=order.pax)
        if (status == OrderStatus.AWAITING_CONFIRMATION and order.confirmed_total is not None
                and order.total != order.confirmed_total):   # RF-84
            sentence = say.say_price_changed_since(order.total, order.confirmed_total, lang)
        return OrderStatusResponse(
            order.id, status, sentence,
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
