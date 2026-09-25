"""Porta verso il contatore di quota HofJ condiviso tra istanze (RF-36..38, RF-47).

Una sola finestra fissa di 60 s, ancorata da `GET /v1/quota` (`sync_from_snapshot`) e poi fatta
avanzare dall'orologio di Vela. `acquire` prenota atomicamente un blocco di chiamate o non
prenota nulla. Prima della prima sincronizzazione la finestra parte dalla prima richiesta con
il limite dichiarato da HofJ (120/min) e `needs_refresh` è vero.
"""
from datetime import datetime
from typing import Protocol

from vela.domain.models import QuotaClass
from vela.ports.hofj import QuotaSnapshot

DEFAULT_LIMIT_PER_MINUTE = 120


class QuotaStore(Protocol):
    def acquire(self, cls: QuotaClass, n: int, now: datetime, purchase_waiting: bool = False) -> bool: ...
    def on_429(self, now: datetime) -> None: ...
    def needs_refresh(self, now: datetime) -> bool: ...
    def sync_from_snapshot(self, snapshot: QuotaSnapshot) -> None: ...
    def snapshot(self, now: datetime) -> dict: ...
    def next_window_start(self, now: datetime) -> datetime: ...
