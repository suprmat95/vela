"""Fixture del catalogo di staging (M7) e scenari dei criteri 1, 3 e 4 su di essa.

`fixtures/catalog-staging.json` è registrata su HofJ staging in `en`, senza prodotto trappola: il
criterio 4 è stato eseguito il 2026-09-26 e la trappola, che dopo "troppo caro" compariva anche su
intenti non su Firenze, è stata tolta (decisione M7). Gli scenari usano le frasi di
`scripts/rest_flow.py` e il dominio vero con repository in memoria, alla data della
registrazione: gli id attesi valgono per la fixture del 2026-09-25 e vanno rivisti se la si
rigenera.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from vela.adapters.hofj_replay import ReplayHofJ
from vela.adapters.repo_memory import MemoryRepositories
from vela.adapters.stripe_fake import FakePayments
from vela.config import DEFAULT_TRAVELER
from vela.domain.catalog import select_fixtures
from vela.domain.models import NoMatch, ProposalMade
from vela.domain.usecases import Vela

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import rest_flow  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
FIXTURE = os.path.join(FIXTURES, "catalog-staging.json")
STAGING = "https://staging.api.hofj.com"
RECORDED = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
TRAP = "900078"


def vela_on_staging():
    repos = MemoryRepositories()
    repos.products.upsert_many(ReplayHofJ(FIXTURE).load_catalog())
    return Vela(repos, ReplayHofJ(), FakePayments("http://test"), DEFAULT_TRAVELER, now=lambda: RECORDED)


@unittest.skipUnless(os.path.exists(FIXTURE), "fixtures/catalog-staging.json assente")
class StagingFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.catalog = json.load(fh)

    def test_recorded_on_staging_in_english_for_the_staging_brand(self):
        self.assertEqual((self.catalog["base_url"], self.catalog["locale"], self.catalog["brand"],
                          self.catalog["sport"]),
                         (STAGING, "en", "staging.weebora.com", "padel"))

    def test_live_on_staging_selects_it_and_production_keeps_the_m1_fixture(self):
        staging = [os.path.basename(p) for p in select_fixtures(FIXTURES, STAGING)]
        production = [os.path.basename(p) for p in select_fixtures(FIXTURES, "https://api.hofj.com")]
        self.assertIn("catalog-staging.json", staging)
        self.assertNotIn("catalog.json", staging)
        self.assertIn("catalog.json", production)

    def test_no_trap_product(self):
        self.assertEqual([p["id"] for p in self.catalog["products"] if p.get("vela_trap")], [])
        self.assertNotIn(TRAP, self.catalog["details"])

    def test_every_active_product_has_a_detail(self):
        active = sorted(p["id"] for p in self.catalog["products"] if not p["archived"])
        self.assertEqual(active, sorted(self.catalog["details"]))


@unittest.skipUnless(os.path.exists(FIXTURE), "fixtures/catalog-staging.json assente")
class CriteriaScenarioTest(unittest.TestCase):
    def test_flow_intent_then_too_expensive_gives_a_cheaper_single_proposal(self):
        """Criteri 1 e 3: Bela Padel a Barcellona (1390 €), poi Tarragona (720 €), dichiarata in
        Catalogna. La frase di §10.1 (Spagna) portava al 867, che su staging ha un errore di
        configurazione HofJ (decisione M7)."""
        vela = vela_on_staging()
        iid = vela.create_intent(rest_flow.INTENT_FLOW).intent_id
        first = vela.get_proposal(iid)
        self.assertEqual((first.product.product_id, first.proposal.total_from), ("158", Decimal("1390")))
        second = vela.reject_proposal(first.proposal.id, rest_flow.REASON)
        self.assertIsInstance(second, ProposalMade)
        self.assertEqual((second.product.product_id, second.proposal.total_from), ("115", Decimal("720")))
        self.assertIn("Catalogna", second.proposal.reason)

    def test_flow_intent_never_reaches_the_misconfigured_867(self):
        vela = vela_on_staging()
        iid = vela.create_intent(rest_flow.INTENT_FLOW).intent_id
        r = vela.get_proposal(iid)
        seen = []
        while isinstance(r, ProposalMade) and len(seen) < 3:
            seen.append(r.product.product_id)
            r = vela.reject_proposal(r.proposal.id, rest_flow.REASON)
        self.assertEqual(seen, ["158", "115", "28"])

    def test_florence_intent_proposes_the_real_product_78(self):
        vela = vela_on_staging()
        first = vela.get_proposal(vela.create_intent(rest_flow.INTENT_TRAP).intent_id)
        self.assertEqual(first.product.product_id, "78")

    def test_spain_phrase_of_section_10_1_ends_with_nothing_cheaper(self):
        """La frase originale di §10.1 su staging: 28 (398 €), 867 (200 €), poi `price`."""
        vela = vela_on_staging()
        iid = vela.create_intent("un weekend di padel in Spagna a ottobre, siamo in due, "
                                 "massimo 800 euro").intent_id
        r = vela.get_proposal(iid)
        seen = []
        while isinstance(r, ProposalMade):
            seen.append(r.product.product_id)
            r = vela.reject_proposal(r.proposal.id, rest_flow.REASON)
        self.assertEqual(seen, ["28", "867"])
        self.assertIsInstance(r, NoMatch)
        self.assertEqual(r.failed_criterion, "price")


if __name__ == "__main__":
    unittest.main()
