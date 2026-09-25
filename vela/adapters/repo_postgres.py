"""Repository Postgres con SQLAlchemy Core (RNF-01): una transazione per metodo, nessuno stato in processo."""
from datetime import date, datetime
from typing import Iterable, List, Optional, Set

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from vela.adapters.schema import (intents_t, orders_t, products_t, proposals_t, rejections_t,
                                  stripe_events_t)
from vela.domain.models import (Availability, Criteria, Intent, Order, OrderStatus, Product,
                                Proposal, Rejection, criteria_from_dict, criteria_to_dict,
                                profile_from_dict, profile_to_dict)
from vela.ports.repositories import DuplicateOrder


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
        "provider_id": p.provider_id,
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
        provider_id=m["provider_id"])


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
    }


def _order(m) -> Order:
    return Order(m["id"], m["proposal_id"], m["intent_id"], m["product_id"],
                 OrderStatus(m["status"]), m["pax"], m["price_from"], m["total"], m["currency"],
                 profile_from_dict(m["traveler"]), m["created_at"], m["updated_at"],
                 itinerary_id=m["itinerary_id"], payment_url=m["payment_url"],
                 payment_ref=m["payment_ref"], booking_code=m["booking_code"],
                 failure_reason=m["failure_reason"], paid_at=m["paid_at"])


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

    def save(self, order: Order) -> None:
        values = {k: v for k, v in _order_row(order).items() if k != "id"}
        with self.engine.begin() as conn:
            conn.execute(update(orders_t).where(orders_t.c.id == order.id).values(**values))

    def ids_with_status(self, status: OrderStatus) -> List[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(orders_t.c.id).where(orders_t.c.status == status.value)
                                .order_by(orders_t.c.id)).all()
        return [r[0] for r in rows]


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


class PostgresWebhookEvents:
    def __init__(self, engine: Engine):
        self.engine = engine

    def claim(self, event_id: str, event_type: str, at: datetime) -> bool:
        stmt = pg_insert(stripe_events_t).values(
            id=event_id, type=event_type, received_at=at).on_conflict_do_nothing(
            index_elements=[stripe_events_t.c.id])
        with self.engine.begin() as conn:
            return conn.execute(stmt).rowcount == 1

    def release(self, event_id: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(stripe_events_t).where(stripe_events_t.c.id == event_id))


class PostgresRepositories:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.products = PostgresProducts(engine)
        self.intents = PostgresIntents(engine)
        self.proposals = PostgresProposals(engine)
        self.orders = PostgresOrders(engine)
        self.rejections = PostgresRejections(engine)
        self.webhook_events = PostgresWebhookEvents(engine)
