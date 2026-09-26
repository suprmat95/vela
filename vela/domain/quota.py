"""Regole pure della quota HofJ (RF-47, RF-48): token bucket a ritmo costante, attesa stimata.

Limite effettivo = `limitPerMinute` meno un margine (chiave condivisa con altri client). Le
chiamate escono da un token bucket di capienza B e ritmo r con B + 60·r = limite effettivo:
in qualsiasi intervallo di 60 s passano al massimo B + 60·r chiamate, qualunque sia la regola
della finestra di HofJ (ancorata come misurato, a griglia o scorrevole). Decisione M18.

Riserva `booking` come soglia (decisione M18): `purchase` e `sync` prendono gettoni solo se nel
bucket ne restano almeno `floor`, `booking` può arrivare a zero. Le prenotazioni degli ordini
pagati passano quindi sempre per prime. L'attesa stimata (RF-48) conta per gli acquisti solo
la quota `1 − reserve` del ritmo.

Le percentuali passano da Decimal perché il floor su float sbaglia (100 × 0,29 = 28,999…).
"""
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Optional

from vela.domain.models import QuotaClass

CALLS_PER_PURCHASE = 5   # RF-46: itinerario, customer, lettura pax, scrittura pax, totale
DEFAULT_BURST = 8        # B: con 108 effettive, r = 100/60 ≈ 1,67 chiamate/s
DEFAULT_FLOOR = 2        # gettoni che `purchase` e `sync` lasciano alle prenotazioni
WINDOW = timedelta(seconds=60)
_EPSILON = 1e-9          # tolleranza dei float del refill


def _floor_share(value: int, share: float) -> int:
    return int((Decimal(value) * Decimal(str(share))).to_integral_value(rounding=ROUND_FLOOR))


def effective_limit(limit_per_minute: int, margin: float) -> int:
    return _floor_share(limit_per_minute, 1 - Decimal(str(margin)))


@dataclass(frozen=True)
class BucketRules:
    margin: float = 0.10     # limite effettivo = limitPerMinute × 0,9
    reserve: float = 0.20    # quota del ritmo che l'attesa stimata (RF-48) lascia alle prenotazioni
    burst: int = DEFAULT_BURST
    floor: int = DEFAULT_FLOOR

    def __post_init__(self):
        if self.floor + CALLS_PER_PURCHASE > self.burst:
            raise ValueError("capienza %d: non contiene un acquisto (%d) più la soglia %d"
                             % (self.burst, CALLS_PER_PURCHASE, self.floor))

    def rate(self, limit_per_minute: int) -> float:
        """Gettoni al secondo: (limite effettivo − B) / 60, così B + 60·r = limite effettivo."""
        spare = effective_limit(limit_per_minute, self.margin) - self.burst
        if spare <= 0:
            raise ValueError("limite %d/min: niente ritmo oltre la capienza %d" % (limit_per_minute, self.burst))
        return spare / 60

    def floor_for(self, cls: QuotaClass) -> int:
        return 0 if cls == QuotaClass.BOOKING else self.floor


def purchases_per_minute(rate: float, reserve: float, calls_per_purchase: int = CALLS_PER_PURCHASE) -> float:
    """RF-48: acquisti al minuto su cui si stima l'attesa (80% del ritmo, prudente)."""
    per_minute = Decimal(str(rate)) * 60 * (1 - Decimal(str(reserve)))
    if per_minute <= 0:
        raise ValueError("nessun ritmo per gli acquisti")
    return float(per_minute / calls_per_purchase)


def estimated_wait_seconds(position: int, per_minute: float) -> int:
    """RF-48: posizione × 60 s ÷ acquisti al minuto, per eccesso. Nessun tetto."""
    return math.ceil(position * 60 / per_minute)


def wait_minutes(seconds: int) -> int:
    """Minuti da dire al viaggiatore (RF-45): per eccesso, almeno 1."""
    return max(1, math.ceil(seconds / 60))


# --- Stato del bucket (RF-36..38, RF-47): puro, salvato dagli adapter -----------------------

@dataclass(frozen=True)
class QuotaBucket:
    tokens: float                # può essere negativo: bucket bloccato fino alla fine della finestra HofJ
    refilled_at: datetime
    limit_per_minute: int
    needs_refresh: bool
    window_start: datetime       # ultima finestra nota di HofJ (snapshot), solo informativa
    window_end: datetime


def fresh_bucket(now: datetime, limit_per_minute: int, rules: BucketRules) -> QuotaBucket:
    """Stato prima di ogni `GET /v1/quota`: bucket pieno, limite dichiarato, da sincronizzare."""
    return QuotaBucket(float(rules.burst), now, limit_per_minute, True, now, now + WINDOW)


def refill(b: QuotaBucket, now: datetime, rules: BucketRules) -> QuotaBucket:
    """Gettoni maturati da `refilled_at`, fino a B. Un orologio indietro non toglie né aggiunge."""
    if now <= b.refilled_at:
        return b
    gained = (now - b.refilled_at).total_seconds() * rules.rate(b.limit_per_minute)
    return replace(b, tokens=min(float(rules.burst), b.tokens + gained), refilled_at=now)


def try_take(b: QuotaBucket, cls: QuotaClass, n: int, now: datetime, rules: BucketRules,
             purchase_waiting: bool = False) -> Optional[QuotaBucket]:
    """Nuovo stato con `n` gettoni presi, o None: tutto il blocco o niente (RF-47)."""
    if cls == QuotaClass.SYNC and purchase_waiting:
        return None
    b = refill(b, now, rules)
    if b.tokens - n < rules.floor_for(cls) - _EPSILON:
        return None
    return replace(b, tokens=b.tokens - n)


def claim_refresh(b: QuotaBucket, now: datetime, rules: BucketRules) -> Optional[QuotaBucket]:
    """Una sola rilettura di `/v1/quota` per il cluster: 1 gettone `booking` e `needs_refresh`
    spento nello stesso passo. None se non serve o se manca il gettone."""
    if not b.needs_refresh:
        return None
    taken = try_take(b, QuotaClass.BOOKING, 1, now, rules)
    return None if taken is None else replace(taken, needs_refresh=False)


def after_429(b: QuotaBucket, now: datetime, rules: BucketRules, hold_seconds: float = 0.0) -> QuotaBucket:
    """RF-38: un 429 svuota il bucket e chiede una rilettura. `hold_seconds` lo tiene fermo più
    a lungo (429 sulla rilettura stessa: senza informazioni si aspetta una finestra intera)."""
    b = refill(b, now, rules)
    blocked = -hold_seconds * rules.rate(b.limit_per_minute)
    return replace(b, tokens=min(b.tokens, 0.0, blocked), needs_refresh=True)


def from_snapshot(b: QuotaBucket, limit_per_minute: int, used_in_window: int, started: datetime,
                  ends: datetime, now: datetime, rules: BucketRules) -> QuotaBucket:
    """Allinea al `GET /v1/quota`: nuovo limite; mai più gettoni di quanti HofJ ne lasci nella
    finestra; finestra esaurita → bucket negativo, torna a zero quando la finestra HofJ scade."""
    b = replace(refill(b, now, rules), limit_per_minute=limit_per_minute, needs_refresh=False,
                window_start=started, window_end=ends)
    left = effective_limit(limit_per_minute, rules.margin) - used_in_window
    if left > 0:
        cap = float(left)
    else:
        cap = -max(0.0, (ends - now).total_seconds()) * rules.rate(limit_per_minute)
    return replace(b, tokens=min(b.tokens, cap, float(rules.burst)))


def seconds_until(b: QuotaBucket, cls: QuotaClass, n: int, now: datetime, rules: BucketRules) -> float:
    """Secondi prima che il bucket possa dare `n` gettoni a `cls` (0 se può già)."""
    b = refill(b, now, rules)
    missing = n + rules.floor_for(cls) - b.tokens
    return max(0.0, missing / rules.rate(b.limit_per_minute))


def available_at(b: QuotaBucket, now: datetime, rules: BucketRules, cls: QuotaClass = QuotaClass.PURCHASE,
                 n: int = CALLS_PER_PURCHASE) -> datetime:
    """Istante in cui `cls` potrà prendere `n` gettoni: il `run_after` di chi resta senza budget.
    Di default un acquisto intero."""
    return now + timedelta(seconds=seconds_until(b, cls, n, now, rules))


def describe(b: QuotaBucket, now: datetime, rules: BucketRules) -> dict:
    """Vista per `/health`, per l'attesa stimata e per i test, senza modificare lo stato."""
    b = refill(b, now, rules)
    rate = rules.rate(b.limit_per_minute)
    return {"limit_per_minute": b.limit_per_minute,
            "effective_limit": effective_limit(b.limit_per_minute, rules.margin),
            "burst": rules.burst, "rate_per_minute": round(rate * 60, 3),
            "purchase_floor": rules.floor, "tokens": round(b.tokens, 3),
            "purchases_per_minute": purchases_per_minute(rate, rules.reserve),
            "needs_refresh": b.needs_refresh,
            "hofj_window_start": b.window_start, "hofj_window_end": b.window_end}
