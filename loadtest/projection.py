"""Proiezione dei giri ridotti al twist (M13a): 1k, 10k, 50k viaggiatori in 10 minuti.

Modello a coda satura, marcato **[proiezione]** in RESULTS.md: arrivi uniformi, una frazione
`accept` accetta subito, Vela produce `rate` link al minuto (misurato nei giri ridotti, dove la
coda è satura). Oltre la saturazione chiamate HofJ al minuto e ritmo non dipendono dal numero di
viaggiatori: cresce solo la coda.

- accettazioni al minuto λ = accept · N / T;
- se λ ≤ rate la coda non cresce; altrimenti chi accetta al minuto t ha davanti (λ − rate)·t
  persone e aspetta (λ − rate)·t / rate minuti;
- smaltire tutte le accettazioni richiede accept · N / rate minuti;
- richieste REST al secondo a fine arrivi: conversazione (intento, proposta, 30% rifiuti, 20%
  accept) più lo stato chiesto da chi aspetta, in media ogni `poll_seconds` secondi.
"""
import argparse
import json
import sys
from dataclasses import asdict, dataclass

REQUESTS_PER_ARRIVAL = 1 + 1 + 0.30 + 0.20   # intento, proposta, rifiuto, accept


@dataclass(frozen=True)
class Projection:
    travelers: int
    minutes: float
    accepts_per_minute: float
    rate: float
    saturated: bool
    queue_at_end: int
    wait_at_minute_1: float        # Marco, minuti
    wait_at_60_percent: float      # Anna, minuti
    wait_at_end: float             # ultimo ad accettare, minuti
    drain_minutes: float
    rest_rps_at_end: float


def project(travelers: int, rate: float, minutes: float = 10.0, accept: float = 0.20,
            poll_seconds: float = 45.0) -> Projection:
    if rate <= 0:
        raise ValueError("ritmo misurato non positivo")
    lam = accept * travelers / minutes
    excess = max(lam - rate, 0.0)
    wait = lambda t: round(excess * t / rate, 1)
    queue = excess * minutes
    rest = travelers / minutes / 60 * REQUESTS_PER_ARRIVAL + queue / poll_seconds
    return Projection(travelers, minutes, round(lam, 1), rate, lam > rate, round(queue),
                      wait(1), wait(0.6 * minutes), wait(minutes),
                      round(accept * travelers / rate, 1), round(rest, 1))


def markdown(rate: float, sizes=(1_000, 10_000, 50_000), minutes: float = 10.0) -> str:
    rows = ["| Viaggiatori in %g min | Accettazioni/min | Coda a fine arrivi | Attesa di Marco "
            "(min) | Attesa di Anna (min) | Attesa dell'ultimo (min) | Smaltimento (h) | REST req/s "
            "a fine arrivi |" % minutes, "|---|---|---|---|---|---|---|---|"]
    for n in sizes:
        p = project(n, rate, minutes)
        rows.append("| %d | %g | %d | %g | %g | %g | %.1f | %g |" % (
            n, p.accepts_per_minute, p.queue_at_end, p.wait_at_minute_1, p.wait_at_60_percent,
            p.wait_at_end, p.drain_minutes / 60, p.rest_rps_at_end))
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rate", type=float, required=True, help="link al minuto misurati a coda satura")
    ap.add_argument("--minutes", type=float, default=10.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.json:
        print(json.dumps([asdict(project(n, args.rate, args.minutes)) for n in (1_000, 10_000, 50_000)],
                         indent=2))
    else:
        print(markdown(args.rate, minutes=args.minutes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
