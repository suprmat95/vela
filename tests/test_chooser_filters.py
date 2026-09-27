"""M21-E: `choose` e `cheapest_total` condividono i filtri duri. Le sequenze sotto sono
registrate sulle fixture `catalog.json` e `catalog-tennis.json`: rifiutando ogni volta la scelta
si ottiene tutto l'elenco dei candidati filtrati e ordinati. Se un filtro o l'ordinamento
cambiasse anche un solo candidato o l'ordine, la sequenza cambierebbe. Registrate con il chooser
v2 (commit 4b5881b) e ri-registrate in M21-B con l'ordinamento v3 di RF-60 (stessi insiemi di
prodotti, ordine per partenza, `featured`, prezzo, id numerico); elencate in `docs/decisions.md`.
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
        "1023 257 1027 1078 239 181 186 256 1013 910 426 648 250 308 273 995 218 235 230 270 "
        "999 302 896 886 1009 207 645 342 443 278 688 766 201 210 229 244 190 330 751 940 "
        "663 197 296 217 221 948 1071 985 1051 925 944 457 969 1043 454 291"),
    "tennis 3 persone": (
        Criteria("tennis", None, None, 3), NOW, None,
        "363 1044 931 369 988 707 523 716 608 1003 373 430 626 1020 506 1037 710 855 955 826 "
        "860 695 854 960 1034 1087 378 970 1042 372 697 1031 959 1075 894 893"),
    "any dicembre 1, weekend": (
        Criteria("any", None, DEC, 1, duration_min_nights=1, duration_max_nights=3), NOW, None,
        "239 688 201 181 278 1013 1003 1009 1071 308 273 995 1075 1059 1065 207 988 645 186 "
        "256 766 663 426 235 1020 1037 959 964 569 244 443 270 697 221 710 999 302 210 624 "
        "763 748 1055"),
    "padel Italia 5, tetto 2000": (
        Criteria("padel", geo.find_area("Italia"), None, 5, Decimal("3000")), NOW, Decimal("2000"),
        "688 766 210 229 244 190 201 1023 257 1027 1078 1059 1065"),
    "padel 2 senza now": (
        Criteria("padel", None, None, 2), None, None,
        "330 181 186 256 688 766 210 229 244 201 296 250 1051 751 940 995 1071 1013 308 273 "
        "1009 663 482 426 197 622 218 235 239 230 270 190 217 221 999 302 838 1023 910 648 "
        "257 1027 896 886 948 207 645 985 342 443 278 1078 925 944 457 969 1043 454 291 393 "
        "964 569 1059 1065 624 763 748 1055 1090 1093"),

}


def catalog():
    return (load_fixture(os.path.join(FIXTURES, "catalog.json"), NOW)
            + load_fixture(os.path.join(FIXTURES, "catalog-tennis.json"), NOW))


class ChooseUnchangedTest(unittest.TestCase):
    """Filtri e ordinamento v3 fissati sulle fixture: nessuna scelta di `choose` cambia."""

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
