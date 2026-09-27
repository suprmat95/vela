"""Proiezione di un giro misurato a più viaggiatori (es. 10.000 → 50.000), con gli stessi gruppi.

Modello a coda satura, marcato **[proiezione]** in RESULTS.md: arrivi uniformi in `minutes`, i
gruppi `link` e `pay` accettano subito, Vela produce `rate` link al minuto (misurato nel giro, dove
la coda è satura). Oltre la saturazione chiamate HofJ al minuto e ritmo non dipendono dal numero
di viaggiatori: cresce solo la coda.

- accettazioni al minuto λ = (link + pay) · N / T;
- se λ ≤ rate la coda non cresce; altrimenti chi accetta al minuto t ha davanti (λ − rate)·t
  persone e aspetta (λ − rate)·t / rate minuti prima del link, cioè prima di poter pagare: la
  mediana è chi accetta a metà della finestra, l'ultimo chi accetta alla fine;
- smaltire tutte le accettazioni richiede (link + pay) · N / rate minuti;
- link entro la fine del giro (arrivi + coda): al più rate · (T + coda), mai più delle
  accettazioni; i paganti ne sono la quota pay / (link + pay);
- richieste REST al secondo a fine arrivi: conversazione (intento e proposta per chi non naviga
  soltanto, accettazione e conferma del prezzo per chi accetta, checkout per chi paga) più lo
  stato chiesto da chi aspetta, in media ogni `poll_seconds` secondi. Chi naviga solo il sito
  non chiama Vela.
"""
import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from loadtest.scenario import Mix, group_counts  # noqa: E402

SIZES = (10_000, 50_000)


def requests_per_arrival(mix: Mix) -> float:
    s = {g: v / 100 for g, v in mix.shares().items()}
    return (1 - s["browse"]) * 2 + (s["link"] + s["pay"]) * 2 + s["pay"]


@dataclass(frozen=True)
class Projection:
    travelers: int
    minutes: float
    tail_minutes: float
    groups: dict
    accepts: int
    accepts_per_minute: float
    rate: float
    saturated: bool
    queue_at_end: int
    wait_at_minute_1: float        # Marco, minuti
    wait_median: float             # chi accetta a metà della finestra, minuti
    wait_at_60_percent: float      # Anna, minuti
    wait_at_end: float             # ultimo ad accettare, minuti
    drain_minutes: float
    links_by_end: int              # link consegnati entro arrivi + coda
    paid_by_end: int
    rest_rps_at_end: float


def project(travelers: int, rate: float, minutes: float = 5.0, mix: Mix = Mix(),
            tail_minutes: float = 3.0, poll_seconds: float = 45.0) -> Projection:
    if rate <= 0:
        raise ValueError("ritmo misurato non positivo")
    groups = group_counts(travelers, mix)
    accepts = groups["link"] + groups["pay"]
    lam = accepts / minutes
    excess = max(lam - rate, 0.0)

    def wait(t):
        return round(excess * t / rate, 1)
    queue = excess * minutes
    links = min(accepts, int(rate * (minutes + tail_minutes)))
    paid = round(links * groups["pay"] / accepts) if accepts else 0
    rest = travelers / minutes / 60 * requests_per_arrival(mix) + queue / poll_seconds
    return Projection(travelers, minutes, tail_minutes, groups, accepts, round(lam, 1), rate,
                      lam > rate, round(queue), wait(1), wait(minutes / 2), wait(0.6 * minutes),
                      wait(minutes),
                      round(accepts / rate, 1), links, paid, round(rest, 1))


PAY_WITHIN = (5, 15, 30, 60, 120, 240)


def paid_within(p: Projection, minutes_after_arrival: float) -> float:
    """Quota dei paganti con il link (quindi in grado di pagare) entro `minutes_after_arrival`
    dal loro arrivo. Chi accetta al minuto t aspetta (λ − rate)·t / rate: ce la fa se accetta
    entro X · rate / (λ − rate), e gli arrivi sono uniformi nella finestra."""
    excess = p.accepts_per_minute - p.rate
    if excess <= 0:
        return 1.0
    return min(1.0, minutes_after_arrival * p.rate / excess / p.minutes)


def pay_markdown(rate: float, sizes=SIZES, minutes: float = 5.0, mix: Mix = Mix(),
                 within=PAY_WITHIN) -> str:
    rows = ["| Viaggiatori in %g min | Paganti | %s |" % (
                minutes, " | ".join("Possono pagare entro %g min dall'arrivo" % x for x in within)),
            "|---|---|%s" % ("---|" * len(within))]
    for n in sizes:
        p = project(n, rate, minutes, mix)
        rows.append("| %d | %d | %s |" % (n, p.groups["pay"], " | ".join(
            "%d%% (%d)" % (round(100 * paid_within(p, x)), round(p.groups["pay"] * paid_within(p, x)))
            for x in within)))
    return "\n".join(rows)


def markdown(rate: float, sizes=SIZES, minutes: float = 5.0, mix: Mix = Mix(),
             tail_minutes: float = 3.0) -> str:
    rows = ["| Viaggiatori in %g min | Solo sito / proposta / link / paga | Accettazioni/min "
            "| Coda a fine arrivi | Dall'accettazione al link, cioè a poter pagare: Marco (minuto 1) "
            "/ mediana / ultimo (min) | Smaltimento (min) | Link / pagati entro %g min "
            "| REST req/s a fine arrivi |" % (minutes, minutes + tail_minutes),
            "|---|---|---|---|---|---|---|---|"]
    for n in sizes:
        p = project(n, rate, minutes, mix, tail_minutes)
        rows.append("| %d | %s | %g | %d | %g / %g / %g | %g | %d / %d | %g |" % (
            n, " / ".join(str(p.groups[g]) for g in ("browse", "proposal", "link", "pay")),
            p.accepts_per_minute, p.queue_at_end, p.wait_at_minute_1, p.wait_median,
            p.wait_at_end, p.drain_minutes, p.links_by_end, p.paid_by_end, p.rest_rps_at_end))
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rate", type=float, required=True, help="link al minuto misurati a coda satura")
    ap.add_argument("--minutes", type=float, default=5.0, help="minuti di arrivi (default 5)")
    ap.add_argument("--tail-minutes", type=float, default=3.0, help="minuti di coda (default 3)")
    ap.add_argument("--browse", type=float, default=50.0)
    ap.add_argument("--proposal", type=float, default=30.0)
    ap.add_argument("--link", type=float, default=18.0)
    ap.add_argument("--sizes", default=",".join(str(n) for n in SIZES),
                    help="viaggiatori separati da virgola (default 10000,50000)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        mix = Mix(args.browse, args.proposal, args.link)
    except ValueError as exc:
        ap.error(str(exc))
    sizes = [int(n) for n in args.sizes.split(",")]
    if args.json:
        print(json.dumps([asdict(project(n, args.rate, args.minutes, mix, args.tail_minutes))
                          for n in sizes], indent=2))
    else:
        print(markdown(args.rate, sizes, args.minutes, mix, args.tail_minutes))
        print()
        print(pay_markdown(args.rate, sizes, args.minutes, mix))
    return 0


if __name__ == "__main__":
    sys.exit(main())
