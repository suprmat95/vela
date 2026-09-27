"""Etichette del prodotto dal testo del catalogo (RF-63, RF-64, M21-C, UC-C).

La tabella usa frasi vere delle fixture: ogni frase è cercata nel dettaglio del prodotto, così che
il test non possa inventarsi il catalogo. Le riserve esplicite non compaiono in nessuna fixture
(verificato il 2026-09-27) e sono provate su frasi scritte qui, quelle di UC-C.
"""
import json
import os
import unittest

from vela.domain.labels import (ADVANCED, ALL, BEGINNER, INTERMEDIATE, ProductLabels, _clean,
                                label_texts, labels_of, ordered)

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def details(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)["details"]


PADEL = details("catalog.json")
B, I, A = BEGINNER, INTERMEDIATE, ADVANCED

# (id, frase vera della descrizione, livelli attesi, coaching atteso)
REAL = [
    ("962", "Ti allenerai al **Bela Padel Center** con istruttori esperti. Questo viaggio per "
            "**giocatori di livello intermedio e avanzato** include la colazione", {I, A}, True),
    ("1027", "Migliora il tuo gioco sulla **Costa del Sol** con la coach Sandra Flores. Questa "
             "vacanza offre **sei ore di allenamento** e tre ore di partita. Il programma è ideale "
             "per **giocatrici di livello intermedio** e principianti.", {B, I}, True),
    ("218", "Il programma è stato progettato per offrire un'esperienza di padel completa, adatta a "
            "ogni livello di gioco", {ALL}, False),
    ("218", "che tu sia un principiante che desidera sviluppare fondamentali solidi o un giocatore "
            "esperto che mira ad affinare tattiche avanzate, le sessioni sono adattate al tuo "
            "livello", {B, A}, False),
    ("940", "Allenati con un **allenatore spagnolo residente** durante un **campo di padel di tre "
            "notti** pensato per giocatori di tutti i livelli.", {ALL}, True),
    ("622", "Oltre i campi da gioco, esplora l'**atmosfera leggendaria** di Mykonos", set(), False),
    # parole di livello che non parlano dei giocatori: nessun livello
    ("230", "combinando perfezionamento tecnico, tattica avanzata e allenamenti ad alta intensità "
            "per portare il tuo gioco a un livello superiore.", set(), True),
    ("645", "con **8 ore di campo guidate da coach esperti**. È il mix perfetto tra tecnica, "
            "intensità e spirito di competizione.", set(), True),
    ("230", "5 giorni di padel ad alto livello a Madrid", set(), False),
    ("1090", "Questo viaggio è adatto a giocatori **da principianti a intermedi**.", {B, I}, False),
]


class RealSentencesTest(unittest.TestCase):
    def test_table_of_real_catalog_sentences(self):
        for pid, sentence, levels, coaching in REAL:
            with self.subTest(pid=pid, sentence=sentence[:40]):
                raw = PADEL[pid]["raw"]
                whole = _clean("%s %s" % (raw.get("shortDescription") or "", raw.get("description") or ""))
                self.assertIn(_clean(sentence), whole)   # la frase è davvero nel catalogo
                got = label_texts(sentence, None)
                self.assertEqual((set(got.levels), got.levels_exclusive, got.coaching),
                                 (levels, False, coaching))

    def test_whole_descriptions_of_the_uc_c_products(self):
        """UC-C: 962 intermedio e avanzato, non esclusivo; 1027 principianti e intermedi; 218
        ogni livello; 940 tutti i livelli; 622 nessuna parola sul livello né sulle lezioni."""
        expected = {"962": ({I, A}, True), "1027": ({B, I}, True), "218": ({B, A, ALL}, True),
                    "940": ({ALL}, True), "622": (set(), False)}
        for pid, (levels, coaching) in expected.items():
            with self.subTest(pid):
                got = labels_of(PADEL[pid]["raw"])
                self.assertEqual((set(got.levels), got.levels_exclusive, got.coaching),
                                 (levels, False, coaching))

    def test_english_sentences_of_the_staging_catalogues(self):
        staging = details("catalog-staging.json")
        tennis = details("catalog-staging-tennis.json")
        self.assertEqual(labels_of(staging["157"]["raw"]).levels, {B, ALL})   # all levels, from beginners
        self.assertEqual(labels_of(tennis["588"]["raw"]).levels, {B, A, ALL})  # every level, to competitive
        self.assertEqual(label_texts("Whether you're an experienced player or looking to take your "
                                     "skills to the next level", None).levels, {A})


class ExclusiveTest(unittest.TestCase):
    """RF-64: solo una riserva esplicita rende esclusivo il livello; `levels` = livelli ammessi."""

    def test_explicit_reservations(self):
        table = [
            ("Viaggio solo per avanzati.", {A}),
            ("Il camp è riservato a giocatori esperti.", {A}),
            ("Solo per giocatori intermedi e avanzati.", {I, A}),
            ("Riservato esclusivamente ai principianti.", {B}),
            ("Advanced players only.", {A}),
            ("Only for intermediate and advanced players.", {I, A}),
            ("Not suitable for beginners.", {I, A}),
            ("Il programma non è adatto ai principianti.", {I, A}),
            ("Sconsigliato ai principianti, pensato per giocatori di livello intermedio.", {I, A}),
        ]
        for text, levels in table:
            with self.subTest(text):
                got = label_texts(text, None)
                self.assertTrue(got.levels_exclusive)
                self.assertEqual(set(got.levels), levels)

    def test_a_reservation_about_people_or_seats_is_not_about_the_level(self):
        for text in ("L'esperienza è riservata a **un minimo di 2 partecipanti che viaggiano insieme**",
                     "posto riservato Premium in Platea", "Your only job is to soak in the tennis",
                     "per giocatori di livello intermedio e avanzato"):
            with self.subTest(text):
                self.assertFalse(label_texts(text, None).levels_exclusive)

    def test_short_description_is_read_too(self):
        got = label_texts("Un weekend al mare.", "Solo per avanzati, con coach.")
        self.assertEqual(got, ProductLabels(frozenset({A}), True, True))

    def test_empty_texts(self):
        self.assertEqual(label_texts(None, None), ProductLabels())
        self.assertEqual(labels_of(None), ProductLabels())
        self.assertEqual(labels_of({"title": "x"}), ProductLabels())


class OrderedTest(unittest.TestCase):
    def test_stable_order(self):
        self.assertEqual(ordered({ALL, A, B}), ["beginner", "advanced", "all"])
        self.assertEqual(ordered(frozenset()), [])


class FixtureCountsTest(unittest.TestCase):
    """Quante volte si accende ogni etichetta sui dettagli delle fixture (2026-09-27, riportato in
    `docs/decisions.md`): cambiare una regola cambia questi numeri e va deciso."""

    EXPECTED = {
        "catalog.json": {"details": 77, "any": 30, BEGINNER: 4, INTERMEDIATE: 6, ADVANCED: 3,
                         ALL: 24, "exclusive": 0, "coaching": 66},
        "catalog-tennis.json": {"details": 49, "any": 24, BEGINNER: 1, INTERMEDIATE: 2,
                                ADVANCED: 1, ALL: 22, "exclusive": 0, "coaching": 35},
        "catalog-staging.json": {"details": 56, "any": 3, BEGINNER: 1, INTERMEDIATE: 0,
                                 ADVANCED: 1, ALL: 2, "exclusive": 0, "coaching": 42},
        "catalog-staging-tennis.json": {"details": 13, "any": 3, BEGINNER: 2, INTERMEDIATE: 1,
                                        ADVANCED: 2, ALL: 3, "exclusive": 0, "coaching": 10},
    }

    def test_counts(self):
        for name, expected in self.EXPECTED.items():
            with self.subTest(name):
                labels = [labels_of(d["raw"]) for d in details(name).values()]
                got = {"details": len(labels), "any": sum(1 for x in labels if x.levels),
                       "exclusive": sum(x.levels_exclusive for x in labels),
                       "coaching": sum(x.coaching for x in labels)}
                for level in (BEGINNER, INTERMEDIATE, ADVANCED, ALL):
                    got[level] = sum(level in x.levels for x in labels)
                self.assertEqual(got, expected)


if __name__ == "__main__":
    unittest.main()
