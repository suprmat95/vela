"""Esecuzione della prenotazione dopo il pagamento (RF-27, RNF-02): thread nel processo.

`BookingRunner` sottomette `complete_booking` a un pool di thread; `resume()` riprende gli
ordini `paid_pending_booking` all'avvio. `InlineRunner` esegue subito, per i test.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List

from vela.domain.orders import OrderService

log = logging.getLogger("vela.booking")


class InlineRunner:
    def __init__(self, orders: OrderService):
        self.orders = orders

    def submit(self, order_id: str) -> None:
        self.orders.complete_booking(order_id)

    def resume(self) -> List[str]:
        ids = self.orders.pending_booking_ids()
        for order_id in ids:
            self.submit(order_id)
        return ids

    def shutdown(self, wait: bool = True) -> None:
        pass


class BookingRunner:
    def __init__(self, orders: OrderService, max_workers: int = 2):
        self.orders = orders
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="booking")

    def _run(self, order_id: str) -> None:
        try:
            self.orders.complete_booking(order_id)
        except Exception:   # noqa: BLE001 - un thread non deve morire in silenzio
            log.exception("prenotazione dell'ordine %s non completata", order_id)

    def submit(self, order_id: str) -> None:
        self._executor.submit(self._run, order_id)

    def resume(self) -> List[str]:
        ids = self.orders.pending_booking_ids()
        for order_id in ids:
            self.submit(order_id)
        return ids

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
