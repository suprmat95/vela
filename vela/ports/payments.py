"""Porta verso il pagamento (RF-18, RF-19, RF-21). Implementazioni: finta (M2), Stripe (M6)."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

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


class PaymentsPort(Protocol):
    def create_payment_link(self, order: Order, description: str) -> PaymentLink: ...
