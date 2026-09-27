"""Repository Postgres con SQLAlchemy Core (RNF-01): una transazione per metodo, nessuno stato in processo."""
import threading
from dataclasses import replace
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import and_, case, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from vela.adapters.schema import (intents_t, jobs_t, orders_t, price_quotes_t, products_t,
                                  proposals_t, quota_window_t, rejections_t)
from vela.domain.models import (Availability, Criteria, Intent, Job, JobKind, JobStatus, Order,
                                OrderStatus, PriceQuote, Product, Proposal, QuotaClass, QuoteKey,
                                QuoteStatus, Rejection, criteria_from_dict, criteria_to_dict,
                                profile_from_dict, profile_to_dict)
from vela.domain.quota import (CALLS_PER_PURCHASE, DEFAULT_BURST, DEFAULT_FLOOR, BucketRules, QuotaBucket, after_429,
                               claim_refresh, describe, fresh_bucket, from_snapshot,
                               available_at, try_take)
from vela.ports.hofj import QuotaSnapshot
from vela.ports.jobs import DuplicateJob
from vela.ports.quota import DEFAULT_LIMIT_PER_MINUTE
from vela.ports.repositories import DuplicateOrder, SyncState


def _product_row(p: Product) -> dict:
    return {
        "id": p.id, "title": p.title, "slug": p.slug, "short_description": p.short_description,
        "sport": p.sport, "category": p.category, "destination": p.destination,
        "country": p.country, "venue": p.venue, "hotel": p.hotel, "price": p.price,
        "currency": p.currency, "min_pax": p.min_pax, "max_pax": p.max_pax,
        "min_date": p.min_date, "max_date": p.max_date,
        "availabilities": [{"start": a.start.isoformat(), "end": a.end.isoformat()}
                           for a in p.availabilities],
        "duration_days": p.duration_days, "hofj_updated_at": p.hofj_updated_at, "raw": p.raw,
        "fetched_at": p.fetched_at, "bookable": p.bookable,
        "bookable_checked_at": p.bookable_checked_at, "archived": p.archived,
        "provider_id": p.provider_id, "brand": p.brand,
        "featured": p.featured, "special_offer": p.special_offer,
        "max_pax_per_room": p.max_pax_per_room,
    }


def _product(m, raw: Optional[dict]) -> Product:
    return Product(
        id=m["id"], title=m["title"], slug=m["slug"], short_description=m["short_description"],
        sport=m["sport"], category=m["category"], destination=m["destination"],
        country=m["country"], venue=m["venue"], hotel=m["hotel"], price=m["price"],
        currency=m["currency"], min_pax=m["min_pax"], max_pax=m["max_pax"],
        min_date=m["min_date"], max_date=m["max_date"],
        availabilities=tuple(Availability(date.fromisoformat(a["start"]), date.fromisoformat(a["end"]))
                             for a in m["availabilities"]),
        duration_days=m["duration_days"], hofj_updated_at=m["hofj_updated_at"],
        raw=raw if raw is not None else {}, fetched_at=m["fetched_at"], bookable=m["bookable"],
        bookable_checked_at=m["bookable_checked_at"], archived=m["archived"],
        provider_id=m["provider_id"], brand=m["brand"],
        featured=bool(m["featured"]), special_offer=bool(m["special_offer"]),
        max_pax_per_room=m["max_pax_per_room"])


class PostgresProducts:
    def __init__(self, engine: Engine):
        self.engine = engine

    def upsert_many(self, products: Iterable[Product]) -> None:
        rows = [_product_row(p) for p in products]
        if not rows:
            return
        stmt = pg_insert(products_t).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[products_t.c.id],
            set_={c.name: stmt.excluded[c.name] for c in products_t.c if c.name != "id"})
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(products_t)).scalar_one()

    def list_all(self) -> List[Product]:
        columns = [c for c in products_t.c if c.name != "raw"]
        with self.engine.connect() as conn:
            rows = conn.execute(select(*columns).order_by(products_t.c.id)).mappings().all()
        return [_product(m, None) for m in rows]

    def get(self, product_id: str) -> Optional[Product]:
        with self.engine.connect() as conn:
            m = conn.execute(select(products_t).where(products_t.c.id == product_id)).mappings().first()
        return None if m is None else _product(m, m["raw"])

    def last_fetched_at(self) -> Optional[datetime]:
        with self.engine.connect() as conn:
            return conn.execute(select(func.max(products_t.c.fetched_at))).scalar_one()

    def set_bookable(self, product_id: str, bookable: bool, checked_at: datetime) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(products_t).where(products_t.c.id == product_id)
                         .values(bookable=bookable, bookable_checked_at=checked_at))

    def archive_missing(self, keep_ids: Iterable[str], brand: Optional[str] = None) -> int:
        """Archivia (mai DELETE: proposte e ordini hanno FK) i prodotti attivi fuori da `keep_ids`;
        con `brand` solo tra i prodotti di quel brand (M10)."""
        stmt = update(products_t).where(products_t.c.archived.is_(False))
        if brand is not None:
            stmt = stmt.where(products_t.c.brand == brand)
        keep = list(keep_ids)
        if keep:
            stmt = stmt.where(products_t.c.id.notin_(keep))
        with self.engine.begin() as conn:
            return conn.execute(stmt.values(archived=True)).rowcount


    def sync_state(self, ids: Iterable[str]) -> Dict[str, SyncState]:
        wanted = list(ids)
        if not wanted:
            return {}
        stmt = (select(products_t.c.id, products_t.c.brand, products_t.c.hofj_updated_at,
                       products_t.c.archived)
                .where(products_t.c.id.in_(wanted)))
        with self.engine.connect() as conn:
            return {r.id: SyncState(r.brand, r.hofj_updated_at, r.archived) for r in conn.execute(stmt)}

    def mark_seen(self, ids: Iterable[str], brand: str, sport: str, seen_at: datetime) -> None:
        wanted = list(ids)
        if not wanted:
            return
        with self.engine.begin() as conn:
            conn.execute(update(products_t).where(products_t.c.id.in_(wanted))
                         .values(brand=brand, sport=sport, fetched_at=seen_at))


class PostgresIntents:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, intent: Intent) -> None:
        with self.engine.begin() as conn:
            conn.execute(intents_t.insert().values(
                id=intent.id, text=intent.text, criteria=criteria_to_dict(intent.criteria),
                profile=profile_to_dict(intent.profile), language=intent.criteria.language,
                created_at=intent.created_at))

    def get(self, intent_id: str) -> Optional[Intent]:
        with self.engine.connect() as conn:
            m = conn.execute(select(intents_t).where(intents_t.c.id == intent_id)).mappings().first()
        if m is None:
            return None
        return Intent(m["id"], m["text"], criteria_from_dict(m["criteria"]),
                      profile_from_dict(m["profile"]), m["created_at"])

    def update_criteria(self, intent_id: str, criteria: Criteria) -> None:
        with self.engine.begin() as conn:
            conn.execute(intents_t.update().where(intents_t.c.id == intent_id).values(
                criteria=criteria_to_dict(criteria), language=criteria.language))


def _proposal(m) -> Proposal:
    return Proposal(m["id"], m["intent_id"], m["product_id"], m["start_date"], m["end_date"],
                    m["pax"], m["price_from"], m["currency"], m["reason"], m["created_at"])


class PostgresProposals:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, p: Proposal) -> None:
        with self.engine.begin() as conn:
            conn.execute(proposals_t.insert().values(
                id=p.id, intent_id=p.intent_id, product_id=p.product_id, start_date=p.start_date,
                end_date=p.end_date, pax=p.pax, price_from=p.price_from, currency=p.currency,
                reason=p.reason, created_at=p.created_at))

    def get(self, proposal_id: str) -> Optional[Proposal]:
        with self.engine.connect() as conn:
            m = conn.execute(select(proposals_t).where(proposals_t.c.id == proposal_id)).mappings().first()
        return None if m is None else _proposal(m)

    def list_for_intent(self, intent_id: str) -> List[Proposal]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(proposals_t).where(proposals_t.c.intent_id == intent_id)
                                .order_by(proposals_t.c.created_at, proposals_t.c.id)).mappings().all()
        return [_proposal(m) for m in rows]


def _order_row(o: Order) -> dict:
    return {
        "id": o.id, "proposal_id": o.proposal_id, "intent_id": o.intent_id,
        "product_id": o.product_id, "status": o.status.value, "pax": o.pax,
        "price_from": o.price_from, "total": o.total, "currency": o.currency,
        "traveler": profile_to_dict(o.traveler), "itinerary_id": o.itinerary_id,
        "payment_url": o.payment_url, "payment_ref": o.payment_ref,
        "booking_code": o.booking_code, "failure_reason": o.failure_reason,
        "created_at": o.created_at, "updated_at": o.updated_at, "paid_at": o.paid_at,
        "enqueued_at": o.enqueued_at, "replacement_proposal_id": o.replacement_proposal_id,
        "orphan_itineraries": o.orphan_itineraries, "rooms": o.rooms,
        "follows_quote": o.follows_quote, "confirmed_total": o.confirmed_total,
    }


def _order(m) -> Order:
    return Order(m["id"], m["proposal_id"], m["intent_id"], m["product_id"],
                 OrderStatus(m["status"]), m["pax"], m["price_from"], m["total"], m["currency"],
                 profile_from_dict(m["traveler"]), m["created_at"], m["updated_at"],
                 itinerary_id=m["itinerary_id"], payment_url=m["payment_url"],
                 payment_ref=m["payment_ref"], booking_code=m["booking_code"],
                 failure_reason=m["failure_reason"], paid_at=m["paid_at"],
                 enqueued_at=m["enqueued_at"], replacement_proposal_id=m["replacement_proposal_id"],
                 orphan_itineraries=m["orphan_itineraries"], rooms=m["rooms"],
                 follows_quote=bool(m["follows_quote"]), confirmed_total=m["confirmed_total"])


class PostgresOrders:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, order: Order) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(orders_t.insert().values(**_order_row(order)))
        except IntegrityError as exc:
            if "uq_orders_proposal_id" in str(exc.orig):
                raise DuplicateOrder(order.proposal_id) from exc
            raise

    def get(self, order_id: str) -> Optional[Order]:
        with self.engine.connect() as conn:
            m = conn.execute(select(orders_t).where(orders_t.c.id == order_id)).mappings().first()
        return None if m is None else _order(m)

    def get_by_proposal(self, proposal_id: str) -> Optional[Order]:
        with self.engine.connect() as conn:
            m = conn.execute(select(orders_t).where(orders_t.c.proposal_id == proposal_id)).mappings().first()
        return None if m is None else _order(m)

    def get_by_replacement(self, proposal_id: str) -> Optional[Order]:
        with self.engine.connect() as conn:
            m = conn.execute(select(orders_t).where(orders_t.c.replacement_proposal_id == proposal_id)).mappings().first()
        return None if m is None else _order(m)

    def save(self, order: Order) -> None:
        values = {k: v for k, v in _order_row(order).items() if k != "id"}
        with self.engine.begin() as conn:
            conn.execute(update(orders_t).where(orders_t.c.id == order.id).values(**values))

    def save_if_status(self, order: Order, expected: OrderStatus) -> bool:
        """Un solo `UPDATE ... WHERE status = expected`: tra due scritture concorrenti vince una."""
        values = {k: v for k, v in _order_row(order).items() if k != "id"}
        with self.engine.begin() as conn:
            res = conn.execute(update(orders_t).where(orders_t.c.id == order.id,
                                                      orders_t.c.status == expected.value).values(**values))
        return res.rowcount == 1

    def ids_with_status(self, status: OrderStatus) -> List[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(orders_t.c.id).where(orders_t.c.status == status.value)
                                .order_by(orders_t.c.id)).all()
        return [r[0] for r in rows]

    def orphan_itineraries_total(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.coalesce(func.sum(orders_t.c.orphan_itineraries), 0))).scalar())


class PostgresRejections:
    def __init__(self, engine: Engine):
        self.engine = engine

    def add(self, r: Rejection) -> None:
        stmt = pg_insert(rejections_t).values(
            intent_id=r.intent_id, proposal_id=r.proposal_id, product_id=r.product_id,
            reason=r.reason, created_at=r.created_at).on_conflict_do_nothing(
            index_elements=[rejections_t.c.proposal_id])
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def product_ids_for_intent(self, intent_id: str) -> Set[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(rejections_t.c.product_id)
                                .where(rejections_t.c.intent_id == intent_id)).all()
        return {r[0] for r in rows}

    def proposal_ids_for_intent(self, intent_id: str) -> Set[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(rejections_t.c.proposal_id)
                                .where(rejections_t.c.intent_id == intent_id)).all()
        return {r[0] for r in rows}

    def list_for_intent(self, intent_id: str) -> List[Rejection]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(rejections_t).where(rejections_t.c.intent_id == intent_id)
                                .order_by(rejections_t.c.created_at)).mappings().all()
        return [Rejection(m["intent_id"], m["proposal_id"], m["product_id"], m["reason"],
                          m["created_at"]) for m in rows]


_QUOTE_FIELDS = ("status", "leader_order_id", "total", "priced_at", "updated_at")


def _quote_where(key: QuoteKey):
    t = price_quotes_t.c
    return and_(t.product_id == key.product_id, t.start_date == key.start_date,
                t.adults == key.adults, t.rooms == key.rooms, t.currency == key.currency)


def _followers_where(key: QuoteKey):
    """Ordini `queued` agganciati alla chiave; la data sta sulla proposta."""
    o = orders_t.c
    return and_(o.follows_quote.is_(True), o.status == OrderStatus.QUEUED.value,
                o.product_id == key.product_id, o.pax == key.adults, o.rooms == key.rooms,
                o.currency == key.currency,
                o.proposal_id.in_(select(proposals_t.c.id).where(proposals_t.c.start_date == key.start_date)))


def _quote(m) -> PriceQuote:
    return PriceQuote(QuoteKey(m["product_id"], m["start_date"], m["adults"], m["rooms"], m["currency"]),
                      QuoteStatus(m["status"]), m["leader_order_id"], m["updated_at"],
                      m["total"], m["priced_at"])


class PostgresQuotes:
    """RF-84: una riga per chiave; elezione del leader con un solo `INSERT ... ON CONFLICT`."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, key: QuoteKey) -> Optional[PriceQuote]:
        with self.engine.connect() as conn:
            m = conn.execute(select(price_quotes_t).where(_quote_where(key))).mappings().first()
        return None if m is None else _quote(m)

    def _upsert(self, key: QuoteKey, **values):
        stmt = pg_insert(price_quotes_t).values(**key._asdict(), **values)
        return stmt, {f: stmt.excluded[f] for f in _QUOTE_FIELDS}

    def claim(self, key: QuoteKey, order_id: str, now: datetime, fresh_after: datetime) -> bool:
        """Due passi nella stessa transazione. `INSERT ... DO NOTHING` vince se la riga manca;
        altrimenti `SELECT ... FOR UPDATE` mette in fila i concorrenti sulla riga e ognuno, con
        statement nuovi (READ COMMITTED), vede il leader scritto da chi lo precede. Un solo
        `ON CONFLICT DO UPDATE ... WHERE` non basta: la sottoquery sul leader userebbe la snapshot
        di inizio statement e potrebbe non vedere un leader appena confermato."""
        t = price_quotes_t.c
        pending = dict(status=QuoteStatus.PENDING.value, leader_order_id=order_id, total=None,
                       priced_at=None, updated_at=now)
        with self.engine.begin() as conn:
            inserted = conn.execute(pg_insert(price_quotes_t).values(**key._asdict(), **pending)
                                    .on_conflict_do_nothing().returning(t.leader_order_id)).first()
            if inserted is not None:
                return True
            row = conn.execute(select(price_quotes_t).where(_quote_where(key)).with_for_update()).mappings().first()
            if row is None:   # cancellata tra i due statement: riprova l'inserimento
                return conn.execute(pg_insert(price_quotes_t).values(**key._asdict(), **pending)
                                    .on_conflict_do_nothing().returning(t.leader_order_id)).first() is not None
            if row["status"] == QuoteStatus.READY.value:
                takeable = row["priced_at"] < fresh_after
            else:
                leader_id = row["leader_order_id"]
                leader = conn.execute(select(orders_t.c.status).where(orders_t.c.id == leader_id)).scalar()
                busy = conn.execute(select(jobs_t.c.id).where(
                    jobs_t.c.order_id == leader_id, jobs_t.c.kind == JobKind.PURCHASE.value,
                    jobs_t.c.status.in_(ACTIVE)).limit(1)).first() is not None
                takeable = (leader != OrderStatus.QUEUED.value
                            or (not busy and row["updated_at"] < fresh_after))
            if takeable:
                conn.execute(update(price_quotes_t).where(_quote_where(key)).values(**pending))
            return takeable

    def publish(self, key: QuoteKey, leader_order_id: str, total: Decimal, now: datetime) -> List[str]:
        stmt, excluded = self._upsert(key, status=QuoteStatus.READY.value, leader_order_id=leader_order_id,
                                      total=total, priced_at=now, updated_at=now)
        fanout = (update(orders_t).where(_followers_where(key))
                  .values(status=OrderStatus.AWAITING_CONFIRMATION.value, total=total,
                          follows_quote=False, updated_at=now)
                  .returning(orders_t.c.id))
        with self.engine.begin() as conn:
            conn.execute(stmt.on_conflict_do_update(index_elements=list(QuoteKey._fields), set_=excluded))
            return sorted(r[0] for r in conn.execute(fanout))

    def release(self, key: QuoteKey, leader_order_id: str) -> List[Order]:
        t = price_quotes_t.c
        with self.engine.begin() as conn:
            gone = conn.execute(delete(price_quotes_t).where(
                _quote_where(key), t.status == QuoteStatus.PENDING.value,
                t.leader_order_id == leader_order_id)).rowcount
            if gone != 1:
                return []
            rows = conn.execute(update(orders_t).where(_followers_where(key))
                                .values(follows_quote=False).returning(*orders_t.c)).mappings().all()
        return sorted((_order(m) for m in rows), key=lambda o: o.id)

    def detach(self, order: Order) -> bool:
        values = {k: v for k, v in _order_row(order).items() if k != "id"}
        with self.engine.begin() as conn:
            res = conn.execute(update(orders_t).where(
                orders_t.c.id == order.id, orders_t.c.status == OrderStatus.QUEUED.value,
                orders_t.c.follows_quote.is_(True)).values(**values))
        return res.rowcount == 1


def _job_row(j: Job) -> dict:
    return {"id": j.id, "kind": j.kind.value, "order_id": j.order_id, "status": j.status.value,
            "step": j.step, "attempts": j.attempts, "enqueued_at": j.enqueued_at,
            "run_after": j.run_after, "locked_at": j.locked_at, "last_error": j.last_error}


def _job(m) -> Job:
    return Job(m["id"], JobKind(m["kind"]), m["order_id"], JobStatus(m["status"]), m["enqueued_at"],
               m["run_after"], step=m["step"], attempts=m["attempts"], locked_at=m["locked_at"],
               last_error=m["last_error"])


ACTIVE = (JobStatus.PENDING.value, JobStatus.RUNNING.value)
CLAIM_PRIORITY = case({JobKind.BOOKING.value: 0, JobKind.PAYMENT_CHECK.value: 1,
                       JobKind.SMS_LINK.value: 2, JobKind.SMS_CONFIRMED.value: 2},
                      value=jobs_t.c.kind, else_=3)


class PostgresJobs:
    """Coda dei job (RF-50): ogni worker preleva con `FOR UPDATE SKIP LOCKED`, così due
    istanze non prendono mai lo stesso job e non si aspettano a vicenda."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def enqueue(self, job: Job) -> None:
        try:
            with self.engine.begin() as conn:
                conn.execute(jobs_t.insert().values(**_job_row(job)))
        except IntegrityError as exc:
            if "uq_jobs_active_booking" in str(exc.orig):
                raise DuplicateJob(job.order_id) from exc
            raise

    def get(self, job_id: str) -> Optional[Job]:
        with self.engine.connect() as conn:
            m = conn.execute(select(jobs_t).where(jobs_t.c.id == job_id)).mappings().first()
        return None if m is None else _job(m)

    def save(self, job: Job) -> None:
        values = {k: v for k, v in _job_row(job).items() if k != "id"}
        with self.engine.begin() as conn:
            conn.execute(update(jobs_t).where(jobs_t.c.id == job.id).values(**values))

    def claim(self, now: datetime, lease_seconds: int) -> Optional[Job]:
        stale = now - timedelta(seconds=lease_seconds)
        ready = or_(and_(jobs_t.c.status == JobStatus.PENDING.value, jobs_t.c.run_after <= now),
                    and_(jobs_t.c.status == JobStatus.RUNNING.value, jobs_t.c.locked_at <= stale))
        pick = (select(jobs_t.c.id).where(ready)
                .order_by(CLAIM_PRIORITY, jobs_t.c.enqueued_at, jobs_t.c.id)
                .limit(1).with_for_update(skip_locked=True))
        with self.engine.begin() as conn:
            job_id = conn.execute(pick).scalar()
            if job_id is None:
                return None
            m = conn.execute(update(jobs_t).where(jobs_t.c.id == job_id)
                             .values(status=JobStatus.RUNNING.value, locked_at=now)
                             .returning(*jobs_t.c)).mappings().one()
        return _job(m)

    def active_for_order(self, order_id: str, kind: JobKind) -> Optional[Job]:
        with self.engine.connect() as conn:
            m = conn.execute(select(jobs_t).where(jobs_t.c.order_id == order_id,
                                                  jobs_t.c.kind == kind.value,
                                                  jobs_t.c.status.in_(ACTIVE))).mappings().first()
        return None if m is None else _job(m)

    def queued_purchase_position(self, order_id: str) -> Optional[int]:
        pending = and_(jobs_t.c.kind == JobKind.PURCHASE.value,
                       jobs_t.c.status == JobStatus.PENDING.value)
        with self.engine.connect() as conn:
            mine = conn.execute(select(jobs_t.c.enqueued_at, jobs_t.c.id)
                                .where(pending, jobs_t.c.order_id == order_id)).first()
            if mine is None:
                return None
            ahead = conn.execute(select(func.count()).select_from(jobs_t).where(
                pending, or_(jobs_t.c.enqueued_at < mine.enqueued_at,
                             and_(jobs_t.c.enqueued_at == mine.enqueued_at, jobs_t.c.id < mine.id)))).scalar()
        return ahead + 1

    def purchase_waiting(self) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(select(jobs_t.c.id).where(jobs_t.c.kind == JobKind.PURCHASE.value,
                                                          jobs_t.c.status.in_(ACTIVE)).limit(1)).first() is not None

    def oldest_purchase_enqueued_at(self) -> Optional[datetime]:
        with self.engine.connect() as conn:
            return conn.execute(select(func.min(jobs_t.c.enqueued_at)).where(
                jobs_t.c.kind == JobKind.PURCHASE.value, jobs_t.c.status.in_(ACTIVE))).scalar()


QUOTA_ROW = 1


def _bucket_row(b: QuotaBucket) -> dict:
    return {"window_start": b.window_start, "window_end": b.window_end,
            "limit_per_minute": b.limit_per_minute, "needs_refresh": b.needs_refresh,
            "tokens": b.tokens, "refilled_at": b.refilled_at}


def _bucket(m) -> QuotaBucket:
    return QuotaBucket(m["tokens"], m["refilled_at"], m["limit_per_minute"], m["needs_refresh"],
                       m["window_start"], m["window_end"])


class PostgresQuota:
    """Token bucket condiviso tra istanze (RF-36, RF-47, M18): una riga, bloccata con
    `SELECT ... FOR UPDATE` per tutta la decisione, così due worker non prendono gli stessi
    gettoni. Le regole sono quelle pure di `vela.domain.quota`."""

    def __init__(self, engine: Engine, margin: float = 0.10, reserve: float = 0.20,
                 rules: Optional[BucketRules] = None):
        self.engine = engine
        self.rules = rules or BucketRules(margin, reserve)

    def _locked(self, conn, now: datetime) -> QuotaBucket:
        conn.execute(pg_insert(quota_window_t).values(
            id=QUOTA_ROW, **_bucket_row(fresh_bucket(now, DEFAULT_LIMIT_PER_MINUTE, self.rules)))
            .on_conflict_do_nothing(index_elements=[quota_window_t.c.id]))
        m = conn.execute(select(quota_window_t).where(quota_window_t.c.id == QUOTA_ROW)
                         .with_for_update()).mappings().one()
        return _bucket(m)

    def _read(self, now: datetime) -> QuotaBucket:
        with self.engine.connect() as conn:
            m = conn.execute(select(quota_window_t).where(quota_window_t.c.id == QUOTA_ROW)).mappings().first()
        return fresh_bucket(now, DEFAULT_LIMIT_PER_MINUTE, self.rules) if m is None else _bucket(m)

    def _save(self, conn, b: QuotaBucket) -> None:
        conn.execute(update(quota_window_t).where(quota_window_t.c.id == QUOTA_ROW).values(**_bucket_row(b)))

    def _change(self, now: datetime, rule) -> bool:
        """Applica `rule` alla riga bloccata; None dalla regola = nessuna modifica."""
        with self.engine.begin() as conn:
            new = rule(self._locked(conn, now))
            if new is not None:
                self._save(conn, new)
            return new is not None

    def acquire(self, cls: QuotaClass, n: int, now: datetime, purchase_waiting: bool = False) -> bool:
        return self._change(now, lambda b: try_take(b, cls, n, now, self.rules, purchase_waiting))

    def on_429(self, now: datetime, hold_seconds: float = 0.0) -> None:
        self._change(now, lambda b: after_429(b, now, self.rules, hold_seconds))

    def needs_refresh(self, now: datetime) -> bool:
        return self._read(now).needs_refresh

    def claim_refresh(self, now: datetime) -> bool:
        return self._change(now, lambda b: claim_refresh(b, now, self.rules))

    def mark_refresh_needed(self, now: datetime) -> None:
        self._change(now, lambda b: replace(b, needs_refresh=True))

    def sync_from_snapshot(self, snapshot: QuotaSnapshot, now: datetime) -> None:
        self._change(now, lambda b: from_snapshot(
            b, snapshot.limit_per_minute, snapshot.used_in_window, snapshot.window_started_at,
            snapshot.window_ends_at, now, self.rules))

    def snapshot(self, now: datetime) -> dict:
        return describe(self._read(now), now, self.rules)

    def next_window_start(self, now: datetime, cls: QuotaClass = QuotaClass.PURCHASE,
                          n: int = CALLS_PER_PURCHASE) -> datetime:
        return available_at(self._read(now), now, self.rules, cls, n)


# chiave dell'advisory lock del sync del catalogo (RF-30): costante, unica per tutti i brand
CATALOG_LOCK_KEY = 7_646_512_010


class PostgresRepositories:
    def __init__(self, engine: Engine, quota_margin: float = 0.10, booking_reserve: float = 0.20,
                 quota_burst: int = DEFAULT_BURST, quota_floor: int = DEFAULT_FLOOR):
        self.engine = engine
        self._local_lock = threading.Lock()   # SQLite dei test: nessun advisory lock
        self.products = PostgresProducts(engine)
        self.intents = PostgresIntents(engine)
        self.proposals = PostgresProposals(engine)
        self.orders = PostgresOrders(engine)
        self.rejections = PostgresRejections(engine)
        self.jobs = PostgresJobs(engine)
        self.quotes = PostgresQuotes(engine)
        self.quota = PostgresQuota(engine, rules=BucketRules(quota_margin, booking_reserve,
                                                             quota_burst, quota_floor))

    @contextmanager
    def catalog_lock(self):
        """`pg_try_advisory_lock` su una connessione tenuta per tutto il sync: il lock è di
        sessione, quindi cade anche se il processo muore (RF-30)."""
        if self.engine.dialect.name != "postgresql":
            acquired = self._local_lock.acquire(blocking=False)
            try:
                yield acquired
            finally:
                if acquired:
                    self._local_lock.release()
            return
        with self.engine.connect() as conn:
            acquired = conn.execute(text("SELECT pg_try_advisory_lock(:k)"),
                                    {"k": CATALOG_LOCK_KEY}).scalar_one()
            conn.commit()
            try:
                yield bool(acquired)
            finally:
                if acquired:
                    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CATALOG_LOCK_KEY})
                    conn.commit()
