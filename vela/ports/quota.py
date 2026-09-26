"""Porta verso il token bucket della quota HofJ condiviso tra istanze (RF-36..38, RF-47).

Ritmo costante (M18): capienza B e ritmo r con B + 60·r = limite effettivo, così nessun
intervallo di 60 s supera il limite qualunque sia la finestra di HofJ. `acquire` prende
atomicamente un blocco di gettoni o niente. `GET /v1/quota` (`sync_from_snapshot`) aggiorna il
limite e toglie gettoni se HofJ ne lascia meno. Prima della prima sincronizzazione il bucket è
pieno, con il limite dichiarato da HofJ (120/min), e `needs_refresh` è vero.
"""
from datetime import datetime
from typing import Protocol

from vela.domain.models import QuotaClass
from vela.domain.quota import CALLS_PER_PURCHASE
from vela.ports.hofj import QuotaSnapshot

DEFAULT_LIMIT_PER_MINUTE = 120


class QuotaStore(Protocol):
    def acquire(self, cls: QuotaClass, n: int, now: datetime, purchase_waiting: bool = False) -> bool: ...
    def on_429(self, now: datetime, hold_seconds: float = 0.0) -> None: ...
    def needs_refresh(self, now: datetime) -> bool: ...
    def claim_refresh(self, now: datetime) -> bool:
        """Prende il gettone della rilettura e spegne `needs_refresh`: una sola istanza rilegge."""
    def mark_refresh_needed(self, now: datetime) -> None: ...
    def sync_from_snapshot(self, snapshot: QuotaSnapshot, now: datetime) -> None: ...
    def snapshot(self, now: datetime) -> dict: ...
    def next_window_start(self, now: datetime, cls: QuotaClass = QuotaClass.PURCHASE,
                          n: int = CALLS_PER_PURCHASE) -> datetime:
        """Istante in cui `cls` potrà prendere `n` gettoni, di default un acquisto intero
        (nome storico, da prima del token bucket)."""
