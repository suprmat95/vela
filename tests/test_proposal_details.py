"""RF-83: programma e dettagli del pacchetto proposto, dal `raw` salvato dal sync."""
import unittest
from dataclasses import replace

from support import FakeHofJ, StubPayments, assert_single_product, make_product
from test_mcp_tools import McpCase
from test_rest import AUTH, make_client, new_intent
from vela.adapters.repo_memory import MemoryRepositories
from vela.domain import say
from vela.domain.details import blocks_text, details_of
from vela.domain.usecases import NotFound, Vela

PROGRAM = {
    "id": "733", "description": "Tre giorni di **padel** e mare.",
    "details": [{"id": "1", "title": "Programma", "days": [
        {"id": "d1", "title": "Giorno 1 - Arrivo", "description": "Check-in in hotel.",
         "events": [{"id": "e1", "time": "18:00", "text": "Benvenuto al club"},
                    {"id": "e2", "text": "  "}]},
        {"id": "d2", "title": "Giorno 2", "events": [{"id": "e3", "time": None, "text": "Clinic"}]},
    ]}, {"id": "2", "title": "Vuota", "days": []}],
}
RAW = {
    "description": "Un weekend **intenso**.\n",
    "travelProgram": PROGRAM,
    "venue": {"id": "492", "title": "TocaHub Lanzarote", "shortDescription": "8 campi panoramici"},
    "rawAttributes": {
        "hotels": {"data": [{"id": 5, "attributes": {
            "name": "THB Lanzarote Beach ", "stars": None, "address": None,
            "description": [{"type": "paragraph", "children": [{"type": "text", "text": "Hotel 4 stelle"},
                                                               {"type": "text", "text": " sul mare."}]},
                            {"type": "paragraph", "children": [{"type": "text", "text": "Piscina."}]}],
            "location": {"description": "Plaza Janubio, 2, Costa Teguise "}}}]},
        "playingHours": "six_or_plus", "style": ["tactics", "gameplay"], "goal": ["improve"],
        "bestForLevel": ["intermediate"], "whyThisTrip": None, "acceptsCompanions": False,
    },
}


class DetailsOfTest(unittest.TestCase):
    def test_reads_program_hotel_venue_and_play_fields(self):
        d = details_of(RAW)
        self.assertEqual(d["description"], "Un weekend **intenso**.")
        self.assertEqual(d["program"], {"description": "Tre giorni di **padel** e mare.", "sections": [
            {"title": "Programma", "days": [
                {"title": "Giorno 1 - Arrivo", "description": "Check-in in hotel.",
                 "events": [{"time": "18:00", "text": "Benvenuto al club"}]},
                {"title": "Giorno 2", "description": None, "events": [{"time": None, "text": "Clinic"}]},
            ]}]})
        self.assertEqual(d["hotel"], {"name": "THB Lanzarote Beach", "stars": None,
                                      "description": "Hotel 4 stelle sul mare.\n\nPiscina.",
                                      "address": "Plaza Janubio, 2, Costa Teguise"})
        self.assertEqual(d["venue"], {"name": "TocaHub Lanzarote", "description": "8 campi panoramici"})
        self.assertEqual((d["playing_hours"], d["style"], d["goal"], d["best_for_level"]),
                         ("six_or_plus", ["tactics", "gameplay"], ["improve"], ["intermediate"]))
        self.assertIsNone(d["why_this_trip"])
        self.assertIs(d["accepts_companions"], False)

    def test_empty_raw_gives_empty_fields(self):
        self.assertEqual(details_of({}), {
            "description": None, "why_this_trip": None, "program": None, "hotel": None,
            "venue": None, "playing_hours": None, "style": [], "goal": [], "best_for_level": [],
            "accepts_companions": None})

    def test_program_without_description_nor_days_is_none(self):
        self.assertIsNone(details_of({"travelProgram": {"id": "1", "description": " ", "details": []}})["program"])
        self.assertIsNone(details_of({"travelProgram": None})["program"])

    def test_blocks_text_accepts_a_plain_string(self):
        self.assertEqual(blocks_text(" testo "), "testo")
        self.assertIsNone(blocks_text(42))

    def test_recorded_fixture_has_hotel_and_venue_but_no_program(self):
        """Le fixture registrate prima di RF-83 non hanno `travelProgram` (docs/fixtures.md)."""
        from vela.adapters.hofj_replay import ReplayHofJ
        product = next(p for p in ReplayHofJ().load_catalog() if p.id == "181")
        d = details_of(product.raw)
        self.assertIsNone(d["program"])
        self.assertEqual(d["hotel"]["name"], "THB Lanzarote Beach")
        self.assertTrue(d["hotel"]["description"].startswith("Il THB Lanzarote Beach"))
        self.assertEqual(d["venue"]["name"], "TocaHub Lanzarote")


def vela_with(raw, text="un weekend di padel in Spagna a ottobre, siamo in due"):
    repos = MemoryRepositories()
    repos.products.upsert_many([replace(make_product(1, destination="Lanzarote"), raw=raw)])
    vela = Vela(repos, FakeHofJ(), StubPayments())
    intent = vela.create_intent(text)
    return vela, vela.get_proposal(intent.intent_id)


class UseCaseTest(unittest.TestCase):
    def test_returns_the_details_of_the_proposed_product(self):
        vela, made = vela_with(RAW)
        result = vela.get_proposal_details(made.proposal.id)
        d = result.to_dict()
        assert_single_product(self, d)
        self.assertEqual((d["proposal_id"], d["product"]["product_id"]), (made.proposal.id, "1"))
        self.assertEqual(d["program"]["sections"][0]["days"][0]["title"], "Giorno 1 - Arrivo")
        self.assertEqual(d["say"], say.say_details(made.product, True))
        self.assertIn("programma giorno per giorno", d["say"])

    def test_without_program_the_say_tells_so(self):
        vela, made = vela_with({})
        d = vela.get_proposal_details(made.proposal.id).to_dict()
        self.assertIsNone(d["program"])
        self.assertIn("non c'è", d["say"])

    def test_english_intent_gets_an_english_say(self):
        vela, made = vela_with(RAW, "a padel weekend in Spain in October for two")
        self.assertTrue(vela.get_proposal_details(made.proposal.id).say.startswith("Here are the details"))

    def test_changes_nothing(self):
        vela, made = vela_with(RAW)
        vela.get_proposal_details(made.proposal.id)
        self.assertEqual(vela.get_proposal(made.proposal.intent_id).proposal.id, made.proposal.id)
        self.assertIsNone(vela.repos.orders.get_by_proposal(made.proposal.id))

    def test_unknown_proposal(self):
        vela, _ = vela_with(RAW)
        with self.assertRaises(NotFound):
            vela.get_proposal_details("nope")


class McpTest(McpCase):
    async def test_tool_returns_the_details(self):
        intent = await self.ok("create_intent", text="un weekend di padel in Spagna a ottobre, siamo in due")
        made = await self.ok("get_proposal", intent_id=intent["intent_id"])
        d = await self.ok("get_proposal_details", proposal_id=made["proposal_id"])
        self.assertEqual(d["product"], made["product"])
        self.assertIn("program", d)

    async def test_unknown_proposal_is_a_readable_error(self):
        self.assertEqual(await self.error_text("get_proposal_details", proposal_id="nope"),
                         say.say_not_found("proposal"))


class RestTest(unittest.TestCase):
    def test_details_endpoint(self):
        c, _ = make_client()
        intent = new_intent(c)
        made = c.get("/v1/intents/%s/proposal" % intent["intent_id"], headers=AUTH).json()
        r = c.get("/v1/proposals/%s/details" % made["proposal_id"], headers=AUTH)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        assert_single_product(self, body)
        self.assertEqual((body["outcome"], body["product"]), ("proposal_details", made["product"]))
        self.assertIsNotNone(body["venue"])

    def test_unknown_proposal_is_404(self):
        c, _ = make_client()
        r = c.get("/v1/proposals/nope/details", headers=AUTH)
        self.assertEqual(r.status_code, 404)

    def test_needs_the_token(self):
        c, _ = make_client()
        self.assertEqual(c.get("/v1/proposals/nope/details").status_code, 401)


if __name__ == "__main__":
    unittest.main()
