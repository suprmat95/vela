"""Etichette del prodotto lette dal testo del catalogo (RF-63, M21-C): livelli, esclusività del
livello, lezioni o coach.

Regole deterministiche it/en, le stesse su ogni catalogo qualunque sia la sua lingua (decisione
M21-C, opzione A: i cataloghi `it` hanno anche frasi in inglese). Si leggono `description` e
`shortDescription` del dettaglio HofJ. Un livello conta solo se riferito ai giocatori ("giocatori
di livello intermedio e avanzato", "advanced players", "tutti i livelli"): "tattiche avanzate",
"istruttori esperti", "alto livello" o "élite" parlano del programma o dei coach, non di chi può
partecipare. `levels_exclusive` è vero solo con una riserva esplicita ("solo per avanzati",
"advanced players only", "non adatto ai principianti"): allora `levels` sono i soli livelli
ammessi. Nessuna parola sul livello = `levels` vuoto, livello sconosciuto (compatibile con
tutti). Funzione pura: la usano il sync (`catalog.project_detail`) e il backfill della migrazione
0012, così le regole non si duplicano.
"""
import re
from dataclasses import dataclass
from typing import Optional

BEGINNER, INTERMEDIATE, ADVANCED, ALL = "beginner", "intermediate", "advanced", "all"
LEVELS = (BEGINNER, INTERMEDIATE, ADVANCED)       # i livelli di gioco del viaggiatore (RF-62)
LABEL_ORDER = (BEGINNER, INTERMEDIATE, ADVANCED, ALL)   # ordine stabile per colonna e fixture

# parole di livello riferite a persone, con il livello che indicano
_WORDS = (
    (BEGINNER, r"principiant[ei]|beginners?|novices?|neofit[aie]"),
    (INTERMEDIATE, r"intermedi[oae]?|intermediate"),
    (ADVANCED, r"avanzat[oiae]|espert[oiae]|agonist[aie]|advanced|experts?|experienced|competitive"),
)
_ANY_WORD = "|".join(w for _, w in _WORDS)
_LIST = r"(?:%s)(?:\s*(?:,|e|ed|o|and|or)\s*(?:%s))*" % (_ANY_WORD, _ANY_WORD)
_PLAYERS_IT = r"(?:giocator[ei]|giocatric[ei]|tennist[ie]|padelist[ie])"

_LEVEL_RULES = (
    (BEGINNER, re.compile(r"\b(?:principiant[ei]|beginners?|novices?|neofit[aie]|alle prime armi|"
                          r"mai giocato|never played)\b")),
    (INTERMEDIATE, re.compile(r"\b(?:intermedi[oae]?|intermediate)\b")),
    # avanzato solo se detto dei giocatori o del livello: mai "tattiche avanzate", "coach esperti"
    (ADVANCED, re.compile(
        r"\bagonist[aie]\b|"
        r"\b%s\s+(?:(?:molto|più|già)\s+)?(?:avanzat[oiae]|espert[oiae]|agonist[aie])\b|"
        r"\blivell[oi]\s+(?:(?:intermedio|medio)\s+(?:e|o|ed)\s+)?(?:avanzat[oi]|agonistic[oi])\b|"
        r"\b(?:advanced|experienced|expert|competitive)\s+players?\b|"
        r"\badvanced\s+level\b|\b(?:intermediate|beginner)\s+(?:and|or|to)\s+advanced\b|"
        r"\b(?:per|a|ad|agli|ai|all')\s*(?:giocatori\s+)?(?:avanzat[ie]|espert[ie])\b" % _PLAYERS_IT)),
    (ALL, re.compile(r"\b(?:tutti i livelli|ogni livello|qualsiasi livello|qualunque livello|"
                     r"livelli misti|all (?:skill |playing )?levels|every (?:skill )?level|"
                     r"any (?:skill )?level|whatever your level|mixed levels)\b")),
)

# riserve esplicite (RF-64): il gruppo 1 è l'elenco dei livelli ammessi o esclusi
_RESERVED = (
    re.compile(r"\b(?:solo|soltanto|esclusivamente|riservat[oa](?:\s+(?:solo|esclusivamente))?)\s+"
               r"(?:per|a|ai|agli|alle)\s+(?:%s\s+)?(?:di\s+livello\s+)?(%s)\b" % (_PLAYERS_IT, _LIST)),
    re.compile(r"\b(%s)\s+players\s+only\b" % _LIST),
    re.compile(r"\b(?:only|exclusively|reserved|restricted)\s+(?:for|to)\s+(?:the\s+)?(%s)\b" % _LIST),
)
_EXCLUDED = (
    re.compile(r"\bnon\s+(?:è\s+)?(?:adatt[oa]|indicat[oa]|pensat[oa]|consigliat[oa])\s+"
               r"(?:a|ai|agli|alle|per)\s+(?:%s\s+)?(%s)\b" % (_PLAYERS_IT, _LIST)),
    re.compile(r"\bsconsigliat[oa]\s+(?:a|ai|agli|alle|per)\s+(?:%s\s+)?(%s)\b" % (_PLAYERS_IT, _LIST)),
    re.compile(r"\bnot\s+(?:suitable|recommended|designed|intended|meant)?\s*for\s+(%s)\b" % _LIST),
)

_COACHING = re.compile(
    r"\b(?:coach\w*|clinic\w*|lezion[ei]|maestr[oiae]|allenament[oi]|allenator[ei]|allenatric[ei]|"
    r"istruttor[ei]|istruttric[ei]|lessons?|training|instructors?|cors[oi] di)\b|"
    r"(?<!the )\bstage\b")


@dataclass(frozen=True)
class ProductLabels:
    levels: frozenset = frozenset()     # ⊆ LABEL_ORDER; vuoto = livello sconosciuto
    levels_exclusive: bool = False      # riserva esplicita: ammessi solo `levels` (RF-64)
    coaching: bool = False              # lezioni, coach, allenamenti (RF-63)


def ordered(levels) -> list:
    """I livelli nell'ordine di `LABEL_ORDER`: per la colonna JSON e le fixture."""
    return [lv for lv in LABEL_ORDER if lv in levels]


def _clean(text: str) -> str:
    """Minuscole, senza markdown né entità HTML, spazi singoli."""
    text = text.lower().replace("&#x27;", "'").replace("&amp;", "&").replace("’", "'")
    text = re.sub(r"[*_#|]", " ", text)
    return " ".join(text.split())


def _levels_in(words: str) -> set:
    return {level for level, pattern in _WORDS for w in re.findall(r"[a-zà-ÿ']+", words)
            if re.fullmatch(pattern, w)}


def _reserved(text: str) -> Optional[frozenset]:
    """Livelli ammessi da una riserva esplicita, o None senza riserva."""
    allowed = set().union(*(_levels_in(m.group(1)) for p in _RESERVED for m in p.finditer(text)))
    excluded = set().union(*(_levels_in(m.group(1)) for p in _EXCLUDED for m in p.finditer(text)))
    if not allowed and not excluded:
        return None
    reserved = (allowed or set(LEVELS)) - excluded
    return frozenset(reserved) or None


def label_texts(description: Optional[str], short_description: Optional[str]) -> ProductLabels:
    text = _clean("%s\n%s" % (short_description or "", description or ""))
    coaching = _COACHING.search(text) is not None
    reserved = _reserved(text)
    if reserved is not None:
        return ProductLabels(reserved, True, coaching)
    levels = frozenset(level for level, pattern in _LEVEL_RULES if pattern.search(text))
    return ProductLabels(levels, False, coaching)


def labels_of(detail: Optional[dict]) -> ProductLabels:
    """RF-63 sul dettaglio HofJ (o sul `raw` salvato): `description` e `shortDescription`."""
    detail = detail or {}
    return label_texts(detail.get("description"), detail.get("shortDescription"))
