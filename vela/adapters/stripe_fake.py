"""Pagamento finto per la modalità replay (RNF-08): il link porta a `GET /replay/checkout/{order_id}`.

Il checkout di replay "paga" il link con `pay`; `link_status` lo riporta come farebbe Stripe.
Lo stato vive nel processo: dopo un riavvio un link torna aperto finché non viene ripagato.
"""
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from vela.domain.models import Order
from vela.ports.payments import LinkStatus, PaymentLink, to_cents

DEFAULT_PUBLIC_URL = "http://localhost:8000"
LINK_TTL = timedelta(hours=24)   # RF-21


class FakePayments:
    def __init__(self, public_url: Optional[str] = None,
                 now: Optional[Callable[[], datetime]] = None):
        self.base = (public_url or DEFAULT_PUBLIC_URL).rstrip("/")
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._paid: Dict[str, LinkStatus] = {}

    @staticmethod
    def reference_for(order: Order) -> str:
        return "pi_replay_%s" % order.id

    def create_payment_link(self, order: Order, description: str) -> PaymentLink:
        return PaymentLink("%s/replay/checkout/%s" % (self.base, order.id), self.now() + LINK_TTL,
                           self.reference_for(order))

    def pay(self, order: Order) -> LinkStatus:
        ref = self.reference_for(order)
        status = LinkStatus("paid", to_cents(order.total), order.currency.upper(), ref)
        with self._lock:
            self._paid[ref] = status
        return status

    def link_status(self, reference: str) -> LinkStatus:
        with self._lock:
            return self._paid.get(reference) or LinkStatus("open", None, None, None)
