# M9 — Parser completo, rifiuto con motivo, fallback Haiku: piano di esecuzione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Data: 2026-09-25. Branch: `task/m9`. Destinazione di questo file: `docs/plans/2026-09-25-m9-parser-rifiuti-haiku.md`.

**Goal:** RF-02, RF-03 e RF-08 completi: il parser deterministico it/en riconosce intervalli di date, parti di mese, persone e budget in molte forme e regioni del catalogo; se non trova né sport né periodo e `ANTHROPIC_API_KEY` esiste, Claude Haiku 4.5 compila lo stesso schema; il motivo di un rifiuto modifica i criteri dell'intento (budget, area, periodo, sport, persone) prima della proposta successiva; le frasi `say` e le domande seguono la lingua dell'intento (it/en).

**Architecture:** esagonale come in M2. Il parser resta in `vela/domain/intent.py` (funzioni pure, `today` iniettato). Il fallback è una porta nuova `vela/ports/llm.py` (`IntentExtractor`) con un adapter `vela/adapters/haiku.py` sull'SDK `anthropic`; il dominio valida l'output e non importa mai l'SDK. L'interpretazione dei rifiuti è una funzione pura nuova in `vela/domain/refine.py`; `Vela.reject_proposal` la applica e persiste i criteri con un metodo nuovo `IntentRepository.update_criteria`. Le tabelle geografiche (regioni, nomi inglesi, "più a sud/nord") stanno in `vela/domain/geo.py`.

**Tech Stack:** Python 3.12, `unittest`, SQLAlchemy Core (repository Postgres), FastAPI (solo wiring), SDK `anthropic` (dipendenza nuova, concordata).

**Spec:** `docs/spec.md` (RF-02, RF-03, RF-04, RF-08, RF-42), `docs/roadmap.md` sezione M9. Il design approvato nell'intervista del 2026-09-25 è la sezione "Design" qui sotto: non esiste un file di spec separato.

## Contesto

- Esiste già (M2): parser minimo in `vela/domain/intent.py` (`parse_intent`, `parse_period`, `parse_pax`, `parse_budget`, `detect_language`, `QUESTION_*`), dizionario `vela/domain/geo.py` (`PLACES`, `COUNTRIES`, `find_area`, `area_of_destination`), chooser v1 `vela/domain/chooser.py`, frasi solo italiane `vela/domain/say.py`, orchestratore `vela/domain/usecases.py` (`Vela`), repository in memoria e Postgres, contratto condiviso `tests/repo_contract.py`.
- Oggi `reject_proposal` salva solo il rifiuto: i criteri non cambiano (decisione M2).
- `fixtures/catalog.json`: `destination.geohierarchy` vale solo `"<paese>_<id GeoNames>"`, senza genitori, e per Nicosia è `IT_2591221` pur con `country: "CY"`. Non c'è latitudine. Per questo niente `geohierarchy` e niente coordinate: tabelle statiche.
- Tutti gli slug di `destination` della fixture si risolvono già con `find_area(slug.replace("-", " "))` tranne `weebora` (destinazione fittizia).
- M11 (chooser v2, branch `task/m11`) tocca `intent.py` e `chooser.py`: chi arriva secondo fa rebase prima del merge (regola della roadmap).
- Interprete: `uv run python` (3.12). Il `python3` di sistema è 3.7.

## Decisioni prese nell'intervista (già in `docs/decisions.md`)

| Decisione | Scelta | Motivo |
|---|---|---|
| Criteri dopo un rifiuto | Nuovo `IntentRepository.update_criteria(intent_id, criteria)` (memoria + Postgres), nessuna migrazione | L'intento mostra sempre i criteri correnti; `criteria` è già JSON |
| "Più a sud" / "più a nord" | Tabelle statiche `SOUTH_OF` / `NORTH_OF` in `geo.py`: luogo o paese → aree ordinate; si prende la prima | La fixture non ha coordinate e `geohierarchy` non ha gerarchia |
| "Più vicino" | Non gestito: motivo non riconosciuto, esclude solo il prodotto | Vicino a cosa è ambiguo senza la posizione del viaggiatore |
| Fallback | SDK `anthropic`, `claude-haiku-4-5-20251001`, strumento forzato `record_criteria`, timeout 5 s, 1 retry | Output strutturato ed errori tipizzati; dipendenza prevista dalla roadmap |
| Quando si chiama Haiku | Solo se il parser non trova né sport né periodo e l'extractor esiste (chiave presente) | RF-03 letto alla lettera; poche chiamate |
| Combinazione | Haiku sovrascrive i campi che restituisce validi; un valore invalido è scartato e resta quello del parser; la lingua resta quella del parser | Scelta dell'utente; la validazione evita valori impossibili |
| "Troppo caro" | Budget = 80% di prezzo × persone della proposta rifiutata (mai sopra il budget attuale); una cifra nel motivo vince | Scelta dell'utente (sconto percentuale) |
| Frasi inglesi | `say_*`, domande di RF-04 e motivazione del chooser in it/en secondo `criteria.language` | Rimandate da M2 a M9 |
| Regioni | Aggiunte a mano: Andalusia, Catalogna, Costa del Sol, Comunità Valenciana, Lombardia, Veneto, Emilia-Romagna, Occitania; valgono come corrispondenza di paese nel chooser v1 | Il catalogo ha città, non regioni; M11 raffina |

## Global Constraints

- Test: `uv run python -m unittest discover -s tests` verde senza servizi esterni, senza `DATABASE_URL` e senza `ANTHROPIC_API_KEY`.
- **Nessuna chiamata ad Anthropic nei test automatici.** L'adapter si testa con un client finto; il dominio con un extractor finto.
- Mai aprire, stampare o loggare `.env`, chiavi o token. Il testo dell'intento non va nei log (dati personali).
- Unica dipendenza nuova: `anthropic` (via `uv add anthropic`, che aggiorna `pyproject.toml` e `uv.lock`). Nessun'altra.
- `vela/domain` importa solo `vela.ports`, `vela.domain.*` e stdlib. Mai `anthropic`, `fastapi`, `sqlalchemy`.
- Nessuna variabile d'ambiente nuova: `ANTHROPIC_API_KEY` esiste già in `Settings` e nel README.
- Nessuna migrazione dello schema.
- `say` senza markdown e senza URL (RF-42); nessuna risposta con più di un prodotto (RF-10).
- Commit piccoli, uno per task, messaggio imperativo in inglese come nella storia del repo, che termina con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nessun force push.
- Test singolo modulo: `uv run python -m unittest discover -s tests -p "test_intent.py" -v` (i test importano `support` dalla cartella `tests`).

## Review Focus

1. "massimo 4 persone" non deve diventare un budget di 4 euro: pax 4, budget `None`. Test in Task 3 (`test_number_before_people_is_not_budget`).
2. "Lloret de Mar a ottobre": l'abbreviazione `mar` non deve produrre marzo; le abbreviazioni valgono solo accanto a un giorno. Test in Task 2 (`test_abbreviation_only_next_to_a_day`).
3. Budget a persona ("500 euro a testa, siamo in 2") diventa il totale 1000; senza numero di persone resta il valore scritto. Test in Task 3 (`test_per_person_budget`).
4. Haiku restituisce spazzatura (sport "golf", area inesistente, date invertite o passate, pax 0 o `true`, budget negativo o testuale): i campi sono ignorati e la domanda di RF-04 resta. Test in Task 4 (`test_invalid_fields_are_ignored`).
5. Lo stesso rifiuto "troppo caro" inviato due volte non abbassa il budget due volte. Test in Task 8 (`test_double_reject_does_not_lower_twice`).

---

## Design

### Parser deterministico (`vela/domain/intent.py`)

- **Periodo**: `parse_period` diventa una sequenza di finder, il primo che restituisce un `Period` vince (un finder che trova una data impossibile restituisce `None` e si passa al successivo). Ordine: intervallo ISO (`2026-11-07 - 2026-11-09`), intervallo gg/mm (`10/10 al 13/10`), intervallo giorno-prima (`dal 10 al 14 ottobre`, `20-23 novembre`, `dal 28 dicembre al 3 gennaio`, `from the 3rd to the 7th of December`), intervallo "tra/between" (`tra il 5 e l'8 dicembre`, `between 14 and 20 November`), intervallo mese-prima (`October 10-12`), data ISO, data gg/mm, giorno-mese (`12 ott`, `10th of October`), mese-giorno (`Oct 3rd`, non seguito da parole di persone), parte di mese (`inizio/metà/fine`, `early/mid/late`: 1-10, 11-20, 21-fine), mese prossimo (`il mese prossimo`, `next month`), mese intero, stagione, weekend.
- Le abbreviazioni dei mesi (`gen, feb, mar, apr, mag, giu, lug, ago, set, ott, nov, dic, jan, jun, jul, aug, sep, sept, oct, dec`) valgono solo accanto a un numero di giorno. Il mese isolato riconosce solo i nomi interi.
- Anno: un inizio già passato va all'anno prossimo; una fine prima dell'inizio va all'anno successivo all'inizio.
- Resta com'era: "un weekend a ottobre" = tutto ottobre (il mese batte il weekend).
- **Persone**: pattern numerici con moltiplicatore (`due coppie` = 4, `famiglia di 4`, `group of 6`), poi frasi fisse (`in coppia`, `a couple` non seguito da `of`, `io e mia moglie`, `me and my`, `my wife and I` = 2; `da solo`, `just me`, `on my own`, `alone` = 1). I numeri espliciti vincono sulle frasi.
- **Budget**: `2k`/`1,5k` = migliaia; nuove parole chiave (`sotto i`, `non oltre`, `below`, `at most`, `tetto di`); un numero seguito da parole di persone, notti o giorni non è un budget. Budget a persona (`a testa`, `a persona`, `per persona`, `each`, `per person`, `per head`) moltiplicato per le persone in `parse_intent`.
- **Lingua**: marcatori estesi; a parità vince l'italiano.
- **Domande RF-04**: in italiano o inglese secondo la lingua rilevata.

### Geografia (`vela/domain/geo.py`)

- Regioni nuove in `PLACES` (vedi decisioni). `area_by_name(name)` restituisce l'`Area` di un nome canonico (luogo o paese). `display_name(area, lang)` dà il nome inglese quando serve (`Spagna` → `Spain`, `Barcellona` → `Barcelona`).
- `SOUTH_OF` / `NORTH_OF`: chiave = nome canonico di un luogo o di un paese; valore = tupla ordinata di nomi canonici. Una tupla vuota significa "niente più a sud/nord": non si ricade sul paese.
- `move(area, direction)`: cerca prima `area.name`, poi il paese di `area`; restituisce l'`Area` del primo nome della tupla, oppure `None`.

### Fallback Haiku

- Porta `vela/ports/llm.py`: `IntentExtractor.extract(text, today) -> Optional[dict]` con chiavi `sport`, `area`, `period_start`, `period_end`, `pax`, `budget` (valori `null` se il testo non li dice).
- `parse_intent(text, profile=None, today=None, extractor=None)`: se dopo il parser deterministico mancano sia `sport` sia `period` e `extractor` non è `None`, lo chiama. Ogni eccezione dell'extractor è loggata (solo il nome della classe) e ignorata. I campi validi sovrascrivono quelli del parser: sport ∈ {padel, tennis}; area risolta con `geo.find_area`; periodo con entrambe le date ISO, inizio ≤ fine, fine non passata (label `"llm"`); pax intero 1-20 (non booleano); budget numerico > 0 (arrotondato al centesimo). `language` resta quella del parser.
- Adapter `vela/adapters/haiku.py`: `HaikuExtractor(client)`; `HaikuExtractor.from_api_key(key)` costruisce `anthropic.Anthropic(api_key=key, timeout=5.0, max_retries=1)`. Una chiamata `messages.create` con `tools=[TOOL]` e `tool_choice={"type": "tool", "name": "record_criteria"}`. `anthropic.APIError` (connessione, timeout, stato HTTP) → log e `None`; risposta senza `tool_use` → `None`.
- `Vela(..., extractor=None)`; `build_vela` crea l'extractor solo se `settings.anthropic_api_key` è presente, importando l'adapter solo in quel caso.
- `scripts/try_haiku.py`: prova manuale con **una** chiamata reale, mai eseguita dai test.

### Rifiuto con motivo (`vela/domain/refine.py`)

`refine(criteria, reason, proposal, product_area, today) -> Criteria`, funzione pura; le regole si combinano:

- **Budget**: una cifra nel motivo (`parse_budget`) vince. Altrimenti una parola di prezzo (`troppo caro`, `costa troppo`, `più economico`, `too expensive`, `cheaper`...) porta il budget a `min(budget attuale, 0.8 × price_from × pax)`, arrotondato al centesimo.
- **Direzione**: `più a sud`, `further south`... / `più a nord`, `further north`... → `geo.move(product_area, direzione)`; se non c'è voce, nessun cambio d'area.
- **Luogo esplicito** (`meglio in Grecia`): solo se non c'è una direzione.
- **Periodo, sport, persone**: `parse_period`, `parse_sport`, `parse_pax` sul motivo.
- Nessuna regola → gli stessi criteri (`"più vicino"`, `"non mi piace"`, stringa vuota).

`Vela.reject_proposal` salva il rifiuto, calcola l'area del prodotto rifiutato con `geo.area_of_destination`, applica `refine` e, se i criteri cambiano, chiama `repos.intents.update_criteria` prima di `_propose`. `refine` è idempotente sullo stesso motivo e la stessa proposta (il budget è un `min`).

### Frasi bilingui

- `say.fmt_date(d, lang)`, `say.fmt_money(v, lang)` ("1 October 2026", "812.50 euros"); ogni `say_*` riceve `lang` (default `"it"`); `say_intent_created` usa `c.language`.
- Il chooser scrive la motivazione nella lingua dei criteri; con corrispondenza solo di paese nomina il paese (non l'area chiesta, che può essere una regione).
- `Vela` passa `intent.criteria.language` a tutte le frasi; `get_order_status` e `accept_proposal` la ricavano dall'intento dell'ordine o della proposta. La pagina di checkout replay resta in italiano.

## Mappa dei file

| File | Azione | Responsabilità |
|---|---|---|
| `vela/domain/geo.py` | Modifica | regioni, `area_by_name`, `display_name`, `SOUTH_OF`/`NORTH_OF`, `move` |
| `vela/domain/intent.py` | Modifica | periodi, persone, budget, lingua, domande bilingui, gate del fallback |
| `vela/ports/llm.py` | Crea | porta `IntentExtractor` |
| `vela/adapters/haiku.py` | Crea | `HaikuExtractor` sull'SDK `anthropic` |
| `vela/domain/refine.py` | Crea | criteri aggiornati da un motivo di rifiuto |
| `vela/ports/repositories.py` | Modifica | `IntentRepository.update_criteria` |
| `vela/adapters/repo_memory.py`, `vela/adapters/repo_postgres.py` | Modifica | `update_criteria` |
| `vela/domain/usecases.py` | Modifica | `extractor`, rifiuto con `refine`, lingua delle frasi |
| `vela/domain/say.py`, `vela/domain/chooser.py` | Modifica | frasi e motivazione it/en |
| `vela/app.py` | Modifica | extractor solo con chiave |
| `scripts/try_haiku.py` | Crea | prova manuale (1 chiamata) |
| `tests/test_geo.py`, `tests/test_intent.py`, `tests/test_say.py`, `tests/test_chooser.py`, `tests/test_usecases.py`, `tests/test_app_replay.py`, `tests/repo_contract.py` | Modifica | vedi task |
| `tests/test_refine.py`, `tests/test_haiku.py` | Crea | vedi task |
| `README.md`, `docs/decisions.md` | Modifica | doc finale |

---

### Task 1: Geografia: regioni, nomi, direzioni

**Files:**
- Modify: `vela/domain/geo.py`
- Test: `tests/test_geo.py`

**Interfaces:**
- Produces: `geo.area_by_name(name: str) -> Optional[Area]`; `geo.display_name(area: Area, lang: str) -> str`; `geo.SOUTH_OF`, `geo.NORTH_OF: Dict[str, Tuple[str, ...]]`; `geo.move(area: Optional[Area], direction: str) -> Optional[Area]` con `direction` ∈ `{"south", "north"}`.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_geo.py` cambia l'import in:

```python
from vela.domain.geo import (COUNTRIES, NORTH_OF, SOUTH_OF, area_by_name, area_of_destination,
                             display_name, find_area, move)
```

e aggiungi prima di `FixtureCoverageTest`:

```python
class RegionTest(unittest.TestCase):
    def test_regions_it_and_en(self):
        self.assertEqual(find_area("padel in Andalusia"), Area("region", "Andalusia", "ES"))
        self.assertEqual(find_area("tennis in Catalonia"), Area("region", "Catalogna", "ES"))
        self.assertEqual(find_area("Emilia Romagna"), Area("region", "Emilia-Romagna", "IT"))
        self.assertEqual(find_area("in Lombardy"), Area("region", "Lombardia", "IT"))

    def test_valencian_community_is_not_valencia(self):
        self.assertEqual(find_area("Comunità Valenciana").name, "Comunità Valenciana")
        self.assertEqual(find_area("Valencia").name, "Valencia")


class NamesTest(unittest.TestCase):
    def test_area_by_name(self):
        self.assertEqual(area_by_name("Spagna"), Area("country", "Spagna", "ES"))
        self.assertEqual(area_by_name("Malaga"), Area("city", "Malaga", "ES"))
        self.assertEqual(area_by_name("Canarie"), Area("region", "Canarie", "ES"))
        self.assertIsNone(area_by_name("Atlantide"))

    def test_display_name(self):
        self.assertEqual(display_name(Area("country", "Spagna", "ES"), "en"), "Spain")
        self.assertEqual(display_name(Area("country", "Spagna", "ES"), "it"), "Spagna")
        self.assertEqual(display_name(Area("city", "Barcellona", "ES"), "en"), "Barcelona")
        self.assertEqual(display_name(Area("region", "Lanzarote", "ES"), "en"), "Lanzarote")


class DirectionTest(unittest.TestCase):
    def test_tables_only_name_known_areas(self):
        for table in (SOUTH_OF, NORTH_OF):
            for key, targets in table.items():
                self.assertIsNotNone(area_by_name(key), key)
                for target in targets:
                    self.assertIsNotNone(area_by_name(target), "%s → %s" % (key, target))
                    self.assertNotEqual(target, key)

    def test_place_entry_wins(self):
        self.assertEqual(move(Area("city", "Valencia", "ES"), "south"), Area("city", "Alicante", "ES"))
        self.assertEqual(move(Area("city", "Valencia", "ES"), "north"), Area("city", "Tarragona", "ES"))

    def test_falls_back_to_country(self):
        self.assertEqual(move(Area("city", "Malaga", "ES"), "south"), Area("country", "Marocco", "MA"))
        self.assertEqual(move(Area("city", "Milano", "IT"), "north"), Area("country", "Francia", "FR"))

    def test_empty_entry_stops(self):
        self.assertIsNone(move(Area("region", "Lanzarote", "ES"), "south"))
        self.assertIsNone(move(Area("city", "Reims", "FR"), "north"))

    def test_unknown(self):
        self.assertIsNone(move(Area("city", "Buenos Aires", "AR"), "north"))
        self.assertIsNone(move(None, "south"))
```

In `FixtureCoverageTest` aggiungi:

```python
    def test_every_fixture_destination_slug_resolves(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            data = json.load(fh)
        for detail in data["details"].values():
            dest = detail["catalog"].get("destination") or {}
            slug, country = dest.get("slug"), dest.get("country")
            if not slug or dest.get("title") in self.SKIP:
                continue
            area = find_area(slug.replace("-", " "))
            self.assertIsNotNone(area, "slug non in geo.py: %r" % slug)
            self.assertEqual(area.country_code, country, slug)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_geo.py" -v`
Expected: ERROR all'import (`cannot import name 'NORTH_OF'`).

- [ ] **Step 3: Implementa**

In `vela/domain/geo.py`:

1. Aggiorna la docstring del modulo: `M9 aggiunge regioni, nomi inglesi e le tabelle "più a sud/nord". geohierarchy della fixture non si usa: contiene solo paese e id GeoNames (per Nicosia con il paese sbagliato).`
2. Aggiungi a `PLACES`, dopo la voce `("Baleari", ...)`:

```python
    # regioni che contengono città del catalogo: nel chooser v1 valgono come paese
    ("Andalusia", "region", "ES", "andalucia", "andalucía"),
    ("Catalogna", "region", "ES", "catalonia", "catalunya", "cataluña"),
    ("Costa del Sol", "region", "ES"),
    ("Comunità Valenciana", "region", "ES", "comunitat valenciana", "valencian community"),
    ("Lombardia", "region", "IT", "lombardy"), ("Veneto", "region", "IT"),
    ("Emilia-Romagna", "region", "IT", "emilia romagna"),
    ("Occitania", "region", "FR", "occitanie"),
```

3. Dopo `_INDEX = _build_index()` aggiungi:

```python
_BY_NAME = {place[0]: Area(place[1], place[0], place[2]) for place in PLACES}
_BY_NAME.update({name: Area("country", name, code) for code, name in COUNTRIES.items()})

EN_NAMES = {
    "Spagna": "Spain", "Italia": "Italy", "Francia": "France", "Grecia": "Greece",
    "Marocco": "Morocco", "Egitto": "Egypt", "Cipro": "Cyprus", "Thailandia": "Thailand",
    "Barcellona": "Barcelona", "Firenze": "Florence", "Maiorca": "Mallorca", "Milano": "Milan",
    "Minorca": "Menorca", "Sardegna": "Sardinia", "Siviglia": "Seville", "Toscana": "Tuscany",
    "Venezia": "Venice", "Canarie": "Canary Islands", "Baleari": "Balearic Islands",
    "Catalogna": "Catalonia", "Comunità Valenciana": "Valencian Community",
    "Lombardia": "Lombardy", "Occitania": "Occitanie",
}

_CANARIES = ("Canarie", "Lanzarote", "Fuerteventura", "Tenerife")
_BALEARICS = ("Baleari", "Maiorca", "Palma de Mallorca", "Ibiza", "Minorca")
_ANDALUSIA = ("Andalusia", "Costa del Sol", "Malaga", "Estepona", "Torre del Mar", "Siviglia")
_TUSCANY = ("Toscana", "Firenze", "Pietrasanta")

# nome canonico → aree più a sud, dalla più vicina; tupla vuota = niente più a sud nel catalogo
SOUTH_OF = {
    "Francia": ("Spagna", "Italia"), "Reims": ("Cap d'Agde", "Barcellona"),
    "Cap d'Agde": ("Barcellona", "Maiorca"), "Occitania": ("Barcellona", "Maiorca"),
    "Italia": ("Tunisia", "Marocco"), "Milano": ("Toscana", "Sardegna"),
    "Lombardia": ("Toscana", "Sardegna"), "Venezia": ("Riccione", "Toscana"),
    "Veneto": ("Riccione", "Toscana"), "Riccione": ("Toscana", "Sardegna"),
    "Emilia-Romagna": ("Toscana", "Sardegna"),
    "Spagna": ("Marocco", "Canarie"), "Catalogna": ("Valencia", "Malaga"),
    "Barcellona": ("Valencia", "Malaga"), "Lloret de Mar": ("Barcellona", "Valencia"),
    "Tarragona": ("Valencia", "Malaga"), "Madrid": ("Siviglia", "Malaga"),
    "Valencia": ("Alicante", "Malaga"), "Comunità Valenciana": ("Alicante", "Malaga"),
    "Dénia": ("Alicante", "Malaga"), "Alicante": ("Malaga", "Marocco"),
    "Grecia": ("Cipro", "Egitto"), "Cipro": ("Egitto",), "Marocco": ("Canarie",),
    "Tunisia": ("Egitto",), "Egitto": ("Tanzania",), "Thailandia": ("Indonesia",),
}
SOUTH_OF.update({name: ("Sardegna",) for name in _TUSCANY})
SOUTH_OF.update({name: ("Malaga", "Marocco") for name in _BALEARICS})
SOUTH_OF.update({name: () for name in _CANARIES})

# nome canonico → aree più a nord, dalla più vicina; tupla vuota = niente più a nord nel catalogo
NORTH_OF = {
    "Spagna": ("Francia", "Italia"), "Alicante": ("Valencia", "Barcellona"),
    "Dénia": ("Valencia", "Barcellona"), "Valencia": ("Tarragona", "Barcellona"),
    "Comunità Valenciana": ("Tarragona", "Barcellona"), "Madrid": ("Barcellona", "Francia"),
    "Italia": ("Francia",), "Sardegna": ("Toscana", "Milano"),
    "Riccione": ("Venezia", "Milano"), "Emilia-Romagna": ("Venezia", "Milano"),
    "Francia": (), "Reims": (), "Cap d'Agde": ("Reims",), "Occitania": ("Reims",),
    "Marocco": ("Spagna",), "Tunisia": ("Italia",), "Egitto": ("Cipro", "Grecia"),
    "Cipro": ("Grecia",), "Grecia": ("Italia",), "Tanzania": ("Egitto",),
    "Indonesia": ("Thailandia",),
}
NORTH_OF.update({name: ("Malaga", "Maiorca") for name in _CANARIES})
NORTH_OF.update({name: ("Madrid", "Barcellona") for name in _ANDALUSIA})
NORTH_OF.update({name: ("Venezia", "Milano") for name in _TUSCANY})

_DIRECTIONS = {"south": SOUTH_OF, "north": NORTH_OF}


def area_by_name(name: Optional[str]) -> Optional[Area]:
    return _BY_NAME.get(name)


def display_name(area: Area, lang: str) -> str:
    return EN_NAMES.get(area.name, area.name) if lang == "en" else area.name


def move(area: Optional[Area], direction: str) -> Optional[Area]:
    """Area più a sud o più a nord di `area` (RF-08): prima la voce del luogo, poi quella del paese."""
    if area is None:
        return None
    table = _DIRECTIONS[direction]
    for key in (area.name, COUNTRIES.get(area.country_code)):
        if key in table:
            targets = table[key]
            return _BY_NAME[targets[0]] if targets else None
    return None
```

- [ ] **Step 4: Verifica che passino**

Run: `uv run python -m unittest discover -s tests -p "test_geo.py" -v`
Expected: PASS. Poi l'intera suite: `uv run python -m unittest discover -s tests` → OK.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/geo.py tests/test_geo.py
git commit -m "Add regions, English names and south/north tables to the geo dictionary"
```

---

### Task 2: Parser: periodi (intervalli, abbreviazioni, parti di mese, mese prossimo)

**Files:**
- Modify: `vela/domain/intent.py` (costanti dei mesi e `parse_period`)
- Test: `tests/test_intent.py` (`PeriodTest`)

**Interfaces:**
- Produces: `parse_period(text: str, today: date) -> Optional[Period]` (firma invariata); costanti `MONTH_ABBR`, `ALL_MONTHS`.

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `PeriodTest` in `tests/test_intent.py`:

```python
    def span(self, text, today=TODAY):
        p = parse_period(text, today)
        return (p.start, p.end) if p else None

    def test_ranges(self):
        cases = [
            ("dal 10 al 14 ottobre", (date(2026, 10, 10), date(2026, 10, 14))),
            ("20-23 novembre", (date(2026, 11, 20), date(2026, 11, 23))),
            ("from 10 to 14 October", (date(2026, 10, 10), date(2026, 10, 14))),
            ("from the 3rd to the 7th of December", (date(2026, 12, 3), date(2026, 12, 7))),
            ("tra il 5 e l'8 dicembre", (date(2026, 12, 5), date(2026, 12, 8))),
            ("between 14 and 20 November", (date(2026, 11, 14), date(2026, 11, 20))),
            ("October 10-12", (date(2026, 10, 10), date(2026, 10, 12))),
            ("oct 10 to nov 2", (date(2026, 10, 10), date(2026, 11, 2))),
            ("dal 10/10 al 13/10", (date(2026, 10, 10), date(2026, 10, 13))),
            ("2026-11-07 - 2026-11-09", (date(2026, 11, 7), date(2026, 11, 9))),
            ("dal 28 ottobre al 3 novembre", (date(2026, 10, 28), date(2026, 11, 3))),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.span(text), expected)

    def test_range_across_new_year(self):
        self.assertEqual(self.span("dal 28 dicembre al 3 gennaio"),
                         (date(2026, 12, 28), date(2027, 1, 3)))

    def test_past_range_is_next_year(self):
        self.assertEqual(self.span("dal 1 al 5 giugno"), (date(2027, 6, 1), date(2027, 6, 5)))

    def test_impossible_range_falls_through(self):
        p = parse_period("dal 30 al 31 febbraio", TODAY)
        self.assertEqual(p.label, "febbraio")

    def test_abbreviations_and_ordinals(self):
        self.assertEqual(self.span("il 12 ott"), (date(2026, 10, 12), date(2026, 10, 12)))
        self.assertEqual(self.span("the 10th of October"), (date(2026, 10, 10), date(2026, 10, 10)))
        self.assertEqual(self.span("Oct 3rd"), (date(2026, 10, 3), date(2026, 10, 3)))

    def test_abbreviation_only_next_to_a_day(self):
        self.assertEqual(parse_period("Lloret de Mar a ottobre", TODAY).label, "ottobre")
        self.assertIsNone(parse_period("padel a Lloret de Mar", TODAY))

    def test_month_first_is_not_people(self):
        p = parse_period("October 2 people", TODAY)
        self.assertEqual((p.start, p.end), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_month_parts(self):
        self.assertEqual(self.span("a inizio ottobre"), (date(2026, 10, 1), date(2026, 10, 10)))
        self.assertEqual(self.span("a metà marzo"), (date(2027, 3, 11), date(2027, 3, 20)))
        self.assertEqual(self.span("a fine ottobre"), (date(2026, 10, 21), date(2026, 10, 31)))
        self.assertEqual(self.span("early November"), (date(2026, 11, 1), date(2026, 11, 10)))
        self.assertEqual(self.span("mid-October"), (date(2026, 10, 11), date(2026, 10, 20)))
        self.assertEqual(self.span("late February"), (date(2027, 2, 21), date(2027, 2, 28)))

    def test_fine_settimana_is_still_weekend(self):
        self.assertEqual(parse_period("fine settimana", TODAY).label, "fine settimana")

    def test_next_month(self):
        self.assertEqual(self.span("il mese prossimo"), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(self.span("next month", date(2026, 12, 10)),
                         (date(2027, 1, 1), date(2027, 1, 31)))

    def test_impossible_single_date_falls_through(self):
        self.assertEqual(parse_period("il 31/02 a marzo", TODAY).label, "marzo")
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_intent.py" -v`
Expected: FAIL/ERROR sui nuovi test (per esempio `test_ranges` restituisce la sola data finale o `None`).

- [ ] **Step 3: Implementa**

In `vela/domain/intent.py`, dopo `SEASONS` aggiungi:

```python
# abbreviazioni valide solo accanto a un giorno ("12 ott", "Oct 3"): "mar" da solo è Lloret de Mar
MONTH_ABBR = {
    "gen": 1, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6, "jun": 6, "lug": 7,
    "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "sept": 9, "ott": 10, "oct": 10, "nov": 11,
    "dic": 12, "dec": 12,
}
ALL_MONTHS = {**MONTHS, **MONTH_ABBR}
MONTH_PARTS = {"inizio": (1, 10), "early": (1, 10), "metà": (11, 20), "meta": (11, 20),
               "mid": (11, 20), "fine": (21, None), "late": (21, None)}
```

Sostituisci `_MONTH_RE`, `_SEASON_RE`, `_WEEKEND_RE` e l'intera `parse_period` (e `_day_period`, `_month_period`) con:

```python
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_ANY_MONTH_RE = "|".join(sorted(ALL_MONTHS, key=len, reverse=True))
_SEASON_RE = "|".join(sorted(SEASONS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"
_TO = r"\s*(?:-|–|al|to|till|until)\s*"
_PEOPLE_AFTER = (r"(?!\s*(?:persone|adulti|giocatori|amici|people|persons|adults|players|"
                 r"friends|pax|of us))")
_WEEKEND_RE = re.compile(r"\bweek-?end\b|\bfine settimana\b")
_RANGE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})%s(\d{4})-(\d{2})-(\d{2})\b" % _TO)
_RANGE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})%s(\d{1,2})/(\d{1,2})\b" % _TO)
_RANGE_DAY_FIRST = re.compile(
    r"\b(?:dal\s+|from\s+(?:the\s+)?)?(\d{1,2})%s(?:\s+(?:of\s+)?(%s))?%s(?:the\s+)?(\d{1,2})%s"
    r"\s+(?:of\s+)?(%s)\b" % (_ORD, _ANY_MONTH_RE, _TO, _ORD, _ANY_MONTH_RE))
_RANGE_BETWEEN = re.compile(
    r"\b(?:tra|fra|between)\s+(?:il\s+|l'|the\s+)?(\d{1,2})%s(?:\s+(?:of\s+)?(%s))?\s+(?:e|and)\s+"
    r"(?:il\s+|l'|the\s+)?(\d{1,2})%s\s+(?:of\s+)?(%s)\b"
    % (_ORD, _ANY_MONTH_RE, _ORD, _ANY_MONTH_RE))
_RANGE_MONTH_FIRST = re.compile(
    r"\b(%s)\s+(\d{1,2})%s%s(?:(%s)\s+)?(\d{1,2})%s\b"
    % (_ANY_MONTH_RE, _ORD, _TO, _ANY_MONTH_RE, _ORD))
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})%s\s+(?:of\s+)?(%s)\b" % (_ORD, _ANY_MONTH_RE))
_MONTH_DAY = re.compile(r"\b(%s)\s+(\d{1,2})%s\b%s" % (_ANY_MONTH_RE, _ORD, _PEOPLE_AFTER))
_MONTH_PART = re.compile(r"\b(inizio|fine|metà|meta|early|mid|late)[\s-]+(?:di\s+|of\s+)?(%s)\b"
                         % _MONTH_RE)
_NEXT_MONTH = re.compile(r"\b(?:il\s+)?(?:mese prossimo|prossimo mese|next month)\b")
_MONTH = re.compile(r"\b(%s)\b" % _MONTH_RE)
_SEASON = re.compile(r"\b(%s)\b" % _SEASON_RE)


def _month_period(month: int, today: date, label: str) -> Period:
    year = today.year if month >= today.month else today.year + 1
    return Period(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), label)


def _span(d1: int, m1: int, y1: Optional[int], d2: int, m2: int, y2: Optional[int], today: date,
          label: str) -> Optional[Period]:
    """Intervallo da giorno/mese/anno; senza anno l'inizio passato va all'anno prossimo e una fine
    prima dell'inizio va all'anno successivo. Una data impossibile dà None."""
    try:
        start = date(y1 or today.year, m1, d1)
        if y1 is None and start < today:
            start = date(today.year + 1, m1, d1)
        end = date(y2 or start.year, m2, d2)
        if y2 is None and end < start:
            end = date(start.year + 1, m2, d2)
    except ValueError:
        return None
    return Period(start, end, label) if start <= end else None


def _range_iso(low, today):
    m = _RANGE_ISO.search(low)
    if m:
        g = [int(x) for x in m.groups()]
        return _span(g[2], g[1], g[0], g[5], g[4], g[3], today, m.group(0))


def _range_slash(low, today):
    m = _RANGE_SLASH.search(low)
    if m:
        d1, m1, d2, m2 = (int(x) for x in m.groups())
        return _span(d1, m1, None, d2, m2, None, today, m.group(0))


def _range_day_first(low, today):
    for pattern in (_RANGE_DAY_FIRST, _RANGE_BETWEEN):
        m = pattern.search(low)
        if m:
            d1, first, d2, second = m.groups()
            month2 = ALL_MONTHS[second]
            month1 = ALL_MONTHS[first] if first else month2
            return _span(int(d1), month1, None, int(d2), month2, None, today, m.group(0).strip())


def _range_month_first(low, today):
    m = _RANGE_MONTH_FIRST.search(low)
    if m:
        first, d1, second, d2 = m.groups()
        month1 = ALL_MONTHS[first]
        month2 = ALL_MONTHS[second] if second else month1
        return _span(int(d1), month1, None, int(d2), month2, None, today, m.group(0))


def _single_iso(low, today):
    m = _ISO_DATE.search(low)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return _span(d, mo, y, d, mo, y, today, m.group(0))


def _single_slash(low, today):
    m = _SLASH_DATE.search(low)
    if m:
        year = int(m.group(3)) if m.group(3) else None
        d, mo = int(m.group(1)), int(m.group(2))
        return _span(d, mo, year, d, mo, year, today, m.group(0))


def _single_day_month(low, today):
    m = _DAY_MONTH.search(low)
    if m:
        d, mo = int(m.group(1)), ALL_MONTHS[m.group(2)]
        return _span(d, mo, None, d, mo, None, today, m.group(0))


def _single_month_day(low, today):
    m = _MONTH_DAY.search(low)
    if m:
        mo, d = ALL_MONTHS[m.group(1)], int(m.group(2))
        return _span(d, mo, None, d, mo, None, today, m.group(0))


def _month_part(low, today):
    m = _MONTH_PART.search(low)
    if m:
        whole = _month_period(MONTHS[m.group(2)], today, m.group(0))
        first, last = MONTH_PARTS[m.group(1)]
        end = whole.end if last is None else whole.start.replace(day=last)
        return Period(whole.start.replace(day=first), end, m.group(0))


def _next_month(low, today):
    m = _NEXT_MONTH.search(low)
    if m:
        return _month_period(today.month % 12 + 1, today, m.group(0).strip())


def _whole_month(low, today):
    m = _MONTH.search(low)
    if m:
        return _month_period(MONTHS[m.group(1)], today, m.group(1))


def _season(low, today):
    m = _SEASON.search(low)
    if m:
        first, last = SEASONS[m.group(1)]
        if first == 12:   # inverno: dicembre → febbraio
            year = today.year if today.month >= 3 else today.year - 1
            return Period(date(year, 12, 1), date(year + 1, 3, 1) - timedelta(days=1), m.group(1))
        year = today.year if last >= today.month else today.year + 1
        return Period(date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1]),
                      m.group(1))


def _weekend(low, today):
    m = _WEEKEND_RE.search(low)
    if m:
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        return Period(start, start + timedelta(days=1), m.group(0))


# dal più specifico al più generico: vince il primo che produce un periodo valido
_PERIOD_FINDERS = (_range_iso, _range_slash, _range_day_first, _range_month_first, _single_iso,
                   _single_slash, _single_day_month, _single_month_day, _month_part, _next_month,
                   _whole_month, _season, _weekend)


def parse_period(text: str, today: date) -> Optional[Period]:
    low = text.lower()
    for finder in _PERIOD_FINDERS:
        period = finder(low, today)
        if period is not None:
            return period
    return None
```

Nota: `_single_iso` con anno esplicito mantiene il comportamento M2 (una data ISO passata resta passata; il chooser la scarta). `_day_period` non esiste più: se qualche altro modulo la importa, `grep -rn "_day_period" vela tests` deve dare zero risultati.

- [ ] **Step 4: Verifica che passino**

Run: `uv run python -m unittest discover -s tests -p "test_intent.py" -v`
Expected: PASS, compresi i test M2 (`TableTest`, `test_month_beats_weekend`, `test_day_month_slash`, `test_winter_in_january`).
Poi: `uv run python -m unittest discover -s tests` → OK.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/intent.py tests/test_intent.py
git commit -m "Parse date ranges, month parts, abbreviations and next month in intents"
```

---

### Task 3: Parser: persone, budget, lingua e tabella da almeno 30 casi

**Files:**
- Modify: `vela/domain/intent.py` (`_PAX_PATTERNS`, `parse_pax`, `_BUDGET_PATTERNS`, `parse_budget`, `is_per_person`, marcatori di lingua, `parse_intent`)
- Test: `tests/test_intent.py` (`TABLE`, `PaxTest`, `BudgetTest`, `LanguageTest`)

**Interfaces:**
- Produces: `is_per_person(text: str) -> bool`; `parse_pax`, `parse_budget` con firme invariate.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_intent.py` aggiungi `is_per_person` all'import da `vela.domain.intent`. Estendi `TABLE` con queste 22 righe (totale 32):

```python
    ("padel dal 10 al 14 ottobre a Malaga, siamo in 2",
     ("padel", "ES", (date(2026, 10, 10), date(2026, 10, 14)), 2, None, "it")),
    ("tennis from 10 to 14 October in Greece, two of us",
     ("tennis", "GR", (date(2026, 10, 10), date(2026, 10, 14)), 2, None, "en")),
    ("padel 20-23 novembre in Sardegna per 4 persone, budget 2k",
     ("padel", "IT", (date(2026, 11, 20), date(2026, 11, 23)), 4, Decimal("2000"), "it")),
    ("padel tra il 5 e l'8 dicembre, in coppia",
     ("padel", None, (date(2026, 12, 5), date(2026, 12, 8)), 2, None, "it")),
    ("tennis dal 28 dicembre al 3 gennaio a Tenerife, siamo in tre",
     ("tennis", "ES", (date(2026, 12, 28), date(2027, 1, 3)), 3, None, "it")),
    ("padel October 10-12 in Mallorca for two",
     ("padel", "ES", (date(2026, 10, 10), date(2026, 10, 12)), 2, None, "en")),
    ("padel a fine ottobre per 2 persone",
     ("padel", None, (date(2026, 10, 21), date(2026, 10, 31)), 2, None, "it")),
    ("tennis in early November, just me",
     ("tennis", None, (date(2026, 11, 1), date(2026, 11, 10)), 1, None, "en")),
    ("padel a metà marzo a Valencia, io e mia moglie",
     ("padel", "ES", (date(2027, 3, 11), date(2027, 3, 20)), 2, None, "it")),
    ("padel il mese prossimo, siamo una famiglia di 4",
     ("padel", None, (date(2026, 10, 1), date(2026, 10, 31)), 4, None, "it")),
    ("tennis next month in Italy, a couple, under 1500 euros",
     ("tennis", "IT", (date(2026, 10, 1), date(2026, 10, 31)), 2, Decimal("1500"), "en")),
    ("padel in Andalusia a novembre, 500 euro a testa, siamo in 2",
     ("padel", "ES", (date(2026, 11, 1), date(2026, 11, 30)), 2, Decimal("1000"), "it")),
    ("padel weekend in Catalonia for 3 people, 400 euros each",
     ("padel", "ES", (date(2026, 9, 26), date(2026, 9, 27)), 3, Decimal("1200"), "en")),
    ("padel a Lloret de Mar a ottobre in 2",
     ("padel", "ES", (date(2026, 10, 1), date(2026, 10, 31)), 2, None, "it")),
    ("vorrei giocare a padel il 12 ott, sotto i 900 euro, da solo",
     ("padel", None, (date(2026, 10, 12), date(2026, 10, 12)), 1, Decimal("900"), "it")),
    ("tennis Oct 3rd in Madrid for four players",
     ("tennis", "ES", (date(2026, 10, 3), date(2026, 10, 3)), 4, None, "en")),
    ("padel in primavera in Grecia, due coppie, massimo 3000 euro",
     ("padel", "GR", (date(2027, 3, 1), date(2027, 5, 31)), 4, Decimal("3000"), "it")),
    ("tennis on 2026-11-07 - 2026-11-09 in Emilia-Romagna, we are 2, max 1.200 euros",
     ("tennis", "IT", (date(2026, 11, 7), date(2026, 11, 9)), 2, Decimal("1200"), "en")),
    ("padel dal 10/10 al 13/10, siamo in 4",
     ("padel", None, (date(2026, 10, 10), date(2026, 10, 13)), 4, None, "it")),
    ("tennis tra il 1 e il 5 giugno in Toscana per due",
     ("tennis", "IT", (date(2027, 6, 1), date(2027, 6, 5)), 2, None, "it")),
    ("tennis in Zanzibar between 14 and 20 November for 2 people",
     ("tennis", "TZ", (date(2026, 11, 14), date(2026, 11, 20)), 2, None, "en")),
    ("padel from the 3rd to the 7th of December in Cyprus, 2 adults",
     ("padel", "CY", (date(2026, 12, 3), date(2026, 12, 7)), 2, None, "en")),
```

E sotto `TABLE`:

```python
class TableSizeTest(unittest.TestCase):
    def test_at_least_thirty_cases_in_both_languages(self):
        self.assertGreaterEqual(len(TABLE), 30)
        langs = [row[1][5] for row in TABLE]
        self.assertGreaterEqual(langs.count("en"), 10)
        self.assertGreaterEqual(langs.count("it"), 15)
```

In `PaxTest` aggiungi:

```python
    def test_new_forms(self):
        for text, pax in [("in coppia", 2), ("siamo una coppia", 2), ("as a couple", 2),
                          ("a couple", 2), ("io e mia moglie", 2), ("io e il mio compagno", 2),
                          ("me and my wife", 2), ("my husband and I", 2), ("da solo", 1),
                          ("da sola", 1), ("just me", 1), ("on my own", 1), ("alone", 1),
                          ("famiglia di 4", 4), ("a family of five", 5), ("group of 6", 6),
                          ("due coppie", 4), ("three couples", 6)]:
            with self.subTest(text=text):
                self.assertEqual(parse_pax(text), pax)

    def test_number_beats_phrase(self):
        self.assertEqual(parse_pax("io e mia moglie, in tutto siamo in 4"), 4)

    def test_couple_of_days_is_not_pax(self):
        self.assertIsNone(parse_pax("a couple of days of padel"))
```

In `BudgetTest` aggiungi:

```python
    def test_new_forms(self):
        for text, budget in [("budget 2k", 2000), ("max 1,5k", 1500), ("1.5k euro", 1500),
                             ("sotto i 900 euro", 900), ("sotto 900", 900), ("non oltre 700", 700),
                             ("below 650", 650), ("at most 1000", 1000), ("tetto di 1200", 1200)]:
            with self.subTest(text=text):
                self.assertEqual(parse_budget(text), Decimal(budget))

    def test_number_before_people_is_not_budget(self):
        self.assertIsNone(parse_budget("massimo 4 persone"))
        self.assertIsNone(parse_budget("max 3 nights"))
        self.assertIsNone(parse_budget("massimo 40 persone"))
        self.assertEqual(parse_intent("padel a ottobre, massimo 4 persone", today=TODAY).criteria.pax, 4)

    def test_per_person(self):
        self.assertTrue(is_per_person("500 euro a testa"))
        self.assertTrue(is_per_person("400 euros each"))
        self.assertTrue(is_per_person("600 per person"))
        self.assertFalse(is_per_person("per persone 4"))
        self.assertFalse(is_per_person("massimo 800 euro"))

    def test_per_person_budget(self):
        c = parse_intent("padel a ottobre, 500 euro a testa, siamo in 3", today=TODAY).criteria
        self.assertEqual(c.budget, Decimal("1500"))
        c = parse_intent("padel a ottobre, 500 euro a testa", today=TODAY).criteria
        self.assertEqual(c.budget, Decimal("500"))
        self.assertIsNone(c.pax)
```

In `LanguageTest` aggiungi:

```python
    def test_new_markers(self):
        self.assertEqual(detect_language("tennis in early November, just me"), "en")
        self.assertEqual(detect_language("padel tra il 5 e l'8 dicembre, in coppia"), "it")
        self.assertEqual(detect_language("padel a Lloret de Mar a ottobre in 2"), "it")
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_intent.py" -v`
Expected: FAIL su `TableTest` (nuove righe), `PaxTest.test_new_forms`, `BudgetTest.*`, ERROR all'import di `is_per_person`.

- [ ] **Step 3: Implementa**

In `vela/domain/intent.py`:

1. Estendi i marcatori:

```python
IT_MARKERS = {"un", "una", "di", "del", "della", "per", "siamo", "con", "massimo", "vorrei",
              "voglio", "noi", "persone", "giorni", "il", "la", "viaggio", "vacanza", "due",
              "tre", "quattro", "fine", "settimana", "euro", "e", "dal", "al", "tra", "fra",
              "coppia", "coppie", "io", "mia", "mio", "moglie", "marito", "prossimo", "mese",
              "sotto", "testa", "solo", "sola", "famiglia", "gruppo", "metà", "inizio",
              "vorremmo", "giocare"}
EN_MARKERS = {"the", "of", "for", "we", "are", "with", "max", "want", "would", "like", "people",
              "under", "and", "two", "three", "four", "our", "my", "trip", "holiday", "us",
              "euros", "next", "camp", "from", "to", "between", "month", "couple", "couples",
              "each", "just", "early", "late", "mid", "family", "group", "alone", "players",
              "adults", "wife", "husband", "friends", "below"}
```

2. Sostituisci `_PAX_PATTERNS` con pattern e moltiplicatori, e aggiungi le frasi fisse:

```python
# (pattern, moltiplicatore): il numero catturato × moltiplicatore; i numeri espliciti vincono
_PAX_PATTERNS = [
    (re.compile(r"\b(\w+)\s+(?:coppie|couples)\b"), 2),
    (re.compile(r"\bsiamo in (\w+)"), 1),
    (re.compile(r"\bwe are (\w+)"), 1),
    (re.compile(r"\bwe're (\w+)"), 1),
    (re.compile(r"\b(\w+)\s+(?:persone|adulti|giocatori|amici|people|adults|players|friends|pax)\b"), 1),
    (re.compile(r"\b(\w+)\s+of us\b"), 1),
    (re.compile(r"\b(?:famiglia|gruppo|family|group)\s+(?:di|of)\s+(\w+)"), 1),
    (re.compile(r"\b(?:per|for)\s+(\w+)\b"), 1),
    (re.compile(r"\bx\s?(\d+)\b"), 1),
    (re.compile(r"\bin\s+(\d+)\b"), 1),
]
_PAX_PHRASES = [
    (re.compile(r"\b(?:in coppia|una coppia|as a couple|a couple\b(?! of)|"
                r"io e (?:mia|mio|il mio|la mia|un|una)\b|me and my\b|"
                r"my (?:wife|husband|partner|girlfriend|boyfriend|friend) and i\b)"), 2),
    (re.compile(r"\b(?:da sol[oa]|solo io|io solo|just me|only me|on my own|by myself|alone)\b"), 1),
]
```

e sostituisci `parse_pax`:

```python
def parse_pax(text: str) -> Optional[int]:
    low = text.lower()
    for pattern, factor in _PAX_PATTERNS:
        for m in pattern.finditer(low):
            value = _to_int(m.group(1))
            if value is not None and 1 <= value * factor <= MAX_PAX:
                return value * factor
    for pattern, value in _PAX_PHRASES:
        if pattern.search(low):
            return value
    return None
```

3. Sostituisci `_BUDGET_PATTERNS` e `parse_budget` e aggiungi `is_per_person`:

```python
_NOT_MONEY_AFTER = (r"(?!\s*(?:persone|persona|adulti|giocatori|amici|people|persons|adults|"
                    r"players|friends|pax|notti|nights|giorni|days|stelle|stars))")
_BUDGET_PATTERNS = [
    re.compile(r"(?:al massimo|massimo|max|budget|under|up to|fino a|entro|non più di|non oltre|"
               r"no more than|not more than|less than|meno di|sotto(?: i| ai| a)?|below|at most|"
               r"tetto(?: di)?)\s*(?:di\s+)?(?:€|eur|euro|euros)?\s*(\d[\d.,]*+)" + _NOT_MONEY_AFTER),
    re.compile(r"(\d[\d.,]*+)\s*(?:€|euros?\b|eur\b)"),
    re.compile(r"€\s*(\d[\d.,]*+)"),
]
_THOUSANDS_K = re.compile(r"(\d+(?:[.,]\d+)?)\s*k\b")
_PER_PERSON = re.compile(r"\b(?:a testa|a persona|per persona|each|per person|per head|pp)\b")


def _expand_thousands(low: str) -> str:
    """'2k' → '2000', '1,5k' → '1500'."""
    return _THOUSANDS_K.sub(
        lambda m: format((Decimal(m.group(1).replace(",", ".")) * 1000).quantize(Decimal(1)), "f"),
        low)


def parse_budget(text: str) -> Optional[Decimal]:
    low = _expand_thousands(text.lower())
    for pattern in _BUDGET_PATTERNS:
        m = pattern.search(low)
        if m:
            value = _to_money(m.group(1))
            if value is not None and value > 0:
                return value
    return None


def is_per_person(text: str) -> bool:
    return _PER_PERSON.search(text.lower()) is not None
```

4. In `parse_intent`, sostituisci la costruzione di `criteria` con:

```python
    pax = parse_pax(text) or profile.pax
    budget = parse_budget(text)
    if budget is not None and pax and is_per_person(text):
        budget = budget * pax
    criteria = Criteria(
        sport=parse_sport(text),
        area=geo.find_area(text),
        period=parse_period(text, today),
        pax=pax,
        budget=budget,
        language=detect_language(text),
    )
```

- [ ] **Step 4: Verifica che passino**

Run: `uv run python -m unittest discover -s tests -p "test_intent.py" -v`
Expected: PASS (tutte le 32 righe di `TableTest` e i test M2).
Se una riga fallisce, correggi il pattern, non l'atteso: gli attesi sono la specifica. Poi `uv run python -m unittest discover -s tests` → OK.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/intent.py tests/test_intent.py
git commit -m "Extend pax, budget and language parsing; grow the parser table to 32 cases"
```

---

### Task 4: Porta del fallback e gate in `parse_intent`

**Files:**
- Create: `vela/ports/llm.py`
- Modify: `vela/domain/intent.py` (`parse_intent`, `_llm_overrides`), `vela/domain/usecases.py` (`Vela.__init__`, `create_intent`)
- Test: `tests/test_intent.py` (`FallbackTest`), `tests/test_usecases.py` (`CreateIntentTest`)

**Interfaces:**
- Produces: `vela.ports.llm.IntentExtractor` (Protocol con `extract(text: str, today: date) -> Optional[dict]`); `parse_intent(text, profile=None, today=None, extractor=None) -> ParseResult`; `Vela(repos, hofj, payments, defaults=None, now=None, new_id=None, extractor=None)` con attributo `vela.extractor`; costante `LLM_PERIOD_LABEL = "llm"`.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_intent.py`:

```python
class FakeExtractor:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def extract(self, text, today):
        self.calls.append((text, today))
        if self.error:
            raise self.error
        return self.result


VAGUE = "una vacanza con la racchetta in Spagna per due"   # né sport né periodo
GOOD = {"sport": "padel", "area": "Greece", "period_start": "2026-11-01",
        "period_end": "2026-11-30", "pax": 3, "budget": 1500}


class FallbackTest(unittest.TestCase):
    def test_not_called_when_sport_found(self):
        fx = FakeExtractor(GOOD)
        parse_intent("padel in Spagna per due", today=TODAY, extractor=fx)
        self.assertEqual(fx.calls, [])

    def test_not_called_when_period_found(self):
        fx = FakeExtractor(GOOD)
        parse_intent("qualcosa a ottobre per due", today=TODAY, extractor=fx)
        self.assertEqual(fx.calls, [])

    def test_called_when_both_missing_and_overrides(self):
        fx = FakeExtractor(GOOD)
        r = parse_intent(VAGUE, today=TODAY, extractor=fx)
        self.assertEqual(fx.calls, [(VAGUE, TODAY)])
        c = r.criteria
        self.assertEqual(c.sport, "padel")
        self.assertEqual(c.area, Area("country", "Grecia", "GR"))
        self.assertEqual(c.period, Period(date(2026, 11, 1), date(2026, 11, 30), "llm"))
        self.assertEqual(c.pax, 3)
        self.assertEqual(c.budget, Decimal("1500"))
        self.assertEqual(c.language, "it")
        self.assertIsNone(r.question)

    def test_null_fields_keep_parser_values(self):
        fx = FakeExtractor({"sport": "tennis", "area": None, "period_start": None,
                            "period_end": None, "pax": None, "budget": None})
        c = parse_intent(VAGUE, today=TODAY, extractor=fx).criteria
        self.assertEqual((c.sport, c.area.country_code, c.pax), ("tennis", "ES", 2))

    def test_invalid_fields_are_ignored(self):
        baseline = parse_intent(VAGUE, today=TODAY).criteria
        for bad in [
            {"sport": "golf", "area": "Atlantide", "period_start": "2026-12-10",
             "period_end": "2026-12-01", "pax": 0, "budget": -5},
            {"sport": 7, "area": 3, "period_start": "2025-01-01", "period_end": "2025-01-05",
             "pax": True, "budget": "abc"},
            {"period_start": "ieri", "period_end": "domani", "pax": 50, "budget": True},
            {"period_start": "2026-11-01"},
        ]:
            with self.subTest(bad=bad):
                r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor(bad))
                self.assertEqual(r.criteria, baseline)
                self.assertEqual(r.question, QUESTION_SPORT_OR_PERIOD)

    def test_extractor_error_is_ignored(self):
        r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor(error=RuntimeError("boom")))
        self.assertEqual(r.question, QUESTION_SPORT_OR_PERIOD)

    def test_extractor_returning_none_or_junk(self):
        for result in (None, "testo", ["x"]):
            with self.subTest(result=result):
                r = parse_intent(VAGUE, today=TODAY, extractor=FakeExtractor(result))
                self.assertEqual(r.question, QUESTION_SPORT_OR_PERIOD)

    def test_no_extractor_no_error(self):
        self.assertEqual(parse_intent(VAGUE, today=TODAY).question, QUESTION_SPORT_OR_PERIOD)
```

In `tests/test_usecases.py`, dentro `CreateIntentTest`:

```python
    def test_fallback_extractor_is_used(self):
        class Fx:
            calls = 0

            def extract(self, text, today):
                Fx.calls += 1
                return {"sport": "padel", "area": None, "period_start": "2026-10-01",
                        "period_end": "2026-10-31", "pax": None, "budget": None}
        vela = make_vela()
        vela.extractor = Fx()
        r = vela.create_intent("una vacanza con la racchetta in Spagna per due")
        self.assertIsInstance(r, IntentCreated)
        self.assertEqual(r.criteria.sport, "padel")
        self.assertEqual(Fx.calls, 1)

    def test_default_has_no_extractor(self):
        self.assertIsNone(make_vela().extractor)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_intent.py" -v` e `-p "test_usecases.py"`
Expected: ERROR (`parse_intent() got an unexpected keyword argument 'extractor'`, `'Vela' object has no attribute 'extractor'`).

- [ ] **Step 3: Implementa**

Crea `vela/ports/llm.py`:

```python
"""Porta del fallback LLM per l'estrazione dei criteri di un intento (RF-03)."""
from datetime import date
from typing import Optional, Protocol


class IntentExtractor(Protocol):
    def extract(self, text: str, today: date) -> Optional[dict]:
        """Campi grezzi `sport`, `area`, `period_start`, `period_end` (ISO), `pax`, `budget`,
        ognuno `None` se il testo non lo dice; `None` se il servizio non è disponibile.
        Il dominio valida ogni campo prima di usarlo."""
        ...
```

In `vela/domain/intent.py`:

- aggiorna la docstring del modulo: `Parser deterministico degli intenti, italiano e inglese (RF-02, RF-04), con fallback LLM opzionale (RF-03).` seguita dalle frasi esistenti su domanda e `today`;
- aggiungi gli import `import logging` e `from dataclasses import dataclass, replace` (sostituisce l'import di `dataclass`), `from vela.ports.llm import IntentExtractor`;
- aggiungi sotto le costanti:

```python
log = logging.getLogger(__name__)
LLM_PERIOD_LABEL = "llm"
```

- aggiungi prima di `parse_intent`:

```python
def _llm_overrides(raw: dict, today: date) -> dict:
    """Campi validi dell'output del fallback; quelli invalidi o nulli non compaiono."""
    out = {}
    sport = raw.get("sport")
    if isinstance(sport, str) and sport.lower() in ("padel", "tennis"):
        out["sport"] = sport.lower()
    area = raw.get("area")
    if isinstance(area, str):
        found = geo.find_area(area)
        if found is not None:
            out["area"] = found
    try:
        start = date.fromisoformat(raw.get("period_start"))
        end = date.fromisoformat(raw.get("period_end"))
    except (TypeError, ValueError):
        start = end = None
    if start is not None and start <= end and end >= today:
        out["period"] = Period(start, end, LLM_PERIOD_LABEL)
    pax = raw.get("pax")
    if isinstance(pax, int) and not isinstance(pax, bool) and 1 <= pax <= MAX_PAX:
        out["pax"] = pax
    budget = raw.get("budget")
    if isinstance(budget, (int, float, str)) and not isinstance(budget, bool):
        try:
            value = Decimal(str(budget))
        except ArithmeticError:
            value = None
        if value is not None and value.is_finite() and value > 0:
            out["budget"] = value.quantize(Decimal("0.01"))
    return out


def _with_fallback(criteria: Criteria, text: str, today: date,
                   extractor: IntentExtractor) -> Criteria:
    try:
        raw = extractor.extract(text, today)
    except Exception as exc:   # il fallback non deve mai rompere create_intent
        log.warning("fallback LLM fallito: %s", type(exc).__name__)
        return criteria
    if not isinstance(raw, dict):
        return criteria
    return replace(criteria, **_llm_overrides(raw, today))
```

- cambia la firma e il corpo di `parse_intent`:

```python
def parse_intent(text: str, profile: Optional[TravelerProfile] = None,
                 today: Optional[date] = None,
                 extractor: Optional[IntentExtractor] = None) -> ParseResult:
    today = today or date.today()
    profile = profile or TravelerProfile()
    # ... pax, budget, criteria come nel Task 3 ...
    if criteria.sport is None and criteria.period is None and extractor is not None:
        criteria = _with_fallback(criteria, text, today, extractor)
    question = None
    if criteria.sport is None and criteria.period is None:
        question = QUESTION_SPORT_OR_PERIOD
    elif criteria.pax is None:
        question = QUESTION_PAX
    return ParseResult(criteria, question)
```

In `vela/domain/usecases.py`:

```python
from vela.ports.llm import IntentExtractor
```

`Vela.__init__` riceve `extractor: Optional[IntentExtractor] = None` come ultimo parametro e fa `self.extractor = extractor`; `create_intent` chiama
`parse_intent(text, profile, today=self.now().date(), extractor=self.extractor)`.

- [ ] **Step 4: Verifica che passino**

Run: `uv run python -m unittest discover -s tests` → OK.

- [ ] **Step 5: Commit**

```bash
git add vela/ports/llm.py vela/domain/intent.py vela/domain/usecases.py tests/test_intent.py tests/test_usecases.py
git commit -m "Add the LLM extractor port and the fallback gate to the intent parser"
```

---

### Task 5: Adapter Haiku, dipendenza `anthropic`, wiring e prova manuale

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Create: `vela/adapters/haiku.py`, `scripts/try_haiku.py`
- Modify: `vela/app.py` (`build_vela`), `README.md`
- Test: `tests/test_haiku.py` (nuovo), `tests/test_app_replay.py` (`ModeTest`)

**Interfaces:**
- Consumes: `IntentExtractor` (Task 4), `Vela(..., extractor=...)` (Task 4).
- Produces: `vela.adapters.haiku.HaikuExtractor(client)`, `HaikuExtractor.from_api_key(api_key: str)`, costanti `MODEL = "claude-haiku-4-5-20251001"`, `TOOL_NAME = "record_criteria"`, `TIMEOUT_SECONDS = 5.0`, `MAX_RETRIES = 1`.

- [ ] **Step 1: Aggiungi la dipendenza**

Run: `uv add anthropic`
Expected: `pyproject.toml` contiene `"anthropic>=<versione>"` tra le `dependencies`; `uv.lock` aggiornato. Annota la versione installata (`uv run python -c "import anthropic; print(anthropic.__version__)"`) nel messaggio del report finale.
Nota SDK: dalla 1.x l'SDK usa `httpx2` invece di `httpx`; per costruire eccezioni nei test serve un `Request` della libreria che l'SDK usa (helper `_request()` sotto).

- [ ] **Step 2: Scrivi i test che falliscono**

Crea `tests/test_haiku.py`:

```python
"""Adapter Haiku (RF-03) con un client finto: nessuna chiamata ad Anthropic."""
import unittest
from datetime import date
from types import SimpleNamespace

import anthropic

from vela.adapters.haiku import (MAX_RETRIES, MODEL, TIMEOUT_SECONDS, TOOL, TOOL_NAME,
                                 HaikuExtractor)

TODAY = date(2026, 9, 25)
INPUT = {"sport": "padel", "area": "Spain", "period_start": "2026-10-01",
         "period_end": "2026-10-31", "pax": 2, "budget": 800}


def _request():
    try:
        import httpx2 as http
    except ImportError:
        import httpx as http
    return http.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def client(response=None, error=None):
    return SimpleNamespace(messages=FakeMessages(response, error))


def tool_use(name=TOOL_NAME, data=INPUT):
    return SimpleNamespace(type="tool_use", name=name, input=data)


class HaikuExtractorTest(unittest.TestCase):
    def test_request_shape(self):
        c = client(SimpleNamespace(content=[tool_use()], stop_reason="tool_use"))
        HaikuExtractor(c).extract("padel a ottobre", TODAY)
        call = c.messages.calls[0]
        self.assertEqual(call["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(MODEL, call["model"])
        self.assertEqual(call["tool_choice"], {"type": "tool", "name": TOOL_NAME})
        self.assertEqual(call["tools"], [TOOL])
        self.assertIn("2026-09-25", call["messages"][0]["content"])
        self.assertIn("padel a ottobre", call["messages"][0]["content"])
        self.assertLessEqual(call["max_tokens"], 1024)

    def test_schema_matches_domain_fields(self):
        props = TOOL["input_schema"]["properties"]
        self.assertEqual(set(props), {"sport", "area", "period_start", "period_end", "pax", "budget"})
        self.assertEqual(set(TOOL["input_schema"]["required"]), set(props))

    def test_returns_tool_input(self):
        c = client(SimpleNamespace(content=[SimpleNamespace(type="text", text="ok"), tool_use()],
                                   stop_reason="tool_use"))
        self.assertEqual(HaikuExtractor(c).extract("x", TODAY), INPUT)

    def test_no_tool_use_is_none(self):
        c = client(SimpleNamespace(content=[SimpleNamespace(type="text", text="?")],
                                   stop_reason="end_turn"))
        self.assertIsNone(HaikuExtractor(c).extract("x", TODAY))

    def test_other_tool_or_bad_input_is_none(self):
        self.assertIsNone(HaikuExtractor(client(SimpleNamespace(
            content=[tool_use(name="altro")], stop_reason="tool_use"))).extract("x", TODAY))
        self.assertIsNone(HaikuExtractor(client(SimpleNamespace(
            content=[tool_use(data="testo")], stop_reason="tool_use"))).extract("x", TODAY))

    def test_api_errors_are_none(self):
        for error in (anthropic.APIConnectionError(request=_request()),
                      anthropic.APITimeoutError(request=_request())):
            with self.subTest(error=type(error).__name__):
                with self.assertLogs("vela.adapters.haiku", level="WARNING") as logs:
                    self.assertIsNone(HaikuExtractor(client(error=error)).extract("segreto", TODAY))
                self.assertNotIn("segreto", "\n".join(logs.output))

    def test_from_api_key_configures_client(self):
        ex = HaikuExtractor.from_api_key("sk-ant-test")
        self.assertIsInstance(ex.client, anthropic.Anthropic)
        self.assertEqual(ex.client.timeout, TIMEOUT_SECONDS)
        self.assertEqual(ex.client.max_retries, MAX_RETRIES)
```

In `tests/test_app_replay.py`, dentro `ModeTest`:

```python
    def test_no_key_no_extractor(self):
        app = create_app(Settings(database_url="sqlite://"))
        self.assertIsNone(app.state.vela.extractor)

    def test_key_builds_haiku_extractor_without_calling_it(self):
        from vela.adapters.haiku import HaikuExtractor
        app = create_app(Settings(database_url="sqlite://", anthropic_api_key="sk-ant-test"))
        self.assertIsInstance(app.state.vela.extractor, HaikuExtractor)
```

- [ ] **Step 3: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_haiku.py" -v`
Expected: ERROR (`No module named 'vela.adapters.haiku'`).

- [ ] **Step 4: Implementa**

Crea `vela/adapters/haiku.py`:

```python
"""Fallback Claude Haiku 4.5 per l'estrazione dei criteri (RF-03).

Una sola chiamata con lo strumento `record_criteria` forzato: il suo input è lo schema dei
criteri. Ogni errore dell'API diventa `None` e resta il risultato del parser deterministico.
Il testo dell'intento non viene mai loggato.
"""
import logging
from datetime import date
from typing import Optional

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_SECONDS = 5.0
MAX_RETRIES = 1
MAX_TOKENS = 512
TOOL_NAME = "record_criteria"
TOOL = {
    "name": TOOL_NAME,
    "description": "Registra i criteri del viaggio letti nel testo. null per ogni campo non detto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sport": {"type": ["string", "null"], "enum": ["padel", "tennis", None]},
            "area": {"type": ["string", "null"],
                     "description": "Paese, regione o città come scritto nel testo."},
            "period_start": {"type": ["string", "null"], "description": "Inizio, YYYY-MM-DD."},
            "period_end": {"type": ["string", "null"], "description": "Fine, YYYY-MM-DD."},
            "pax": {"type": ["integer", "null"], "description": "Numero di persone."},
            "budget": {"type": ["number", "null"],
                       "description": "Budget totale massimo in euro per tutto il gruppo."},
        },
        "required": ["sport", "area", "period_start", "period_end", "pax", "budget"],
        "additionalProperties": False,
    },
}
SYSTEM = ("Estrai i criteri di un viaggio di padel o tennis dal testo del viaggiatore, scritto in "
          "italiano o in inglese. Chiama sempre record_criteria. Usa null per ogni campo che il "
          "testo non dice: non inventare. Le date sono nel formato YYYY-MM-DD e non precedono la "
          "data di oggi indicata nel messaggio. Il budget è il totale massimo in euro per tutto il "
          "gruppo.")


class HaikuExtractor:
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_api_key(cls, api_key: str) -> "HaikuExtractor":
        return cls(anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS,
                                       max_retries=MAX_RETRIES))

    def extract(self, text: str, today: date) -> Optional[dict]:
        try:
            message = self.client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM, tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user",
                           "content": "Oggi è %s.\n\n%s" % (today.isoformat(), text)}])
        except anthropic.APIError as exc:
            log.warning("fallback Haiku non disponibile: %s %s", type(exc).__name__,
                        getattr(exc, "status_code", ""))
            return None
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == TOOL_NAME:
                return dict(block.input) if isinstance(block.input, dict) else None
        log.warning("fallback Haiku senza record_criteria (stop_reason=%s)",
                    getattr(message, "stop_reason", None))
        return None
```

In `vela/app.py`, dentro `build_vela` prima di creare `Vela`:

```python
    extractor = None
    if settings.anthropic_api_key:   # RF-03: senza chiave il fallback è spento, senza errori
        from vela.adapters.haiku import HaikuExtractor
        extractor = HaikuExtractor.from_api_key(settings.anthropic_api_key)
    vela = Vela(PostgresRepositories(engine), hofj, FakePayments(settings.vela_public_url),
                DEFAULT_TRAVELER, extractor=extractor)
```

Crea `scripts/try_haiku.py`:

```python
"""Prova manuale del fallback Haiku (RF-03): esegue UNA chiamata reale ad Anthropic.

Non è un test automatico. Serve ANTHROPIC_API_KEY nell'ambiente:
    uv run python scripts/try_haiku.py "un'idea per il ponte dei morti con la racchetta, siamo in 2"
Stampa i criteri risultanti e l'eventuale domanda. Senza chiave non chiama nulla.
"""
import os
import sys
from datetime import date

from vela.adapters.haiku import HaikuExtractor
from vela.domain.intent import parse_intent
from vela.domain.models import criteria_to_dict

DEFAULT_TEXT = "un'idea per il ponte dei morti con la racchetta, siamo in 2"


def main(argv) -> int:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY assente: nessuna chiamata.")
        return 1
    text = argv[1] if len(argv) > 1 else DEFAULT_TEXT
    result = parse_intent(text, today=date.today(), extractor=HaikuExtractor.from_api_key(key))
    print(criteria_to_dict(result.criteria))
    print("domanda:", result.question)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

In `README.md`, nella riga di `ANTHROPIC_API_KEY`, completa la descrizione: `Se presente abilita il fallback Claude Haiku 4.5 (claude-haiku-4-5-20251001) quando il parser non trova né sport né periodo; timeout 5 s, 1 retry. Prova manuale (una chiamata): uv run python scripts/try_haiku.py "testo".`

- [ ] **Step 5: Verifica che passino**

Run: `uv run python -m unittest discover -s tests` → OK, senza rete.
Controlla anche che i test non abbiano chiamato Anthropic: nessun test costruisce un client reale tranne `test_from_api_key_configures_client`, che non invia richieste.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock vela/adapters/haiku.py vela/app.py scripts/try_haiku.py README.md tests/test_haiku.py tests/test_app_replay.py
git commit -m "Add the Claude Haiku fallback adapter, wired only when ANTHROPIC_API_KEY is set"
```

- [ ] **Step 7 (manuale, opzionale, a pagamento): una chiamata reale**

Solo dopo aver detto all'utente "eseguo 1 chiamata a `claude-haiku-4-5-20251001` con `scripts/try_haiku.py`" e aver ricevuto l'OK. La chiave non va mai stampata: se sta in `.env`, caricala nella stessa riga (`set -a; . ./.env; set +a; uv run python scripts/try_haiku.py`). Annota l'esito (criteri ottenuti, nessun errore) nel report del task, non nel repo.

---

### Task 6: Interpretazione del motivo di rifiuto (`refine`)

**Files:**
- Create: `vela/domain/refine.py`
- Test: `tests/test_refine.py`

**Interfaces:**
- Consumes: `geo.move`, `geo.find_area` (Task 1); `parse_budget`, `parse_pax`, `parse_period`, `parse_sport` (Task 2-3).
- Produces: `refine(criteria: Criteria, reason: Optional[str], proposal: Proposal, product_area: Optional[Area], today: date) -> Criteria`; `PRICE_FACTOR = Decimal("0.8")`.

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/test_refine.py`:

```python
"""Rifiuto con motivo (RF-08): dal motivo in testo libero ai criteri aggiornati."""
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from support import NOW, TODAY
from vela.domain.models import Area, Criteria, Period, Proposal
from vela.domain.refine import refine

SPAIN = Area("country", "Spagna", "ES")
VALENCIA = Area("city", "Valencia", "ES")
OCTOBER = Period(date(2026, 10, 1), date(2026, 10, 31), "ottobre")
CRIT = Criteria("padel", SPAIN, OCTOBER, 2, Decimal("800"), "it")
PROPOSAL = Proposal("p1", "i1", "1", date(2026, 10, 1), date(2026, 10, 4), 2, Decimal("350"),
                    "EUR", "Motivo.", NOW)   # totale 700 → 80% = 560


def refined(reason, criteria=CRIT, area=VALENCIA):
    return refine(criteria, reason, PROPOSAL, area, TODAY)


class PriceTest(unittest.TestCase):
    def test_price_words_lower_budget_to_80_percent(self):
        for reason in ("troppo caro", "Troppo cara!", "costa troppo", "vorrei qualcosa di più economico",
                       "too expensive", "a bit too pricey", "something cheaper"):
            with self.subTest(reason=reason):
                self.assertEqual(refined(reason).budget, Decimal("560.00"))

    def test_explicit_figure_wins(self):
        self.assertEqual(refined("troppo caro, max 500 euro").budget, Decimal("500"))
        self.assertEqual(refined("massimo 650 euro").budget, Decimal("650"))

    def test_without_budget(self):
        self.assertEqual(refined("troppo caro", replace(CRIT, budget=None)).budget, Decimal("560.00"))

    def test_never_raises_budget(self):
        self.assertEqual(refined("troppo caro", replace(CRIT, budget=Decimal("400"))).budget,
                         Decimal("400"))


class DirectionTest(unittest.TestCase):
    def test_south_and_north(self):
        self.assertEqual(refined("più a sud").area, Area("city", "Alicante", "ES"))
        self.assertEqual(refined("further north please").area, Area("city", "Tarragona", "ES"))

    def test_no_entry_keeps_area(self):
        self.assertEqual(refined("più a sud", area=Area("region", "Lanzarote", "ES")).area, SPAIN)
        self.assertEqual(refined("più a sud", area=None).area, SPAIN)

    def test_direction_beats_named_place(self):
        self.assertEqual(refined("più a sud, magari in Grecia").area, Area("city", "Alicante", "ES"))


class OtherFieldsTest(unittest.TestCase):
    def test_named_place(self):
        self.assertEqual(refined("meglio in Grecia").area, Area("country", "Grecia", "GR"))

    def test_period(self):
        self.assertEqual(refined("a novembre").period,
                         Period(date(2026, 11, 1), date(2026, 11, 30), "novembre"))
        self.assertEqual(refined("dal 10 al 14 novembre").period.start, date(2026, 11, 10))

    def test_sport_and_pax(self):
        self.assertEqual(refined("preferisco il tennis").sport, "tennis")
        self.assertEqual(refined("siamo in 4").pax, 4)

    def test_rules_combine(self):
        c = refined("troppo caro e a novembre")
        self.assertEqual((c.budget, c.period.start), (Decimal("560.00"), date(2026, 11, 1)))
        self.assertEqual((c.sport, c.area, c.pax, c.language), ("padel", SPAIN, 2, "it"))


class UnrecognizedTest(unittest.TestCase):
    def test_unrecognized_reasons_keep_criteria(self):
        for reason in ("più vicino", "closer to home", "non mi piace", "no", "", None):
            with self.subTest(reason=reason):
                self.assertIs(refined(reason), CRIT)

    def test_idempotent(self):
        once = refined("troppo caro")
        self.assertEqual(refine(once, "troppo caro", PROPOSAL, VALENCIA, TODAY), once)

    def test_language_is_kept(self):
        en = replace(CRIT, language="en")
        self.assertEqual(refined("too expensive", en).language, "en")
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_refine.py" -v`
Expected: ERROR (`No module named 'vela.domain.refine'`).

- [ ] **Step 3: Implementa**

Crea `vela/domain/refine.py`:

```python
"""Interpretazione del motivo di un rifiuto (RF-08): criteri aggiornati, funzione pura.

Regole it/en che si combinano: budget (una cifra nel motivo, altrimenti "troppo caro" porta il
budget all'80% del totale proposto, senza mai alzarlo), direzione ("più a sud"/"più a nord"
con le tabelle di `geo`), luogo esplicito, periodo, sport e persone con gli stessi parser
dell'intento. Un motivo non riconosciuto restituisce gli stessi criteri: il prodotto rifiutato
resta comunque escluso. Stesso motivo e stessa proposta danno sempre lo stesso risultato.
"""
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.intent import parse_budget, parse_pax, parse_period, parse_sport
from vela.domain.models import Area, Criteria, Proposal

PRICE_FACTOR = Decimal("0.8")

_PRICE = re.compile(r"\b(?:troppo car[oaie]|costa troppo|costano troppo|costos[oaie]|"
                    r"più economic[oaie]|meno car[oaie]|too expensive|too pricey|too much|"
                    r"cheaper|less expensive)\b")
_SOUTH = re.compile(r"\b(?:più a sud|più al sud|più giù|further south|farther south|more south|"
                    r"more to the south)\b")
_NORTH = re.compile(r"\b(?:più a nord|più al nord|più su|further north|farther north|more north|"
                    r"more to the north)\b")


def refine(criteria: Criteria, reason: Optional[str], proposal: Proposal,
           product_area: Optional[Area], today: date) -> Criteria:
    low = (reason or "").lower()
    changes = {}
    budget = parse_budget(low)
    if budget is not None:
        changes["budget"] = budget
    elif _PRICE.search(low):
        lowered = (proposal.price_from * proposal.pax * PRICE_FACTOR).quantize(Decimal("0.01"))
        changes["budget"] = lowered if criteria.budget is None else min(lowered, criteria.budget)
    direction = "south" if _SOUTH.search(low) else "north" if _NORTH.search(low) else None
    if direction is not None:
        moved = geo.move(product_area, direction)
        if moved is not None:
            changes["area"] = moved
    else:
        area = geo.find_area(low)
        if area is not None:
            changes["area"] = area
    for name, value in (("period", parse_period(low, today)), ("sport", parse_sport(low)),
                        ("pax", parse_pax(low))):
        if value is not None:
            changes[name] = value
    return replace(criteria, **changes) if changes else criteria
```

- [ ] **Step 4: Verifica che passino**

Run: `uv run python -m unittest discover -s tests -p "test_refine.py" -v` → PASS; poi l'intera suite → OK.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/refine.py tests/test_refine.py
git commit -m "Interpret rejection reasons into updated intent criteria"
```

---

### Task 7: `IntentRepository.update_criteria` (memoria e Postgres)

**Files:**
- Modify: `vela/ports/repositories.py`, `vela/adapters/repo_memory.py`, `vela/adapters/repo_postgres.py`
- Test: `tests/repo_contract.py` (eseguito da `tests/test_repo_memory.py` sempre e da `tests/test_repo_postgres.py` con `DATABASE_URL`)

**Interfaces:**
- Produces: `IntentRepository.update_criteria(intent_id: str, criteria: Criteria) -> None`. Un id sconosciuto non ha effetto e non solleva.

- [ ] **Step 1: Scrivi il test che fallisce**

In `tests/repo_contract.py` aggiungi `Area` all'import da `vela.domain.models` e, dopo `test_intents_round_trip`:

```python
    def test_intents_update_criteria(self):
        self.repos.intents.add(intent())
        new = replace(CRITERIA, budget=Decimal("560.00"), area=Area("city", "Alicante", "ES"),
                      language="en")
        self.repos.intents.update_criteria("i1", new)
        got = self.repos.intents.get("i1")
        self.assertEqual(got.criteria, new)
        self.assertEqual((got.id, got.text, got.profile, got.created_at),
                         ("i1", intent().text, PROFILE, NOW))
        self.repos.intents.update_criteria("nope", new)   # nessun effetto, nessun errore
        self.assertIsNone(self.repos.intents.get("nope"))
```

- [ ] **Step 2: Verifica che fallisca**

Run: `uv run python -m unittest discover -s tests -p "test_repo_memory.py" -v`
Expected: ERROR (`'MemoryIntents' object has no attribute 'update_criteria'`).

- [ ] **Step 3: Implementa**

`vela/ports/repositories.py`: importa `Criteria` da `vela.domain.models` e aggiungi a `IntentRepository`:

```python
    def update_criteria(self, intent_id: str, criteria: Criteria) -> None: ...
```

`vela/adapters/repo_memory.py`: aggiungi `from dataclasses import replace` e in `MemoryIntents`:

```python
    def update_criteria(self, intent_id: str, criteria: Criteria) -> None:
        intent = self._items.get(intent_id)
        if intent is not None:
            self._items[intent_id] = replace(intent, criteria=criteria)
```

(aggiungi `Criteria` all'import dei modelli).

`vela/adapters/repo_postgres.py`, in `PostgresIntents`:

```python
    def update_criteria(self, intent_id: str, criteria: Criteria) -> None:
        with self.engine.begin() as conn:
            conn.execute(intents_t.update().where(intents_t.c.id == intent_id).values(
                criteria=criteria_to_dict(criteria), language=criteria.language))
```

(aggiungi `Criteria` all'import dei modelli).

- [ ] **Step 4: Verifica che passi**

Run: `uv run python -m unittest discover -s tests` → OK (il test Postgres è saltato senza `DATABASE_URL`).
Con il DB disponibile: `set -a; . ./.env; set +a; uv run python -m unittest discover -s tests -p "test_repo_postgres.py" -v` → PASS (schema `vela_test`). Il file `.env` non va aperto né stampato.

- [ ] **Step 5: Commit**

```bash
git add vela/ports/repositories.py vela/adapters/repo_memory.py vela/adapters/repo_postgres.py tests/repo_contract.py
git commit -m "Add update_criteria to the intent repositories"
```

---

### Task 8: `reject_proposal` aggiorna i criteri

**Files:**
- Modify: `vela/domain/usecases.py` (`reject_proposal`, nuovo `_refined`)
- Test: `tests/test_usecases.py` (`RejectProposalTest`)

**Interfaces:**
- Consumes: `refine` (Task 6), `repos.intents.update_criteria` (Task 7), `geo.area_of_destination`.
- Produces: comportamento di `Vela.reject_proposal(proposal_id, reason)` con firma invariata.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_usecases.py`, aggiungi `from vela.domain.models import Area` (o estendi l'import esistente) e in `RejectProposalTest`:

```python
    def test_too_expensive_lowers_budget(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)                  # prodotto 3, 350 × 2 = 700
        second = vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertEqual(vela.repos.intents.get(iid).criteria.budget, Decimal("560.00"))
        self.assertEqual(second.product.product_id, "4")
        self.assertIn("più economica", second.proposal.reason)

    def test_double_reject_does_not_lower_twice(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        vela.reject_proposal(first.proposal.id, "troppo caro")
        vela.reject_proposal(first.proposal.id, "troppo caro")
        self.assertEqual(vela.repos.intents.get(iid).criteria.budget, Decimal("560.00"))

    def test_further_south_changes_area(self):
        vela = make_vela([
            make_product(1, price=350, country="ES", destination="Valencia"),
            make_product(2, price=380, country="ES", destination="Barcellona"),
            make_product(3, price=600, country="ES", destination="Alicante"),
        ])
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        self.assertEqual(first.product.product_id, "1")
        second = vela.reject_proposal(first.proposal.id, "più a sud")
        self.assertEqual(vela.repos.intents.get(iid).criteria.area, Area("city", "Alicante", "ES"))
        self.assertEqual(second.product.product_id, "3")

    def test_new_period_in_reason(self):
        vela = make_vela([
            make_product(1, price=350, country="ES", destination="Valencia"),
            make_product(2, price=450, country="ES", destination="Madrid",
                         windows=(("2026-11-05", "2026-11-08"),)),
        ])
        iid = vela.create_intent(INTENT).intent_id
        first = vela.get_proposal(iid)
        second = vela.reject_proposal(first.proposal.id, "a novembre")
        self.assertEqual(second.product.product_id, "2")
        self.assertEqual(second.proposal.start_date, date(2026, 11, 5))

    def test_unknown_reason_keeps_criteria(self):
        vela = make_vela()
        iid = vela.create_intent(INTENT).intent_id
        before = vela.repos.intents.get(iid).criteria
        first = vela.get_proposal(iid)
        vela.reject_proposal(first.proposal.id, "più vicino")
        self.assertEqual(vela.repos.intents.get(iid).criteria, before)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests -p "test_usecases.py" -v`
Expected: FAIL (`budget` resta 800, area resta Spagna, `test_new_period_in_reason` → `NoMatch`).

- [ ] **Step 3: Implementa**

In `vela/domain/usecases.py`:

```python
from vela.domain import geo, say
from vela.domain.refine import refine
```

e sostituisci `reject_proposal`:

```python
    def reject_proposal(self, proposal_id: str, reason: str) -> Union[ProposalMade, NoMatch]:
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        self.repos.rejections.add(Rejection(intent.id, proposal.id, proposal.product_id,
                                            reason or "", self.now()))
        return self._propose(self._refined(intent, proposal, reason or ""))

    def _refined(self, intent: Intent, proposal: Proposal, reason: str) -> Intent:
        """RF-08: il motivo aggiorna i criteri dell'intento, persistiti prima della nuova scelta."""
        product = self.repos.products.get(proposal.product_id)
        area = geo.area_of_destination(product.destination, product.country) if product else None
        criteria = refine(intent.criteria, reason, proposal, area, self.now().date())
        if criteria == intent.criteria:
            return intent
        self.repos.intents.update_criteria(intent.id, criteria)
        return replace(intent, criteria=criteria)
```

Aggiorna la docstring della sezione `# --- RF-06..11` se cita il rifiuto senza criteri.

- [ ] **Step 4: Verifica che passino**

Run: `uv run python -m unittest discover -s tests` → OK, compresi i test M2 `test_reject_gives_a_different_product`, `test_never_proposes_a_rejected_product_again`, `test_reject_twice_same_proposal_is_idempotent` e `FullReplayFlowTest`.

- [ ] **Step 5: Commit**

```bash
git add vela/domain/usecases.py tests/test_usecases.py
git commit -m "Update intent criteria from the rejection reason before the next proposal"
```

---

### Task 9: Frasi, domande e motivazione in italiano e inglese

**Files:**
- Modify: `vela/domain/say.py` (riscritto), `vela/domain/intent.py` (domande), `vela/domain/chooser.py` (`_reason`), `vela/domain/usecases.py` (lingua)
- Test: `tests/test_say.py`, `tests/test_intent.py` (`QuestionTest`), `tests/test_chooser.py` (`ReasonAndWindowTest`), `tests/test_usecases.py`

**Interfaces:**
- Consumes: `geo.display_name`, `geo.area_by_name`, `geo.COUNTRIES` (Task 1).
- Produces: `say.fmt_date(d, lang="it")`, `say.fmt_money(v, lang="it")`, `say.say_intent_created(c)` (usa `c.language`), `say.say_proposal(product, p, lang="it")`, `say.say_no_match(criterion, lang="it")`, `say.say_missing(missing, lang="it")`, `say.say_accept(total, estimate, differs, lang="it")`, `say.say_status(status, code, reason, lang="it")`; `intent.QUESTION_SPORT_OR_PERIOD_EN`, `intent.QUESTION_PAX_EN`.

- [ ] **Step 1: Scrivi i test che falliscono**

In `tests/test_say.py` aggiungi:

```python
class EnglishTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(say.fmt_date(date(2026, 10, 1), "en"), "1 October 2026")
        self.assertEqual(say.fmt_money(Decimal("800"), "en"), "800 euros")
        self.assertEqual(say.fmt_money(Decimal("812.5"), "en"), "812.50 euros")

    def test_intent_created(self):
        c = Criteria("padel", Area("country", "Spagna", "ES"),
                     Period(date(2026, 10, 1), date(2026, 10, 31), "october"), 2, Decimal("800"), "en")
        s = say.say_intent_created(c)
        for piece in ("padel", "Spain", "1 October 2026", "31 October 2026", "2 people", "800 euros"):
            self.assertIn(piece, s)
        self.assertNotIn("Spagna", s)
        self.assertIn("1 person", say.say_intent_created(Criteria(pax=1, language="en")))

    def test_proposal(self):
        s = say.say_proposal(PRODUCT, PROPOSAL, "en")
        for piece in ("Magnifico Padel a Lanzarote", "THB Lanzarote Beach", "1 October 2026",
                      "4 October 2026", "2 people", "578 euros"):
            self.assertIn(piece, s)
        self.assertNotIn("http", s)

    def test_no_match(self):
        from vela.domain.chooser import FILTERS
        texts = {c: say.say_no_match(c, "en") for c in FILTERS}
        self.assertEqual(len(set(texts.values())), 5)
        self.assertIn("period", texts["dates"])
        self.assertNotEqual(texts["dates"], say.say_no_match("dates"))

    def test_missing(self):
        s = say.say_missing(["email", "phone", "participants[0].last_name"], "en")
        self.assertIn("the email", s)
        self.assertIn("the phone number", s)
        self.assertIn("last name of the second participant", s)
        self.assertIn(" and ", s)

    def test_accept_and_status(self):
        self.assertIn("750 euros", say.say_accept(Decimal("750"), Decimal("700"), True, "en"))
        for status in OrderStatus:
            with self.subTest(status=status):
                it = say.say_status(status, "R-1", None)
                en = say.say_status(status, "R-1", None, "en")
                self.assertNotEqual(it, en)
        self.assertIn("R-1", say.say_status(OrderStatus.CONFIRMED, "R-1", None, "en"))

    def test_italian_is_default(self):
        self.assertEqual(say.say_no_match("pax"), say.say_no_match("pax", "it"))
```

In `tests/test_intent.py`, `QuestionTest`, aggiungi `QUESTION_PAX_EN, QUESTION_SPORT_OR_PERIOD_EN` all'import e:

```python
    def test_questions_in_english(self):
        self.assertEqual(parse_intent("a trip to Spain for the two of us", today=TODAY).question,
                         QUESTION_SPORT_OR_PERIOD_EN)
        self.assertEqual(parse_intent("we want padel in October", today=TODAY).question,
                         QUESTION_PAX_EN)
```

In `tests/test_chooser.py`, `ReasonAndWindowTest`:

```python
    def test_reason_in_english(self):
        r = choose([make_product(1, price=300)], crit(language="en"), set(), TODAY)
        self.assertIn("Spain", r.reason)
        self.assertIn("1 October 2026", r.reason)
        self.assertIn("800 euros", r.reason)
        r = choose([make_product(1, price=900)], crit(area=None, language="en"), set(), TODAY)
        self.assertIn("cheapest", r.reason)

    def test_region_match_names_the_country(self):
        r = choose([make_product(1, price=300, destination="Malaga")],
                   crit(area=Area("region", "Andalusia", "ES")), set(), TODAY)
        self.assertIn("Spagna", r.reason)
        self.assertNotIn("Andalusia", r.reason)
```

In `tests/test_usecases.py`:

```python
class LanguageFlowTest(unittest.TestCase):
    def test_english_intent_gets_english_answers(self):
        vela = make_vela()
        created = vela.create_intent("a padel weekend in Spain in October, we are two, max 800 euros")
        self.assertIn("Spain", created.say)
        proposal = vela.get_proposal(created.intent_id)
        self.assertIn("per person", proposal.say)
        missing = vela.accept_proposal(proposal.proposal.id)
        self.assertIn("To book", missing.say)
        accepted = vela.accept_proposal(proposal.proposal.id, TravelerProfile(
            "Anna", "Rossi", "a@x.it", "+39", participants=(Participant("Bo", "Bi"),)))
        self.assertIn("payment link", accepted.say)
        self.assertIn("waiting for payment", vela.get_order_status(accepted.order_id).say)

    def test_english_no_match(self):
        vela = make_vela([])                       # catalogo vuoto: si ferma al filtro "archived"
        iid = vela.create_intent("tennis in October, we are two").intent_id
        self.assertIn("try again later", vela.get_proposal(iid).say)
```

(aggiungi `Participant` all'import da `vela.domain.models`; verifica con `grep -n "order_id" vela/domain/models.py` il nome del campo in `AcceptResponse` e adatta `accepted.order_id` se diverso).

- [ ] **Step 2: Verifica che falliscano**

Run: `uv run python -m unittest discover -s tests` 
Expected: FAIL/ERROR sui nuovi test (`fmt_date() takes 1 positional argument`, import di `QUESTION_PAX_EN`, testo italiano nelle risposte inglesi).

- [ ] **Step 3: Implementa `say.py`**

Sostituisci `vela/domain/say.py` con:

```python
"""Frasi pronte da leggere in italiano e inglese (RF-42): nessun markdown, nessun URL.

Ogni funzione riceve la lingua dell'intento (`"it"` default, `"en"`). I nomi dei luoghi dei
criteri passano da `geo.display_name`; titoli, destinazioni e hotel del catalogo restano come
sono (catalogo in locale `it`).
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from vela.domain import geo
from vela.domain.models import Criteria, OrderStatus, ProductSummary, Proposal

MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]


def fmt_date(d: date, lang: str = "it") -> str:
    months = MONTHS_EN if lang == "en" else MONTHS_IT
    return "%d %s %d" % (d.day, months[d.month - 1], d.year)


def fmt_money(value: Decimal, lang: str = "it") -> str:
    q = value.quantize(Decimal("0.01"))
    unit = "euros" if lang == "en" else "euro"
    if q == q.to_integral_value():
        return "%d %s" % (int(q), unit)
    number = format(q, "f")
    return "%s %s" % (number if lang == "en" else number.replace(".", ","), unit)


def _people(n: Optional[int], lang: str = "it") -> str:
    if n is None:
        return ""
    if lang == "en":
        return "1 person" if n == 1 else "%d people" % n
    return "1 persona" if n == 1 else "%d persone" % n


def _join(parts: list, lang: str = "it") -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + (" and " if lang == "en" else " e ") + parts[-1]


def say_intent_created(c: Criteria) -> str:
    lang = c.language
    if lang == "en":
        parts = ["a %s trip" % c.sport if c.sport else "a trip"]
        if c.area:
            parts.append("in %s" % geo.display_name(c.area, lang))
        if c.period:
            if c.period.start == c.period.end:
                parts.append("on %s" % fmt_date(c.period.start, lang))
            else:
                parts.append("between %s and %s" % (fmt_date(c.period.start, lang),
                                                    fmt_date(c.period.end, lang)))
        if c.pax:
            parts.append("for %s" % _people(c.pax, lang))
        if c.budget is not None:
            parts.append("with a maximum budget of %s" % fmt_money(c.budget, lang))
        return "Got it: %s. I'm looking for the right proposal." % " ".join(parts)
    parts = ["un viaggio di %s" % c.sport if c.sport else "un viaggio"]
    if c.area:
        parts.append(("in %s" if c.area.kind == "country" else "a %s") % c.area.name)
    if c.period:
        if c.period.start == c.period.end:
            parts.append("il %s" % fmt_date(c.period.start))
        else:
            parts.append("tra il %s e il %s" % (fmt_date(c.period.start), fmt_date(c.period.end)))
    if c.pax:
        parts.append("per %s" % _people(c.pax))
    if c.budget is not None:
        parts.append("con un budget massimo di %s" % fmt_money(c.budget))
    return "Ho capito: %s. Cerco la proposta giusta." % " ".join(parts)


def say_proposal(product: ProductSummary, p: Proposal, lang: str = "it") -> str:
    hotel = ", hotel %s" % product.hotel if product.hotel else ""
    if lang == "en":
        where = " in %s" % product.destination if product.destination else ""
        if p.start_date == p.end_date:
            when = "on %s" % fmt_date(p.start_date, lang)
        else:
            when = "from %s to %s" % (fmt_date(p.start_date, lang), fmt_date(p.end_date, lang))
        return ("I suggest %s%s%s, %s for %s, starting at %s per person. %s Shall I go ahead?"
                % (product.title, where, hotel, when, _people(p.pax, lang),
                   fmt_money(p.price_from, lang), p.reason))
    where = " a %s" % product.destination if product.destination else ""
    if p.start_date == p.end_date:
        when = "il %s" % fmt_date(p.start_date)
    else:
        when = "dal %s al %s" % (fmt_date(p.start_date), fmt_date(p.end_date))
    return ("Ti propongo %s%s%s, %s per %s, a partire da %s a persona. %s Ti va?"
            % (product.title, where, hotel, when, _people(p.pax), fmt_money(p.price_from), p.reason))


_NO_MATCH = {
    "it": {
        "archived": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
        "bookable": "Al momento non ho nessun viaggio prenotabile: riprova più tardi.",
        "rejected": "Hai già scartato tutte le proposte compatibili con la tua richiesta: prova a riformularla.",
        "sport": "Non trovo nessun viaggio per lo sport che hai chiesto: prova con l'altro sport o riformula la richiesta.",
        "dates": "Non trovo partenze nel periodo che hai chiesto: prova con un altro periodo.",
        "pax": "Non trovo viaggi per il numero di persone indicato: prova a cambiare il numero di persone.",
        None: "Non trovo nessun viaggio compatibile: prova a riformulare la richiesta.",
    },
    "en": {
        "archived": "Right now I have no bookable trips: please try again later.",
        "bookable": "Right now I have no bookable trips: please try again later.",
        "rejected": "You have already turned down every proposal that matches your request: try rephrasing it.",
        "sport": "I can't find any trip for the sport you asked for: try the other sport or rephrase the request.",
        "dates": "I can't find departures in the period you asked for: try another period.",
        "pax": "I can't find trips for that number of people: try changing the number of people.",
        None: "I can't find any matching trip: try rephrasing the request.",
    },
}


def say_no_match(criterion: str, lang: str = "it") -> str:
    texts = _NO_MATCH.get(lang, _NO_MATCH["it"])
    return texts.get(criterion, texts[None])


_ORDINALS = {
    "it": ["secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo"],
    "en": ["second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"],
}
_FIELD_LABELS = {
    "it": {"first_name": "il nome", "last_name": "il cognome", "email": "l'email",
           "phone": "il telefono"},
    "en": {"first_name": "the first name", "last_name": "the last name", "email": "the email",
           "phone": "the phone number"},
}


def _label(field: str, lang: str = "it") -> str:
    labels = _FIELD_LABELS.get(lang, _FIELD_LABELS["it"])
    if field.startswith("participants["):
        index = int(field[len("participants["):field.index("]")])
        leaf = field.split(".")[-1]
        ordinals = _ORDINALS.get(lang, _ORDINALS["it"])
        if lang == "en":
            ordinal = ordinals[index] if index < len(ordinals) else "number %d" % (index + 2)
            return "%s of the %s participant" % (labels[leaf], ordinal)
        ordinal = ordinals[index] if index < len(ordinals) else "numero %d" % (index + 2)
        return "%s del %s partecipante" % (labels[leaf], ordinal)
    return labels.get(field, field)


def say_missing(missing: list, lang: str = "it") -> str:
    head = "To book I still need: %s." if lang == "en" else "Per prenotare mi servono ancora: %s."
    return head % _join([_label(f, lang) for f in missing], lang)


def say_accept(total, price_from_total, total_differs: bool, lang: str = "it") -> str:
    if lang == "en":
        head = ("The real total is %s, not the estimated %s. "
                % (fmt_money(total, lang), fmt_money(price_from_total, lang))) if total_differs else ""
        return (head + "The total is %s. I'm sending you the payment link by text: as soon as the "
                "payment arrives, I'll book and give you the code." % fmt_money(total, lang))
    head = ""
    if total_differs:
        head = "Il totale reale è %s, non i %s stimati. " % (fmt_money(total), fmt_money(price_from_total))
    return (head + "Il totale è %s. Ti mando il link di pagamento per testo: appena il pagamento "
            "arriva, prenoto e ti do il codice." % fmt_money(total))


_STATUS = {
    "it": {
        OrderStatus.CONFIRMED: "La tua prenotazione è confermata, codice %s.",
        OrderStatus.AWAITING_PAYMENT: "L'ordine è in attesa del pagamento: usa il link che ti ho mandato.",
        OrderStatus.PAID_PENDING_BOOKING: ("Pagamento ricevuto, sto completando la prenotazione: "
                                           "richiedi lo stato tra qualche secondo."),
        OrderStatus.BOOKING_FAILED: ("Il pagamento è arrivato ma la prenotazione non è riuscita: "
                                     "riprovo io, e se non ci riesco ti avviso."),
        None: "Il link di pagamento è scaduto: dimmi se vuoi che prepari una nuova proposta.",
    },
    "en": {
        OrderStatus.CONFIRMED: "Your booking is confirmed, code %s.",
        OrderStatus.AWAITING_PAYMENT: "The order is waiting for payment: use the link I sent you.",
        OrderStatus.PAID_PENDING_BOOKING: ("Payment received, I'm completing the booking: ask for "
                                           "the status again in a few seconds."),
        OrderStatus.BOOKING_FAILED: ("The payment arrived but the booking did not go through: "
                                     "I'll try again, and if I can't I'll let you know."),
        None: "The payment link has expired: tell me if you want me to prepare a new proposal.",
    },
}


def say_status(status: OrderStatus, booking_code: Optional[str], failure_reason: Optional[str],
               lang: str = "it") -> str:
    texts = _STATUS.get(lang, _STATUS["it"])
    text = texts.get(status, texts[None])
    return text % booking_code if status == OrderStatus.CONFIRMED else text


def say_paid() -> str:
    return "Pagamento simulato registrato: la prenotazione è in corso."
```

Prima di sostituire, controlla con `grep -n "class OrderStatus" -A8 vela/domain/models.py` che gli stati siano esattamente `AWAITING_PAYMENT`, `PAID_PENDING_BOOKING`, `CONFIRMED`, `BOOKING_FAILED` più quello di scadenza: il testo di scadenza è il ramo `None` come nel codice M2.

- [ ] **Step 4: Implementa domande, motivazione e lingua nei casi d'uso**

`vela/domain/intent.py`, sotto le domande italiane:

```python
QUESTION_SPORT_OR_PERIOD_EN = ("Which sport are you interested in, padel or tennis, and when "
                               "would you like to go?")
QUESTION_PAX_EN = "How many people are travelling?"
_QUESTIONS = {"it": (QUESTION_SPORT_OR_PERIOD, QUESTION_PAX),
              "en": (QUESTION_SPORT_OR_PERIOD_EN, QUESTION_PAX_EN)}
```

e in `parse_intent`:

```python
    ask_sport_or_period, ask_pax = _QUESTIONS.get(criteria.language, _QUESTIONS["it"])
    question = None
    if criteria.sport is None and criteria.period is None:
        question = ask_sport_or_period
    elif criteria.pax is None:
        question = ask_pax
```

`vela/domain/chooser.py`, sostituisci `_reason`:

```python
def _reason(product: Product, criteria: Criteria, window: Availability) -> str:
    lang = criteria.language
    en = lang == "en"
    parts = []
    score = area_score(product, criteria.area)
    if score == 2:
        parts.append(("it's in %s" if en else "è a %s") % product.destination)
    elif score == 1:   # solo il paese coincide: si nomina il paese, non l'area chiesta
        country = geo.area_by_name(geo.COUNTRIES.get(criteria.area.country_code)) or criteria.area
        parts.append(("it's in %s" if en else "è in %s") % geo.display_name(country, lang))
    elif product.destination:
        parts.append(("it's in %s" if en else "è a %s") % product.destination)
    parts.append(("it starts on %s" if en else "parte il %s") % fmt_date(window.start, lang))
    if criteria.budget is not None and _within_budget(product, criteria):
        parts.append(("it stays within your budget of %s" if en else "resta nel tuo budget di %s")
                     % fmt_money(criteria.budget, lang))
    else:
        parts.append("it's the cheapest of the compatible options" if en
                     else "è la proposta più economica tra quelle compatibili")
    conj = " and " if en else " e "
    sentence = ", ".join(parts[:-1]) + conj + parts[-1] if len(parts) > 1 else parts[0]
    return sentence[0].upper() + sentence[1:] + "."
```

`vela/domain/usecases.py`: ogni frase riceve la lingua dell'intento.

```python
    def _propose(self, intent: Intent) -> Union[ProposalMade, NoMatch]:
        lang = intent.criteria.language
        # ... invariato fino a:
        if open_proposals:
            return self._made(open_proposals[-1], lang=lang)
        # ...
        if not isinstance(result, Choice):
            return NoMatch(intent.id, result.failed_criterion,
                           say.say_no_match(result.failed_criterion, lang))
        # ...
        return self._made(proposal, result.product, lang)

    def _made(self, proposal: Proposal, product: Optional[Product] = None,
              lang: str = "it") -> ProposalMade:
        product = product or self.repos.products.get(proposal.product_id)
        summary = summary_of(product)
        return ProposalMade(proposal, summary, say.say_proposal(summary, proposal, lang))
```

In `accept_proposal` sposta la lettura dell'intento subito dopo il controllo della proposta e usa `lang = intent.criteria.language` in `say.say_missing(missing, lang)` e in ogni `self._accepted(..., lang)`:

```python
    def accept_proposal(self, proposal_id, traveler=None):
        proposal = self.repos.proposals.get(proposal_id)
        if proposal is None:
            raise NotFound("proposal", proposal_id)
        intent = self.repos.intents.get(proposal.intent_id)
        lang = intent.criteria.language
        existing = self.repos.orders.get_by_proposal(proposal_id)
        if existing is not None:
            return self._accepted(existing, lang)
        # ... resto invariato, con lang passato a say_missing e ai due _accepted rimanenti

    def _accepted(self, order: Order, lang: str = "it") -> AcceptResponse:
        estimate = order.price_from * order.pax
        differs = order.total != estimate
        return AcceptResponse(order.id, order.status, order.total, order.currency, estimate,
                              differs, order.payment_url or "",
                              say.say_accept(order.total, estimate, differs, lang))

    def get_order_status(self, order_id: str) -> OrderStatusResponse:
        order = self.orders.get(order_id)
        intent = self.repos.intents.get(order.intent_id)
        lang = intent.criteria.language if intent is not None else "it"
        return OrderStatusResponse(order.id, order.status, order.booking_code,
                                   say.say_status(order.status, order.booking_code,
                                                  order.failure_reason, lang))
```

`vela/surfaces/replay.py` resta invariato (italiano di default).

- [ ] **Step 5: Verifica che passino**

Run: `uv run python -m unittest discover -s tests` → OK, compresi i test italiani M2 di `test_say.py`, `test_chooser.py` (`test_reason_mentions_area_dates_and_budget` trova ancora "Spagna"), `test_usecases.py` e `test_app_replay.py`.

- [ ] **Step 6: Commit**

```bash
git add vela/domain/say.py vela/domain/intent.py vela/domain/chooser.py vela/domain/usecases.py tests/test_say.py tests/test_intent.py tests/test_chooser.py tests/test_usecases.py
git commit -m "Answer in the intent language: English say phrases, questions and choice reasons"
```

---

### Task 10: Documentazione e verifica finale

**Files:**
- Modify: `docs/decisions.md`, `vela/domain/intent.py` e `vela/domain/geo.py` (solo docstring, se ancora parlano di "M9 completerà")

- [ ] **Step 1: Decisioni prese durante l'esecuzione**

Aggiungi in coda a `docs/decisions.md` una sezione `## 2026-09-25 — M9: decisioni prese durante l'esecuzione` con una riga per ogni scelta non prevista da questo piano (per esempio una forma del parser cambiata perché in conflitto con un test M2, la versione di `anthropic` installata, l'esito della prova manuale se eseguita). Se non ce ne sono, scrivi una riga "Nessuna deviazione dal piano" con la versione di `anthropic`.

- [ ] **Step 2: Docstring**

`grep -n "M9" vela/domain/*.py` e aggiorna i riferimenti futuri ("completo in M9", "M9 estende") al presente.

- [ ] **Step 3: Verifica completa**

Run: `uv run python -m unittest discover -s tests` → OK senza `DATABASE_URL` e senza `ANTHROPIC_API_KEY`.
Run (se il DB è disponibile): `set -a; . ./.env; set +a; uv run python -m unittest discover -s tests` → OK anche i test Postgres.
Run: `grep -rn "import anthropic" vela/domain vela/ports` → nessun risultato.
Run: `grep -rn "fastapi\|sqlalchemy" vela/domain` → nessun risultato.

- [ ] **Step 4: Commit**

```bash
git add docs/decisions.md vela/domain/intent.py vela/domain/geo.py
git commit -m "Record M9 execution decisions"
```

---

## Copertura dei test di completamento della roadmap M9

| Test richiesto dalla roadmap | Dove |
|---|---|
| Tabelle parser it/en (≥ 30 casi) | Task 3: `TABLE` con 32 righe (≥ 10 en, ≥ 15 it), `TableSizeTest` |
| Rifiuti con motivo → criteri attesi | Task 6: `tests/test_refine.py`; Task 8: `RejectProposalTest` sui casi d'uso |
| Fallback con client finto | Task 4: `FallbackTest` (extractor finto); Task 5: `tests/test_haiku.py` (client SDK finto) |
| Chiave assente → nessun errore, nessuna chiamata | Task 4: `test_no_extractor_no_error`, `test_default_has_no_extractor`; Task 5: `test_no_key_no_extractor` |

## Requisiti coperti

RF-02 (Task 1-3), RF-03 (Task 4-5), RF-04 (domande bilingui, Task 9), RF-08 (Task 6-8), RF-42 (frasi inglesi, Task 9).

## Fuori scope (task successive)

- Gerarchia geografica, durata e intersezioni parziali nel chooser: M11.
- "Più vicino" rispetto alla posizione del viaggiatore: richiede un dato che il profilo non ha.
- Est/ovest nelle tabelle di direzione.
- Nomi inglesi dei titoli del catalogo: il catalogo è in locale `it` (decisione M1).
