"""Regole pure della quota HofJ (RF-47, RF-48): limite effettivo, riserva, tetti, attesa stimata.

Limite effettivo = `limitPerMinute` meno un margine (chiave condivisa con altri client); la
classe `booking` ha una riserva garantita, `purchase` e `sync` si fermano prima di intaccarla.
Le percentuali passano da Decimal perché il floor su float sbaglia (100 × 0,29 = 28,999…).
"""
import math
from decimal import ROUND_FLOOR, Decimal

from vela.domain.models import QuotaClass

CALLS_PER_PURCHASE = 5   # RF-46: itinerario, customer, lettura pax, scrittura pax, totale


def _floor_share(value: int, share: float) -> int:
    return int((Decimal(value) * Decimal(str(share))).to_integral_value(rounding=ROUND_FLOOR))


def effective_limit(limit_per_minute: int, margin: float) -> int:
    return _floor_share(limit_per_minute, 1 - Decimal(str(margin)))


def booking_reserve(effective: int, reserve: float) -> int:
    return _floor_share(effective, reserve)


def cap_for(cls: QuotaClass, effective: int, reserve: int) -> int:
    """Chiamate che una classe può usare nella finestra: solo `booking` arriva al limite."""
    return effective if cls == QuotaClass.BOOKING else effective - reserve


def purchases_per_window(effective: int, reserve: int, calls_per_purchase: int = CALLS_PER_PURCHASE) -> float:
    budget = effective - reserve
    if budget <= 0:
        raise ValueError("nessun budget per gli acquisti: limite %d, riserva %d" % (effective, reserve))
    return budget / calls_per_purchase


def estimated_wait_seconds(position: int, per_window: float) -> int:
    """RF-48: posizione × 60 s ÷ acquisti per finestra, per eccesso. Nessun tetto."""
    return math.ceil(position * 60 / per_window)


def wait_minutes(seconds: int) -> int:
    """Minuti da dire al viaggiatore (RF-45): per eccesso, almeno 1."""
    return max(1, math.ceil(seconds / 60))
