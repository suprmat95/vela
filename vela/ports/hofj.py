"""Porta verso House of Journeys (spec §2 "Porta", RF-14, RF-23). Implementazioni: replay (M2), HTTP (M5)."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Protocol

from vela.domain.models import Product


class HofJError(Exception):
    """Base degli errori della porta."""


class ProductError(HofJError):
    """Errore riconducibile al prodotto (RF-17): il chooser lo marcherà non prenotabile (M5)."""


class QuotaError(HofJError):
    """Quota esaurita (RF-37)."""


class UpstreamError(HofJError):
    """Rete, timeout, 5xx non riconducibili al prodotto."""


@dataclass(frozen=True)
class Itinerary:
    id: str
    total: Decimal
    currency: str


@dataclass(frozen=True)
class Customer:
    first_name: str
    last_name: str
    email: str
    phone: str
    street1: str
    postal_code: str
    city: str
    region: str
    country_code: str


@dataclass(frozen=True)
class Pax:
    ref_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@dataclass(frozen=True)
class PaymentProof:
    payment_intent_id: str
    payment_status: str
    payment_type: str = "full"


class HofJPort(Protocol):
    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> Itinerary: ...
    def set_customer(self, itinerary_id: str, customer: Customer) -> None: ...
    def get_pax(self, itinerary_id: str) -> List[Pax]: ...
    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None: ...
    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str: ...
