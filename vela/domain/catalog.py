"""Dal formato della fixture (`docs/fixtures.md`) ai `Product` del dominio (RF-28).

Lo sport non è un campo dell'API: viene dal brand del catalogo (una fixture per brand, con
`brand` e `sport` nei metadati, decisione M10). Solo per una fixture senza `sport` si cerca
`padel`/`tennis` in titolo, slug, descrizione breve e descrizione, in quest'ordine; senza segnale
il prodotto è padel (decisione M2).
"""
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, List, Optional

from vela.domain.models import Availability, Product

SPORTS = ("padel", "tennis")
# chiavi scartate a ogni profondità del dettaglio: immagini e programma di viaggio
MEDIA_KEYS = frozenset(["gallery", "image", "images", "cover", "media", "travelProgram"])
# campi di RF-28 presi pari pari dal dettaglio (category, venue, destination, hotels a parte)
CATALOG_FIELDS = ("id", "title", "slug", "shortDescription", "price", "currency", "minPax",
                  "maxPax", "minDate", "maxDate", "availabilities", "defaultDurationInDays",
                  "updatedAt")


def strip_media(value):
    """Copia ricorsiva di `value` senza le chiavi in MEDIA_KEYS. Non modifica l'input."""
    if isinstance(value, dict):
        return {k: strip_media(v) for k, v in value.items() if k not in MEDIA_KEYS}
    if isinstance(value, list):
        return [strip_media(v) for v in value]
    return value


def project_detail(detail: dict) -> dict:
    """Campi di RF-28 presi dal dettaglio esteso, con i nomi dell'API; None se mancanti.
    È il `catalog` delle fixture e l'ingresso di `product_from_entry` nel sync (M10)."""
    catalog = {k: detail.get(k) for k in CATALOG_FIELDS}
    catalog["category"] = detail.get("category")
    catalog["venue"] = detail.get("venue")
    catalog["destination"] = detail.get("destination")
    raw_attributes = detail.get("rawAttributes") or {}
    catalog["hotels"] = strip_media(raw_attributes.get("hotels"))
    return catalog


def detect_sport(*texts: Optional[str]) -> str:
    for text in texts:
        low = (text or "").lower()
        for sport in SPORTS:
            if sport in low:
                return sport
    return "padel"


def _date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value[:10]) if value else None


def _hotel_name(entry: dict) -> Optional[str]:
    hotels = entry.get("hotels") or {}
    data = hotels.get("data") or []
    if not data:
        return None
    name = (data[0].get("attributes") or {}).get("name")
    return name.strip() if name else None


def product_from_entry(entry: dict, archived: bool, raw: dict, fetched_at: datetime,
                       brand: Optional[str] = None, sport: Optional[str] = None) -> Product:
    """Un `Product` da un item o un dettaglio HofJ; `sport` (dal brand) prevale sul testo."""
    category = entry.get("category") or {}
    venue = entry.get("venue") or {}
    destination = entry.get("destination") or {}
    windows = sorted(
        (Availability(_date(a["startDate"]), _date(a["endDate"])) for a in entry.get("availabilities") or []),
        key=lambda a: (a.start, a.end))
    return Product(
        id=str(entry["id"]),
        title=(entry.get("title") or "").strip(),
        slug=entry.get("slug") or "",
        short_description=(entry.get("shortDescription") or "").strip(),
        sport=sport or detect_sport(entry.get("title"), entry.get("slug"),
                                    entry.get("shortDescription"), entry.get("description")),
        category=category.get("name") or None,
        destination=(destination.get("title") or "").strip() or None,
        country=destination.get("country") or None,
        venue=(venue.get("title") or "").strip() or None,
        hotel=_hotel_name(entry),
        price=Decimal(str(entry["price"])),
        currency=entry.get("currency") or "EUR",
        min_pax=entry.get("minPax"),
        max_pax=entry.get("maxPax"),
        min_date=_date(entry.get("minDate")),
        max_date=_date(entry.get("maxDate")),
        availabilities=tuple(windows),
        duration_days=entry.get("defaultDurationInDays"),
        hofj_updated_at=entry.get("updatedAt"),
        raw=raw,
        fetched_at=fetched_at,
        bookable=True,
        bookable_checked_at=None,
        archived=archived,
        provider_id=entry.get("providerID"),
        brand=brand,
    )


def load_fixture(path, fetched_at: Optional[datetime] = None) -> list:
    """Tutti i prodotti della fixture: i non archiviati dal dettaglio `details[id].catalog`
    (con `raw`), gli archiviati dall'item di lista (senza dettaglio)."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    details = data.get("details") or {}
    brand, sport = data.get("brand"), data.get("sport")
    products = []
    for item in data.get("products") or []:
        pid = str(item["id"])
        detail = details.get(pid)
        if detail and not item.get("archived"):
            products.append(product_from_entry(detail["catalog"], archived=False,
                                               raw=detail.get("raw") or {}, fetched_at=fetched_at,
                                               brand=brand, sport=sport))
        else:
            products.append(product_from_entry(item, archived=bool(item.get("archived")),
                                               raw=item, fetched_at=fetched_at,
                                               brand=brand, sport=sport))
    return products


def fixture_meta(path) -> dict:
    """Host, locale, brand e sport con cui la fixture è stata registrata."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {"base_url": data.get("base_url"), "locale": data.get("locale"), "brand": data.get("brand"),
            "sport": data.get("sport")}


def select_fixtures(fixtures_dir, base_url: str) -> List[str]:
    """Le fixture `catalog*.json` registrate sull'host `base_url`, una per brand (RF-32, M10).
    Lo `/` finale non conta. Nessuna corrispondenza → RuntimeError con gli host trovati; due
    fixture dello stesso brand sullo stesso host → RuntimeError."""
    wanted = base_url.rstrip("/")
    found, selected, brands = [], [], {}
    for name in sorted(os.listdir(fixtures_dir)):
        if not (name.startswith("catalog") and name.endswith(".json")):
            continue
        path = os.path.join(fixtures_dir, name)
        meta = fixture_meta(path)
        host = (meta["base_url"] or "").rstrip("/")
        if host != wanted:
            found.append("%s (%s)" % (host, name))
            continue
        if meta["brand"] in brands:
            raise RuntimeError("due fixture del brand %s su %s: %s e %s"
                               % (meta["brand"], wanted, brands[meta["brand"]], name))
        brands[meta["brand"]] = name
        selected.append(path)
    if not selected:
        raise RuntimeError("nessuna fixture del catalogo registrata su %s; trovate: %s"
                           % (wanted, ", ".join(found) or "nessuna"))
    return selected


BRAND_DESTINATIONS = ("Weebora", "Terrarossa")
GIFT_CARD_SLUGS = ("gift-card", "giftcard")
# categoria dei pacchetti evento (Hospitality, Watch & Stay/Play, Ticket + Hotel) per nome: gli id
# cambiano tra host e brand (Terrarossa 23 in produzione, 15 su staging). Tutti i brand (M10).
EVENT_CATEGORIES = ("Tornei", "Tournaments")


def is_trip(product: Product) -> bool:
    """Falso per i prodotti del catalogo che non sono viaggi da giocare: la destinazione è un
    brand (Weebora Gift Card), il prodotto è una gift card di qualunque brand, riconosciuta dallo
    slug o dal titolo, o sta nella categoria dei pacchetti evento (decisioni M11 e M10)."""
    if product.destination in BRAND_DESTINATIONS or product.category in EVENT_CATEGORIES:
        return False
    if any(slug in product.slug for slug in GIFT_CARD_SLUGS):
        return False
    return "gift card" not in product.title.lower()
