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


from decimal import Decimal as _Decimal
from datetime import timedelta as _timedelta

from vela.ports.hofj import Itinerary, Pax
from vela.ports.payments import PaymentLink, PaymentsError


class FakeHofJ:
    """Porta HofJ finta e ispezionabile: totale configurabile, errori a comando."""

    def __init__(self, total=None, fail_itinerary=None, fail_booking=None, code="R-000001"):
        self.total = total
        self.fail_itinerary = fail_itinerary
        self.fail_booking = fail_booking
        self.code = code
        self.calls = []
        self.customers = {}
        self.pax = {}
        self.bookings = 0

    def create_itinerary(self, product, start_date, adults, rooms, currency):
        self.calls.append(("create_itinerary", product.id, start_date, adults, rooms, currency))
        if self.fail_itinerary:
            raise self.fail_itinerary
        iid = "it-%s" % product.id
        self.pax[iid] = [Pax("ref-%d" % i) for i in range(adults)]
        total = self.total if self.total is not None else product.price * adults
        return Itinerary(iid, _Decimal(total), currency)

    def set_customer(self, itinerary_id, customer):
        self.calls.append(("set_customer", itinerary_id, customer))
        self.customers[itinerary_id] = customer

    def get_pax(self, itinerary_id):
        self.calls.append(("get_pax", itinerary_id))
        return list(self.pax[itinerary_id])

    def set_pax(self, itinerary_id, pax):
        self.calls.append(("set_pax", itinerary_id, pax))
        self.pax[itinerary_id] = list(pax)

    def create_booking(self, itinerary_id, proof):
        self.calls.append(("create_booking", itinerary_id, proof))
        if self.fail_booking:
            raise self.fail_booking
        self.bookings += 1
        return self.code


class StubPayments:
    def __init__(self, base="http://pay.test"):
        self.base = base
        self.links = []
        self.descriptions = []

    def create_payment_link(self, order, description):
        self.descriptions.append(description)
        link = PaymentLink("%s/%s" % (self.base, order.id), NOW + _timedelta(hours=24),
                           "pi_%s" % order.id)
        self.links.append(link)
        return link


class FlakyPayments(StubPayments):
    """Fallisce le prime `failures` chiamate con PaymentsError, poi si comporta come StubPayments."""

    def __init__(self, failures=1, base="http://pay.test"):
        super().__init__(base)
        self.failures = failures
        self.attempts = 0

    def create_payment_link(self, order, description):
        self.attempts += 1
        if self.failures:
            self.failures -= 1
            raise PaymentsError("fornitore non raggiungibile")
        return super().create_payment_link(order, description)


PROBLEM_JSON = "application/problem+json"


def assert_problem(testcase, response, status, slug):
    """Risposta RFC 7807 completa con `say` leggibile; restituisce il corpo."""
    testcase.assertEqual(response.status_code, status, response.text)
    testcase.assertTrue(response.headers["content-type"].startswith(PROBLEM_JSON),
                        response.headers["content-type"])
    body = response.json()
    testcase.assertEqual(body["type"], "/problems/" + slug)
    testcase.assertEqual(body["status"], status)
    for key in ("title", "detail", "instance", "say"):
        testcase.assertTrue(body.get(key), "campo 7807 mancante: %s" % key)
    testcase.assertNotIn("http", body["say"])
    return body
