"""Dal formato della fixture (`docs/fixtures.md`) ai `Product` del dominio (RF-28).

Lo sport non è un campo dell'API: si cerca `padel`/`tennis` in titolo, slug, descrizione breve
e descrizione, in quest'ordine; senza segnale il prodotto è padel (decisione M2).
"""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from vela.domain.models import Availability, Product

SPORTS = ("padel", "tennis")


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


def product_from_entry(entry: dict, archived: bool, raw: dict, fetched_at: datetime) -> Product:
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
        sport=detect_sport(entry.get("title"), entry.get("slug"), entry.get("shortDescription"),
                           entry.get("description")),
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
    )


def load_fixture(path, fetched_at: Optional[datetime] = None) -> list:
    """Tutti i prodotti della fixture: i non archiviati dal dettaglio `details[id].catalog`
    (con `raw`), gli archiviati dall'item di lista (senza dettaglio)."""
    fetched_at = fetched_at or datetime.now(timezone.utc)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    details = data.get("details") or {}
    products = []
    for item in data.get("products") or []:
        pid = str(item["id"])
        detail = details.get(pid)
        if detail and not item.get("archived"):
            products.append(product_from_entry(detail["catalog"], archived=False,
                                               raw=detail.get("raw") or {}, fetched_at=fetched_at))
        else:
            products.append(product_from_entry(item, archived=bool(item.get("archived")),
                                               raw=item, fetched_at=fetched_at))
    return products
