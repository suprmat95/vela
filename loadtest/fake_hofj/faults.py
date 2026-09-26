"""Guasti e latenza del finto HofJ (M13a), estratti da generatori con seme fisso.

Un guasto si dichiara per endpoint: `"POST /v1/bookings=hang_then_execute:0.05"`.
- `hang_then_execute`: l'effetto avviene, poi la risposta resta appesa oltre il timeout del
  client (un timeout è un esito incerto, seconda lettura §3.3);
- `hang`: resta appeso senza eseguire;
- `5xx`: 503 senza eseguire;
- `product_502`: 502 `upstream-error` come un prodotto che il brand non trova.

Latenza [previsto]: `standard` = 2-6 s su `POST /v1/itineraries` (brief), 0,3-1,5 s sugli altri
endpoint (acceptance.md ha solo il totale di 53 s, non il dettaglio); `pessimistic` = 2-6 s
ovunque; `none` = nessuna (test).
"""
import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

KINDS = ("hang_then_execute", "hang", "5xx", "product_502")
SLOW_ENDPOINT = "POST /v1/itineraries"
LATENCY = {
    "standard": {"slow": (2.0, 6.0), "other": (0.3, 1.5)},
    "pessimistic": {"slow": (2.0, 6.0), "other": (2.0, 6.0)},
    "none": {"slow": (0.0, 0.0), "other": (0.0, 0.0)},
}


@dataclass(frozen=True)
class Fault:
    endpoint: str
    kind: str
    probability: float


def parse_fault(text: str) -> Fault:
    """`"<METODO> <rotta>=<tipo>:<probabilità>"` → `Fault`; ValueError con il motivo."""
    try:
        endpoint, rest = text.rsplit("=", 1)
        kind, probability = rest.split(":", 1)
        p = float(probability)
    except ValueError:
        raise ValueError("guasto %r: formato '<METODO> <rotta>=<tipo>:<probabilità>'" % text) from None
    if kind not in KINDS:
        raise ValueError("guasto %r: tipo %r sconosciuto, ammessi %s" % (text, kind, ", ".join(KINDS)))
    if not 0 <= p <= 1:
        raise ValueError("guasto %r: probabilità fuori da [0, 1]" % text)
    return Fault(endpoint.strip(), kind, p)


class FaultPlan:
    """Un'estrazione per chiamata: al più un guasto, scelto sulle probabilità cumulate."""

    def __init__(self, faults: Iterable[Fault], seed: int):
        self.by_endpoint: Dict[str, List[Fault]] = {}
        for f in faults:
            self.by_endpoint.setdefault(f.endpoint, []).append(f)
        for endpoint, fs in self.by_endpoint.items():
            if sum(f.probability for f in fs) > 1:
                raise ValueError("guasti di %s: probabilità totale oltre 1" % endpoint)
        self.rng = random.Random(seed)

    def pick(self, endpoint: str) -> Optional[str]:
        faults = self.by_endpoint.get(endpoint)
        if not faults:
            return None
        draw, acc = self.rng.random(), 0.0
        for f in faults:
            acc += f.probability
            if draw < acc:
                return f.kind
        return None


class Latency:
    def __init__(self, profile: str, seed: int):
        if profile not in LATENCY:
            raise ValueError("latenza %r sconosciuta: %s" % (profile, ", ".join(LATENCY)))
        self.ranges = LATENCY[profile]
        self.rng = random.Random(seed + 1)

    def draw(self, endpoint: str) -> float:
        low, high = self.ranges["slow" if endpoint == SLOW_ENDPOINT else "other"]
        return self.rng.uniform(low, high) if high > 0 else 0.0

    def bounds(self, endpoint: str) -> Tuple[float, float]:
        return self.ranges["slow" if endpoint == SLOW_ENDPOINT else "other"]
