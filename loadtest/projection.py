"""Proiezione dei giri ridotti al twist (M13a): 1k, 10k, 50k viaggiatori in 10 minuti.

Modello a coda satura, marcato **[proiezione]** in RESULTS.md: arrivi uniformi, una frazione
`accept` accetta subito, Vela produce `rate` link al minuto (misurato nei giri ridotti, dove la
coda è satura). Oltre la saturazione le chiamate HofJ al minuto e il ritmo non dipendono dal
numero di viaggiatori: cresce solo la coda.

- accettazioni al minuto λ = accept · N / T;
- se λ ≤ rate la coda non cresce; altrimenti chi accetta al minuto t ha davanti (λ − rate)·t
  persone e aspetta (λ − rate)·t / rate minuti;
- smaltire tutte le accettazioni richiede accept · N / rate minuti;
- richieste REST al secondo a fine arrivi: conversazione (N/T · richieste per viaggiatore / 60)
  più lo stato chiesto da chi aspetta, in media ogni `poll` secondi.
"""
from dataclasses import dataclass
from typing import Optional

REQUESTS_PER_ARRIVAL = 2.3   # intento + proposta + 30% rifiuti (+ accept per il 20%, vedi sotto)


@dataclass(frozen=True)
class Projection:
    travelers: int
    minutes: float
    accepts_per_minute: float
    rate: float
    saturated: bool
    queue_at_end: float
    wait_at_minute_1: float        # Marco
    wait_at_60_percent: float      # Anna
    wait_last_minutes: float
    drain_minutes: float
    rest_rps_at_end: float


def project(travelers: int, rate: float, minutes: float = 10.0, accept: float = 0.20,
            poll_seconds: float = 45.0) -> Projection:
    if rate <= 0:
        raise ValueError("ritmo misurato non positivo")
    lam = accept * travelers / minutes
    excess = max(lam - rate, 0.0)
    wait = lambda t: excess * t / rate
    queue = excess * minutes
    arrivals_per_second = travelers / minutes / 60
    rest = arrivals_per_second * (REQUESTS_PER_ARRIVAL + accept) + queue / poll_seconds
    return Projection(travelers, minutes, round(lam, 1), rate, lam > rate, round(queue),
                      round(wait(1), 1), round(wait(0.6 * minutes), 1), round(wait(minutes), 1),
                      round(accept * travelers / rate, 1), round(rest, 1))
