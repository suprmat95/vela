"""Scenario del load test a modello aperto: chi arriva, quando, e cosa fa. Puro, con seme.

Ogni viaggiatore sta in uno solo di quattro gruppi (`Mix`, percentuali sul totale):
- `browse`: naviga solo il sito. La landing è un sito statico separato e non chiama Vela: il
  viaggiatore è contato ma non fa richieste;
- `proposal`: `create_intent` e `get_proposal`, poi si ferma;
- `link`: accetta, conferma il prezzo effettivo, arriva al link di pagamento e non paga;
- `pay`: il resto, paga e aspetta la conferma.
I gruppi hanno numeri esatti (`group_counts`), distribuiti a caso con il seme; nessuno rifiuta.
Chi ha accettato chiede lo stato ogni 30-60 s.

Sentinelle, in più degli N viaggiatori e fuori dai gruppi (pagano sempre):
- **Marco** arriva a 55 s e accetta a 60 s, paga appena ha il link: la seconda lettura (§6) prevede
  il codice entro il minuto 7;
- **Anna** arriva al 60% della finestra degli arrivi (il minuto 6 di 10 del twist; il minuto 3
  nei giri ridotti da 5), rifiuta ("troppo caro") e accetta: proposta < 500 ms e un'attesa
  dichiarata, senza errori.
Le sentinelle chiedono lo stato ogni 5 s per misurare i tempi con precisione.
"""
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Frasi che sul catalogo di produzione (padel weebora.com + tennis terrarossa.com) danno una
# proposta e, dopo "troppo caro", un'altra (tests/test_loadtest_scenario.py).
INTENTS = (
    ("un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro", "padel"),
    ("padel a Lanzarote a novembre, siamo in due", "padel"),
    ("tennis in Italia a novembre, siamo in due", "tennis"),
    ("tennis in Spagna a ottobre, siamo in due, massimo 1500 euro", "tennis"),
)
REASON = "troppo caro"
PROFILE = {"first_name": "Prova", "last_name": "Carico", "email": "prova.carico@example.com",
           "phone": "+390000000000", "participants": [{"first_name": "Seconda", "last_name": "Prova"}]}
SENTINEL_POLL = 5.0


GROUPS = ("browse", "proposal", "link", "pay")
POLL = (30.0, 60.0)


@dataclass(frozen=True)
class Mix:
    """Percentuali dei primi tre gruppi; `pay` è il resto fino a 100."""
    browse: float = 50.0
    proposal: float = 30.0
    link: float = 18.0

    def __post_init__(self):
        parts = (self.browse, self.proposal, self.link)
        if any(p < 0 for p in parts) or sum(parts) > 100 + 1e-9:
            raise ValueError("percentuali %g + %g + %g non valide: ognuna ≥ 0, somma ≤ 100"
                             % parts)

    @property
    def pay(self) -> float:
        return max(0.0, 100.0 - self.browse - self.proposal - self.link)

    def shares(self) -> Dict[str, float]:
        return {"browse": self.browse, "proposal": self.proposal, "link": self.link,
                "pay": self.pay}


def group_counts(n: int, mix: Mix) -> Dict[str, int]:
    """Viaggiatori per gruppo, che sommano a `n`: parte intera e resti più grandi."""
    exact = {g: n * share / 100 for g, share in mix.shares().items()}
    counts = {g: int(v) for g, v in exact.items()}
    for g in sorted(GROUPS, key=lambda g: exact[g] - counts[g], reverse=True)[:n - sum(counts.values())]:
        counts[g] += 1
    return counts


@dataclass(frozen=True)
class Traveler:
    index: int
    arrival: float                 # secondi dall'inizio dello scenario
    text: str
    sport: str
    rejects: bool
    accepts: bool
    pays: bool
    group: str = "pay"
    role: Optional[str] = None     # "marco", "anna" o None
    accept_at: Optional[float] = None   # Marco accetta a un istante fisso
    poll: Optional[Tuple[float, float]] = None


def arrivals(n: int, minutes: float, rng: random.Random) -> List[float]:
    """N istanti uniformi in [0, minutes·60), ordinati: arrivi indipendenti dal sistema."""
    return sorted(rng.uniform(0, minutes * 60) for _ in range(n))


def travelers(n: int, minutes: float = 10.0, seed: int = 13, mix: Mix = Mix(),
              sentinels: bool = True) -> List[Traveler]:
    rng = random.Random(seed)
    groups = [g for g, count in group_counts(n, mix).items() for _ in range(count)]
    rng.shuffle(groups)
    out = []
    for i, (t, group) in enumerate(zip(arrivals(n, minutes, rng), groups)):
        text, sport = INTENTS[rng.randrange(len(INTENTS))]
        out.append(Traveler(i, t, text, sport, rejects=False, accepts=group in ("link", "pay"),
                            pays=group == "pay", group=group, poll=POLL))
    if sentinels:   # solo se arrivano dentro la finestra degli arrivi (giri brevi di prova)
        text, sport = INTENTS[0]
        marco = Traveler(n, 55.0, text, sport, rejects=False, accepts=True, pays=True,
                         role="marco", accept_at=60.0, poll=(SENTINEL_POLL, SENTINEL_POLL))
        anna = Traveler(n + 1, 0.6 * minutes * 60, text, sport, rejects=True, accepts=True, pays=True,
                        role="anna", poll=(SENTINEL_POLL, SENTINEL_POLL))
        out += [tr for tr in (marco, anna) if tr.arrival < minutes * 60]
    return sorted(out, key=lambda tr: tr.arrival)
