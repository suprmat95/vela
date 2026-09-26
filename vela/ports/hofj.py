"""Porta verso House of Journeys (spec §2 "Porta", RF-14, RF-23). Implementazioni: replay (M2), HTTP (M5)."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Protocol

from vela.domain.models import Product


class HofJError(Exception):
    """Base degli errori della porta."""


class ProductError(HofJError):
    """Errore riconducibile al prodotto (RF-17): il chooser lo marcherà non prenotabile (M5)."""


class QuotaError(HofJError):
    """Quota esaurita, 429 (RF-37, RF-38). `retry_after` in secondi se HofJ lo dichiara."""

    def __init__(self, message: str = "quota esaurita", retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ConfigError(HofJError):
    """401/403: chiave o profilo sbagliati. Non è colpa del prodotto né della rete."""


class UpstreamError(HofJError):
    """Rete, timeout, 5xx non riconducibili al prodotto."""


class UpstreamTimeout(UpstreamError):
    """Esito incerto (M18): il nostro client o HofJ verso il brand hanno smesso di aspettare, ma
    l'operazione può essere avvenuta. Si ripete come ogni `UpstreamError`."""


@dataclass(frozen=True)
class Itinerary:
    id: str
    total: Decimal       # importo da pagare: `checkout.openAmount` (verifiche §8)
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
class QuotaSnapshot:
    """Risposta di `GET /v1/quota` (RF-36): finestra fissa di 60 s ancorata da HofJ."""
    limit_per_minute: int
    used_in_window: int
    window_started_at: datetime
    window_ends_at: datetime


@dataclass(frozen=True)
class PaymentProof:
    payment_intent_id: str
    payment_status: str
    payment_type: str = "full"


class HofJPort(Protocol):
    """Ogni metodo è una chiamata HofJ e consuma quota (RF-36), `get_quota` compreso."""
    def create_itinerary(self, product: Product, start_date: date, adults: int, rooms: int,
                         currency: str) -> str: ...
    def set_customer(self, itinerary_id: str, customer: Customer) -> None: ...
    def get_pax(self, itinerary_id: str) -> List[Pax]: ...
    def set_pax(self, itinerary_id: str, pax: List[Pax]) -> None: ...
    def get_itinerary(self, itinerary_id: str) -> Itinerary: ...
    def create_booking(self, itinerary_id: str, proof: PaymentProof) -> str: ...
    def get_quota(self) -> QuotaSnapshot: ...


class HofJRouter(Protocol):
    """Un `HofJPort` per brand (M10, RF-56): carrello e prenotazione usano il brand del prodotto
    dell'ordine. La quota è per chiave API, una sola per tutti i brand."""
    def client(self, brand: str) -> HofJPort: ...
    def client_for(self, product: Optional[Product]) -> HofJPort:
        """Il client del brand del prodotto; brand NULL (righe pre-M10) → brand del suo sport."""
        ...
    def get_quota(self) -> QuotaSnapshot: ...
