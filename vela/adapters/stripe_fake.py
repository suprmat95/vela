"""Pagamento finto per la modalità replay (RNF-08): il link porta a `GET /replay/checkout/{order_id}`."""
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from vela.domain.models import Order
from vela.ports.payments import PaymentLink

DEFAULT_PUBLIC_URL = "http://localhost:8000"
LINK_TTL = timedelta(hours=24)   # RF-21


class FakePayments:
    def __init__(self, public_url: Optional[str] = None,
                 now: Optional[Callable[[], datetime]] = None):
        self.base = (public_url or DEFAULT_PUBLIC_URL).rstrip("/")
        self.now = now or (lambda: datetime.now(timezone.utc))

    def create_payment_link(self, order: Order) -> PaymentLink:
        return PaymentLink("%s/replay/checkout/%s" % (self.base, order.id), self.now() + LINK_TTL,
                           "pi_replay_%s" % order.id)
