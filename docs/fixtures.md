# Fixture del catalogo (`fixtures/catalog.json`)

Snapshot del catalogo House of Journeys in locale `it` (RF-32): lista `GET /v1/products`
integrale (anche archiviati) più dettaglio `GET /v1/products/{id}?extended=true` dei
prodotti non archiviati. Usato dalla modalità replay, dall'avvio a freddo e dalla demo se
la quota è esaurita. Piano e decisioni: `docs/plans/2026-09-25-m1-fixture-catalogo.md`,
`docs/decisions.md` (2026-09-25, M1).

## Formato

| Chiave | Contenuto |
|---|---|
| `recorded_at` | istante dell'ultima risposta registrata (ISO-8601 UTC) |
| `locale` | `it` |
| `brand` | valore di `HOFJ_BRAND` usato, `null` se omesso (default del server: `weebora.com`) |
| `base_url` | base URL dell'API al momento della costruzione |
| `products` | item della lista così come li restituisce l'API, in ordine di id |
| `details[id].catalog` | campi di RF-28 con i nomi dell'API: `id, title, slug, shortDescription, price, currency, minPax, maxPax, minDate, maxDate, availabilities, defaultDurationInDays, updatedAt, category, venue, destination, hotels` (`hotels` = `rawAttributes.hotels` senza media) |
| `details[id].raw` | dettaglio esteso senza `gallery`, `image`, `images`, `cover`, `media`, `travelProgram` a qualsiasi profondità |

## Rigenerare la fixture

Variabili: `HOFJ_API_KEY` (o `API_BEAR_KEY`), opzionali `HOFJ_BASE_URL`, `HOFJ_BRAND`.
La chiave non viene mai stampata né salvata. Le risposte grezze vanno in una cartella
fuori dal repository e permettono di ricostruire il file senza consumare quota.

```bash
python3 scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-it --dry-run   # solo conteggio
python3 scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-it             # ≈ 96 chiamate, 2 finestre
python3 scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-it --build-only  # ricostruzione
python3 -m unittest tests.test_catalog_fixture -v                               # validazione
```

Pacing: budget per finestra di 60 s = min(`remainingInWindow`, 90 − `usedInWindow`), attesa
fino a `windowEndsAt` + 2 s, stop immediato su 429 (`scripts/api_explore.py`).

## Ultima registrazione

| Voce | Valore |
|---|---|
| `recorded_at` | 2026-09-25T12:53:14Z |
| Prodotti totali (lista) | 110 |
| Non archiviati (dettagli scaricati) | 77 |
| Archiviati | 33 |
| Chiamate autenticate eseguite | 80 (2 liste + 77 dettagli + 1 sync quota) |
| Finestre da 60 s usate | 1 (il pacing ne aveva preventivate 2 sulla stima; il conteggio reale è
  rientrato in una sola finestra da 90 chiamate) |
| Dimensione file | 1 434 730 byte |

Differenze rispetto alla stima `en` (`docs/api/counts.md`, 123 prodotti / 92 non archiviati):
il catalogo `it` ne conta 110 in lista e 77 non archiviati, cioè meno prodotti totali (-13) e
meno prodotti attivi (-15) rispetto alla stima usata per pianificare le chiamate. Di
conseguenza la registrazione reale ha richiesto solo 80 chiamate autenticate in una finestra,
contro le ~96 in 2 finestre dichiarate prima della corsa (nessun 429, nessuno STOP).

- Il catalogo `it` è un insieme di voci CMS distinto da quello `en`, non un sottoinsieme o una
  traduzione parallela: gli id vanno da 181 a 1093 (in `en`: 12-1088) e i `categoryId` sono
  prevalentemente 8/7/9 (in `en`: 2/1/3; 108 prodotti su 110 in `it`, più due outlier isolati
  con `categoryId` 20 e 28). Gli id non sono quindi confrontabili tra le due locale.
