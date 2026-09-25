"""Macchina a stati dell'ordine (RF-20, RF-23, RF-25, RF-27, RNF-03).

`awaiting_payment` → `paid_pending_booking` (mark_paid) → `confirmed` | `booking_failed`
(complete_booking); `awaiting_payment` → `expired` (M6). Ogni transizione è idempotente: uno
stato diverso da quello atteso lascia l'ordine com'è. Retry con backoff: M5.
"""
from dataclasses import replace
from datetime import datetime
from typing import Callable, List

from vela.domain.models import Order, OrderStatus
from vela.ports.hofj import HofJError, HofJPort, PaymentProof
from vela.ports.repositories import Repositories


class NotFound(Exception):
    def __init__(self, kind: str, id: str):
        super().__init__("%s %s non trovato" % (kind, id))
        self.kind = kind
        self.id = id


class OrderService:
    def __init__(self, repos: Repositories, hofj: HofJPort, now: Callable[[], datetime]):
        self.repos = repos
        self.hofj = hofj
        self.now = now

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
