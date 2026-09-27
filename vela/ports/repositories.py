"""Repository del dominio (RNF-01): intenti, proposte, ordini, rifiuti e catalogo stanno fuori dal processo."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import ContextManager, Dict, Iterable, List, NamedTuple, Optional, Protocol, Set

from vela.domain.models import (Criteria, Intent, Order, OrderStatus, PriceQuote, Product, Proposal,
                                QuoteKey, Rejection)
from vela.ports.jobs import JobRepository
from vela.ports.quota import QuotaStore


class DuplicateOrder(Exception):
    """Esiste già un ordine per la proposta (RNF-03)."""


class SyncState(NamedTuple):
    """Quanto serve al sync (M10) per decidere se scaricare il dettaglio di un prodotto."""
    brand: Optional[str]
    updated_at: Optional[str]
    archived: bool


class ProductRepository(Protocol):
    def upsert_many(self, products: Iterable[Product]) -> None: ...
    def count(self) -> int: ...
    def list_all(self) -> List[Product]: ...
    def get(self, product_id: str) -> Optional[Product]: ...
    def last_fetched_at(self) -> Optional[datetime]: ...
    def set_bookable(self, product_id: str, bookable: bool, checked_at: datetime) -> None: ...
    def archive_missing(self, keep_ids: Iterable[str], brand: Optional[str] = None) -> int: ...
    def sync_state(self, ids: Iterable[str]) -> Dict[str, SyncState]: ...
    def mark_seen(self, ids: Iterable[str], brand: str, sport: str, seen_at: datetime) -> None: ...


class IntentRepository(Protocol):
    def add(self, intent: Intent) -> None: ...
    def get(self, intent_id: str) -> Optional[Intent]: ...
    def update_criteria(self, intent_id: str, criteria: Criteria) -> None: ...


class ProposalRepository(Protocol):
    def add(self, proposal: Proposal) -> None: ...
    def get(self, proposal_id: str) -> Optional[Proposal]: ...
    def list_for_intent(self, intent_id: str) -> List[Proposal]: ...


class OrderRepository(Protocol):
    def add(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Optional[Order]: ...
    def get_by_proposal(self, proposal_id: str) -> Optional[Order]: ...
    def get_by_replacement(self, proposal_id: str) -> Optional[Order]: ...
    def save(self, order: Order) -> None: ...
    def save_if_status(self, order: Order, expected: OrderStatus) -> bool:
        """Salva solo se l'ordine è ancora in `expected`, in modo atomico; dice se ha salvato."""
    def ids_with_status(self, status: OrderStatus) -> List[str]: ...
    def orphan_itineraries_total(self) -> int: ...
    def touch(self, order_id: str, at: datetime, min_interval: timedelta) -> bool:
        """M19: `last_seen_at = at` se è nullo o più vecchio di `min_interval`; dice se ha scritto.
        È l'unica scrittura di `last_seen_at` dopo l'inserimento: `save` e `save_if_status` non
        lo toccano, così una scrittura con l'ordine letto prima non lo riporta indietro."""


class RejectionRepository(Protocol):
    def add(self, rejection: Rejection) -> None: ...
    def product_ids_for_intent(self, intent_id: str) -> Set[str]: ...
    def proposal_ids_for_intent(self, intent_id: str) -> Set[str]: ...
    def list_for_intent(self, intent_id: str) -> List[Rejection]: ...


class QuoteRepository(Protocol):
    """RF-84: cache del prezzo per chiave, condivisa tra le istanze."""
    def get(self, key: QuoteKey) -> Optional[PriceQuote]: ...
    def claim(self, key: QuoteKey, order_id: str, now: datetime, fresh_after: datetime) -> bool:
        """Atomica: `order_id` diventa leader (riga `pending`) se la riga manca, se è `ready` con
        `priced_at < fresh_after`, o se è `pending` con un leader che non è più `queued` oppure
        che non ha un job d'acquisto attivo e ha preso la riga prima di `fresh_after`."""
    def publish(self, key: QuoteKey, leader_order_id: str, total: Decimal, now: datetime) -> List[str]:
        """Riga `ready` con il totale e, nella stessa transazione, gli ordini `queued` agganciati
        alla chiave passano a `awaiting_confirmation` con quel totale (fanout). Id sbloccati."""
    def release(self, key: QuoteKey, leader_order_id: str) -> List[Order]:
        """Cancella la riga se è `pending` con quel leader e sgancia i suoi ordini
        (`follows_quote` falso), restituiti in ordine di id; altrimenti []."""
    def detach(self, order: Order) -> bool:
        """Salva `order` solo se l'ordine salvato è ancora `queued` e agganciato, in modo atomico
        rispetto a `release` e `publish`; dice se ha salvato."""


class Repositories(Protocol):
    products: ProductRepository
    intents: IntentRepository
    proposals: ProposalRepository
    orders: OrderRepository
    rejections: RejectionRepository
    jobs: JobRepository
    quota: QuotaStore
    quotes: QuoteRepository

    def catalog_lock(self) -> ContextManager[bool]:
        """Un solo sync del catalogo alla volta fra tutte le istanze (RF-30): True se preso,
        False se un altro sync lo tiene già; mai bloccante."""
        ...
