"""Casi d'uso del contratto agente-tool (docs/usecases/agente-tool.md, UC1-UC9, RF-52..55)."""
import unittest

from support import StubPayments, FakeHofJ, assert_single_product, make_product
from test_usecases import Clock
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain.intent import QUESTION_SPORT
from vela.domain.models import (IntentCreated, IntentQuestion, NoMatch, ProposalMade,
                                StructuredFields)
from vela.domain.usecases import Vela


class FakeExtractor:
    """Fallback finto: nessuna chiamata ad Anthropic."""

    def __init__(self, result=None):
        self.result, self.calls = result, []

    def extract(self, text, today):
        self.calls.append(text)
        return self.result


CATALOG = [
    make_product(1, price=300, destination="Siviglia"),
    make_product(2, price=450, destination="Madrid"),
    make_product(3, price=400, sport="tennis", country="IT", destination="Roma",
                 title="Tennis a Roma 3"),
    make_product(4, price=350, country="IT", destination="Riccione"),
]


def make_vela(products=CATALOG, extractor=None):
    repos = MemoryRepositories()
    repos.products.upsert_many(products)
    ids = iter("id%d" % i for i in range(1, 100))
    return Vela(repos, FakeHofJ(), StubPayments(), now=Clock(), new_id=lambda: next(ids),
                extractor=extractor)


PADEL_SPAIN = "Un weekend di padel in Spagna a ottobre, siamo in due"


def propose(vela, text=PADEL_SPAIN, fields=None):
    intent = vela.create_intent(text, fields=fields)
    return intent, vela.get_proposal(intent.intent_id)


class UC1CompleteRequestTest(unittest.TestCase):
    def test_fields_and_text_agree(self):
        fx = FakeExtractor()
        vela = make_vela(extractor=fx)
        text = "Un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"
        fields = StructuredFields(sport="padel", area="Spagna", period_start="2026-10-01",
                                  period_end="2026-10-31", pax=2, budget=800)
        with self.assertNoLogs("vela.domain.usecases", "INFO"):
            r = vela.create_intent(text, fields=fields)
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(fx.calls, [])
        c = vela.repos.intents.get(r.intent_id).criteria
        self.assertEqual((c.sport, c.area.name, c.pax, str(c.budget)), ("padel", "Spagna", 2, "800.00"))
        self.assertTrue(r.say.startswith("Ho capito: un viaggio di padel in Spagna"))
        for piece in ("2 persone", "800 euro", "Cerco la proposta giusta."):
            self.assertIn(piece, r.say)
        assert_single_product(self, r.to_dict())


class UC2SportNotSaidTest(unittest.TestCase):
    TEXT = "Trovami qualcosa per il ponte dell'8 dicembre, siamo in due."

    def test_without_sport_asks_and_saves_nothing(self):
        fx = FakeExtractor({"sport": None})
        vela = make_vela(extractor=fx)
        r = vela.create_intent(self.TEXT, fields=StructuredFields(
            period_start="2026-12-05", period_end="2026-12-08", pax=2))
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual((r.question, r.say), (QUESTION_SPORT, QUESTION_SPORT))
        self.assertEqual(len(fx.calls), 1)
        self.assertIsNone(vela.repos.intents.get("id1"))

    def test_answer_creates_the_intent(self):
        vela = make_vela()
        r = vela.create_intent(self.TEXT + " Tennis.", fields=StructuredFields(
            sport="tennis", period_start="2026-12-05", period_end="2026-12-08", pax=2))
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(r.criteria.sport, "tennis")
        self.assertIn("un viaggio di tennis tra il 5 dicembre 2026 e l'8 dicembre 2026", r.say)


class UC3AnySportTest(unittest.TestCase):
    def test_any_from_field_means_no_sport_filter(self):
        vela = make_vela(products=[CATALOG[2]])   # solo tennis
        intent, proposal = propose(vela, "Padel o tennis? Indifferente, siamo in due",
                                   StructuredFields(sport="any"))
        self.assertEqual(vela.repos.intents.get(intent.intent_id).criteria.sport, "any")
        self.assertIn("padel o tennis", intent.say)
        self.assertIsInstance(proposal, ProposalMade)
        self.assertEqual(proposal.product.product_id, "3")

    def test_any_from_text_only(self):
        r = make_vela().create_intent("padel e tennis a novembre, siamo in due")
        self.assertEqual(r.criteria.sport, "any")
        self.assertEqual(r.to_dict()["criteria"]["sport"], "any")


class UC4TooHotTest(unittest.TestCase):
    REASON = "Troppo caldo, vorrei un posto più fresco"

    def check_moves_north(self, fields):
        vela = make_vela()
        intent, first = propose(vela)
        self.assertEqual(first.product.destination, "Siviglia")
        r = vela.reject_proposal(first.proposal.id, self.REASON, fields=fields)
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(r.proposal.intent_id, intent.intent_id)
        self.assertNotEqual(r.product.product_id, first.product.product_id)
        self.assertEqual(r.product.destination, "Madrid")
        self.assertEqual(len(vela.repos.rejections.list_for_intent(intent.intent_id)), 1)
        self.assertIn("Ho capito: un viaggio di padel a Madrid", r.say)
        self.assertIn("Ti propongo", r.say)
        assert_single_product(self, r.to_dict())

    def test_direction_field(self):
        self.check_moves_north(StructuredFields(direction="north"))

    def test_text_only_client(self):
        self.check_moves_north(None)


class UC5ChangeSportTest(unittest.TestCase):
    def test_reject_with_sport_field(self):
        vela = make_vela()
        intent, first = propose(vela)
        r = vela.reject_proposal(first.proposal.id, "Preferisco il tennis",
                                 fields=StructuredFields(sport="tennis"))
        self.assertEqual(r.proposal.intent_id, intent.intent_id)
        self.assertEqual(r.product.product_id, "3")
        self.assertEqual(vela.repos.intents.get(intent.intent_id).criteria.sport, "tennis")
        self.assertIn("un viaggio di tennis", r.say)


class UC6UntranslatableReasonTest(unittest.TestCase):
    def test_only_the_rejected_product_is_excluded(self):
        vela = make_vela()
        intent, first = propose(vela)
        before = vela.repos.intents.get(intent.intent_id).criteria
        # M21-F: senza tipo "hotel con la spa" è un rifiuto `hotel` (RF-72); la frase di RF-54 resta
        # per `reject_kind="other"` esplicito
        r = vela.reject_proposal(first.proposal.id, "Voglio un hotel con la spa",
                                 StructuredFields(reject_kind="other"))
        self.assertEqual(vela.repos.intents.get(intent.intent_id).criteria, before)
        self.assertNotEqual(r.product.product_id, first.product.product_id)
        self.assertTrue(r.say.startswith("Non so scegliere in base a questo"))
        self.assertIn("Ho capito:", r.say)

    def test_empty_reason_is_not_untranslatable(self):
        vela = make_vela()
        _, first = propose(vela)
        r = vela.reject_proposal(first.proposal.id, "", StructuredFields(reject_kind="other"))
        self.assertIsInstance(r, ProposalMade)
        self.assertNotIn("Non so scegliere", r.say)


class UC7InvalidFieldTest(unittest.TestCase):
    def test_unknown_area_is_discarded_and_invented_budget_is_repeated(self):
        vela = make_vela()
        r = vela.create_intent("Padel a Atlantide, siamo in tre.", fields=StructuredFields(
            sport="padel", area="Atlantide", pax=3, rooms=2, budget=1000))
        self.assertIsInstance(r, IntentCreated)
        self.assertIsNone(r.criteria.area)
        self.assertTrue(r.say.startswith("Non conosco il luogo Atlantide."))
        # M21-E: la lettura del budget (RF-70); 1000 copre il più economico (300 × 3), quindi in tutto
        self.assertIn("un viaggio di padel per 3 persone in 2 camere con un budget di 1000 euro in tutto",
                      r.say)

    def test_discarded_field_before_the_question(self):
        r = make_vela().create_intent("una vacanza per due", fields=StructuredFields(sport="golf"))
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.question, QUESTION_SPORT)
        self.assertEqual(r.say, "Lo sport golf non lo tratto: solo padel o tennis. Padel o tennis?")

    def test_invalid_direction_on_reject_is_declared(self):
        vela = make_vela()
        _, first = propose(vela)
        r = vela.reject_proposal(first.proposal.id, "", fields=StructuredFields(direction="east"))
        self.assertTrue(r.say.startswith("Non so spostare la ricerca verso east."))
        # M21-F: la direzione scartata non dice cosa non va → domanda di RF-75, dopo lo scarto
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.say, "Non so spostare la ricerca verso east. Cosa non ti convince: il posto, "
                                "l'hotel, le date o il prezzo?")


class UC8ConflictTest(unittest.TestCase):
    def test_field_wins_and_conflict_is_logged(self):
        vela = make_vela()
        with self.assertLogs("vela.domain.usecases", "INFO") as logs:
            r = vela.create_intent("Tennis a Roma a maggio, siamo in due",
                                   fields=StructuredFields(sport="padel"))
        self.assertEqual(r.criteria.sport, "padel")
        self.assertIn("un viaggio di padel", r.say)
        line = "\n".join(logs.output)
        for piece in (r.intent_id, "sport", "tennis", "padel"):
            self.assertIn(piece, line)
        self.assertNotIn("Roma a maggio", line)   # il testo dell'intento non va nei log

    def test_area_and_direction_conflict_on_reject_is_logged(self):
        vela = make_vela()
        intent, first = propose(vela)
        with self.assertLogs("vela.domain.usecases", "INFO") as logs:
            r = vela.reject_proposal(first.proposal.id, "più fresco",
                                     fields=StructuredFields(area="Italia", direction="north"))
        self.assertEqual(vela.repos.intents.get(intent.intent_id).criteria.area.name, "Italia")
        self.assertIsInstance(r, ProposalMade)
        self.assertIn("area", "\n".join(logs.output))


class UC9TextOnlyClientTest(unittest.TestCase):
    def test_question_then_intent(self):
        fx = FakeExtractor({"sport": None, "area": None})
        vela = make_vela(extractor=fx)
        r = vela.create_intent("Vorrei una vacanza a Maiorca a giugno per due")
        self.assertIsInstance(r, IntentQuestion)
        self.assertEqual(r.question, QUESTION_SPORT)
        self.assertEqual(len(fx.calls), 1)
        self.assertIsNone(vela.repos.intents.get("id1"))
        r = vela.create_intent("Vorrei una vacanza a Maiorca a giugno per due. Padel.")
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(r.criteria.sport, "padel")


class NoMatchAfterRejectionTest(unittest.TestCase):
    """RF-55: il no_match di un rifiuto riporta la proposta da cui ripartire."""

    def test_second_reject_on_the_same_proposal(self):
        vela = make_vela(products=[CATALOG[0], CATALOG[2]])   # un padel in Spagna, un tennis
        intent, first = propose(vela)
        nomatch = vela.reject_proposal(first.proposal.id, "no", StructuredFields(reject_kind="other"))
        self.assertIsInstance(nomatch, NoMatch)
        self.assertEqual(nomatch.rejected_proposal_id, first.proposal.id)
        self.assertEqual(nomatch.to_dict()["rejected_proposal_id"], first.proposal.id)
        self.assertIn("Ho capito:", nomatch.say)
        r = vela.reject_proposal(first.proposal.id, "Preferisco il tennis",
                                 fields=StructuredFields(sport="tennis"))
        self.assertIsInstance(r, ProposalMade)
        self.assertEqual(r.product.product_id, "3")
        self.assertEqual(r.proposal.intent_id, intent.intent_id)
        self.assertEqual(len(vela.repos.rejections.list_for_intent(intent.intent_id)), 1)

    def test_get_proposal_no_match_has_no_rejected_proposal_id(self):
        vela = make_vela(products=[CATALOG[2]])
        _, r = propose(vela)
        self.assertIsInstance(r, NoMatch)
        self.assertNotIn("rejected_proposal_id", r.to_dict())


if __name__ == "__main__":
    unittest.main()
