"""Dettagli di un pacchetto dal dettaglio esteso HofJ salvato in `Product.raw` (RF-83).

Solo lettura del JSON già scaricato dal sync: nessuna chiamata. I testi restano nella lingua del
catalogo del brand. Ogni campo assente o vuoto diventa None (o lista vuota), mai un errore: la
forma di `rawAttributes` e di `travelProgram` non è documentata dall'OAS (`docs/api/products.md`).
"""
from typing import Optional


def _text(value) -> Optional[str]:
    return value.strip() or None if isinstance(value, str) else None


def blocks_text(value) -> Optional[str]:
    """Testo semplice da un campo rich text del CMS (lista di blocchi con `children`/`text`),
    un paragrafo per blocco; una stringa passa così com'è."""
    if isinstance(value, str):
        return _text(value)
    if not isinstance(value, list):
        return None

    def flat(node) -> str:
        if isinstance(node, dict):
            if isinstance(node.get("text"), str):
                return node["text"]
            return "".join(flat(c) for c in node.get("children") or [])
        return ""
    paragraphs = [flat(b).strip() for b in value]
    return "\n\n".join(p for p in paragraphs if p) or None


def _events(day: dict) -> list:
    return [{"time": _text(e.get("time")), "text": _text(e.get("text"))}
            for e in day.get("events") or [] if isinstance(e, dict) and _text(e.get("text"))]


def program_of(raw: dict) -> Optional[dict]:
    """`travelProgram` del dettaglio esteso: descrizione e sezioni con i giorni; None se manca
    o non ha né descrizione né giorni."""
    tp = raw.get("travelProgram")
    if not isinstance(tp, dict):
        return None
    sections = []
    for section in tp.get("details") or []:
        if not isinstance(section, dict):
            continue
        days = [{"title": _text(d.get("title")), "description": _text(d.get("description")),
                 "events": _events(d)}
                for d in section.get("days") or [] if isinstance(d, dict)]
        if days:
            sections.append({"title": _text(section.get("title")), "days": days})
    description = _text(tp.get("description"))
    if description is None and not sections:
        return None
    return {"description": description, "sections": sections}


def hotel_of(raw: dict) -> Optional[dict]:
    """Il primo hotel di `rawAttributes.hotels`, lo stesso di `Product.hotel` (catalogo)."""
    data = (((raw.get("rawAttributes") or {}).get("hotels") or {}).get("data") or [])
    if not data or not isinstance(data[0], dict):
        return None
    attrs = data[0].get("attributes") or {}
    name = _text(attrs.get("name"))
    if name is None:
        return None
    location = attrs.get("location") or {}
    address = _text(attrs.get("address")) or _text(location.get("description"))
    return {"name": name, "stars": attrs.get("stars"), "description": blocks_text(attrs.get("description")),
            "address": address}


def venue_of(raw: dict) -> Optional[dict]:
    venue = raw.get("venue") or {}
    name = _text(venue.get("title"))
    if name is None:
        return None
    return {"name": name, "description": _text(venue.get("shortDescription"))}


def _list(value) -> list:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def details_of(raw: dict) -> dict:
    """I campi di `ProposalDetails` ricavati da `raw` (vuoto per i prodotti senza dettaglio)."""
    raw = raw or {}
    attrs = raw.get("rawAttributes") or {}
    companions = attrs.get("acceptsCompanions")
    return {
        "description": _text(raw.get("description")),
        "why_this_trip": _text(attrs.get("whyThisTrip")),
        "program": program_of(raw),
        "hotel": hotel_of(raw),
        "venue": venue_of(raw),
        "playing_hours": _text(attrs.get("playingHours")),
        "style": _list(attrs.get("style")),
        "goal": _list(attrs.get("goal")),
        "best_for_level": _list(attrs.get("bestForLevel")),
        "accepts_companions": companions if isinstance(companions, bool) else None,
    }
