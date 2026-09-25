"""Repository in memoria: test del dominio (RNF-09) e app nei test delle superfici."""
import threading
from dataclasses import replace
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set

from vela.domain.models import (Criteria, Intent, Order, OrderStatus, Product, Proposal,
                                QuotaClass, Rejection)
from vela.domain.quota import (QuotaWindow, after_429, describe, fresh_window, from_snapshot,
                               rolled, try_acquire)
from vela.ports.hofj import QuotaSnapshot
from vela.ports.quota import DEFAULT_LIMIT_PER_MINUTE
from vela.ports.repositories import DuplicateOrder


class MemoryProducts:
    def __init__(self):
        self._items: Dict[str, Product] = {}

    def upsert_many(self, products: Iterable[Product]) -> None:
        for p in products:
            self._items[p.id] = p

    def count(self) -> int:
        return len(self._items)

    def list_all(self) -> List[Product]:
        return list(self._items.values())

    def get(self, product_id: str) -> Optional[Product]:
        return self._items.get(product_id)

    def last_fetched_at(self) -> Optional[datetime]:
        return max((p.fetched_at for p in self._items.values()), default=None)


class MemoryIntents:
    def __init__(self):
        self._items: Dict[str, Intent] = {}

    def add(self, intent: Intent) -> None:
        self._items[intent.id] = intent

    def get(self, intent_id: str) -> Optional[Intent]:
        return self._items.get(intent_id)

    def update_criteria(self, intent_id: str, criteria: Criteria) -> None:
        intent = self._items.get(intent_id)
        if intent is not None:
            self._items[intent_id] = replace(intent, criteria=criteria)


class MemoryProposals:
    def __init__(self):
        self._items: Dict[str, Proposal] = {}

    def add(self, proposal: Proposal) -> None:
        self._items[proposal.id] = proposal

    def get(self, proposal_id: str) -> Optional[Proposal]:
        return self._items.get(proposal_id)

    def list_for_intent(self, intent_id: str) -> List[Proposal]:
        return sorted((p for p in self._items.values() if p.intent_id == intent_id),
                      key=lambda p: (p.created_at, p.id))


class MemoryOrders:
    def __init__(self):
        self._items: Dict[str, Order] = {}
        self._lock = threading.Lock()

    def add(self, order: Order) -> None:
        with self._lock:
            if any(o.proposal_id == order.proposal_id for o in self._items.values()):
                raise DuplicateOrder(order.proposal_id)
            self._items[order.id] = order

    def get(self, order_id: str) -> Optional[Order]:
        return self._items.get(order_id)

    def get_by_proposal(self, proposal_id: str) -> Optional[Order]:
        for o in self._items.values():
            if o.proposal_id == proposal_id:
                return o
        return None

    def save(self, order: Order) -> None:
        with self._lock:
            self._items[order.id] = order

    def ids_with_status(self, status: OrderStatus) -> List[str]:
        return sorted(o.id for o in self._items.values() if o.status == status)


class MemoryRejections:
    def __init__(self):
        self._items: Dict[str, Rejection] = {}   # per proposal_id

    def add(self, rejection: Rejection) -> None:
        self._items.setdefault(rejection.proposal_id, rejection)

    def product_ids_for_intent(self, intent_id: str) -> Set[str]:
        return {r.product_id for r in self._items.values() if r.intent_id == intent_id}

    def proposal_ids_for_intent(self, intent_id: str) -> Set[str]:
        return {r.proposal_id for r in self._items.values() if r.intent_id == intent_id}


class MemoryRepositories:
    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.products = MemoryProducts()
        self.intents = MemoryIntents()
        self.proposals = MemoryProposals()
        self.orders = MemoryOrders()
        self.rejections = MemoryRejections()


class MemoryQuota:
    """Contatore di quota in memoria (test e replay): stesse regole di Postgres, lock di processo."""

    def __init__(self, margin: float = 0.10, reserve: float = 0.20):
        self.margin, self.reserve = margin, reserve
        self._lock = threading.Lock()
        self._window: Optional[QuotaWindow] = None

    def _current(self, now: datetime) -> QuotaWindow:
        return self._window or fresh_window(now, DEFAULT_LIMIT_PER_MINUTE)

    def acquire(self, cls: QuotaClass, n: int, now: datetime, purchase_waiting: bool = False) -> bool:
        with self._lock:
            new = try_acquire(self._current(now), cls, n, now, self.margin, self.reserve, purchase_waiting)
            if new is not None:
                self._window = new
            return new is not None

    def on_429(self, now: datetime) -> None:
        with self._lock:
            self._window = after_429(self._current(now), now, self.margin, self.reserve)

    def needs_refresh(self, now: datetime) -> bool:
        with self._lock:
            return self._window is None or self._window.needs_refresh

    def sync_from_snapshot(self, snapshot: QuotaSnapshot) -> None:
        with self._lock:
            self._window = from_snapshot(snapshot.limit_per_minute, snapshot.used_in_window,
                                         snapshot.window_started_at, snapshot.window_ends_at)

    def snapshot(self, now: datetime) -> dict:
        with self._lock:
            return describe(self._current(now), now, self.margin, self.reserve)

    def next_window_start(self, now: datetime) -> datetime:
        with self._lock:
            return rolled(self._current(now), now).window_end

