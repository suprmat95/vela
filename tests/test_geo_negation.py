"""M21-F (RF-73): luoghi negati nel testo e Marbella nel dizionario `geo`."""
import unittest

from vela.domain import geo
from vela.domain.models import Area

ESTEPONA = Area("city", "Estepona", "ES")
SPAIN = Area("country", "Spagna", "ES")
MARBELLA = Area("city", "Marbella", "ES")


class FindPlacesTest(unittest.TestCase):
    CASES = [
        ("Estepona no, ma la Spagna va bene", [(ESTEPONA, True), (SPAIN, False)]),
        ("non a Estepona", [(ESTEPONA, True)]),
        ("ovunque tranne Estepona", [(ESTEPONA, True)]),
        ("tutto eccetto Estepona", [(ESTEPONA, True)]),
        ("niente Estepona, grazie", [(ESTEPONA, True)]),
        ("Estepona non mi piace", [(ESTEPONA, True)]),
        ("no alle Canarie", [(Area("region", "Canarie", "ES"), True)]),
        ("not Estepona, Spain is fine", [(ESTEPONA, True), (SPAIN, False)]),
        ("anywhere but Estepona", [(ESTEPONA, True)]),
        ("except Mallorca", [(Area("region", "Maiorca", "ES"), True)]),
        ("Marbella no", [(MARBELLA, True)]),
        ("vorrei andare a Valencia", [(Area("city", "Valencia", "ES"), False)]),
        ("a Palma de Mallorca", [(Area("city", "Palma de Mallorca", "ES"), False)]),
        ("troppo caro", []),
    ]

    def test_table(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(geo.find_places(text), expected)

    def test_negated_and_new_area(self):
        self.assertEqual(geo.negated_places("Estepona no, ma la Spagna va bene"), [ESTEPONA])
        self.assertEqual(geo.find_area_not_negated("Estepona no, ma la Spagna va bene"), SPAIN)
        self.assertIsNone(geo.find_area_not_negated("Estepona no"))
        self.assertEqual(geo.find_area_not_negated("in Portogallo? no, a Valencia"),
                         Area("city", "Valencia", "ES"))


class MarbellaTest(unittest.TestCase):
    def test_marbella_is_on_the_costa_del_sol(self):
        self.assertEqual(geo.find_area("padel a Marbella"), MARBELLA)
        self.assertEqual([a.name for a in geo.ancestors(MARBELLA)],
                         ["Marbella", "Costa del Sol", "Andalusia", "Spagna"])
        self.assertEqual(geo.move(MARBELLA, "north"), geo.area_by_name("Madrid"))
        self.assertEqual(geo.where(MARBELLA), "a Marbella")


if __name__ == "__main__":
    unittest.main()
