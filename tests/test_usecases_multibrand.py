"""Casi d'uso MB1-MB9 di `docs/usecases/multi-brand.md` (M10): catalogo di due brand in memoria.

Lo sport arriva dal testo o, per MB5, dal campo strutturato `sport="any"` di M17; MB5 si verifica
anche sul chooser con criteri senza filtro sport (`None`). La domanda "Padel o tennis?" di MB6 e
MB7 è di M17 ed è testata lì.
"""
import os
import unittest
from datetime import date

from support import NOW, TODAY, FakeHofJ, StubPayments, drain_to_link, make_product
from test_usecases import Clock
from vela.adapters.hofj_router import BrandRouter
from vela.adapters.repo_memory import MemoryRepositories
from vela.app import build_worker
from vela.config import DEFAULT_TRAVELER, Settings
from vela.domain.chooser import Choice, NoChoice, choose
from vela.domain.models import (Criteria, IntentCreated, NoMatch, OrderStatus, Participant, Period,
                                ProposalMade, StructuredFields, TravelerProfile)
from vela.domain.usecases import Vela

BRANDS = {"padel": "weebora.com", "tennis": "terrarossa.com"}
OTHER = StructuredFields(reject_kind="other")   # M21-F: "Un altro" non dice cosa non va (RF-75)
TRAVELER = TravelerProfile("Anna", "Rossi", "anna@x.it", "+390000", participants=(Participant("Bo", "Bi"),))
MAY = (("2027-05-14", "2027-05-17"),)
JUNE = (("2027-06-11", "2027-06-14"),)
OCTOBER = (("2026-10-09", "2026-10-12"),)
NOVEMBER = (("2026-11-13", "2026-11-16"),)


def padel(pid, **kw):
    return make_product(pid, sport="padel", brand="weebora.com", **kw)


def tennis(pid, **kw):
    kw.setdefault("title", "Tennis a %s %s" % (kw.get("destination", "Roma"), pid))
    return make_product(pid, sport="tennis", brand="terrarossa.com", **kw)


CATALOG = [
    padel(1, country="ES", destination="Valencia", windows=OCTOBER, max_date="2027-12-31"),
    padel(2, country="IT", destination="Riccione", windows=MAY + NOVEMBER, max_date="2027-12-31"),
    tennis(11, country="IT", destination="Roma", windows=MAY + NOVEMBER, max_date="2027-12-31"),
    tennis(12, country="PT", destination="Lisbona", windows=JUNE, max_date="2027-12-31"),
]


class MultiBrand:
    """Vela con i due brand, un client HofJ finto per brand e il worker senza thread."""

    def __init__(self, products=CATALOG, brands=BRANDS):
        self.repos = MemoryRepositories()
        self.repos.products.upsert_many(products)
        self.clients = {brand: FakeHofJ() for brand in brands.values()}
        self.router = BrandRouter(self.clients, brands)
        ids = iter("id%d" % i for i in range(1, 200))
        self.vela = Vela(self.repos, self.router, StubPayments(), DEFAULT_TRAVELER, now=Clock(),
                         new_id=lambda: next(ids))
        self.worker = build_worker(self.vela, Settings(worker_concurrency=0), self.router)

    def propose(self, text, fields=None):
        created = self.vela.create_intent(text, TRAVELER, fields)
        assert isinstance(created, IntentCreated), created
        return self.vela.get_proposal(created.intent_id)

    def buy(self, proposal):
        """Accettazione, prezzo effettivo, conferma e link."""
        order_id = self.vela.accept_proposal(proposal.proposal.id).order_id
        drain_to_link(self.vela, self.worker, proposal.proposal.id)
        return self.vela.get_order_status(order_id)

    def product(self, proposal):
        return self.repos.products.get(proposal.proposal.product_id)

    def cart_calls(self, brand):
        """Chiamate del carrello; `/v1/quota` è per chiave, letta da un client qualsiasi."""
        return [c[0] for c in self.clients[brand].calls if c[0] != "get_quota"]


class MB1TennisTest(unittest.TestCase):
    def test_tennis_request_gets_a_terrarossa_product_and_a_terrarossa_cart(self):
        mb = MultiBrand()
        proposal = mb.propose("Un weekend di tennis in Italia a maggio, siamo in due.")
        self.assertIsInstance(proposal, ProposalMade)
        self.assertEqual((mb.product(proposal).id, mb.product(proposal).brand), ("11", "terrarossa.com"))
        self.assertEqual(mb.buy(proposal).status, OrderStatus.AWAITING_PAYMENT)
        self.assertEqual(mb.cart_calls("terrarossa.com"),
                         ["create_itinerary", "get_itinerary"])   # M19
        self.assertEqual(mb.cart_calls("weebora.com"), [])


class MB2PadelTest(unittest.TestCase):
    def test_padel_request_stays_on_weebora(self):
        mb = MultiBrand()
        proposal = mb.propose("Padel in Spagna a ottobre, siamo in due.")
        self.assertEqual((mb.product(proposal).id, mb.product(proposal).brand), ("1", "weebora.com"))
        mb.buy(proposal)
        self.assertTrue(mb.cart_calls("weebora.com"))
        self.assertEqual(mb.cart_calls("terrarossa.com"), [])


class MB3EnglishTest(unittest.TestCase):
    def test_language_does_not_choose_the_brand(self):
        mb = MultiBrand()
        proposal = mb.propose("A tennis weekend in June for two.")
        self.assertEqual(mb.product(proposal).brand, "terrarossa.com")
        self.assertEqual(proposal.proposal.product_id, "12")


class MB4SwitchSportTest(unittest.TestCase):
    def test_rejecting_padel_for_tennis_moves_to_terrarossa(self):
        mb = MultiBrand()
        first = mb.propose("Padel in Italia a novembre, siamo in due.")
        self.assertEqual(mb.product(first).brand, "weebora.com")
        second = mb.vela.reject_proposal(first.proposal.id, "Preferisco il tennis")
        self.assertIsInstance(second, ProposalMade)
        self.assertEqual((mb.product(second).id, mb.product(second).brand), ("11", "terrarossa.com"))
        mb.buy(second)
        self.assertTrue(mb.cart_calls("terrarossa.com"))
        self.assertEqual(mb.cart_calls("weebora.com"), [])


class MB5AnySportTest(unittest.TestCase):
    """`sport=any` = nessun filtro sport (M17): sul chooser con `None` e dall'agente con "any"."""

    NOVEMBER_FOR_TWO = Criteria(sport=None, period=Period(date(2026, 11, 1), date(2026, 11, 30), "novembre"),
                                pax=2)

    def test_without_sport_filter_both_brands_are_candidates(self):
        chosen, rejected = [], set()
        while True:
            result = choose(CATALOG, self.NOVEMBER_FOR_TWO, rejected, TODAY, NOW)
            if isinstance(result, NoChoice):
                break
            chosen.append(result.product.brand)
            rejected.add(result.product.id)
        self.assertEqual(sorted(chosen), ["terrarossa.com", "weebora.com"])

    def test_sport_any_from_the_agent_proposes_from_both_brands(self):
        """Con il campo strutturato di M17: `create_intent(..., sport="any")`."""
        mb = MultiBrand()
        result = mb.propose("Padel o tennis mi è indifferente, a novembre, siamo in due.",
                            StructuredFields(sport="any", period_start="2026-11-01",
                                             period_end="2026-11-30", pax=2))
        brands = []
        while isinstance(result, ProposalMade):
            brands.append(mb.product(result).brand)
            result = mb.vela.reject_proposal(result.proposal.id, "Un altro", OTHER)
        self.assertEqual(sorted(brands), ["terrarossa.com", "weebora.com"])

    def test_the_brand_of_the_chosen_product_decides_the_cart(self):
        mb = MultiBrand(products=[padel(2, country="IT", destination="Riccione", windows=NOVEMBER, price=900),
                                  tennis(11, country="IT", destination="Roma", windows=NOVEMBER, price=400)])
        result = choose(mb.repos.products.list_all(), self.NOVEMBER_FOR_TWO, set(), TODAY, NOW)
        self.assertIsInstance(result, Choice)
        self.assertEqual(result.product.brand, "terrarossa.com")
        self.assertIs(mb.router.client_for(result.product), mb.clients["terrarossa.com"])


class MB8NoProductForTheSportTest(unittest.TestCase):
    def test_tennis_brand_not_configured_gives_the_existing_sport_no_match(self):
        mb = MultiBrand(products=[p for p in CATALOG if p.sport == "padel"],
                        brands={"padel": "weebora.com"})
        result = mb.propose("Tennis a novembre, siamo in due.")
        self.assertIsInstance(result, NoMatch)
        self.assertEqual(result.failed_criterion, "sport")
        self.assertIn("tennis", result.say)

    def test_no_terrarossa_product_passing_the_filters(self):
        mb = MultiBrand()
        result = mb.propose("Tennis a gennaio, siamo in due.")
        self.assertIsInstance(result, NoMatch)
        self.assertEqual(mb.cart_calls("terrarossa.com"), [])


TENNIS_FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "catalog-tennis.json")


@unittest.skipUnless(os.path.exists(TENNIS_FIXTURE), "fixtures/catalog-tennis.json assente")
class MB9SpectatorPackagesTest(unittest.TestCase):
    """Catalogo di produzione vero (padel + tennis): a Torino ci sono solo pacchetti evento."""

    def test_tennis_in_turin_never_proposes_an_event_package(self):
        from vela.adapters.hofj_replay import ReplayHofJ
        catalog = ReplayHofJ().load_catalog()
        events = {p.id for p in catalog if p.category == "Tornei" and p.sport == "tennis"}
        self.assertTrue({"562", "779"} <= events)   # Hospitality e Watch & Play delle Finals
        mb = MultiBrand(products=catalog)
        result = mb.propose("Tennis a Torino a novembre, siamo in due.")
        seen = []
        while isinstance(result, ProposalMade):
            product = mb.product(result)
            seen.append(product.id)
            self.assertEqual((product.sport, product.brand), ("tennis", "terrarossa.com"))
            result = mb.vela.reject_proposal(result.proposal.id, "Un altro", OTHER)
        self.assertTrue(seen)                        # si propone un viaggio da giocare
        self.assertFalse(events & set(seen))
        self.assertIsInstance(result, NoMatch)


if __name__ == "__main__":
    unittest.main()
