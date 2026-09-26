"""Scenario del twist a modello aperto (M13a): chi arriva, quando, e cosa fa. Puro, con seme.

Imbuto (roadmap M13a): 100% riceve una proposta, 30% dice "troppo caro", 20% accetta, chi ha
accettato chiede lo stato ogni 30-60 s, 60% di chi riceve il link paga. Le scelte sono
indipendenti: si può accettare con o senza rifiuto.

Sentinelle, in più degli N viaggiatori:
- **Marco** arriva a 55 s e accetta a 60 s, paga appena ha il link: la seconda lettura (§6) prevede
  il codice entro il minuto 7;
- **Anna** arriva al minuto 6, rifiuta ("troppo caro") e accetta: proposta < 500 ms e un'attesa
  dichiarata, senza errori.
Le sentinelle chiedono lo stato ogni 5 s per misurare i tempi con precisione.
"""
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

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


@dataclass(frozen=True)
class Funnel:
    reject: float = 0.30
    accept: float = 0.20
    pay: float = 0.60
    poll: Tuple[float, float] = (30.0, 60.0)


@dataclass(frozen=True)
class Traveler:
    index: int
    arrival: float                 # secondi dall'inizio dello scenario
    text: str
    sport: str
    rejects: bool
    accepts: bool
    pays: bool
    role: Optional[str] = None     # "marco", "anna" o None
    accept_at: Optional[float] = None   # Marco accetta a un istante fisso
    poll: Optional[Tuple[float, float]] = None


def arrivals(n: int, minutes: float, rng: random.Random) -> List[float]:
    """N istanti uniformi in [0, minutes·60), ordinati: arrivi indipendenti dal sistema."""
    return sorted(rng.uniform(0, minutes * 60) for _ in range(n))


def travelers(n: int, minutes: float = 10.0, seed: int = 13, funnel: Funnel = Funnel(),
              sentinels: bool = True) -> List[Traveler]:
    rng = random.Random(seed)
    out = []
    for i, t in enumerate(arrivals(n, minutes, rng)):
        text, sport = INTENTS[rng.randrange(len(INTENTS))]
        accepts = rng.random() < funnel.accept
        out.append(Traveler(i, t, text, sport, rejects=rng.random() < funnel.reject,
                            accepts=accepts, pays=rng.random() < funnel.pay, poll=funnel.poll))
    if sentinels:
        text, sport = INTENTS[0]
        out.append(Traveler(n, 55.0, text, sport, rejects=False, accepts=True, pays=True,
                            role="marco", accept_at=60.0, poll=(SENTINEL_POLL, SENTINEL_POLL)))
        out.append(Traveler(n + 1, 360.0, text, sport, rejects=True, accepts=True, pays=True,
                            role="anna", poll=(SENTINEL_POLL, SENTINEL_POLL)))
    return sorted(out, key=lambda tr: tr.arrival)
