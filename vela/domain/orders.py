"""Macchina a stati dell'ordine (RF-20, RF-23, RF-25, RF-27, RNF-03).

`awaiting_payment` → `paid_pending_booking` (mark_paid, che accoda il job `booking`) →
`confirmed` | `booking_failed` (job di prenotazione, `vela.domain.booking`);
`awaiting_payment` → `expired` (expire, dalla verifica della sessione). Ogni transizione è
idempotente: uno stato diverso da quello atteso lascia l'ordine com'è.
"""
import logging
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Callable, List

from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus
from vela.ports.hofj import HofJRouter
from vela.ports.jobs import DuplicateJob
from vela.ports.payments import LinkStatus, to_cents
from vela.ports.repositories import Repositories

log = logging.getLogger(__name__)


class NotFound(Exception):
    def __init__(self, kind: str, id: str):
        super().__init__("%s %s non trovato" % (kind, id))
        self.kind = kind
        self.id = id


class OrderService:
    def __init__(self, repos: Repositories, hofj: HofJRouter, now: Callable[[], datetime],
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())):
        self.repos = repos
        self.hofj = hofj
        self.now = now
        self.new_id = new_id

    def get(self, order_id: str) -> Order:
        order = self.repos.orders.get(order_id)
        if order is None:
            raise NotFound("order", order_id)
        return order

    def mark_paid(self, order_id: str, payment_ref: str) -> Order:
        order = self.get(order_id)
        if order.status != OrderStatus.AWAITING_PAYMENT:
            return order
        now = self.now()
        order = replace(order, status=OrderStatus.PAID_PENDING_BOOKING, payment_ref=payment_ref,
                        paid_at=now, updated_at=now)
        if not self.repos.orders.save_if_status(order, OrderStatus.AWAITING_PAYMENT):
            return self.get(order_id)   # un'altra conferma di pagamento è arrivata prima
        self._enqueue_booking(order.id, now)
        return order

    def _enqueue_booking(self, order_id: str, now: datetime) -> bool:
        """RF-51: un solo job di prenotazione attivo per ordine, garantito dal repository."""
        if self.repos.jobs.active_for_order(order_id, JobKind.BOOKING) is not None:
            return False
        try:
            self.repos.jobs.enqueue(Job(self.new_id(), JobKind.BOOKING, order_id, JobStatus.PENDING, now, now))
        except DuplicateJob:
            return False
        return True

    def resume_bookings(self) -> List[str]:
        """RF-27: al boot, ogni ordine pagato senza job di prenotazione attivo ne riceve uno."""
        now = self.now()
        return [oid for oid in self.pending_booking_ids() if self._enqueue_booking(oid, now)]

    def settle_payment(self, order_id: str, status: LinkStatus) -> Order:
        """RF-20: esito della verifica del link. Pagato con importo e valuta dell'ordine → pagato
        e job di prenotazione; scaduto → `expired`; qualunque incongruenza lascia l'ordine com'è."""
        order = self.get(order_id)
        if order.status != OrderStatus.AWAITING_PAYMENT:
            return order
        if status.state == "expired":
            return self.expire(order_id)
        if status.state != "paid":
            return order
        expected = (to_cents(order.total), order.currency.upper())
        if (status.amount_cents, status.currency) != expected:
            log.warning("pagamento dell'ordine %s non applicato: %s %s invece di %s %s", order_id,
                        status.amount_cents, status.currency, expected[0], expected[1])
            return order
        return self.mark_paid(order_id, status.payment_ref or "")

    def expire(self, order_id: str) -> Order:
        """Link scaduto (RF-21): solo un ordine ancora da pagare passa a `expired`."""
        order = self.get(order_id)
        if order.status != OrderStatus.AWAITING_PAYMENT:
            return order
        order = replace(order, status=OrderStatus.EXPIRED, updated_at=self.now())
        if not self.repos.orders.save_if_status(order, OrderStatus.AWAITING_PAYMENT):
            return self.get(order_id)   # pagato nel frattempo: il pagamento vince
        return order

    def pending_booking_ids(self) -> List[str]:
        return self.repos.orders.ids_with_status(OrderStatus.PAID_PENDING_BOOKING)
