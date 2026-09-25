"""Porta verso il pagamento (RF-18..21). Implementazioni: finta (M2), Stripe (M6).

Nessun webhook (decisione M5): `link_status` legge lo stato del link, e la verifica del
pagamento (`vela.domain.payment_check`) lo interroga finché il viaggiatore non paga.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Protocol

from vela.domain.models import Order


class PaymentsError(Exception):
    """Il fornitore non ha creato il link (rete, timeout, errore Stripe, valuta non supportata)."""


@dataclass(frozen=True)
class PaymentLink:
    url: str
    expires_at: datetime
    reference: str      # id della sessione presso il fornitore (Checkout Session)


def to_cents(amount: Decimal) -> int:
    """Importo in centesimi, come lo vuole e lo restituisce Stripe."""
    return int((amount * 100).quantize(Decimal("1")))


@dataclass(frozen=True)
class LinkStatus:
    state: str                         # "open" | "paid" | "expired"
    amount_cents: Optional[int]
    currency: Optional[str]            # maiuscola, come negli ordini
    payment_ref: Optional[str]         # id del PaymentIntent, da inoltrare al booking (RF-23)


class PaymentsPort(Protocol):
    def create_payment_link(self, order: Order, description: str) -> PaymentLink: ...
    def link_status(self, reference: str) -> LinkStatus: ...
