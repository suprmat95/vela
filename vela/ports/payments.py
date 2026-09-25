"""Porta verso il pagamento (RF-18, RF-19). Implementazioni: finta (M2), Stripe (M6)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from vela.domain.models import Order


@dataclass(frozen=True)
class PaymentLink:
    url: str
    expires_at: datetime
    reference: str      # id del pagamento presso il fornitore (payment intent)


class PaymentsPort(Protocol):
    def create_payment_link(self, order: Order) -> PaymentLink: ...
