"""Helper condivisi dai test di M2: prodotti sintetici, porta HofJ finta, invariante RF-10."""
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain.models import Availability, Product

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 25)


def make_product(pid, price=500, sport="padel", country="ES", destination="Lanzarote",
                 windows=(("2026-10-01", "2026-10-04"),), min_date="2026-09-25",
                 max_date="2026-12-31", min_pax=None, max_pax=None, archived=False,
                 bookable=True, hotel="Hotel Sole", title=None):
    return Product(
        id=str(pid), title=title or "Padel a %s %s" % (destination, pid), slug="p-%s" % pid,
        short_description="", sport=sport, category="Vacanze", destination=destination,
        country=country, venue="Club %s" % pid, hotel=hotel, price=Decimal(str(price)),
        currency="EUR", min_pax=min_pax, max_pax=max_pax,
        min_date=date.fromisoformat(min_date) if min_date else None,
        max_date=date.fromisoformat(max_date) if max_date else None,
        availabilities=tuple(Availability(date.fromisoformat(a), date.fromisoformat(b))
                             for a, b in windows),
        duration_days=4, hofj_updated_at="2026-09-25T10:44:12.537Z", raw={},
        fetched_at=NOW, bookable=bookable, bookable_checked_at=None, archived=archived,
        provider_id="t%s" % pid)


def count_products(obj):
    """Numero di dizionari con chiave `product_id` a qualunque profondità (invariante RF-10)."""
    if isinstance(obj, dict):
        own = 1 if "product_id" in obj else 0
        return own + sum(count_products(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(count_products(v) for v in obj)
    return 0


def assert_single_product(testcase, d):
    testcase.assertLessEqual(count_products(d), 1, "RF-10 violato: %r" % (d,))
    testcase.assertIn("say", d)
    testcase.assertNotIn("http", d["say"])
    testcase.assertNotIn("**", d["say"])
