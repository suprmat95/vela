"""Repository in memoria: test del dominio (RNF-09) e app nei test delle superfici."""
import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set

from vela.domain.models import (Criteria, Intent, Job, JobKind, JobStatus, Order, OrderStatus,
                                Product, Proposal, QuotaClass, Rejection)
from vela.domain.quota import (CALLS_PER_PURCHASE, DEFAULT_BURST, DEFAULT_FLOOR, BucketRules, QuotaBucket, after_429,
                               claim_refresh, describe, fresh_bucket, from_snapshot,
                               available_at, try_take)
from vela.ports.hofj import QuotaSnapshot
from vela.ports.quota import DEFAULT_LIMIT_PER_MINUTE
from vela.ports.repositories import DuplicateOrder, SyncState


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

    def set_bookable(self, product_id: str, bookable: bool, checked_at: datetime) -> None:
        p = self._items.get(product_id)
        if p is not None:
            self._items[product_id] = replace(p, bookable=bookable, bookable_checked_at=checked_at)

    def archive_missing(self, keep_ids: Iterable[str], brand: Optional[str] = None) -> int:
        keep = set(keep_ids)
        gone = [p for p in self._items.values() if not p.archived and p.id not in keep
                and (brand is None or p.brand == brand)]
        for p in gone:
            self._items[p.id] = replace(p, archived=True)
        return len(gone)

    def sync_state(self, ids: Iterable[str]) -> Dict[str, SyncState]:
        found = (self._items.get(i) for i in ids)
        return {p.id: SyncState(p.brand, p.hofj_updated_at, p.archived) for p in found if p is not None}

    def mark_seen(self, ids: Iterable[str], brand: str, sport: str, seen_at: datetime) -> None:
        for i in ids:
            p = self._items.get(i)
            if p is not None:
                self._items[i] = replace(p, brand=brand, sport=sport, fetched_at=seen_at)


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

    def get_by_replacement(self, proposal_id: str) -> Optional[Order]:
        return next((o for o in self._items.values() if o.replacement_proposal_id == proposal_id), None)

    def save(self, order: Order) -> None:
        with self._lock:
            self._items[order.id] = order

    def orphan_itineraries_total(self) -> int:
        return sum(o.orphan_itineraries for o in self._items.values())

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

    def list_for_intent(self, intent_id: str) -> List[Rejection]:
        return [r for r in self._items.values() if r.intent_id == intent_id]


ACTIVE = (JobStatus.PENDING, JobStatus.RUNNING)
CLAIM_PRIORITY = {JobKind.BOOKING: 0, JobKind.PAYMENT_CHECK: 1, JobKind.SMS_LINK: 2,
                  JobKind.SMS_CONFIRMED: 2, JobKind.PURCHASE: 3}


def claimable(j: Job, now: datetime, lease_seconds: int) -> bool:
    if j.status == JobStatus.PENDING:
        return j.run_after <= now
    return (j.status == JobStatus.RUNNING and j.locked_at is not None
            and (now - j.locked_at).total_seconds() >= lease_seconds)


class MemoryJobs:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def enqueue(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def save(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def claim(self, now: datetime, lease_seconds: int) -> Optional[Job]:
        with self._lock:
            ready = [j for j in self._jobs.values() if claimable(j, now, lease_seconds)]
            if not ready:
                return None
            best = min(ready, key=lambda j: (CLAIM_PRIORITY[j.kind], j.enqueued_at, j.id))
            claimed = replace(best, status=JobStatus.RUNNING, locked_at=now)
            self._jobs[claimed.id] = claimed
            return claimed

    def active_for_order(self, order_id: str, kind: JobKind) -> Optional[Job]:
        return next((j for j in self._jobs.values()
                     if j.order_id == order_id and j.kind == kind and j.status in ACTIVE), None)

    def queued_purchase_position(self, order_id: str) -> Optional[int]:
        pending = sorted((j for j in self._jobs.values()
                          if j.kind == JobKind.PURCHASE and j.status == JobStatus.PENDING),
                         key=lambda j: (j.enqueued_at, j.id))
        ids = [j.order_id for j in pending]
        return ids.index(order_id) + 1 if order_id in ids else None

    def purchase_waiting(self) -> bool:
        return any(j.kind == JobKind.PURCHASE and j.status in ACTIVE for j in self._jobs.values())

    def oldest_purchase_enqueued_at(self) -> Optional[datetime]:
        return min((j.enqueued_at for j in self._jobs.values()
                    if j.kind == JobKind.PURCHASE and j.status in ACTIVE), default=None)


class MemoryRepositories:
    def __init__(self, quota_margin: float = 0.10, booking_reserve: float = 0.20,
                 quota_burst: int = DEFAULT_BURST, quota_floor: int = DEFAULT_FLOOR):
        self.quota_rules = BucketRules(quota_margin, booking_reserve, quota_burst, quota_floor)
        self._catalog_lock = threading.Lock()
        self.clear()

    @contextmanager
    def catalog_lock(self):
        acquired = self._catalog_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                self._catalog_lock.release()

    def clear(self) -> None:
        self.products = MemoryProducts()
        self.intents = MemoryIntents()
        self.proposals = MemoryProposals()
        self.orders = MemoryOrders()
        self.rejections = MemoryRejections()
        self.jobs = MemoryJobs()
        self.quota = MemoryQuota(rules=self.quota_rules)


class MemoryQuota:
    """Token bucket in memoria (test e replay): stesse regole di Postgres, lock di processo."""

    def __init__(self, margin: float = 0.10, reserve: float = 0.20, rules: Optional[BucketRules] = None):
        self.rules = rules or BucketRules(margin, reserve)
        self._lock = threading.Lock()
        self._bucket: Optional[QuotaBucket] = None

    def _current(self, now: datetime) -> QuotaBucket:
        return self._bucket or fresh_bucket(now, DEFAULT_LIMIT_PER_MINUTE, self.rules)

    def acquire(self, cls: QuotaClass, n: int, now: datetime, purchase_waiting: bool = False) -> bool:
        with self._lock:
            new = try_take(self._current(now), cls, n, now, self.rules, purchase_waiting)
            if new is not None:
                self._bucket = new
            return new is not None

    def on_429(self, now: datetime, hold_seconds: float = 0.0) -> None:
        with self._lock:
            self._bucket = after_429(self._current(now), now, self.rules, hold_seconds)

    def needs_refresh(self, now: datetime) -> bool:
        with self._lock:
            return self._current(now).needs_refresh

    def claim_refresh(self, now: datetime) -> bool:
        with self._lock:
            new = claim_refresh(self._current(now), now, self.rules)
            if new is not None:
                self._bucket = new
            return new is not None

    def mark_refresh_needed(self, now: datetime) -> None:
        with self._lock:
            self._bucket = replace(self._current(now), needs_refresh=True)

    def sync_from_snapshot(self, snapshot: QuotaSnapshot, now: datetime) -> None:
        with self._lock:
            self._bucket = from_snapshot(self._current(now), snapshot.limit_per_minute,
                                         snapshot.used_in_window, snapshot.window_started_at,
                                         snapshot.window_ends_at, now, self.rules)

    def snapshot(self, now: datetime) -> dict:
        with self._lock:
            return describe(self._current(now), now, self.rules)

    def next_window_start(self, now: datetime, cls: QuotaClass = QuotaClass.PURCHASE,
                          n: int = CALLS_PER_PURCHASE) -> datetime:
        with self._lock:
            return available_at(self._current(now), now, self.rules, cls, n)
