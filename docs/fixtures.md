# Fixture del catalogo (`fixtures/catalog*.json`)

Snapshot del catalogo House of Journeys, **una fixture per (host, brand)** (RF-32, M10): lista
`GET /v1/products` integrale (anche archiviati) più dettaglio
`GET /v1/products/{id}?extended=true` dei prodotti non archiviati. Servono solo al replay e ai
test: in live il catalogo viene dal sync (`vela/sync.py`, RF-29..31). Il replay carica tutte le
fixture dell'host di produzione (`https://api.hofj.com`), cioè tutti i brand. Piani e decisioni:
`docs/plans/2026-09-25-m1-fixture-catalogo.md`, `docs/decisions.md` (M1, M7, M10).

| File | Host | Brand | Sport | Locale |
|---|---|---|---|---|
| `catalog.json` | `https://api.hofj.com` | `weebora.com` | padel | `it` |
| `catalog-tennis.json` | `https://api.hofj.com` | `terrarossa.com` | tennis | `it` |
| `catalog-staging.json` | `https://staging.api.hofj.com` | `staging.weebora.com` | padel | `en` |
| `catalog-staging-tennis.json` | `https://staging.api.hofj.com` | `staging.tennis.weebora.com` | tennis | `en` |

I nomi seguono `vela.fixtures.fixture_name`: nessun suffisso per produzione e padel. Due
fixture dello stesso brand sullo stesso host fanno fallire la selezione (`select_fixtures`).

## Formato

| Chiave | Contenuto |
|---|---|
| `recorded_at` | istante della fine della registrazione (ISO-8601 UTC) |
| `locale` | locale delle chiamate (`it` in produzione, `en` su staging) |
| `brand` | brand HofJ del catalogo (`?brand=` di ogni chiamata) |
| `sport` | sport del brand secondo `HOFJ_BRANDS` al momento della registrazione: è lo sport di tutti i prodotti della fixture (decisione M10). Senza `sport` lo sport si ricava dal testo (`detect_sport`) |
| `base_url` | host dell'API |
| `products` | item della lista così come li restituisce l'API, nell'ordine delle pagine |
| `details[id].catalog` | campi di RF-28 con i nomi dell'API: `id, title, slug, shortDescription, price, currency, minPax, maxPax, minDate, maxDate, availabilities, defaultDurationInDays, updatedAt, category, venue, destination, hotels` (`hotels` = `rawAttributes.hotels` senza media) |
| `details[id].raw` | dettaglio esteso senza `gallery`, `image`, `images`, `cover`, `media`, `travelProgram` a qualsiasi profondità |

La proiezione (`project_detail`, `strip_media`) sta in `vela/domain/catalog.py` ed è la stessa
che il sync scrive in `products`.

## Rigenerare le fixture

Con il codice del sync: `python -m vela.sync --record` gira `CatalogSync` su repository in memoria
(quindi scarica il dettaglio di ogni prodotto attivo) e scrive una fixture per brand. Prima di
ogni chiamata legge `/v1/quota` e prende uno slot della classe `sync`: rispetta anche le chiamate
fatte da altri client con la stessa chiave e aspetta la finestra successiva quando serve. Un brand
che fallisce non scrive nulla. La chiave viene solo dall'ambiente e non viene mai stampata.

```bash
# piano, nessuna chiamata e nessuna chiave richiesta
HOFJ_BASE_URL=https://api.hofj.com HOFJ_BRANDS=padel=weebora.com,tennis=terrarossa.com \
  uv run python -m vela.sync --record --sport tennis --dry-run
# registrazione (HOFJ_API_KEY nell'ambiente); stampa i file scritti e le chiamate fatte
HOFJ_BASE_URL=https://api.hofj.com HOFJ_BRANDS=padel=weebora.com,tennis=terrarossa.com \
  uv run python -m vela.sync --record --sport tennis
uv run python -m unittest discover -s tests -p "test_*fixture*.py"   # validazione
```

`--sport` limita la registrazione a un brand della mappa; `--locale` sovrascrive il locale delle
fixture già presenti per l'host; `--out-dir` cambia la cartella (default `fixtures/`).

Budget di dimensione: 1 500 000 byte per file (`tests/test_catalog_fixture.py`). `catalog.json`
pesa circa il 96% del limite: una registrazione che lo faccia crescere di oltre il ~5% richiede di
estendere i campi scartati o alzare il limite, con una decisione in `docs/decisions.md`.

Prodotto trappola del criterio 4 (M7): `vela.fixtures.add_trap(catalog, "78")` clona il prodotto
78 con id `900078`, prezzo più basso di 1 e `vela_trap: true`; si scrive con `write_catalog`.

## Registrazioni

### `catalog.json` (M1)

| Voce | Valore |
|---|---|
| Registrata | 2026-09-25T12:53:14Z con `scripts/record_catalog.py` (poi sostituito), senza `?brand=`: il default del server è `weebora.com`. `brand` e `sport` aggiunti a mano il 2026-09-26 (M10), senza chiamate |
| Prodotti | 110 in lista, 77 non archiviati, 33 archiviati |
| Chiamate | 80 (2 liste + 77 dettagli + 1 quota) |
| Dimensione | 1 434 730 byte |

Il catalogo `it` è un insieme di voci CMS distinto da quello `en`: gli id vanno da 181 a 1093 (in
`en`: 12-1088) e i `categoryId` sono diversi. Gli id non sono confrontabili tra le due locale.

### `catalog-staging.json` (M7)

| Voce | Valore |
|---|---|
| Registrata | 2026-09-25, brand `staging.weebora.com`, locale `en` (su staging i prodotti funzionano solo in `en`). `sport` aggiunto il 2026-09-26 (M10) |
| Prodotti | 87 in lista, 56 non archiviati |
| Chiamate | 58 |
| Prodotto trappola | Tolto il 2026-09-26 dopo l'esecuzione del criterio 4 (decisione M7) |

Staging contiene anche prodotti di prova ("GROUP TOUR TEST", "Test Companion e Player") e dati
incoerenti (il 867 "Costa Blanca Padel Experience" ha destinazione Nicosia, Cipro): la fixture li
riporta come sono. Rigenerandola, gli id attesi in `tests/test_staging_fixture.py` vanno rivisti.

### `catalog-tennis.json` e `catalog-staging-tennis.json` (M10)

Registrate il 2026-09-26 con `python -m vela.sync --record --sport tennis`; chiamate dichiarate
prima e rispettate, nessun 429.

| Voce | `catalog-tennis.json` | `catalog-staging-tennis.json` |
|---|---|---|
| Brand, locale | `terrarossa.com`, `it` | `staging.tennis.weebora.com`, `en` |
| Prodotti | 80 in lista, 49 non archiviati | 36 in lista, 13 non archiviati |
| Chiamate | 51 (1 quota + 1 pagina + 49 dettagli) | 15 (1 quota + 1 pagina + 13 dettagli) |
| Dimensione | 873 601 byte | 261 024 byte |
| Categorie attive | Vacanze 23, Accademie 13, Tornei 12, Holidays 1 | Holidays 8, Academies 4, Tournaments 1 |

"Tornei"/"Tournaments" è la categoria dei pacchetti evento (Hospitality delle Finals, Watch &
Stay/Play, Coppa Davis, tornei amatoriali MT100/MT400): `is_trip` la esclude per tutti i brand
(decisione M10).
