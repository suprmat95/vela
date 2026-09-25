"""Macchina a stati dell'ordine (RF-20, RF-23, RF-25, RF-27, RNF-03).

`awaiting_payment` → `paid_pending_booking` (mark_paid, che accoda il job `booking`) →
`confirmed` | `booking_failed` (job di prenotazione, `vela.domain.booking`);
`awaiting_payment` → `expired` (expire, dalla verifica della sessione). Ogni transizione è
idempotente: uno stato diverso da quello atteso lascia l'ordine com'è.
"""
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Callable, List

from vela.domain.models import Job, JobKind, JobStatus, Order, OrderStatus
from vela.ports.hofj import HofJError, HofJPort, PaymentProof
from vela.ports.repositories import Repositories


class NotFound(Exception):
    def __init__(self, kind: str, id: str):
        super().__init__("%s %s non trovato" % (kind, id))
        self.kind = kind
        self.id = id


class OrderService:
    def __init__(self, repos: Repositories, hofj: HofJPort, now: Callable[[], datetime],
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
        self.repos.orders.save(order)
        self._enqueue_booking(order.id, now)
        return order

    def _enqueue_booking(self, order_id: str, now: datetime) -> bool:
        """RF-51: un solo job di prenotazione attivo per ordine."""
        if self.repos.jobs.active_for_order(order_id, JobKind.BOOKING) is not None:
            return False
        self.repos.jobs.enqueue(Job(self.new_id(), JobKind.BOOKING, order_id, JobStatus.PENDING, now, now))
        return True

    def resume_bookings(self) -> List[str]:
        """RF-27: al boot, ogni ordine pagato senza job di prenotazione attivo ne riceve uno."""
        now = self.now()
        return [oid for oid in self.pending_booking_ids() if self._enqueue_booking(oid, now)]

    def expire(self, order_id: str) -> Order:
        """Link scaduto (RF-21): solo un ordine ancora da pagare passa a `expired`."""
        order = self.get(order_id)
        if order.status != OrderStatus.AWAITING_PAYMENT:
            return order
        order = replace(order, status=OrderStatus.EXPIRED, updated_at=self.now())
        self.repos.orders.save(order)
        return order

    def complete_booking(self, order_id: str) -> Order:
        order = self.get(order_id)
        if order.status != OrderStatus.PAID_PENDING_BOOKING:
            return order
        proof = PaymentProof(order.payment_ref or "", "succeeded")
        try:
            code = self.hofj.create_booking(order.itinerary_id, proof)
            order = replace(order, status=OrderStatus.CONFIRMED, booking_code=code,
                            updated_at=self.now())
        except HofJError as exc:
            order = replace(order, status=OrderStatus.BOOKING_FAILED, failure_reason=str(exc),
                            updated_at=self.now())
        self.repos.orders.save(order)
        return order

    def pending_booking_ids(self) -> List[str]:
        return self.repos.orders.ids_with_status(OrderStatus.PAID_PENDING_BOOKING)
