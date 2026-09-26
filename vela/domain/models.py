"""Modelli del dominio di Vela (spec §2, RF-05, RF-06, RF-25) e risposte dei casi d'uso (RF-39, RF-42).

Tutto è dataclass immutabile e senza dipendenze esterne. Le risposte espongono `to_dict()`:
il contratto che le superfici REST (M4) e MCP (M3) serializzano. Nessuna risposta contiene
mai più di un prodotto (RF-10).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


def money_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


# --- intento -----------------------------------------------------------------

@dataclass(frozen=True)
class Area:
    kind: str           # "country" | "region" | "city"
    name: str           # nome canonico italiano, es. "Spagna", "Lanzarote"
    country_code: str   # ISO 3166-1 alpha-2


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str          # testo che lo ha generato, es. "ottobre", "weekend"


@dataclass(frozen=True)
class Criteria:
    sport: Optional[str] = None
    area: Optional[Area] = None
    period: Optional[Period] = None
    pax: Optional[int] = None
    budget: Optional[Decimal] = None
    language: str = "it"


@dataclass(frozen=True)
class StructuredFields:
    """RF-52: criteri già capiti dall'agente, grezzi come arrivano dalla superficie. La
    validazione (RF-53) è in `intent.validate_fields`; `direction` vale solo sul rifiuto."""
    sport: Optional[str] = None
    area: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    pax: Optional[int] = None
    budget: Optional[object] = None
    direction: Optional[str] = None

    def as_dict(self) -> dict:
        return {"sport": self.sport, "area": self.area, "period_start": self.period_start,
                "period_end": self.period_end, "pax": self.pax, "budget": self.budget}


def criteria_to_dict(c: Criteria) -> dict:
    return {
        "sport": c.sport,
        "area": None if c.area is None else {"kind": c.area.kind, "name": c.area.name,
                                             "country_code": c.area.country_code},
        "period": None if c.period is None else {"start": c.period.start.isoformat(),
                                                 "end": c.period.end.isoformat(),
                                                 "label": c.period.label},
        "pax": c.pax,
        "budget": None if c.budget is None else money_str(c.budget),
        "language": c.language,
    }


def criteria_from_dict(d: dict) -> Criteria:
    area = d.get("area")
    period = d.get("period")
    budget = d.get("budget")
    return Criteria(
        sport=d.get("sport"),
        area=None if area is None else Area(area["kind"], area["name"], area["country_code"]),
        period=None if period is None else Period(date.fromisoformat(period["start"]),
                                                  date.fromisoformat(period["end"]),
                                                  period["label"]),
        pax=d.get("pax"),
        budget=None if budget is None else Decimal(budget),
        language=d.get("language") or "it",
    )


@dataclass(frozen=True)
class Participant:
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@dataclass(frozen=True)
class TravelerProfile:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    pax: Optional[int] = None
    participants: tuple = ()   # tuple[Participant, ...]

    def merged_with(self, other: "TravelerProfile") -> "TravelerProfile":
        """I valori non nulli di `other` vincono; i partecipanti di `other` se non vuoti."""
        return TravelerProfile(
            first_name=other.first_name or self.first_name,
            last_name=other.last_name or self.last_name,
            email=other.email or self.email,
            phone=other.phone or self.phone,
            pax=other.pax or self.pax,
            participants=other.participants or self.participants,
        )

    def missing_fields(self, pax: int) -> list:
        """Campi di RF-12 ancora mancanti per `pax` persone: viaggiatore principale completo,
        nome e cognome di ogni altro partecipante."""
        missing = [name for name in ("first_name", "last_name", "email", "phone")
                   if not getattr(self, name)]
        for i in range(max(pax - 1, 0)):
            p = self.participants[i] if i < len(self.participants) else Participant()
            if not p.first_name:
                missing.append("participants[%d].first_name" % i)
            if not p.last_name:
                missing.append("participants[%d].last_name" % i)
        return missing


def profile_to_dict(p: TravelerProfile) -> dict:
    return {"first_name": p.first_name, "last_name": p.last_name, "email": p.email,
            "phone": p.phone, "pax": p.pax,
            "participants": [{"first_name": x.first_name, "last_name": x.last_name}
                             for x in p.participants]}


def profile_from_dict(d: Optional[dict]) -> TravelerProfile:
    d = d or {}
    return TravelerProfile(
        first_name=d.get("first_name"), last_name=d.get("last_name"), email=d.get("email"),
        phone=d.get("phone"), pax=d.get("pax"),
        participants=tuple(Participant(x.get("first_name"), x.get("last_name"))
                           for x in d.get("participants") or []))


@dataclass(frozen=True)
class Intent:
    id: str
    text: str
    criteria: Criteria
    profile: TravelerProfile
    created_at: datetime


# --- catalogo ----------------------------------------------------------------

@dataclass(frozen=True)
class Availability:
    start: date
    end: date


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    slug: str
    short_description: str
    sport: str
    category: Optional[str]
    destination: Optional[str]
    country: Optional[str]
    venue: Optional[str]
    hotel: Optional[str]
    price: Decimal
    currency: str
    min_pax: Optional[int]
    max_pax: Optional[int]
    min_date: Optional[date]
    max_date: Optional[date]
    availabilities: tuple      # tuple[Availability, ...] ordinate per inizio
    duration_days: Optional[int]
    hofj_updated_at: Optional[str]
    raw: dict
    fetched_at: datetime
    bookable: bool = True
    bookable_checked_at: Optional[datetime] = None
    archived: bool = False
    provider_id: Optional[str] = None


# --- proposta, ordine, rifiuto -------------------------------------------------

@dataclass(frozen=True)
class Proposal:
    id: str
    intent_id: str
    product_id: str
    start_date: date
    end_date: date
    pax: int
    price_from: Decimal        # per persona
    currency: str
    reason: str
    created_at: datetime

    @property
    def total_from(self) -> Decimal:
        return self.price_from * self.pax


class OrderStatus(str, Enum):
    """Stati dell'ordine nell'ordine di RF-25."""
    QUEUED = "queued"                  # RF-45: accettato, in attesa del job d'acquisto
    AWAITING_PAYMENT = "awaiting_payment"
    PAID_PENDING_BOOKING = "paid_pending_booking"
    CONFIRMED = "confirmed"
    REPLACED = "replaced"              # RF-17: prodotto non prenotabile, proposta sostitutiva
    CANCELLED = "cancelled"            # RF-49: il viaggiatore ha rinunciato
    FAILED = "failed"                  # RF-46: job d'acquisto fallito dopo i tentativi
    BOOKING_FAILED = "booking_failed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Order:
    id: str
    proposal_id: str
    intent_id: str
    product_id: str
    status: OrderStatus
    pax: int
    price_from: Decimal        # per persona, dalla proposta
    total: Optional[Decimal]   # importo reale da HofJ (openAmount); None finché l'ordine è in coda
    currency: str
    traveler: TravelerProfile
    created_at: datetime
    updated_at: datetime
    itinerary_id: Optional[str] = None
    payment_url: Optional[str] = None
    payment_ref: Optional[str] = None
    booking_code: Optional[str] = None
    failure_reason: Optional[str] = None
    paid_at: Optional[datetime] = None
    enqueued_at: Optional[datetime] = None            # posizione FIFO (RF-48); ereditata in RF-17
    replacement_proposal_id: Optional[str] = None     # RF-17: proposta che sostituisce l'ordine


class JobKind(str, Enum):
    PURCHASE = "purchase"              # RF-46
    BOOKING = "booking"                # RF-23, RF-51
    PAYMENT_CHECK = "payment_check"    # RF-20


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    DEAD = "dead"


class QuotaClass(str, Enum):
    """Classi dello scheduler della quota HofJ (RF-47)."""
    BOOKING = "booking"
    PURCHASE = "purchase"
    SYNC = "sync"


@dataclass(frozen=True)
class Job:
    """Un'unità di lavoro del worker (RF-50), ripartibile dal passo salvato (RF-27)."""
    id: str
    kind: JobKind
    order_id: str
    status: JobStatus
    enqueued_at: datetime
    run_after: datetime
    step: int = 0
    attempts: int = 0
    locked_at: Optional[datetime] = None
    last_error: Optional[str] = None


@dataclass(frozen=True)
class Rejection:
    intent_id: str
    proposal_id: str
    product_id: str
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class TravelerDefaults:
    """Campi richiesti da HofJ ma non chiesti al viaggiatore (RF-13): vincolo del prototipo,
    documentato in ARCHITECTURE.md (M15)."""
    street1: str = "Via del Prototipo 1"
    postal_code: str = "20100"
    city: str = "Milano"
    region: str = "MI"
    country_code: str = "IT"


# --- risposte dei casi d'uso (RF-39, RF-42) -----------------------------------

@dataclass(frozen=True)
class ProductSummary:
    product_id: str
    title: str
    destination: Optional[str]
    hotel: Optional[str]

    def to_dict(self) -> dict:
        return {"product_id": self.product_id, "title": self.title,
                "destination": self.destination, "hotel": self.hotel}


@dataclass(frozen=True)
class IntentCreated:
    intent_id: str
    criteria: Criteria
    say: str

    def to_dict(self) -> dict:
        return {"intent_id": self.intent_id, "criteria": criteria_to_dict(self.criteria),
                "say": self.say}


@dataclass(frozen=True)
class IntentQuestion:
    question: str
    say: str

    def to_dict(self) -> dict:
        return {"question": self.question, "say": self.say}


@dataclass(frozen=True)
class ProposalMade:
    proposal: Proposal
    product: ProductSummary
    say: str
    replaced: bool = False

    def to_dict(self) -> dict:
        p = self.proposal
        return {"proposal_id": p.id, "intent_id": p.intent_id, "product": self.product.to_dict(),
                "start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat(),
                "pax": p.pax, "price_from": money_str(p.price_from),
                "total_from": money_str(p.total_from), "currency": p.currency,
                "reason": p.reason, "replaced": self.replaced, "say": self.say}


@dataclass(frozen=True)
class NoMatch:
    intent_id: str
    failed_criterion: str
    say: str

    def to_dict(self) -> dict:
        return {"intent_id": self.intent_id, "failed_criterion": self.failed_criterion,
                "say": self.say}


@dataclass(frozen=True)
class OrderQueued:
    """RF-45, RF-19: risposta dell'accettazione. Nessun link: arriva con `get_order_status`."""
    order_id: str
    status: OrderStatus
    position: Optional[int]
    wait_seconds: Optional[int]
    say: str

    def to_dict(self) -> dict:
        return {"order_id": self.order_id, "status": self.status.value, "position": self.position,
                "wait_seconds": self.wait_seconds, "say": self.say}


@dataclass(frozen=True)
class MissingTravelerData:
    proposal_id: str
    missing: tuple
    say: str

    def to_dict(self) -> dict:
        return {"proposal_id": self.proposal_id, "missing": list(self.missing), "say": self.say}


@dataclass(frozen=True)
class OrderStatusResponse:
    """RF-25, RF-39: stessi campi per ogni stato, `None` quando non pertinenti."""
    order_id: str
    status: OrderStatus
    say: str
    position: Optional[int] = None             # queued (RF-48)
    wait_seconds: Optional[int] = None         # queued (RF-48)
    total: Optional[Decimal] = None            # importo reale, dopo il job d'acquisto
    currency: Optional[str] = None
    price_from_total: Optional[Decimal] = None
    total_differs: Optional[bool] = None       # RF-16
    payment_url: Optional[str] = None          # solo awaiting_payment (RF-19)
    booking_code: Optional[str] = None         # confirmed
    failure_reason: Optional[str] = None       # failed, booking_failed
    proposal: Optional["ProposalMade"] = None  # replaced (RF-17)

    def to_dict(self) -> dict:
        return {"order_id": self.order_id, "status": self.status.value, "position": self.position,
                "wait_seconds": self.wait_seconds,
                "total": None if self.total is None else money_str(self.total),
                "currency": self.currency,
                "price_from_total": None if self.price_from_total is None else money_str(self.price_from_total),
                "total_differs": self.total_differs, "payment_url": self.payment_url,
                "booking_code": self.booking_code, "failure_reason": self.failure_reason,
                "proposal_changed": self.proposal is not None,
                "proposal": None if self.proposal is None else self.proposal.to_dict(),
                "say": self.say}


