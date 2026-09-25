"""Chooser v2 sul catalogo reale in fixture (M11): tabelle intento → prodotto atteso, rifiuti
in sequenza, casi limite e proprietà verificate esaurendo i rifiuti.

Gli id attesi dipendono da `fixtures/catalog.json` registrata il 2026-09-25: se la fixture
viene rigenerata, le tabelle vanno riviste (le proprietà no).
"""
import os
import re
import unittest
from datetime import date
from decimal import Decimal

from vela.domain import geo
from vela.domain.catalog import is_trip, load_fixture
from vela.domain.chooser import ELSEWHERE, INSIDE, SAME_COUNTRY, SAME_REGION, Choice, NoChoice, choose
from vela.domain.models import Criteria, Period

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog.json")
TODAY = date(2026, 9, 25)


def period(start, end, label="x"):
    return Period(date.fromisoformat(start), date.fromisoformat(end), label)


OCT = period("2026-10-01", "2026-10-31", "ottobre")
NOV = period("2026-11-01", "2026-11-30", "novembre")
DEC = period("2026-12-01", "2026-12-31", "dicembre")
A = geo.find_area

INTENTS = {
    # nome: (criteri, [(id, inizio, fine, area_score, entro budget), ...] per le prime tre scelte)
    "demo §10.1": (Criteria("padel", A("Spagna"), OCT, 2, Decimal("800")), [
        ("1023", "2026-10-01", "2026-10-04", INSIDE, True),
        ("1027", "2026-10-08", "2026-10-11", INSIDE, True),
        ("1078", "2026-10-15", "2026-10-18", INSIDE, True)]),
    "Lanzarote a novembre": (Criteria("padel", A("Lanzarote"), NOV, 2), [
        ("181", "2026-11-05", "2026-11-08", INSIDE, True),
        ("186", "2026-11-01", "2026-11-07", INSIDE, True),           # finestra aperta, 7 giorni
        ("393", "2026-11-01", "2026-11-08", SAME_REGION, True)]),    # Fuerteventura
    "Canarie a dicembre": (Criteria("padel", A("Canarie"), DEC, 1), [
        ("181", "2026-12-03", "2026-12-06", INSIDE, True),
        ("186", "2026-12-01", "2026-12-07", INSIDE, True),
        ("443", "2026-12-06", "2026-12-11", INSIDE, True)]),         # Tenerife
    "Maiorca a ottobre, 1500 euro": (Criteria("padel", A("Maiorca"), OCT, 2, Decimal("1500")), [
        ("239", "2026-10-01", "2026-10-02", INSIDE, True),
        ("910", "2026-10-01", "2026-10-04", INSIDE, False),          # Palma, dentro Maiorca
        ("342", "2026-10-11", "2026-10-16", INSIDE, False)]),
    "Palma a novembre": (Criteria("padel", A("Palma de Mallorca"), NOV, 2), [
        ("910", "2026-11-12", "2026-11-15", INSIDE, True),
        ("239", "2026-11-01", "2026-11-02", SAME_REGION, True),
        ("1023", "2026-11-05", "2026-11-08", SAME_COUNTRY, True)]),
    "Italia a novembre in 4": (Criteria("padel", A("Italia"), NOV, 4, Decimal("2000")), [
        ("688", "2026-11-01", "2026-11-02", INSIDE, True),
        ("766", "2026-11-01", "2026-11-01", INSIDE, True),
        ("210", "2026-11-07", "2026-11-07", INSIDE, True)]),
    "Firenze a ottobre": (Criteria("padel", A("Firenze"), OCT, 2), [
        ("229", "2026-10-03", "2026-10-03", INSIDE, True),
        ("688", "2026-10-01", "2026-10-02", SAME_REGION, True),      # Pietrasanta, Toscana
        ("190", "2026-10-05", "2026-10-07", SAME_REGION, True)]),
    "weekend a Lanzarote": (Criteria("padel", A("Lanzarote"), period("2026-10-10", "2026-10-11"), 2), [
        ("186", "2026-10-10", "2026-10-16", INSIDE, True),
        ("443", "2026-10-11", "2026-10-16", SAME_REGION, True),
        ("239", "2026-10-10", "2026-10-11", SAME_COUNTRY, True)]),
    # casi limite: area senza prodotti, budget impossibile, nessuna area
    "Grecia a novembre": (Criteria("padel", A("Grecia"), NOV, 2), [
        ("688", "2026-11-01", "2026-11-02", ELSEWHERE, True),
        ("766", "2026-11-01", "2026-11-01", ELSEWHERE, True),
        ("210", "2026-11-07", "2026-11-07", ELSEWHERE, True)]),
    "Spagna a ottobre, 50 euro": (Criteria("padel", A("Spagna"), OCT, 2, Decimal("50")), [
        ("1023", "2026-10-01", "2026-10-04", INSIDE, False),
        ("1027", "2026-10-08", "2026-10-11", INSIDE, False),
        ("1078", "2026-10-15", "2026-10-18", INSIDE, False)]),
    "ottobre ovunque": (Criteria("padel", None, OCT, 2), [
        ("688", "2026-10-01", "2026-10-02", ELSEWHERE, True),
        ("766", "2026-10-01", "2026-10-01", ELSEWHERE, True),
        ("323", "2026-10-15", "2026-10-16", ELSEWHERE, True)]),      # senza destinazione
}


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


@unittest.skipUnless(os.path.exists(FIXTURE), "fixture assente")
class FixtureChooserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.products = load_fixture(FIXTURE)
        cls.by_id = {p.id: p for p in cls.products}

    def sequence(self, criteria, n):
        rejected, out = set(), []
        for _ in range(n):
            r = choose(self.products, criteria, rejected, TODAY)
            if not isinstance(r, Choice):
                out.append(r)
                break
            out.append(r)
            rejected.add(r.product.id)
        return out

    def test_table_first_three_choices(self):
        for name, (criteria, expected) in INTENTS.items():
            with self.subTest(name):
                got = [(r.product.id, r.start_date.isoformat(), r.end_date.isoformat(),
                        r.area_score, r.within_budget) for r in self.sequence(criteria, 3)]
                self.assertEqual(got, expected)

    def test_demo_reason(self):
        r = choose(self.products, INTENTS["demo §10.1"][0], set(), TODAY)
        self.assertEqual(r.reason, "È a Torre del Mar, in Spagna come hai chiesto. Parte il 1 ottobre "
                                   "2026, nel periodo che hai chiesto, e costa 558 euro in totale, "
                                   "dentro il tuo budget di 800 euro.")

    def test_compromises_are_declared(self):
        greece = choose(self.products, INTENTS["Grecia a novembre"][0], set(), TODAY)
        self.assertTrue(greece.reason.startswith("Non ho partenze compatibili in Grecia: "), greece.reason)
        cheap = choose(self.products, INTENTS["Spagna a ottobre, 50 euro"][0], set(), TODAY)
        self.assertIn("oltre il tuo budget di 50 euro", cheap.reason)
        firenze = self.sequence(INTENTS["Firenze a ottobre"][0], 2)[1]
        self.assertTrue(firenze.reason.startswith(
            "Non ho partenze compatibili a Firenze: questa è a Pietrasanta, in Toscana."), firenze.reason)

    def test_gift_card_is_never_proposed(self):
        self.assertFalse(is_trip(self.by_id["282"]))
        self.assertEqual([p.id for p in self.products if not p.archived and not is_trip(p)], ["282"])

    def test_no_match_on_sport_and_period(self):
        self.assertEqual(choose(self.products, Criteria("tennis", None, None, 1), set(), TODAY),
                         NoChoice("sport"))
        far = Criteria("padel", A("Spagna"), period("2028-03-01", "2028-03-31"), 2)
        self.assertEqual(choose(self.products, far, set(), TODAY), NoChoice("dates"))

    def test_properties_exhausting_rejections(self):
        for name, (criteria, _) in INTENTS.items():
            with self.subTest(name):
                compatible = {p.id for p in self.products
                              if not p.archived and p.bookable and is_trip(p)
                              and (criteria.sport is None or p.sport == criteria.sport)}
                rejected, previous = set(), None
                while True:
                    r = choose(self.products, criteria, rejected, TODAY)
                    if isinstance(r, NoChoice):
                        self.assertEqual(r.failed_criterion, "rejected")
                        break
                    p = r.product
                    self.assertNotIn(p.id, rejected)                      # mai un rifiutato
                    self.assertFalse(p.archived)
                    self.assertTrue(p.bookable)
                    self.assertTrue(is_trip(p))
                    self.assertIn(p.id, compatible)
                    self.assertLessEqual(r.start_date, r.end_date)
                    self.assertGreaterEqual(r.start_date, TODAY)
                    if criteria.period is not None:
                        self.assertTrue(criteria.period.start <= r.start_date <= criteria.period.end)
                    self.assertTrue(any(w.start <= r.start_date and r.end_date <= w.end
                                        for w in p.availabilities))
                    self.assertLessEqual(len(sentences(r.reason)), 2, r.reason)
                    key = (-r.area_score, not r.within_budget, p.price, p.id)
                    if previous is not None:
                        self.assertLessEqual(previous, key)               # ordinamento non decrescente
                    previous = key
                    rejected.add(p.id)
                self.assertTrue(rejected <= compatible)
