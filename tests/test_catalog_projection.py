"""Proiezione del dettaglio HofJ nel formato del catalogo (fixture e sync, M1 e M10)."""
import unittest

from hofj_samples import detail_of, item
from vela.domain import catalog as cat


class StripMediaTest(unittest.TestCase):
    def test_removes_media_keys_at_any_depth_without_touching_input(self):
        detail = detail_of(item(12))
        out = cat.strip_media(detail)
        for key in ("gallery", "image", "travelProgram"):
            self.assertNotIn(key, out)
        self.assertNotIn("gallery", out["rawAttributes"])
        self.assertNotIn("cover", out["rawAttributes"])
        hotel = out["rawAttributes"]["hotels"]["data"][0]["attributes"]
        self.assertEqual(hotel, {"name": "Hotel Uno"})
        self.assertEqual(out["venue"]["coverUrl"], "https://x/v.jpg")  # una stringa URL resta
        self.assertEqual(out["rawAttributes"]["playtomicLevel"], "3")
        self.assertIn("gallery", detail)  # l'originale non viene modificato

    def test_scalars_and_lists_pass_through(self):
        self.assertEqual(cat.strip_media([1, {"gallery": 1, "a": 2}]), [1, {"a": 2}])
        self.assertIsNone(cat.strip_media(None))


class ProjectDetailTest(unittest.TestCase):
    def test_keeps_rf28_fields_with_api_names(self):
        catalog = cat.project_detail(detail_of(item(12)))
        self.assertEqual(sorted(catalog), sorted([
            "id", "title", "slug", "shortDescription", "price", "currency", "minPax", "maxPax",
            "minDate", "maxDate", "availabilities", "defaultDurationInDays", "updatedAt",
            "category", "venue", "destination", "hotels", "featured", "isSpecialOffer",
            "maxPaxPerRoom", "vela_levels", "vela_levels_exclusive", "vela_coaching"]))
        self.assertEqual(catalog["category"]["slug"], "padel")
        self.assertEqual(catalog["destination"]["geohierarchy"], "IT_123")
        self.assertEqual(catalog["hotels"]["data"][0]["attributes"], {"name": "Hotel Uno"})
        self.assertEqual(catalog["price"], 340)

    def test_keeps_featured_and_special_offer_flags(self):
        """M21-B (RF-60): le due etichette del sync passano dalla proiezione."""
        catalog = cat.project_detail(detail_of(item(12, featured=True, isSpecialOffer=True)))
        self.assertEqual((catalog["featured"], catalog["isSpecialOffer"]), (True, True))

    def test_keeps_max_pax_per_room(self):
        """M21-D (RF-66): il limite per camera del dettaglio passa dalla proiezione."""
        catalog = cat.project_detail(detail_of(item(12, maxPaxPerRoom=2)))
        self.assertEqual(catalog["maxPaxPerRoom"], 2)

    def test_computes_level_and_coaching_labels_from_the_descriptions(self):
        """M21-C (RF-63): le tre etichette di Vela, calcolate da `description` e
        `shortDescription` con `labels_of`; il prefisso `vela_` le separa dai campi dell'API."""
        catalog = cat.project_detail(detail_of(item(
            12, description="Per **giocatori di livello intermedio e avanzato**, con coach.",
            shortDescription="Solo per avanzati")))
        self.assertEqual((catalog["vela_levels"], catalog["vela_levels_exclusive"],
                          catalog["vela_coaching"]), (["advanced"], True, True))
        catalog = cat.project_detail(detail_of(item(12, description="Mare e sole.")))
        self.assertEqual((catalog["vela_levels"], catalog["vela_levels_exclusive"],
                          catalog["vela_coaching"]), ([], False, False))

    def test_missing_fields_become_none(self):
        catalog = cat.project_detail({"id": "1"})
        self.assertIsNone(catalog["venue"])
        self.assertIsNone(catalog["hotels"])
        self.assertIsNone(catalog["price"])
        self.assertIsNone(catalog["featured"])
        self.assertIsNone(catalog["maxPaxPerRoom"])
        self.assertEqual((catalog["vela_levels"], catalog["vela_levels_exclusive"],
                          catalog["vela_coaching"]), ([], False, False))   # nessun testo
