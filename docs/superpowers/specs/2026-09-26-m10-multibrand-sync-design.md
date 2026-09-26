# M10 — Sync multi-brand del catalogo: design

Data: 2026-09-26. Origine: roadmap M10, `docs/usecases/multi-brand.md` (MB1-MB9), spec RF-28..32,
RF-56, §4.8, decisioni 2026-09-26 "M10: sync multi-brand" e "M10: pacchetti evento esclusi".
Decisioni di questo brainstorming in `docs/decisions.md` (2026-09-26, "M10: design del sync").

## Obiettivo

Il catalogo in Postgres contiene tutti i brand di `HOFJ_BRANDS` (padel = Weebora, tennis =
Terrarossa) e si aggiorna da solo. Ogni chiamata del carrello e della prenotazione usa il brand
del prodotto dell'ordine, anche dopo un riavvio o un retry. Le fixture, una per (host, brand),
servono solo a replay e test e si registrano con lo stesso codice del sync.

Successo: da claude.ai una richiesta di tennis riceve una proposta Terrarossa; i test M10 della
roadmap sono verdi; nessun file di M17 toccato.

## Vincoli

- `HofJPort` invariata; `chooser.py`, `intent.py`, `usecases.py`, `mcp.py`, `rest.py` non
  toccati (M17 lavora lì in parallelo).
- Una sola quota per chiave API, condivisa con acquisti e prenotazioni (§4.8): il sync usa la
  classe `SYNC` e cede il passo agli acquisti in attesa.
- Nessuna chiamata HofJ nei test automatici. Le chiamate reali si dichiarano prima e partono
  solo dopo conferma.
- Python 3.12 come il resto del codice (`uv run`); nessuna dipendenza nuova.

## Componenti

### Config (`vela/config.py`)

- `Settings.hofj_brands: Dict[str, str]` (sport → brand), da `HOFJ_BRANDS` nel formato
  `padel=weebora.com,tennis=terrarossa.com`. Spazi attorno a voci e `=` tollerati.
- `parse_brands(raw) -> Dict[str, str]` solleva `ValueError` con messaggio esplicito per: voce
  senza `=`, sport vuoto o fuori da {padel, tennis}, sport ripetuto, brand vuoto, brand
  duplicato, nessuna voce.
- In live: `HOFJ_BRANDS` assente e `HOFJ_BRAND` presente → errore "sostituisci HOFJ_BRAND con
  HOFJ_BRANDS=padel=<brand>"; entrambe assenti → errore di variabile mancante. Gli errori
  diventano `RuntimeError` in `app.build_hofj`, come oggi: l'app non parte.
- In replay `HOFJ_BRANDS` non serve: brand e sport vengono dai metadati delle fixture.
- `render.yaml`: `HOFJ_BRAND` → `HOFJ_BRANDS` (`sync: false`).

### Prodotti (`Product.brand`, migrazione `0006`)

- `Product.brand: Optional[str] = None` in `vela/domain/models.py`.
- `schema.py`: colonna `brand String(64)` nullable. Migrazione Alembic
  `0006_products_brand` (add/drop column, compatibile SQLite con `batch_alter_table`).
- `ProductRepository`:
  - `archive_missing(keep_ids, brand=None) -> int`: con `brand` archivia solo i prodotti attivi
    di quel brand non in `keep_ids`; senza `brand` si comporta come oggi (usato solo dal
    replay).
  - `sync_state(ids) -> Dict[id, SyncState(brand, updated_at, archived)]` per il confronto
    incrementale, `mark_seen(ids, brand, sport, seen_at)` per i prodotti invariati.
- Le righe già su Render restano con `brand` NULL finché il primo sync non le riscrive.

### Porta di lettura del catalogo (`vela/ports/catalog.py`)

```python
class CatalogSource(Protocol):
    def list_page(self, brand: str, cursor: Optional[str]) -> Tuple[List[dict], Optional[str]]: ...
    def detail(self, brand: str, product_id: str) -> dict: ...
```

- `HofJHttp` la implementa: `GET /v1/products?limit=100&cursor=&brand=&locale=` e `GET
  /v1/products/{id}?extended=true&brand=&locale=`. `_call` viene esteso con una variante che
  restituisce anche `meta` (per `nextCursor`); stessa mappa degli errori.
- `FixtureCatalogSource(paths)` la implementa sulle fixture (una per brand), per replay e test.
- Il brand passato alla porta prevale sul brand del costruttore di `HofJHttp`, quindi basta un
  client per il sync.

### Sync (`vela/sync.py`)

`CatalogSync(source, repos, brands, now, sleep, batch_size=25)` con `run() -> SyncReport`.

Per ogni `(sport, brand)` della mappa, in ordine:

1. Lista paginata; cursore ripetuto → errore del brand.
2. Per ogni voce non archiviata: se l'id è già in `products` con un brand diverso (non NULL) →
   `BrandConflict`, il brand si ferma. Se è nuovo o ha `updatedAt` diverso da
   `hofj_updated_at` → dettaglio; altrimenti nessuna chiamata.
   - Prodotto invariato (anche con `brand` NULL): nessun dettaglio, il repository scrive
     `brand`, `sport` e `fetched_at` (`mark_seen(ids, brand, sport, seen_at)`).
   - Prodotto archiviato nel DB e di nuovo attivo in lista: dettaglio anche a `updatedAt`
     invariato.
3. `Product` costruito con `product_from_entry` (esistente) più `brand` e `sport` = sport della
   mappa (`detect_sport` resta come riserva solo per le fixture senza brand).
4. Scrittura per lotti di `batch_size` con `upsert_many`: ogni lotto è una transazione, quindi
   un'interruzione lascia un catalogo parziale ma coerente.
5. A lista completata senza errori: `archive_missing(ids_visti, brand)`. Una lista senza
   prodotti attivi è un errore del brand e non archivia nulla. Un brand con errori non
   archivia nulla e non tocca gli altri brand.

Quota: prima di ogni chiamata `repos.quota.acquire(QuotaClass.SYNC, 1, now,
purchase_waiting=repos.jobs.purchase_waiting())`. Se rifiutata, `sleep` fino a
`next_window_start(now)` e riprova. Su `QuotaError` (429): `quota.on_429(now)` e attesa come
sopra, senza ripetere subito la chiamata. `ConfigError` (401/403) ferma tutto il sync.

Lock: `repos.catalog_lock()` (context manager). Postgres: `pg_try_advisory_lock(<costante>)` su
una connessione dedicata; se occupato il giro termina subito con `skipped=True`. Memoria e
SQLite: lock di processo (`threading.Lock`).

`SyncReport`: per brand pagine, dettagli, scritti, archiviati, errore; totale chiamate.
Loggato in una riga per brand.

Scheduler: `SyncScheduler(sync, repos, now, sleep, interval=6h)`, thread daemon avviato dal
bootstrap in live. Al boot esegue subito se `products.count() == 0` o
`last_fetched_at` più vecchio di 6 h, poi ogni 6 h dall'ultimo giro. Un'eccezione viene loggata
e il thread continua.

Comando: `python -m vela.sync` esegue un giro in live (stessa config dell'app) e stampa il
report. `python -m vela.sync --record [--sport tennis] [--out-dir fixtures]` registra le fixture: stesso
`CatalogSync` su repository in memoria (quindi tutti i dettagli), con la quota allineata prima a
`/v1/quota`; scrive un file per brand, tutto o niente. Prima di partire stampa il piano (stimato
dalle fixture dell'host, se ci sono) e con `--dry-run` si ferma lì; alla fine stampa le chiamate
fatte. `scripts/record_catalog.py` viene rimosso; `strip_media` e `project_detail` passano in
`vela/domain/catalog.py`, `write_catalog` e `add_trap` in `vela/fixtures.py`.

### Router del carrello

- Porta in `vela/ports/hofj.py`:
  ```python
  class HofJRouter(Protocol):
      def client(self, brand: str) -> HofJPort: ...
      def client_for(self, product: Optional[Product]) -> HofJPort: ...
      def get_quota(self) -> QuotaSnapshot: ...
  ```
- `vela/adapters/hofj_router.py`: `BrandRouter(clients: Dict[brand, HofJPort], sport_brands)`;
  `client` con brand sconosciuto → `ConfigError`; `client_for` usa `product.brand`, oppure (NULL)
  il brand dello sport del prodotto, e nessuno dei due → `ConfigError`. In live un `HofJHttp` per
  brand (stessa chiave, stesso host, locale dell'host); in replay e nei test
  `SingleClientRouter`, un solo client per tutti i brand.
- `PurchaseJob` e `BookingJob` ricevono il router. A ogni esecuzione rileggono l'ordine e il
  prodotto e usano `router.client_for(product)` per tutte le chiamate del passo. Nessun brand memorizzato nel job: dopo un riavvio vale il DB.
- `JobProcessor.refresh_quota` usa `router.get_quota()`.
- `Vela` riceve il router nell'argomento `hofj` (l'attributo è solo memorizzato e passato ai
  job). L'annotazione `HofJPort` in `usecases.py:43` resta com'è per non toccare il file di M17;
  si corregge dopo il merge di M17.

### Fixture

- Nomi: `catalog.json` e `catalog-staging.json` (padel, esistenti), `catalog-tennis.json` e
  `catalog-staging-tennis.json` (nuove); vedi `docs/decisions.md`, "M10: esecuzione".
  Metadati: `base_url`, `locale`, `brand`, `sport`, `recorded_at`.
- Le due padel esistenti si adattano offline: aggiunta di `brand` (`weebora.com` in
  produzione, dove era `null`) e `sport`. Nessuna chiamata.
- `select_fixtures(dir, base_url) -> List[path]` sostituisce `select_fixture`; errore esplicito
  se nessuna. Due fixture dello stesso host con lo stesso brand → errore.
- `load_fixture` assegna `brand` e `sport` dai metadati; senza metadato `sport` usa
  `detect_sport`.
- Replay: `ReplayHofJ` carica tutte le fixture dell'host di default (produzione) e il catalogo
  replay contiene entrambi i brand. `FIXTURE_PATH` diventa la cartella.
- Budget di dimensione: 1,5 MB per file, come oggi (`tests/test_catalog_fixture.py`).
- `docs/fixtures.md` aggiornato: formato, comandi, conteggio chiamate.

### `is_trip`

Falso se:
- lo slug contiene `giftcard` o `gift-card`, o il titolo contiene "gift card" (qualunque brand);
- la destinazione è un nome di brand (`Weebora`, `Terrarossa`);
- la categoria è quella dei pacchetti evento, confrontata per nome (`EVENT_CATEGORIES` =
  "Tornei", "Tournaments"), per tutti i brand (`docs/decisions.md`, "M10: esecuzione").

La regola finale si verifica sulle quattro fixture: nessun prodotto giocabile escluso, tutte le
gift card e i pacchetti evento esclusi.

### Boot (`vela/app.py`)

- Live: `build_hofj` costruisce router e `HofJHttp` per il sync; `bootstrap` non chiama più
  `realign_catalog` ma avvia `SyncScheduler` (che decide se eseguire subito). `refresh_quota`,
  `resume_bookings` e il worker come oggi.
- Replay: `realign_catalog` resta, con le fixture di tutti i brand dell'host.
- `/health` invariato: `age_seconds` riflette già `last_fetched_at`.

## Casi d'uso

MB1-MB9 diventano test con repository in memoria: catalogo con prodotti dei due brand,
`Criteria` costruiti direttamente (lo sport strutturato arriva con M17), chooser invariato.
- MB5 (`sport=any`) si verifica con criteri senza filtro sport (`None`): candidati di entrambi i
  brand. Il valore letterale `"any"` lo testa M17.
- MB6/MB7 (domanda "Padel o tennis?") sono di M17: in M10 nessun test.
- MB8 con mappa del solo padel: nessun prodotto tennis nel catalogo → `no_match` sport.
- MB9 con i prodotti evento della fixture Terrarossa di produzione.

## Errori

| Situazione | Effetto |
|---|---|
| Config non valida | L'app e `python -m vela.sync` non partono, messaggio esplicito |
| Id già presente con altro brand | Il sync di quel brand si ferma, niente archiviazione per quel brand, errore nel report |
| 5xx / rete durante un brand | Come sopra; il brand riprova al giro successivo |
| 429 | `on_429`, attesa della finestra, poi riprende |
| 401/403 | Il giro intero si ferma |
| Lock occupato | Giro saltato, `skipped` nel log |
| Brand del prodotto non in mappa e sport senza brand | `ConfigError` nel job: l'ordine segue il percorso d'errore esistente |

## Test

Tutti quelli della roadmap M10, con porta del catalogo finta, client finti per brand che
registrano le chiamate, orologio e `sleep` finti. Postgres (lock, `archive_missing` per brand)
saltati senza `DATABASE_URL`. Migrazione `0006` in `tests/test_migrations.py` su SQLite.

## Chiamate HofJ reali

| # | Cosa | Chiamate |
|---|---|---|
| 1 | Fixture Terrarossa produzione (`terrarossa.com`, `it`, 80 prodotti, ~49 attivi) | 1 quota + 1 pagina + ~49 dettagli ≈ 51 |
| 2 | Fixture staging tennis (`staging.tennis.weebora.com`, `en`, 36 prodotti, ~13 attivi) | 1 quota + 1 pagina + ~13 dettagli ≈ 15 |
| 3 | Sync manuale su Render (fine task) | atteso ≈ 53 (2 pagine padel + 1 tennis + ~49 dettagli tennis + 1 quota), massimo ≈ 130 se tutti i prodotti padel risultano cambiati |

Ogni gruppo parte solo dopo conferma, con `--dry-run` prima.

## Fuori scope

Campi strutturati e `sport=any` in MCP/REST/intent (M17); riconoscimento dello sport nel testo
(M17); `/v1/categories`; multi-tenant.
