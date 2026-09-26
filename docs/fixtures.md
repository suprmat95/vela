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
| `brand` | brand letto dalle pagine di lista registrate (`params.brand`), `null` se le pagine non lo includevano (default del server: `weebora.com`). Un `HOFJ_BRAND` diverso al momento della build (`--build-only` compreso) fa fallire la scrittura della fixture: è solo un controllo incrociato, non la fonte del valore |
| `base_url` | base URL dell'API al momento della costruzione |
| `products` | item della lista così come li restituisce l'API, in ordine di id |
| `details[id].catalog` | campi di RF-28 con i nomi dell'API: `id, title, slug, shortDescription, price, currency, minPax, maxPax, minDate, maxDate, availabilities, defaultDurationInDays, updatedAt, category, venue, destination, hotels` (`hotels` = `rawAttributes.hotels` senza media) |
| `details[id].raw` | dettaglio esteso senza `gallery`, `image`, `images`, `cover`, `media`, `travelProgram` a qualsiasi profondità |

## Rigenerare la fixture

Variabili: `HOFJ_API_KEY` (o `API_BEAR_KEY`), opzionali `HOFJ_BASE_URL`, `HOFJ_BRAND`.
La chiave non viene mai stampata né salvata. Le risposte grezze vanno in una cartella
fuori dal repository e permettono di ricostruire il file senza consumare quota. La cartella
deve essere nuova o vuota: `--raw-dir` non vuota viene rifiutata (evita di mischiare due
registrazioni), quindi si usa un nome datato a ogni corsa.

```bash
RAW=~/vela-raw/catalog-it-$(date +%Y%m%d-%H%M)   # cartella nuova: una non vuota viene rifiutata
python3 scripts/record_catalog.py --raw-dir "$RAW" --dry-run     # solo conteggio
SSL_CERT_FILE=/etc/ssl/cert.pem \
  python3 scripts/record_catalog.py --raw-dir "$RAW"             # ≈ 80 chiamate, 1 finestra (vedi --dry-run)
python3 scripts/record_catalog.py --raw-dir "$RAW" --build-only  # ricostruzione
python3 -m unittest tests.test_catalog_fixture -v                # validazione
```

`SSL_CERT_FILE` serve solo alla corsa reale (fa richieste in rete): il Python 3.7 di
python.org per macOS non porta un bundle di CA proprio e senza questa variabile
l'handshake TLS fallisce (`docs/decisions.md`, 2026-09-25 — Esplorazione read-only).

Pacing: budget per finestra di 60 s = min(`remainingInWindow`, 90 − `usedInWindow`), attesa
fino a `windowEndsAt` + 2 s, stop immediato su 429 (`scripts/api_explore.py`).

Budget di dimensione: l'ultima fixture pesa 1 434 730 byte, circa il 96% del limite di
1 500 000 byte imposto da `tests/test_catalog_fixture.py::test_size_within_budget`. Una
futura registrazione che faccia crescere il catalogo di oltre il ~5% richiederà di estendere
`MEDIA_KEYS` o alzare `MAX_BYTES`: è una decisione da registrare in `docs/decisions.md`,
non da fare silenziosamente.

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

## Fixture di staging (`fixtures/catalog-staging.json`, M7)

Catalogo di HofJ staging per `VELA_UPSTREAM_MODE=live` su staging: in live l'app carica la
fixture il cui `base_url` coincide con `HOFJ_BASE_URL` e usa il suo `locale` per il carrello
(`docs/decisions.md`, M7). Su staging i prodotti funzionano solo in `en`.

| Voce | Valore |
|---|---|
| Registrata | 2026-09-25, host `https://staging.api.hofj.com`, brand `staging.weebora.com`, locale `en` |
| Prodotti | 87 in lista, 56 non archiviati |
| Chiamate autenticate | 58 |
| Prodotto trappola | Tolto il 2026-09-26 dopo l'esecuzione del criterio 4: era il clone del 78 (Firenze) con id `900078`, inesistente su HofJ, 249 € e `vela_trap: true`, e dopo "troppo caro" compariva anche su intenti non su Firenze. Si rimette con `--trap-from 78` |

Staging contiene anche prodotti di prova ("GROUP TOUR TEST", "Test Companion e Player") e dati
incoerenti (il 867 "Costa Blanca Padel Experience" ha destinazione Nicosia, Cipro): la fixture li
riporta come sono.

```bash
# registrazione (la chiave solo dall'ambiente; cartella grezza fuori dal repo, nuova)
HOFJ_BASE_URL=https://staging.api.hofj.com HOFJ_BRAND=staging.weebora.com \
  uv run python scripts/record_catalog.py --raw-dir ~/vela-raw/catalog-staging-en-AAAAMMGG \
  --locale en --out fixtures/catalog-staging.json
# ricostruzione senza chiamate (aggiungere --trap-from 78 per la trappola del criterio 4)
HOFJ_BASE_URL=https://staging.api.hofj.com uv run python scripts/record_catalog.py \
  --raw-dir ~/vela-raw/catalog-staging-en-AAAAMMGG --locale en --build-only \
  --out fixtures/catalog-staging.json
```

Rigenerandola, gli id attesi in `tests/test_staging_fixture.py` vanno rivisti.
