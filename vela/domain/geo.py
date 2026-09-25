"""Dizionario geografico statico it/en (RF-02, parser minimo M2).

Contiene i paesi e le destinazioni presenti in `fixtures/catalog.json` con alias in italiano e
inglese. `tests/test_geo.py` verifica che ogni destinazione della fixture sia coperta: quando
la fixture cambia, il test dice quali voci aggiungere. M11 aggiunge la gerarchia statica
`PARENTS` (città > regione > paese); `geohierarchy` della fixture non si usa perché è piatto.
"""
import re
from typing import Optional

from vela.domain.models import Area

COUNTRIES = {
    "ES": "Spagna", "IT": "Italia", "FR": "Francia", "GR": "Grecia", "MA": "Marocco",
    "EG": "Egitto", "CY": "Cipro", "TN": "Tunisia", "ID": "Indonesia", "TH": "Thailandia",
    "TZ": "Tanzania", "AR": "Argentina",
}

# alias → codice paese
COUNTRY_ALIASES = {
    "spagna": "ES", "spain": "ES", "italia": "IT", "italy": "IT", "francia": "FR", "france": "FR",
    "grecia": "GR", "greece": "GR", "marocco": "MA", "morocco": "MA", "egitto": "EG", "egypt": "EG",
    "cipro": "CY", "cyprus": "CY", "tunisia": "TN", "indonesia": "ID", "thailandia": "TH",
    "thailand": "TH", "tanzania": "TZ", "argentina": "AR",
}

# (nome canonico, tipo, paese, alias aggiuntivi...)
PLACES = [
    ("Lanzarote", "city", "ES"), ("Alicante", "city", "ES"), ("Bali", "region", "ID"),
    ("Barcellona", "city", "ES", "barcelona"), ("Buenos Aires", "city", "AR"),
    ("Dénia", "city", "ES", "denia"), ("Essaouira", "city", "MA"), ("Estepona", "city", "ES"),
    ("Firenze", "city", "IT", "florence"), ("Fuerteventura", "region", "ES"),
    ("Ibiza", "region", "ES"), ("Lloret de Mar", "city", "ES", "costa brava"),
    ("Lombok", "region", "ID"), ("Madrid", "city", "ES"),
    ("Maiorca", "region", "ES", "mallorca", "majorca"), ("Malaga", "city", "ES", "málaga"),
    ("Marrakech", "city", "MA", "marrakesh"), ("Marsa Alam", "city", "EG"),
    ("Milano", "city", "IT", "milan"), ("Minorca", "region", "ES", "menorca"),
    ("Mykonos", "region", "GR"), ("Nicosia", "city", "CY"),
    ("Palma de Mallorca", "city", "ES", "palma"), ("Phuket", "region", "TH"),
    ("Pietrasanta", "city", "IT"), ("Reims", "city", "FR"), ("Riccione", "city", "IT"),
    ("Sardegna", "region", "IT", "sardinia"), ("Siviglia", "city", "ES", "seville", "sevilla"),
    ("Sousse", "city", "TN"), ("Tarragona", "city", "ES"), ("Tenerife", "region", "ES"),
    ("Torre del Mar", "city", "ES"), ("Toscana", "region", "IT", "tuscany"),
    ("Valencia", "city", "ES"), ("Venezia", "city", "IT", "venice"),
    ("Cap d'Agde", "city", "FR", "cap d agde"), ("Zante", "region", "GR", "zakynthos"),
    ("Zanzibar", "region", "TZ"), ("Canarie", "region", "ES", "canary islands", "canaries"),
    ("Baleari", "region", "ES", "balearic islands", "baleares"),
]

# luogo → luogo che lo contiene (solo tra voci di PLACES); il paese chiude sempre la catena
PARENTS = {
    "Lanzarote": "Canarie", "Tenerife": "Canarie", "Fuerteventura": "Canarie",
    "Palma de Mallorca": "Maiorca", "Maiorca": "Baleari", "Minorca": "Baleari", "Ibiza": "Baleari",
    "Firenze": "Toscana", "Pietrasanta": "Toscana",
}

# complemento di luogo quando "in <paese>" / "a <luogo>" non suona italiano
_LOCATIVE = {"Canarie": "alle Canarie", "Baleari": "alle Baleari", "Toscana": "in Toscana",
             "Sardegna": "in Sardegna"}

_BY_NAME = {place[0]: Area(place[1], place[0], place[2]) for place in PLACES}

_WORD = "a-zà-ÿ'"


def _build_index():
    index = []   # (alias, Area)
    for place in PLACES:
        name, kind, country = place[0], place[1], place[2]
        area = Area(kind, name, country)
        for alias in (name.lower(),) + tuple(a.lower() for a in place[3:]):
            index.append((alias, area))
    for alias, code in COUNTRY_ALIASES.items():
        index.append((alias, Area("country", COUNTRIES[code], code)))
    # gli alias più lunghi prima: "palma de mallorca" batte "mallorca"; luoghi prima dei paesi a pari lunghezza
    index.sort(key=lambda pair: (-len(pair[0]), pair[1].kind == "country"))
    return [(re.compile(r"(?<![%s])%s(?![%s])" % (_WORD, re.escape(alias), _WORD)), area)
            for alias, area in index]


_INDEX = _build_index()


def find_area(text: Optional[str]) -> Optional[Area]:
    low = (text or "").lower()
    for pattern, area in _INDEX:
        if pattern.search(low):
            return area
    return None


def area_of_destination(title: Optional[str], country_code: Optional[str]) -> Optional[Area]:
    found = find_area(title)
    if found is not None:
        return found
    return country_area(country_code)


def country_area(code: Optional[str]) -> Optional[Area]:
    if code not in COUNTRIES:
        return None
    return Area("country", COUNTRIES[code], code)


def ancestors(area: Area) -> list:
    """L'area e chi la contiene, fino al paese: Palma de Mallorca → Maiorca → Baleari → Spagna."""
    chain = [area]
    while chain[-1].name in PARENTS:
        chain.append(_BY_NAME[PARENTS[chain[-1].name]])
    if area.kind != "country":
        country = country_area(area.country_code)
        if country is not None:
            chain.append(country)
    return chain


def common_region(a: Area, b: Area) -> Optional[Area]:
    """La prima area non nazionale che contiene sia `a` sia `b` (Lanzarote, Tenerife → Canarie)."""
    others = ancestors(b)
    for candidate in ancestors(a):
        if candidate.kind != "country" and candidate in others:
            return candidate
    return None


def where(area: Area) -> str:
    """Complemento di luogo: "in Spagna", "a Lanzarote", "alle Canarie"."""
    if area.name in _LOCATIVE:
        return _LOCATIVE[area.name]
    return ("in %s" if area.kind == "country" else "a %s") % area.name
