"""Dizionario geografico statico it/en (RF-02, parser minimo M2).

Contiene i paesi e le destinazioni presenti in `fixtures/catalog.json` con alias in italiano e
inglese. `tests/test_geo.py` verifica che ogni destinazione della fixture sia coperta: quando
la fixture cambia, il test dice quali voci aggiungere. M11 aggiunge la gerarchia statica
`PARENTS` (città > regione > paese); M9 aggiunge regioni, nomi inglesi e le tabelle "più a
sud/nord". `geohierarchy` della fixture non si usa: è piatto (solo paese e id GeoNames, per
Nicosia con il paese sbagliato).
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
    # regioni che contengono città del catalogo (M9)
    ("Andalusia", "region", "ES", "andalucia", "andalucía"),
    ("Catalogna", "region", "ES", "catalonia", "catalunya", "cataluña"),
    ("Costa del Sol", "region", "ES"),
    ("Comunità Valenciana", "region", "ES", "comunitat valenciana", "valencian community"),
    ("Lombardia", "region", "IT", "lombardy"), ("Veneto", "region", "IT"),
    ("Emilia-Romagna", "region", "IT", "emilia romagna"),
    ("Occitania", "region", "FR", "occitanie"),
]

# luogo → luogo che lo contiene (solo tra voci di PLACES); il paese chiude sempre la catena
PARENTS = {
    "Lanzarote": "Canarie", "Tenerife": "Canarie", "Fuerteventura": "Canarie",
    "Palma de Mallorca": "Maiorca", "Maiorca": "Baleari", "Minorca": "Baleari", "Ibiza": "Baleari",
    "Firenze": "Toscana", "Pietrasanta": "Toscana",
    # regioni di M9
    "Malaga": "Costa del Sol", "Estepona": "Costa del Sol", "Torre del Mar": "Costa del Sol",
    "Costa del Sol": "Andalusia", "Siviglia": "Andalusia",
    "Barcellona": "Catalogna", "Lloret de Mar": "Catalogna", "Tarragona": "Catalogna",
    "Valencia": "Comunità Valenciana", "Alicante": "Comunità Valenciana",
    "Dénia": "Comunità Valenciana",
    "Milano": "Lombardia", "Venezia": "Veneto", "Riccione": "Emilia-Romagna",
    "Cap d'Agde": "Occitania",
}

# complemento di luogo quando "in <paese>" / "a <luogo>" non suona italiano
_LOCATIVE = {"Canarie": "alle Canarie", "Baleari": "alle Baleari", "Toscana": "in Toscana",
             "Sardegna": "in Sardegna", "Andalusia": "in Andalusia", "Catalogna": "in Catalogna",
             "Costa del Sol": "sulla Costa del Sol",
             "Comunità Valenciana": "nella Comunità Valenciana", "Lombardia": "in Lombardia",
             "Veneto": "in Veneto", "Emilia-Romagna": "in Emilia-Romagna",
             "Occitania": "in Occitania"}
_LOCATIVE_EN = {"Canarie": "in the Canary Islands", "Baleari": "in the Balearic Islands",
                "Costa del Sol": "on the Costa del Sol",
                "Comunità Valenciana": "in the Valencian Community"}

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

_BY_NAME.update({name: Area("country", name, code) for code, name in COUNTRIES.items()})

EN_NAMES = {
    "Spagna": "Spain", "Italia": "Italy", "Francia": "France", "Grecia": "Greece",
    "Marocco": "Morocco", "Egitto": "Egypt", "Cipro": "Cyprus", "Thailandia": "Thailand",
    "Barcellona": "Barcelona", "Firenze": "Florence", "Maiorca": "Mallorca", "Milano": "Milan",
    "Minorca": "Menorca", "Sardegna": "Sardinia", "Siviglia": "Seville", "Toscana": "Tuscany",
    "Venezia": "Venice", "Canarie": "Canary Islands", "Baleari": "Balearic Islands",
    "Catalogna": "Catalonia", "Comunità Valenciana": "Valencian Community",
    "Lombardia": "Lombardy", "Occitania": "Occitanie",
}

_CANARIES = ("Canarie", "Lanzarote", "Fuerteventura", "Tenerife")
_BALEARICS = ("Baleari", "Maiorca", "Palma de Mallorca", "Ibiza", "Minorca")
_ANDALUSIA = ("Andalusia", "Costa del Sol", "Malaga", "Estepona", "Torre del Mar", "Siviglia")
_TUSCANY = ("Toscana", "Firenze", "Pietrasanta")

# nome canonico → aree più a sud, dalla più vicina; tupla vuota = niente più a sud nel catalogo
SOUTH_OF = {
    "Francia": ("Spagna", "Italia"), "Reims": ("Cap d'Agde", "Barcellona"),
    "Cap d'Agde": ("Barcellona", "Maiorca"), "Occitania": ("Barcellona", "Maiorca"),
    "Italia": ("Tunisia", "Marocco"), "Milano": ("Toscana", "Sardegna"),
    "Lombardia": ("Toscana", "Sardegna"), "Venezia": ("Riccione", "Toscana"),
    "Veneto": ("Riccione", "Toscana"), "Riccione": ("Toscana", "Sardegna"),
    "Emilia-Romagna": ("Toscana", "Sardegna"),
    "Spagna": ("Marocco", "Canarie"), "Catalogna": ("Valencia", "Malaga"),
    "Barcellona": ("Valencia", "Malaga"), "Lloret de Mar": ("Barcellona", "Valencia"),
    "Tarragona": ("Valencia", "Malaga"), "Madrid": ("Siviglia", "Malaga"),
    "Valencia": ("Alicante", "Malaga"), "Comunità Valenciana": ("Alicante", "Malaga"),
    "Dénia": ("Alicante", "Malaga"), "Alicante": ("Malaga", "Marocco"),
    "Grecia": ("Cipro", "Egitto"), "Cipro": ("Egitto",), "Marocco": ("Canarie",),
    "Tunisia": ("Egitto",), "Egitto": ("Tanzania",), "Thailandia": ("Indonesia",),
}
SOUTH_OF.update({name: ("Sardegna",) for name in _TUSCANY})
SOUTH_OF.update({name: ("Malaga", "Marocco") for name in _BALEARICS})
SOUTH_OF.update({name: () for name in _CANARIES})

# nome canonico → aree più a nord, dalla più vicina; tupla vuota = niente più a nord nel catalogo
NORTH_OF = {
    "Spagna": ("Francia", "Italia"), "Alicante": ("Valencia", "Barcellona"),
    "Dénia": ("Valencia", "Barcellona"), "Valencia": ("Tarragona", "Barcellona"),
    "Comunità Valenciana": ("Tarragona", "Barcellona"), "Madrid": ("Barcellona", "Francia"),
    "Italia": ("Francia",), "Sardegna": ("Toscana", "Milano"),
    "Riccione": ("Venezia", "Milano"), "Emilia-Romagna": ("Venezia", "Milano"),
    "Francia": (), "Reims": (), "Cap d'Agde": ("Reims",), "Occitania": ("Reims",),
    "Marocco": ("Spagna",), "Tunisia": ("Italia",), "Egitto": ("Cipro", "Grecia"),
    "Cipro": ("Grecia",), "Grecia": ("Italia",), "Tanzania": ("Egitto",),
    "Indonesia": ("Thailandia",),
}
NORTH_OF.update({name: ("Malaga", "Maiorca") for name in _CANARIES})
NORTH_OF.update({name: ("Madrid", "Barcellona") for name in _ANDALUSIA})
NORTH_OF.update({name: ("Venezia", "Milano") for name in _TUSCANY})

_DIRECTIONS = {"south": SOUTH_OF, "north": NORTH_OF}


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


def where(area: Area, lang: str = "it") -> str:
    """Complemento di luogo: "in Spagna", "a Lanzarote", "alle Canarie"; in inglese "in Spain",
    "in the Canary Islands"."""
    if lang == "en":
        return _LOCATIVE_EN.get(area.name) or "in %s" % display_name(area, lang)
    if area.name in _LOCATIVE:
        return _LOCATIVE[area.name]
    return ("in %s" if area.kind == "country" else "a %s") % area.name


def area_by_name(name: Optional[str]) -> Optional[Area]:
    return _BY_NAME.get(name)


def display_name(area: Area, lang: str) -> str:
    return EN_NAMES.get(area.name, area.name) if lang == "en" else area.name


def move(area: Optional[Area], direction: str) -> Optional[Area]:
    """Area più a sud o più a nord di `area` (RF-08): prima la voce del luogo, poi quella del paese."""
    if area is None:
        return None
    table = _DIRECTIONS[direction]
    for key in (area.name, COUNTRIES.get(area.country_code)):
        if key in table:
            targets = table[key]
            return _BY_NAME[targets[0]] if targets else None
    return None
