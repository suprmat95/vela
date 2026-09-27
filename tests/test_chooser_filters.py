"""M21-E: `choose` e `cheapest_total` condividono i filtri duri. Le sequenze sotto sono state
registrate con il chooser di prima (commit 4b5881b), sulle fixture `catalog.json` e
`catalog-tennis.json`: rifiutando ogni volta la scelta si ottiene tutto l'elenco dei candidati
filtrati e ordinati. Se il refactor dei filtri cambiasse anche un solo candidato o l'ordine, la
sequenza cambierebbe. Le sequenze dipendono dalle fixture e dall'ordinamento: M21-B le rivedrà.
"""
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from vela.domain import geo
from vela.domain.catalog import load_fixture
from support import make_product
from vela.domain.chooser import Choice, NoChoice, cheapest_total, choose
from vela.domain.models import Criteria, Period

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()
OCT = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
DEC = Period(date(2026, 12, 1), date(2026, 12, 31), "dicembre")

# nome: (criteri, now, tetto di prezzo, sequenza dei prodotti scelti rifiutando ogni volta)
SEQUENCES = {
    "padel Spagna ottobre 2, 800": (
        Criteria("padel", geo.find_area("Spagna"), OCT, 2, Decimal("800")), NOW, None,
        "1023 1027 1078 257 239 250 645 896 181 995 1013 308 273 648 886 1009 207 910 "
        "278 342 230 186 999 426 302 443 270 256 218 235 688 766 210 229 244 201 190 "
        "217 291 296 1051 751 330 940 1071 221 944 663 948 457 1043 969 925 197 985 454"),
    "tennis 3 persone": (
        Criteria("tennis", None, None, 3), NOW, None,
        "1044 695 893 1087 931 369 988 707 1034 523 860 697 894 716 1031 854 608 855 "
        "955 710 1003 959 373 430 826 363 960 1075 378 1042 970 372 626 1020 506 1037"),
    "any dicembre 1, weekend": (
        Criteria("any", None, DEC, 1, duration_min_nights=1, duration_max_nights=3), NOW, None,
        "1059 1065 688 201 988 239 645 181 1071 995 1013 308 273 1003 1009 207 278 1075 "
        "766 210 244 697 221 710 959 663 964 569 186 999 426 302 443 270 763 1055 256 "
        "235 1020 1037 624 748"),
    "padel Italia 5, tetto 2000": (
        Criteria("padel", geo.find_area("Italia"), None, 5, Decimal("3000")), NOW, Decimal("2000"),
        "688 766 210 229 244 190 1059 1065 1023 1027 201 1078 257"),
    "padel 2 senza now": (
        Criteria("padel", None, None, 2), None, None,
        "1059 1065 688 766 210 229 244 1023 1027 201 190 1078 257 217 291 239 1090 1093 "
        "296 250 1051 751 645 896 330 181 940 1071 995 1013 308 221 273 648 886 944 "
        "1009 207 663 910 278 964 569 342 482 948 230 186 393 999 426 457 1043 969 302 "
        "925 443 270 197 763 1055 256 218 235 985 454 838 624 622 748"),
}


def catalog():
    return (load_fixture(os.path.join(FIXTURES, "catalog.json"), NOW)
            + load_fixture(os.path.join(FIXTURES, "catalog-tennis.json"), NOW))


class ChooseUnchangedTest(unittest.TestCase):
    """Il refactor dei filtri non cambia nessuna scelta di `choose`."""

    @classmethod
    def setUpClass(cls):
        cls.products = catalog()

    def test_sequences(self):
        for name, (criteria, now, cap, expected) in SEQUENCES.items():
            with self.subTest(name=name):
                rejected, seq = set(), []
                while True:
                    r = choose(self.products, criteria, rejected, TODAY, now, max_total=cap)
                    if not isinstance(r, Choice):
                        break
                    seq.append(r.product.id)
                    rejected.add(r.product.id)
                self.assertEqual(" ".join(seq), expected)
                self.assertEqual(r, NoChoice("rejected"))

    def test_hard_filters_still_name_themselves(self):
        """Sulle fixture; tutti gli otto nomi hanno anche un caso sintetico in `test_chooser`."""
        cases = [(Criteria("padel", pax=2, period=Period(date(2030, 1, 1), date(2030, 1, 31), "x")),
                  None, "dates"),
                 (Criteria("golf", pax=2), None, "sport"),
                 (Criteria("padel", pax=2), Decimal("1"), "price")]
        for criteria, cap, failed in cases:
            with self.subTest(failed=failed):
                self.assertEqual(choose(self.products, criteria, set(), TODAY, NOW, max_total=cap),
                                 NoChoice(failed))


class CheapestTotalTest(unittest.TestCase):
    """RF-69, regola 4: totale del prodotto compatibile più economico, filtri duri senza budget."""

    def test_cheapest_compatible_total(self):
        products = [make_product(1, price=500), make_product(2, price=400)]
        self.assertEqual(cheapest_total(products, Criteria("padel", pax=3), TODAY, NOW),
                         Decimal("1200"))

    def test_budget_and_area_do_not_filter(self):
        products = [make_product(1, price=400, country="IT", destination="Roma")]
        c = Criteria("padel", geo.find_area("Spagna"), pax=3, budget=Decimal("10"))
        self.assertEqual(cheapest_total(products, c, TODAY, NOW), Decimal("1200"))

    def test_hard_filters_apply(self):
        cheap = dict(price=100)
        products = [make_product(1, archived=True, **cheap),
                    make_product(2, bookable=False, **cheap),
                    make_product(3, sport="tennis", **cheap),
                    make_product(4, windows=(("2026-12-01", "2026-12-04"),), **cheap),
                    make_product(5, max_pax=2, **cheap),
                    make_product(6, price=400)]
        c = Criteria("padel", period=OCT, pax=3)
        self.assertEqual(cheapest_total(products, c, TODAY, NOW), Decimal("1200"))

    def test_nothing_compatible(self):
        self.assertIsNone(cheapest_total([make_product(1, sport="tennis")], Criteria("padel", pax=2),
                                         TODAY, NOW))

    def test_same_candidates_as_choose_on_the_fixtures(self):
        products = catalog()
        for name, (criteria, now, _, _) in SEQUENCES.items():
            with self.subTest(name=name):
                rejected, totals = set(), []
                while isinstance(r := choose(products, criteria, rejected, TODAY, now), Choice):
                    totals.append(r.product.price * criteria.pax)
                    rejected.add(r.product.id)
                self.assertEqual(cheapest_total(products, criteria, TODAY, now), min(totals))
