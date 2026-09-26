# Decisioni

Registro delle decisioni accettate. Formato: data, decisione, motivo.

## 2026-09-24 — Trascrizione delle chat Claude Code in `agents-log/`

| Decisione | Scelta | Motivo |
|---|---|---|
| Sorgente | Solo Claude Code, solo sessioni future | Sorgente unica con formato noto (JSONL in `~/.claude/projects/`). Le sessioni precedenti non vengono recuperate. |
| Dettaglio | Messaggi utente, risposte dell'agente, una riga per ogni tool usato | Leggibile e compatto. Niente output dei tool né "thinking": rumorosi e possibile veicolo di segreti. |
| Trigger | A ogni `git commit` eseguito dall'agente, solo per la sessione che lo lancia | Il log viaggia con il codice a cui si riferisce. |
| Git | Il file di log viene aggiunto allo stesso commit, automaticamente | Nessun commit separato "rumoroso"; la trascrizione è parte della modifica. |
| Nome file | `YYYY-MM-DD-HHMM-<slug-primo-messaggio>.md` (ora locale) | Ordinabile e riconoscibile. Stesso nome a ogni commit della sessione: il file viene rigenerato. |
| Meccanismo | Hook Claude Code `PreToolUse` su `Bash` in `.claude/settings.json` | Versionato nel repo, nessun setup per clone, riceve direttamente `transcript_path`. Scartato l'hook git `pre-commit`: richiede `core.hooksPath` e dipende da una variabile non documentata. |
| Linguaggio | Python 3, solo stdlib (compatibile con 3.7) | Presente sulla macchina, nessuna dipendenza, testabile con `unittest`. Lo stack del progetto non è ancora deciso. |

## 2026-09-24 — Copia raw del transcript accanto al Markdown

| Decisione | Scelta | Motivo |
|---|---|---|
| Versione raw | Accanto a ogni `.md` viene salvata una copia identica del transcript JSONL, con lo stesso nome e estensione `.jsonl` | Fedeltà totale e possibilità di riprocessare le sessioni in futuro con un formato diverso. Accettato il costo: 100-500 KB a sessione e presenza di output dei tool e contenuti dei file letti dall'agente, quindi possibili segreti. |

## 2026-09-25 — Esplorazione read-only della House of Journeys API

| Decisione | Scelta | Motivo |
|---|---|---|
| Perimetro | Solo GET; escluse POST, PUT e anche PATCH/DELETE. Le GET che richiedono un `itineraryId` o `X-End-User-Authorization` sono documentate solo dallo schema OpenAPI e marcate "non verificate". | Nessun effetto collaterale sull'inventario reale; senza un POST quelle GET non sono raggiungibili. |
| Quota | Script `scripts/api_explore.py` con contatore locale: budget per finestra = min(remainingInWindow, 90 − usedInWindow), attesa fino a `windowEndsAt` + 2 s, stop immediato su 429. | Il limite è 120/min e `/v1/quota` consuma; il margine di 30 copre chiamate esterne allo script e skew di clock. Nessun 429 generato. |
| Conteggio item | Solo con parametri di default (canale Weebora, locale en), `limit=100`. | Contenere le chiamate; gli altri canali hanno un catalogo separato, annotato ma non contato. |
| Chiave API | Letta solo dalla variabile d'ambiente `API_BEAR_KEY`, caricata con `set -a; . ./.env; set +a`. Il file `.env` non viene mai aperto. | Regola del progetto sui segreti. |
| Certificati TLS | `SSL_CERT_FILE=/etc/ssl/cert.pem` quando si usa il Python 3.7 di python.org su macOS. | L'interprete non ha un bundle CA e fallisce l'handshake. |
| Output | `docs/api/` con un file per gruppo di endpoint, `README.md`, `differences.md`, `counts.md`; nel repo solo esempi troncati a un item, dump completi fuori dal repo. | Documentazione leggibile e diff-abile senza versionare centinaia di KB di dati. |

## 2026-09-25 — Requisiti e architettura di Vela

Origine: intervista sul brief (`docs/brief.md`), risultato in `docs/spec.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Forma del prodotto | Core service senza interfaccia propria, chiamato da più superfici: REST e MCP nelle 24h; A2A predisposto e rimandato | Il brief premia "Vela arriva dove il viaggiatore è già": la conversazione la fa l'agente del viaggiatore (Claude, ElevenLabs). Una superficie in più è un adapter, non nuova logica. |
| Demo | Claude via MCP e agente vocale ElevenLabs via MCP | Copre sia il caso con schermo sia "niente occhi, niente schermo". |
| Stack | Python 3, FastAPI, Postgres, deploy su Render | Coerente con il tooling già nel repo, SDK maturi, infrastruttura che l'utente conosce. |
| Architettura | Variante A: dominio esagonale in `vela/`, porte HofJ e Stripe con implementazione reale e replay, un solo processo, task post-pagamento in background con ripresa all'avvio | Scala orizzontalmente perché tutto lo stato è in Postgres; niente worker separato da mantenere in 24h. Scartate B (worker + coda: due deploy) e C (un solo tool sincrono: forza la conversazione in un giro). |
| Pagamento | Stripe Payment Link sull'account test del progetto; webhook firmato; poi `POST /v1/bookings` con `paymentIntentId` e `paymentStatus` | Nessun dato di carta in Vela. Rischio aperto: se HofJ pretende il proprio PaymentIntent, fallback a una pagina minima Stripe.js sul `client_secret` di HofJ. Da verificare nella prima ora. |
| Comprensione dell'intento | Parser deterministico it/en; fallback Claude Haiku 4.5 solo se `ANTHROPIC_API_KEY` è presente | Nessun costo e nessuna dipendenza esterna nel percorso principale; il fallback si accende senza codice aggiuntivo quando la chiave esiste. |
| Proposta unica | Sempre un solo viaggio; "no + motivo" produce un'altra proposta; nessun limite; prodotto non prenotabile saltato in silenzio | È il vincolo squalificante del brief ("mai una lista"). Il limite di tentativi è stato scartato dall'utente. |
| Dati personali | Nome, cognome, email, telefono; pax aggiuntivi solo nome e cognome; indirizzo di default dichiarato | Una conversazione breve tiene il fuoco sull'intento unico. |
| Lingue | Intenti in italiano e inglese; catalogo HofJ in locale `it` | Demo in italiano, giudici anglofoni. |
| Catalogo | Copia in Postgres sincronizzata da un job incrementale (ogni 6 ore, advisory lock, ritmato dalla quota); snapshot `fixtures/catalog.json` committato | Il rate limit di HofJ è al minuto: nessuna richiesta del viaggiatore deve chiamare l'API per cercare. Lo snapshot copre replay, avvio a freddo e demo di emergenza. |
| Prezzo | In proposta "a partire da"; totale reale dall'itinerario prima del link | Il catalogo può essere vecchio di ore senza far pagare un prezzo sbagliato. |
| Load test | Locust contro il core in modalità replay, più i numeri reali di `GET /v1/quota` | Un test contro l'API reale misurerebbe solo il 429 di HofJ. |
| Segreti | Solo variabili d'ambiente (`HOFJ_API_KEY`, `STRIPE_SECRET_KEY`, ...); `.env` mai aperto dagli agenti | Regola del repo; il `.jsonl` in `agent-log/` è versionato. |
| Cartella log | `git mv agents-log agent-log`, con script, hook, doc e test aggiornati | Il brief chiede `/agent-log/`; la storia resta con `git log --follow`. |
| Email del codice | Fuori dalle 24h, elencata tra i prossimi passi | Richiederebbe un servizio non concordato; il codice resta disponibile via `get_order_status`. |

## 2026-09-25 — Roadmap in macro task

Origine: intervista sulla suddivisione del progetto, risultato in `docs/roadmap.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Primo prototipo | Replay end-to-end: 5 tool MCP, HofJ e Stripe finti | Test della conversazione completa da Claude senza quota né Stripe |
| Client del primo test | claude.ai / Claude Desktop contro Render | Il deploy entra nel prototipo (M0), nessun tunnel |
| Postgres | Solo Render Postgres, anche in sviluppo | Nessun setup locale. Conseguenza: test unitari senza DB (repository in memoria), test Postgres saltati se `DATABASE_URL` manca (RNF-09 aggiornato) |
| Fixture | Nuovo giro in locale `it`: lista + `extended=true` dei non archiviati (~96 chiamate in 2-3 finestre) | Fixture nella lingua finale, con destinazione, venue e hotel |
| Verifiche di spec §8 | Primo passo della macro task HofJ reale (M5) | Meno task; il prototipo replay non le richiede |
| Formato roadmap | Un solo file `docs/roadmap.md` | Grafo, tabella, prompt per task e matrice requisiti in un posto solo |
| Parser | Minimo nel prototipo (M2); completo con fallback Haiku in M9 | Prototipo prima |
| Auth MCP | OAuth 2.1 (modifica RF-43), più token statico pre-provisionato per client senza OAuth (ElevenLabs) | I connector custom di claude.ai accettano OAuth o nessuna auth, non un header bearer impostato dall'utente |
| Ponte auth | `/mcp` senza auth finché non esiste l'OAuth (M8) | Meno codice da buttare; l'URL resta aperto per poche ore |
| Taglio | Fette verticali attorno a due traguardi: A prototipo replay (M3), B prenotazione reale (M7) | Prototipo presto, poi massimo parallelismo. Scartati il taglio per strato (prototipo tardi) e poche task grandi (piani illeggibili) |
| DB layer | SQLAlchemy Core + psycopg 3 + Alembic | SQL esplicito, advisory lock semplice, migrazioni al boot |

## 2026-09-25 — Caccia agli easter egg: ambiente e credenziali

| Decisione | Scelta | Motivo |
|---|---|---|
| Ambiente per i carrelli di prova | Staging `https://staging.api.hofj.com`, con fallback a produzione se la chiave non è accettata | Il brand `staging.weebora.com` richiesto dalla traccia esiste solo nel CMS di staging; in produzione i canali sono `weebora.com`, `terrarossa.com`, `booking.hofj.com`. |
| Credenziali | Chiave `API_BEAR_KEY` del client interno `test-dev-2`, caricata nell'ambiente della singola riga di shell, mai letta né stampata | Le rotte itinerari richiedono un client `internal`; la chiave era già disponibile nel worktree `api-recognition`. |
| Dove annotare le chiavi trovate | `docs/easter-eggs.md`, una sezione per chiave con chiamate ed esiti | Riproducibilità: le note guidano le chiavi successive e restano nel repo. |

## 2026-09-25 — M0: toolchain, deploy e health

Origine: intervista sulla task M0 di `docs/roadmap.md`, piano in
`docs/plans/2026-09-25-m0-fondamenta.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Toolchain | `uv` + `pyproject.toml` + `uv.lock`, Python 3.12 (`.python-version`, `requires-python >= 3.12`) | Il `python3` di sistema è 3.7; `uv` è già installato, il lock rende identici locale e Docker. Lo script `scripts/agents_log.py` resta compatibile 3.7 perché l'hook usa il `python3` di sistema. |
| Dipendenze | Tutte quelle concordate: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `httpx`, `mcp`, `stripe`; dev: `locust` | Un solo lock condiviso: le task parallele M2-M6 non toccano `pyproject.toml`. |
| Render | `render.yaml` Blueprint: web service Docker + Postgres, piano free, regione Frankfurt, `healthCheckPath: /health` | Infrastruttura nel repo; il Postgres free basta per le 24 h (scade dopo 30 giorni). |
| Migrazioni | `docker-entrypoint.sh`: `alembic upgrade head` poi `exec uvicorn` | Funziona in locale e su Render, anche sul piano free (senza `preDeployCommand`). |
| `/health` | 200 `{"status":"ok","db":"ok"}`; 503 `{"status":"degraded","db":"error"}` quando il DB manca o non risponde | Render non instrada traffico a un'istanza senza DB; il test senza `DATABASE_URL` verifica il 503. |
| Accesso DB | Engine SQLAlchemy Core sincrono (psycopg sync), endpoint FastAPI `def` nel threadpool | Semplice e testabile; pattern che M2-M6 ereditano. |
| Branch | `task/m0` non mergia `master` durante la task; merge solo alla fine | Scelta dell'utente. Conflitto atteso su questo file (entrambi i branch appendono in coda): tenere entrambe le sezioni. |
| Lingua | `README.md` in italiano | Coerente con `docs/`. |
| Configurazione | `vela/config.py` legge le variabili di spec §6 con `os.environ`, nessuna libreria extra; `DATABASE_URL` normalizzata (`postgres://`, `postgresql://` → `postgresql+psycopg://`) | Render fornisce `postgres://`; SQLAlchemy 2 con psycopg 3 vuole il driver esplicito. Il codice non legge mai `.env`. |
| Rinomina log | Solo la cartella `agents-log/` → `agent-log/`; `scripts/agents_log.py` e `docs/agents-log.md` mantengono il nome (spec §9) | Minimo cambiamento; il brief chiede solo la cartella. |

## 2026-09-25 — M0: decisioni prese durante l'esecuzione e la revisione

| Decisione | Scelta | Motivo |
|---|---|---|
| Pagine OpenAPI | `/docs`, `/redoc`, `/openapi.json` restano ai default FastAPI | Sono strumenti per sviluppatori, non un'interfaccia per il viaggiatore (spec §6 vieta pagine di ricerca, liste, filtri). Utili per rivedere la superficie REST di M4. Una prima versione le disabilitava; il reviewer ha fatto notare che `/openapi.json` restava comunque esposto. |
| `.dockerignore` | Esclude `.git`, `.venv`, `.env*`, `agent-log`, `docs`, `tests`, `scripts`, `loadtest`, `.claude`, `.superpowers`; tiene `fixtures/` | L'immagine contiene solo ciò che serve al runtime; M2 in replay legge `fixtures/catalog.json` dentro il container. |
| Pool Postgres | `pool_timeout` = 3 s (come `connect_timeout`), solo sul dialetto Postgres | Con il pool esaurito `/health` risponde 503 entro pochi secondi invece di attendere 30 s e far scattare l'health check di Render. SQLite in memoria non accetta l'opzione. |
| Percorsi Alembic | `script_location = %(here)s/alembic`, `prepend_sys_path = %(here)s` | Le migrazioni funzionano da qualunque directory di lavoro, non solo dalla radice del repo o da `/app` nel container. |
| Sessioni slash command | `scripts/agents_log.py` logga anche le sessioni il cui unico messaggio utente è uno slash command con argomenti | La sessione di brainstorm di M0 non aveva prodotto alcun log (primo messaggio filtrato come rumore, poi solo risposte ad `AskUserQuestion`). |
| Storia di `agent-log/` | `git log --follow agent-log/<file>` su un singolo file | `--follow` accetta un solo path e non segue una directory attraverso la rinomina. |

## 2026-09-25 — Deploy M0 verificato

| Decisione | Scelta | Motivo |
|---|---|---|
| URL live | `https://vela-n506.onrender.com`, Blueprint da `render.yaml` (web service Docker + Postgres free, Frankfurt) | `curl https://vela-n506.onrender.com/health` → `200 {"status":"ok","db":"ok"}` il 2026-09-25. L'entrypoint esegue `alembic upgrade head` con `set -e` prima di uvicorn: il servizio in ascolto prova che la migrazione `0001` è stata applicata. |

## 2026-09-25 — M1: fixture del catalogo in locale `it`

Origine: intervista sulla macro task M1, piano in `docs/plans/2026-09-25-m1-fixture-catalogo.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Riuso | `scripts/record_catalog.py` importa `Client` e `QuotaGuard` da `scripts/api_explore.py`; le risposte grezze restano fuori dal repo in `--raw-dir` | Zero modifiche al codice esistente; la fixture si ricostruisce con `--build-only` senza consumare quota |
| Contenuto della fixture | `products` = item della lista integrali (anche archiviati); `details[id]` = `{catalog: proiezione ai campi di RF-28 con i nomi dell'API, raw: dettaglio esteso senza chiavi media}` solo per i non archiviati | RF-28 vuole i campi elencati e il JSON grezzo; le immagini non servono e pesano; obiettivo ≈ 1 MB |
| Hotel di default | La proiezione porta `hotels` (= `rawAttributes.hotels` senza media) così com'è; la scelta dell'hotel è di M2 | La forma di `rawAttributes.hotels` non è documentata |
| Chiave API | `HOFJ_API_KEY` (spec §6) con fallback `API_BEAR_KEY` | Nome della spec senza cambiare il `.env` esistente |
| Brand | `HOFJ_BRAND` opzionale: se assente il parametro non viene inviato e il file ha `brand: null` | Configurazione da env come in spec §6 |
| Dry-run | Nessuna chiamata; stima dalla fixture esistente, altrimenti da `docs/api/counts.md` (123 prodotti, 92 attivi) | Il numero esatto di dettagli si conosce solo dopo la lista |
| Cartella grezza | La registrazione rifiuta una `--raw-dir` non vuota | Evita di mischiare due registrazioni |
| Validazione | `tests/test_catalog_fixture.py` verifica il file committato e si salta se manca | RNF-09: suite verde senza servizi esterni |
| Roadmap | `docs/roadmap.md` resta sul branch `doc/roadmap`, non mergiata su `task/m1` | Il piano è autosufficiente |
| Soglia del test | `tests/test_catalog_fixture.py` richiede almeno 70 prodotti attivi invece di 80 | il catalogo `it` registrato il 2026-09-25 ha 110 prodotti e 77 attivi (en: 123/92); il catalogo `it` è un insieme di voci CMS distinto (id 181-1093, categoryId 8/7/9) — margine per il churn |
| Brand nella fixture | letto dalle pagine di lista registrate, `HOFJ_BRAND` al build serve solo da controllo | `--build-only` può girare in una shell diversa: la fixture deve dire cosa è stato registrato |

## 2026-09-25 — M2: dominio, casi d'uso e replay

Origine: intervista sulla macro task M2, piano in `docs/plans/2026-09-25-m2-dominio-replay.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Sport del prodotto | Parole chiave `padel`/`tennis` cercate in ordine in titolo, slug, shortDescription, description; nessun segnale = `padel` | La fixture non ha un campo sport; il brand Weebora è padel; nessun prodotto perso |
| Chooser v1 | Esclusioni: archiviati, non prenotabili, rifiutati, sport diverso, date, pax. Ordinamento: area coincidente (città > paese), totale entro budget, prezzo crescente, id | "Solo prezzo" proporrebbe l'Italia a chi chiede la Spagna nella demo M3. Versione semplificata di RF-07; M11 raffina con geohierarchy |
| Date proposte | Il periodo dell'intento diventa un intervallo; il prodotto passa se l'intervallo interseca `[minDate, maxDate]` e ha una finestra di `availabilities` con inizio nel periodo e non nel passato: quella finestra è la data proposta. Senza periodo: prima finestra futura | RF-06 richiede date proposte; senza finestra non c'è data da dire |
| Rifiuto (RF-08 base) | `reject_proposal` salva prodotto e motivo in `rejections`; i criteri non cambiano | L'interpretazione dei motivi è M9. Con l'ordinamento scelto "troppo caro" produce la successiva per prezzo |
| Catalogo in replay | All'avvio, se `products` è vuota, la fixture viene caricata in Postgres (upsert idempotente). Il chooser legge sempre dal repository | Stesso codice in live; M10 sostituisce solo il caricatore |
| Test repository | Solo Postgres, con `DATABASE_URL` dall'ambiente; saltati senza. Un contratto di test condiviso gira sempre sul repository in memoria | RNF-09; l'URL è disponibile nel `.env` |
| Prenotazione post-pagamento | `BookingRunner` con `ThreadPoolExecutor` nel processo; `resume()` nel lifespan per gli ordini `paid_pending_booking`; `InlineRunner` nei test | RF-27 esercitata davvero; M6 riusa il runner dal webhook |
| Default RF-13 | `TravelerDefaults` costante in `vela/config.py` | L'elenco di variabili di spec §6 resta chiuso |
| Lingua di `say` | Solo italiano in M2; il parser riconosce comunque intenti in inglese e salva `language` | Semplifica; i template inglesi arrivano con M9 |
| Dati viaggiatore mancanti | `accept_proposal` risponde con l'elenco dei campi mancanti e una `say`; nessun ordine finché i dati non sono completi | Nessuno stato aggiuntivo oltre RF-25 |
| Proposta "aperta" | `get_proposal` restituisce l'ultima proposta dell'intento non rifiutata, anche se già accettata; una nuova scelta avviene solo dopo un rifiuto | Idempotenza: due `get_proposal` o un `get_proposal` dopo `accept` non producono un secondo prodotto né un secondo ordine |
| Modalità `live` | `create_app` fallisce all'avvio con `RuntimeError("VELA_UPSTREAM_MODE=live non disponibile prima di M5")` | Niente porte finte spacciate per reali |
| Denaro e id | `Decimal` per prezzi e totali (stringa con due decimali in `to_dict`), uuid4 come stringhe per id; codice prenotazione replay `R-` + 6 cifre | Coerente con `Money.amount` stringa di HofJ |

## 2026-09-25 — M2: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m2-dominio-replay.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| Schema dei test Postgres | I test dei repository usano lo schema `vela_test` (`search_path` nell'URL), creato se manca e svuotato a ogni test | I test cancellano le tabelle e non devono toccare i dati dell'app su Render |
| Migrazione su Render | Il test di M0 `test_upgrade_head_is_idempotent` applica `alembic upgrade head` allo schema `public`: eseguendo la suite con `DATABASE_URL` il DB di Render è passato a `0002` prima del deploy di M2 | Comportamento già previsto da M0; le tabelle nuove sono vuote e il codice M0 in produzione le ignora. Il deploy di M2 troverà la migrazione già applicata |
| Catalogo senza JSON grezzo nel chooser | `products.list_all()` non legge la colonna `raw`; `get()` la include | Il chooser non ne ha bisogno e il JSON grezzo della fixture pesa circa 1 MB |
| Prenotazione replay dopo un riavvio | `ReplayHofJ.create_booking` accetta qualunque id `it-replay-*`, anche se non è più in memoria | La ripresa di RF-27 avviene in un processo nuovo che non ha l'itinerario |
| Default RF-13 | `TravelerDefaults` definita in `vela/domain/models.py` con i valori; `DEFAULT_TRAVELER` in `vela/config.py` | Il dominio non importa la configurazione |
| Verifica end-to-end | Il flusso completo in replay (intento, proposta, rifiuto, doppio accept, checkout, `confirmed` con codice `R-`) è stato eseguito sull'app vera con Postgres nello schema `vela_test` | Prova il wiring reale oltre ai test con repository in memoria |
| Interprete | Test eseguiti con `uv run python` (3.12); il `python3` di sistema è 3.7 | Come da M0 |

## 2026-09-25 — Twist: 50.000 viaggiatori in dieci minuti

Origine: twist del brief ("Vela ha appena chiuso un accordo di distribuzione"); analisi sulla
carta contro `docs/spec.md` e `docs/api/quota-health.md`, nessuna chiamata esterna.

**Verdetto dell'analisi.** Lo strato conversazionale regge: intento, proposta e rifiuto non
toccano HofJ, il processo è stateless e scala con le istanze. Lo strato d'acquisto no: con
120 chiamate al minuto e 6 chiamate per acquisto Vela completa al massimo 20 acquisti al
minuto per client (200 in dieci minuti); il design precedente (RF-37) rispondeva "riprovo tra
un minuto" a quota esaurita, trasformando il picco in errori ripetuti, e RNF-04 (accettazione
sincrona entro 30 s) non teneva con 5 chiamate seriali da 2-6 s.

| Decisione | Scelta | Motivo |
|---|---|---|
| Risposta al twist | Coda d'acquisto + scheduler della quota nel dominio (spec §4.10) | Trasforma il tetto fisico in attesa dichiarata. Scartato "solo analisi in ARCHITECTURE.md" (il load test avrebbe mostrato gli errori) e "più client HofJ" (serve una seconda chiave; resta come prossimo passo in ARCHITECTURE.md) |
| Meccanica | A: coda in Postgres, worker in ogni istanza con `FOR UPDATE SKIP LOCKED`, contatore di quota in Postgres con prenotazione atomica di blocchi | Nessun servizio nuovo, coerente con "un processo", sopravvive ai crash. Scartati B (Redis/Celery: secondo servizio) e C (drenatore unico eletto: nessuna alta disponibilità) |
| Accettazione | Sempre asincrona: `queued` + attesa stimata, link via `get_order_status` | Un solo percorso da testare. Scartato l'ibrido sincrono-se-c'è-budget. Cambia §10.1 e le descrizioni dei tool MCP |
| Attesa lunga | Nessun tetto: l'attesa si dichiara, il viaggiatore può rinunciare con `reject_proposal` | Rifiutare e far ritentare ricrea il problema di RF-37 |
| Priorità | `booking` con riserva 20% della finestra, poi `purchase` FIFO, poi `sync` | Garantisce la prenotazione degli ordini pagati (twist: "una prenotazione al minuto sei") |
| Sostituzione in coda | Errore prodotto → ordine `replaced` con proposta sostitutiva; nuovo accept rientra in testa | Il viaggiatore riacconsente perché prezzo e hotel cambiano; non perde il posto |
| Dove nella roadmap | M5 (dominio, scheduler, worker, superfici adattate) e M13 (scenario twist); M2 non viene riaperta | M2 era già conclusa e mergiata quando è arrivato il twist |
| Degradazione | Interruttore sul fallback Haiku (M9), catalogo in memoria per istanza (M14), MCP stateless (M3) | RNF-12, RNF-13 |

## 2026-09-25 — M3: superficie MCP

Origine: intervista sulla macro task M3, piano in `docs/plans/2026-09-25-m3-superficie-mcp.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Trasporto MCP | Streamable HTTP stateless (`stateless_http=True`) con risposte JSON (`json_response=True`) | Nessuna sessione in memoria: regge riavvii e sleep del piano free di Render e client semplici (ElevenLabs). Lo stato vive già in Postgres |
| Montaggio | Le route di `streamable_http_app(streamable_http_path="/mcp")` sono innestate in `app.router.routes`; `session_manager.run()` nel lifespan dell'app | `Mount("/mcp")` risponde 307 a `POST /mcp`; `Mount("/")` trasformerebbe i 405 in 404 |
| Argomenti dei tool | Piatti: `first_name`, `last_name`, `email`, `phone` opzionali, `participants` lista di `{first_name, last_name}`; `create_intent` ha anche `pax` | Schema semplice da compilare per un modello vocale; `accept_proposal` si richiama finché `missing` è vuoto |
| Risultato dei tool | `CallToolResult` con `structuredContent` = `to_dict()` del caso d'uso e lo stesso JSON come testo; nessun `outputSchema`, nessun campo `kind` aggiunto | Contratto di M2 invariato; il modello distingue le varianti dalle chiavi (`question`, `failed_criterion`, `missing`) |
| Errori | `isError=true` con una sola frase italiana: `say_not_found(kind)` per id sconosciuti, `say_unavailable()` senza dominio, `say_error()` per eccezioni inattese (loggate con `logger.exception` su `vela.mcp`, mai nel risultato) | Il modello legge una frase utile invece di uno stack trace; nessun dettaglio interno esce |
| Lingua | Istruzioni del server e descrizioni dei tool in inglese; `say` resta italiano (M2) | I modelli seguono meglio le istruzioni in inglese; giudici anglofoni |
| Protezione DNS rebinding | Attiva. Host ammessi: `localhost`, `127.0.0.1` (con qualunque porta), `testserver`, host di `VELA_PUBLIC_URL`. Origin ammessi: `https://claude.ai`, `http://localhost:*`, `http://127.0.0.1:*`, origin di `VELA_PUBLIC_URL`; richieste senza Origin accettate | Difesa gratuita dell'SDK, nessuna variabile d'ambiente nuova |
| Dominio assente | `/mcp` sempre montato; senza `DATABASE_URL` ogni tool risponde `isError` con `say_unavailable()` | `/mcp` non va mai in crash; stesso comportamento di `/replay/checkout` (503) |
| Deploy e prova | Merge su `master` fatto dall'utente → autodeploy Render; smoke test automatico con `scripts/mcp_smoke.py` contro l'URL live (solo replay, nessun costo); conversazione in claude.ai fatta dall'utente; esiti in `docs/acceptance.md` | Il connector di claude.ai si configura solo dall'account dell'utente |
| "Troppo caro" | Resta a M9: in M3 il rifiuto produce una proposta diversa, non necessariamente più economica; criterio 1 in replay registrato come parziale | M3 resta solo superficie; nessun conflitto con il worktree di M9 su `intent.py`/`usecases.py` |

## 2026-09-25 — M3: decisioni prese durante l'esecuzione

| Decisione | Scelta | Motivo |
|---|---|---|
| Log dell'SDK MCP | `MCPServer(..., log_level="WARNING")` | Il costruttore chiama `logging.basicConfig` sul root logger (INFO con `RichHandler` di default): l'app avrebbe stampato i log INFO di tutte le librerie. Con WARNING resta visibile ciò che si vedeva prima di M3; M14 riconfigura i log in JSON. Test: `RootLoggingTest` |
| Log attesi nei test | I test che provocano rifiuti dell'SDK (argomenti non validi, Host/Origin non ammessi) li catturano con `assertLogs` e li verificano | Output dei test pulito, e il rifiuto è verificato anche dal log |

## 2026-09-25 — M4: superficie REST

Origine: intervista sulla macro task M4, piano in `docs/plans/2026-09-25-m4-superficie-rest.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| `VELA_API_TOKEN` assente | L'app parte; ogni `/v1/*` risponde 503 `rest-not-configured` (7807). `/health` e `/replay` restano disponibili | Fail closed senza accesso aperto per errore, diagnosi chiara su Render, i test esistenti non cambiano |
| Esiti previsti dei casi d'uso | Sempre 2xx con `{"outcome": ..., **to_dict()}`. 201 per `intent_created` e `order` (anche al secondo accept idempotente), 200 per `question`, `proposal`, `no_match`, `missing_traveler_data`, `order_status` | Domanda, "niente di compatibile" e dati mancanti sono risposte di dominio che l'agente legge (`say`), non errori. `to_dict()` resta invariato per M3 |
| `/health` | Nuovo `ProductRepository.last_fetched_at()` (memoria + Postgres `MAX(fetched_at)`); risposta con `catalog: {products, fetched_at, age_seconds}` (`null` senza dominio o con lettura fallita) e `quota: null` fino a M5; il codice di stato dipende solo dal DB | RNF-06 senza anticipare il guardiano della quota; il controllo di salute di Render non cambia comportamento |
| RFC 7807 | `type` = `/problems/<slug>` (`unauthorized`, `not-found`, `method-not-allowed`, `invalid-request`, `rest-not-configured`, `domain-unavailable`, `internal-error`, `http-error`), più `title`, `status`, `detail`, `instance` e `say` in italiano. Solo sotto `/v1`; `/health`, `/replay`, `/docs` mantengono il formato predefinito | Slug leggibili da un client; `say` permette all'agente di dire qualcosa al viaggiatore anche sull'errore |
| Test manuale §10.3 | Nessuno script: i comandi `curl` del flusso stanno in `docs/rest.md`; l'esecuzione contro Render avviene dopo il merge e l'esito va in `docs/acceptance.md` (creato se M3 non l'ha ancora creato) | Scelta dell'utente |
| Corpi delle richieste | Modelli Pydantic; campi extra ignorati; `text` ripulito dagli spazi, lunghezza 1-1000; `pax` ≥ 1; `profile`/`traveler` con la forma di `profile_to_dict` | Un agente che manda un campo in più non riceve un errore; testo vuoto e pax 0 sono errori del client |
| Autenticazione | `HTTPBearer(auto_error=False)` + `hmac.compare_digest`; schema `Bearer` case-insensitive; auth prima della validazione e del dominio; il token ricevuto non compare mai nella risposta | RFC 6750; niente oracle di validazione per chi non ha il token |
| OpenAPI | `/docs` e `/openapi.json` restano pubblici e includono lo schema Bearer | Utili a chi integra; non espongono dati |
| Endpoint sincroni | `def`, non `async def` | Il dominio è sincrono; FastAPI li esegue nel threadpool |
| Nessuna route per modalità | Il router REST è montato sempre, in replay e in live | La superficie non dipende dall'upstream |
## 2026-09-25 — M4: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m4-superficie-rest.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| Test Postgres di `last_fetched_at` | Non eseguiti in M4: il worktree `task-m4` non ha un `.env` e `DATABASE_URL` non è nell'ambiente, quindi i test Postgres sono saltati | Il `.env` non va cercato né aperto altrove. L'implementazione è una `SELECT MAX(fetched_at)`; da eseguire con `set -a; . ./.env; set +a; uv run python -m unittest discover -s tests` dove il file esiste |
| Guardie di regressione | `test_health_needs_no_token` e `test_health_and_replay_need_no_token` passavano già prima del codice nuovo | Non verificano codice nuovo ma impediscono che il router `/v1` o gli handler 7807 proteggano per errore `/health` e `/replay` |
| Flusso `curl` di `docs/rest.md` | Non eseguito in locale: senza Postgres il dominio non esiste (SQLite non supporta l'upsert Postgres dei repository). Il flusso è coperto dal test `FullFlowTest` sull'app vera con repository in memoria e verrà eseguito su Render dopo il merge | Nessun Postgres locale disponibile in questo worktree |
| Suite finale | 319 test, 12 saltati (Postgres), verde (erano 271 a inizio M4) | — |

## 2026-09-25 — M11: chooser v2

Origine: intervista sulla macro task M11, piano in `docs/plans/2026-09-25-m11-chooser-v2.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Area e budget | Restano criteri di ordinamento, mai di esclusione; se non rispettati la motivazione lo dichiara ("Non ho partenze compatibili a Lanzarote: questa è a Tenerife, alle Canarie") | RF-07 dice "si ordina per"; "nessun match su area/budget" diventa una proposta dichiarata, non un rifiuto |
| Gerarchia geografica | `PARENTS` statico in `geo.py`, solo tra voci già presenti in `PLACES`: Lanzarote, Tenerife, Fuerteventura → Canarie; Palma de Mallorca → Maiorca → Baleari; Minorca, Ibiza → Baleari; Firenze, Pietrasanta → Toscana. Il paese chiude sempre la catena | `geohierarchy` è piatto e sbagliato in due casi; nessun alias nuovo, il parser non cambia |
| `geohierarchy` | Non usato | Piatto, con errori, e richiederebbe un campo nuovo in `Product` |
| Punteggio d'area | 3 = dentro l'area chiesta (anche un paese chiesto e una città di quel paese), 2 = stessa regione (antenato comune non nazionale), 1 = stesso paese, 0 = altrove | RF-07 "città > regione > paese" |
| Area del prodotto | Dalla destinazione; se manca, dal titolo; se non riconosciuta, dal paese (`destination.country`) | 323/326 hanno Milano/Barcellona solo nel titolo; destinazioni nuove dal sync M10 degradano al paese |
| Date proposte | Finestra fissa (lunghezza ≤ durata, o durata assente): il viaggio è la finestra. Finestra aperta: inizio = max(inizio finestra, oggi, `minDate`, inizio periodo), fine = inizio + durata − 1 entro la finestra. L'inizio cade nel periodo e non nel passato; il ritorno può uscire dal periodo; il viaggio sta in `[minDate, maxDate]`. Vale la prima partenza valida | Un "weekend" accetta un 4 giorni che parte venerdì; le finestre aperte non vengono più proposte per intero |
| Ordine dei filtri | archived, bookable, trip, sport, dates, pax, **rejected per ultimo** | Con i rifiutati terzi, rifiutare l'unico padel produceva "nessun viaggio per lo sport chiesto" (falso). Ora `rejected` significa "i compatibili li hai scartati tutti" |
| Non-viaggi | Filtro duro `trip`: esclusi i prodotti con destinazione del brand (`Weebora`) o slug con `gift-card`. Sulla fixture esclude solo il 282 | Una gift card da 50 € non è un viaggio |
| Ordinamento | (−punteggio d'area, fuori budget, prezzo, id); totale = prezzo × (pax o 1) | Ordine di RF-07; tra i fuori budget vince il più vicino al budget |
| Motivazione | Al massimo 2 frasi. Frase 1: area (soddisfatta o compromesso dichiarato). Frase 2: data di partenza (+ "nel periodo che hai chiesto") e budget (dentro / oltre; "la più economica" solo quando è vero) | RF-06 |
| Messaggi RF-09 | `say_no_match(criterion, criteria=None)` cita il valore: sport, periodo, numero di persone | RF-09 "dice quale criterio non riesce a soddisfare" |
| Articolo delle date | `on_date`: "il 1 ottobre", "l'8 ottobre", "l'11 ottobre"; usato nella motivazione, nei periodi e nelle date secche di `say_proposal` | "il 8" non è italiano |
| Preposizioni | `geo.where`: "in Spagna", "a Lanzarote", "alle Canarie", "alle Baleari", "in Toscana", "in Sardegna"; usato anche da `say_intent_created` | Corregge "a Sardegna" di M2 |
| Test di proprietà | Esaustivi sulla fixture: per ogni intento della tabella si rifiuta in sequenza fino a `NoChoice("rejected")`, verificando le proprietà a ogni passo. Nessun generatore casuale, nessuna dipendenza | Scelta dell'intervista |

## 2026-09-25 — M11: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m11-chooser-v2.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| Verifica delle proprietà | Spostando il filtro `rejected` in testa falliscono `test_rejected_is_reported_only_when_compatible_products_were_all_rejected`, `test_failed_criterion_is_the_first_emptying_filter` e le proprietà su tutti gli 11 intenti della tabella; `test_filter_order` no, perché controlla la costante `FILTERS` e non l'ordine dei `steps` | Il piano citava `test_filter_order` tra quelli che dovevano fallire: correzione del piano, nessun cambio di codice |
| Bytecode dopo una mutazione | Dopo un ripristino con `git checkout` nello stesso secondo e con la stessa dimensione del file, Python riusa il `.pyc` della versione mutata: va cancellato `vela/domain/__pycache__/chooser.cpython-312.pyc` | L'invalidazione dei `.pyc` usa mtime in secondi e dimensione; evita falsi rossi dopo le prove di mutazione |

## 2026-09-25 — M6: Stripe, link di pagamento e webhook

Origine: intervista sulla macro task M6, piano in `docs/plans/2026-09-25-m6-stripe.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Tipo di link | Checkout Session, una per ordine, `mode=payment`, solo carta, un line item `price_data` in EUR per il totale reale, `metadata` `{order_id, itinerary_id}` sulla sessione e sul PaymentIntent, `expires_at` = creazione dell'ordine + 24 h − 1 min | I Payment Link non scadono da soli (RF-21). Stripe genera `checkout.session.expired` e accetta al massimo 24 h |
| Idempotenza verso Stripe | `idempotency_key = "vela-order-<order_id>"`, parametri deterministici: `expires_at` dipende da `order.created_at`, non dall'ora corrente | Stripe rifiuta una chiave ripetuta con parametri diversi; così un nuovo tentativo restituisce la stessa sessione e non nascono due link pagabili |
| Scelta dell'adapter | `STRIPE_SECRET_KEY` impostata → `StripePayments`, indipendente da `VELA_UPSTREAM_MODE`; senza `STRIPE_WEBHOOK_SECRET` o `VELA_PUBLIC_URL` l'app non parte (`RuntimeError`). Chiave assente → `FakePayments` | Nessuna variabile nuova (spec §6); il test manuale gira con HofJ in replay e Stripe reale |
| Ritorno dal Checkout | Due pagine HTML statiche servite da Vela: `/checkout/success` e `/checkout/cancel`, in italiano, senza JS, senza leggere il DB né mostrare dati | Scelta dell'utente. Deroga a spec §6 ("la sola pagina web è il Checkout di Stripe"), che viene aggiornata |
| Idempotenza del webhook | Tabella `stripe_events(id PK, type, received_at)` (migrazione `0003`), porta `WebhookEventRepository` con `claim` e `release`. Claim prima di elaborare; duplicato → 200 senza effetti; eccezione → release e 500 perché Stripe ripeta | Copre anche due consegne concorrenti dello stesso evento: vince il primo INSERT |
| Eventi non applicabili | Ordine sconosciuto, metadata mancante, `payment_status` diverso da `paid`, valuta o importo diversi dall'ordine → nessuna transizione, log di warning con id di evento e ordine, evento registrato, 200 | Ripetere l'evento non cambierebbe l'esito |
| Tipi non gestiti | 200 `ignored`, non registrati | Nessun effetto; l'endpoint va configurato su Stripe solo per i due tipi |
| RF-19 | `OrderStatusResponse` guadagna `total`, `currency`, `payment_url` (valorizzato solo per `awaiting_payment`, altrimenti `null`); `say` in `awaiting_payment` dice l'importo, mai l'URL | Campi additivi sull'interfaccia pubblica REST e MCP, approvati |
| Errore di Stripe in `accept` | L'adapter solleva `PaymentsError`; REST → 503 `/problems/payments-unavailable`; MCP → frase `say_payments_unavailable()`. Un nuovo accept sulla stessa proposta trova l'ordine senza link e lo ricrea | L'ordine resta unico; M5 poi sposterà tutto nel job d'acquisto con retry |
| Setup Stripe e test manuale | Fatti dall'utente seguendo `docs/stripe.md`; gli agenti non chiamano mai Stripe | Nessuna chiamata a servizi esterni durante l'esecuzione del piano |
| Etichetta del line item | `create_payment_link(order, description)`: il caso d'uso passa il titolo del prodotto | Il viaggiatore vede nel Checkout che cosa paga; modifica interna della porta |

## 2026-09-25 — M6: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m6-stripe.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| Logging di Alembic | `alembic/env.py` chiama `fileConfig(..., disable_existing_loggers=False)`; nuovo test `test_upgrade_keeps_existing_loggers_enabled` | Le migrazioni lanciate nello stesso processo dei test (`test_migrations`) spegnevano i logger `vela.*` già creati: gli `assertLogs` dei moduli eseguiti dopo (`test_webhooks`) fallivano solo nella suite completa. In produzione le migrazioni girano in un processo separato (`docker-entrypoint.sh`), quindi nessun effetto lì |
| Log nei test | `test_thread_runner_swallows_unexpected_errors` e i test del webhook e di MCP che producono warning ora li verificano con `assertLogs` | Con i logger non più spenti il traceback finiva in console; ora il log è un'asserzione e l'output della suite è pulito |
| Valori attesi letterali | `test_stripe_links.py` e `test_checkout_pages.py` usano URL, path e scadenza letterali (`2026-09-26 11:59 UTC`) invece delle costanti del modulo | Un'aspettativa ricavata dal codice sotto test passa sempre; i path letterali legano anche i `success_url`/`cancel_url` alle route reali |
| Test delle route montate | `test_webhook_and_checkout_routes_always_mounted` verifica le risposte HTTP (503/200) invece di `app.routes` | In questa versione di FastAPI le route dei router inclusi non espongono `path` in `app.routes`. Lo stesso motivo rende vuoto il test esistente `test_replay_router_absent_in_live` (fuori scope M6, da correggere a parte) |
| Test Postgres | Non eseguiti: `DATABASE_URL` non è nell'ambiente di questo worktree, quindi il contratto `claim`/`release` su Postgres e la migrazione `0003` su Postgres sono saltati | Il `.env` non va aperto. Da eseguire dove `DATABASE_URL` è disponibile |
| Merge con `master` (M9) | Fatto con merge, su richiesta dell'utente. 7 file in conflitto, tutti con entrambe le parti tenute. `vela/app.py`: `build_payments(settings)` più `extractor=extractor`. `say_status(status, booking_code, failure_reason, lang="it", total=None)`: il `lang` di M9 resta il quarto argomento, l'importo di M6 viene dopo, con la frase `_AWAITING_AMOUNT` in italiano e in inglese ("waiting for payment of …", compatibile con il test di lingua di M9). `usecases.py`: `_ensure_link` e `lang` insieme | Il merge non riscrive la storia; la suite dopo il merge è verde (534 test, 14 saltati) |
| Suite finale | 445 test, 13 saltati (Postgres), verde (erano 390 a inizio M6) | — |
| Rimozione del webhook Stripe | Tolti `vela/surfaces/webhooks.py`, il suo router, `tests/test_webhooks.py`, la porta `WebhookEventRepository` con le implementazioni in memoria e Postgres, lo schema `stripe_events_t` e il test di contratto; con `STRIPE_SECRET_KEY` basta `VELA_PUBLIC_URL` (niente `STRIPE_WEBHOOK_SECRET`). Restano Checkout Session, `checkoutRefId`, `OrderService.expire`, pagine di ritorno, `PaymentsError`, i campi di stato e il checkout di replay | Cambio di requisito deciso con HofJ: pagamento chiuso con `POST /v1/bookings`, verifica per interrogazione della Checkout Session in M5 (Task 13b). La chiave Stripe è una `rk_test` di HofJ |
| Tabella `stripe_events` | Nuova migrazione `0004_drop_stripe_events` (upgrade: drop; downgrade: ricrea), la `0003` resta; head attesa `0004` | La `0003` era già su `origin/master` (merge `a2c8def`) e forse applicata al DB di Render: cancellarla avrebbe impedito l'avvio. Scelta dell'utente |
| `STRIPE_WEBHOOK_SECRET` in config e `render.yaml` | Lasciata: `Settings` la legge ancora e `render.yaml` la dichiara, ma nessun codice la usa | Fuori dal perimetro della rimozione chiesta; toglierla tocca `test_config.py`, `test_render_yaml.py` e spec §6 (vincolo: non toccare la spec su questo) |
| Test manuale | Spostato dopo M5: senza il job di verifica un ordine pagato resta `awaiting_payment` | Guida aggiornata in `docs/stripe.md` |
| `checkoutRefId` sul PaymentIntent | `payment_intent_data.metadata` porta anche `checkoutRefId` = `itinerary_id`; i `metadata` della sessione restano `{order_id, itinerary_id}` | Aggiunto dopo le verifiche di M5 su staging: il PaymentIntent creato da HofJ (`POST .../payment`) lega il pagamento al carrello con questa etichetta, e la chiave Stripe è di HofJ (stesso account). Se basti a HofJ per riconoscere il pagamento è la domanda 1 di `docs/hofj-questions.md` (su `task/m5`) |

## 2026-09-25 — M9: parser completo, rifiuto con motivo, fallback Haiku

Origine: intervista sulla macro task M9, piano in `docs/plans/2026-09-25-m9-parser-rifiuti-haiku.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Criteri dopo un rifiuto | Nuovo `IntentRepository.update_criteria(intent_id, criteria)` in memoria e Postgres, nessuna migrazione | L'intento mostra sempre i criteri correnti; `criteria` è già una colonna JSON |
| "Più a sud" / "più a nord" | Tabelle statiche `SOUTH_OF` / `NORTH_OF` in `vela/domain/geo.py` (luogo o paese → aree ordinate, si prende la prima) | La fixture non ha coordinate; `geohierarchy` contiene solo paese e id GeoNames (per Nicosia con paese sbagliato) |
| "Più vicino" | Non gestito: motivo non riconosciuto, esclude solo il prodotto | "Vicino" a cosa è ambiguo senza la posizione del viaggiatore |
| Fallback LLM | SDK `anthropic` (dipendenza nuova), `claude-haiku-4-5-20251001`, strumento forzato `record_criteria`, timeout 5 s, 1 retry, dietro la porta `IntentExtractor` | Output strutturato ed errori tipizzati; la roadmap prevedeva l'SDK |
| Quando si chiama Haiku | Solo se il parser non trova né sport né periodo e `ANTHROPIC_API_KEY` è presente | Lettura letterale di RF-03; poche chiamate |
| Combinazione parser/Haiku | Haiku sovrascrive i campi che restituisce validi; valori invalidi scartati; la lingua resta quella del parser | Scelta dell'utente; la validazione evita valori impossibili |
| "Troppo caro" | Budget = 80% di prezzo × persone della proposta rifiutata, mai sopra il budget attuale; una cifra nel motivo vince | Scelta dell'utente (sconto percentuale) |
| Frasi inglesi | `say_*`, domande di RF-04 e motivazione del chooser in it/en secondo `criteria.language` | Rimandate da M2 a M9 |
| Regioni | Aggiunte a mano (Andalusia, Catalogna, Costa del Sol, Comunità Valenciana, Lombardia, Veneto, Emilia-Romagna, Occitania); dopo l'integrazione con M11 stanno nella gerarchia `PARENTS` (vedi sotto) | Il catalogo ha città |
| Documenti | Design e microtask in un solo file in `docs/plans/`, senza spec separata | Scelta dell'utente, come M0-M2 |

## 2026-09-25 — M9: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m9-parser-rifiuti-haiku.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| Versione SDK | `anthropic>=1.8.0` (installata 1.8.0, basata su `httpx2`); i test costruiscono le eccezioni con un `Request` di `httpx2` | Nessuna deviazione dal piano; l'SDK 1.x non usa più `httpx` |
| Test Postgres di `update_criteria` | Eseguiti con `DATABASE_URL` (External Database URL di Render, schema `vela_test`): suite completa 353 test verdi, nessuno saltato | L'URL interno di Render (`dpg-…-a`) non si risolve fuori da Render: in locale serve l'External Database URL |
| Prova reale di Haiku | Eseguita il 2026-09-25 con OK dell'utente, 1 chiamata: "un'idea per il ponte dei morti con la racchetta, siamo in 2" → periodo 2026-11-01/02 (`llm`), sport `null`, pax 2, nessuna domanda | Il fallback riconosce una festività che il parser non conosce e non inventa lo sport quando il testo è ambiguo |

## 2026-09-25 — M9: integrazione con M4 e M11

Origine: rebase di `task/m9` su `master` (che conteneva già M3, M4 e M11) prima del merge.

| Decisione | Scelta | Motivo |
|---|---|---|
| Metodo | Rebase di `task/m9` su `master`, poi merge su `master` | Regola della roadmap ("chi arriva secondo fa rebase"); scelta dell'utente |
| Frasi | Base di M4 (`on_date`, `say_no_match(criterio, criteri)` con il valore citato, frasi di errore delle superfici) più la versione inglese di M9; la lingua di `say_no_match` viene dai criteri | Nessuna regressione delle frasi italiane di M4; le frasi di errore delle superfici restano italiane perché non conoscono l'intento |
| Motivazione della proposta | Frasi del chooser v2 di M11 rese bilingui con la stessa struttura; `geo.where(area, lang)` | La motivazione "la regione nomina il paese" di M9 era per il chooser v1 ed è stata sostituita dalla gerarchia di M11 |
| Regioni di M9 | Aggiunte a `PARENTS` (Malaga → Costa del Sol → Andalusia, Barcellona → Catalogna, Valencia → Comunità Valenciana, Milano → Lombardia, ...) con le preposizioni ("in Andalusia", "sulla Costa del Sol", "nella Comunità Valenciana") | Senza gerarchia il chooser v2 dichiarava "Non ho partenze compatibili a Andalusia" per un prodotto a Malaga; le scelte fissate da M11 sul catalogo registrato non cambiano |
| Collisione dei log | `scripts/agents_log.py` aggiunge le prime 8 cifre dell'id sessione al nome quando il file esiste già con un'altra sessione | Le sessioni M4 e M9 sono partite nello stesso minuto con lo stesso prompt e si sovrascrivevano; il log di M4 resta con il suo nome, quello di M9 è `...-leggi-la-task-612db060.*` |

## 2026-09-25 — M5: HofJ reale, coda d'acquisto e scheduler della quota

Origine: intervista sulla macro task M5, piano in `docs/plans/2026-09-25-m5-hofj-reale.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Ambiente delle verifiche §8 e di M7 | Staging: `staging.api.hofj.com`, brand `staging.weebora.com`, un prodotto di staging (es. 118) invece di `t0054825` | È l'unico ambiente dove i carrelli sono già stati verificati; un booking non crea una prenotazione reale |
| Budget delle verifiche §8 | ≤ 8 chiamate HofJ: quota, POST itinerary, PUT customer, GET pax, PUT pax, GET itinerary, POST booking, più 1 di margine | Il booking (§8 riga 3) richiede il carrello completo; con meno chiamate la risposta resterebbe ambigua. La riga 2 è già coperta da M1 e la riga 5 è M12 |
| `paymentIntentId` per la verifica del booking | Lo crea l'agente con 1 chiamata Stripe in modalità test (`PaymentIntent` confermato con `pm_card_visa`), `STRIPE_SECRET_KEY` da env | Nessuna dipendenza da operazioni manuali in dashboard |
| Momento delle verifiche §8 | Task 1 del piano, manuale con l'utente; l'adapter HTTP (Task 15) parte dalle forme reali | Le forme reali arrivano prima di scrivere l'adapter; il resto procede con porte in memoria |
| Modello della finestra di quota | Finestra fissa di 60 s allineata a HofJ: `window_start`/`window_end` da `/v1/quota` al boot e dopo un 429, poi avanza di 60 s col nostro orologio | È il comportamento osservato su HofJ (finestra ancorata alla prima richiesta) e si realizza con una riga e un `UPDATE` atomico |
| Margine di sicurezza sul limite | Configurabile, default 10%: limite effettivo = floor(`limitPerMinute` × 0,9) = 108 | La chiave è condivisa con script ed esplorazioni |
| Riserva `booking` e formula dell'attesa | Riserva = floor(limite effettivo × 0,20) = 21; acquisti per finestra = (108 − 21) ÷ 5 = 17,4 | Coerenti con il margine: la formula usa il limite effettivo |
| Parametri "configurabili" | Campi di `Settings` con default, senza variabili d'ambiente nuove | L'elenco delle variabili d'ambiente di §6 resta chiuso; M13 imposta i valori nel proprio setup |
| Retry della prenotazione (RF-24) | 5 tentativi, attese di 5, 10, 20 e 40 s tra un tentativo e l'altro, solo su rete, timeout o 5xx; un 4xx porta subito a `booking_failed` | Circa 75 s in totale, vicino a RF-51 |
| Errore "del prodotto" (RF-17, RF-33) | Solo su `POST /v1/itineraries`: 400/404, oppure 502 il cui `detail` riporta un errore upstream 4xx/500 che non sia un timeout. Timeout, rete e altri 5xx sono errori di rete (retry). 401/403 sono errori di configurazione (`failed`, prodotto non marcato) | HofJ risponde 502 sia per un id sbagliato sia per un guasto; non si vogliono marcare prodotti buoni per 24 h |
| Posizione dopo una sostituzione | Il nuovo ordine eredita l'`enqueued_at` dell'ordine sostituito | FIFO per `enqueued_at`: passa davanti a chi è arrivato dopo, senza priorità speciali |
| Rinuncia (RF-49) esteso | Ordine `queued`, in lavorazione o `awaiting_payment` → `cancelled`, e si restituisce la proposta successiva; il job si ferma al passo seguente; l'itinerario HofJ resta orfano. Dopo il pagamento l'ordine non si tocca | Un rifiuto è sempre rispettato finché non c'è denaro in gioco |
| Pagamento in M5 | Il job usa `PaymentsPort`. `VELA_UPSTREAM_MODE=live` rifiuta l'avvio finché M6 non c'è (il `RuntimeError` cita M6) | Scostamento dalla roadmap («con live tutto avviene contro HofJ vero»): la prova reale di M5 passa da Task 1 e dai test con `MockTransport` |
| Esecuzione del worker | N thread per processo (default 4) con polling di 1 s sulla tabella `jobs`; un job `running` con lease scaduto (2 min) torna prelevabile | Il dominio è sincrono; il lease copre RF-27 anche con più istanze |
| Blocco di quota per job | Un acquisto prenota le chiamate HofJ dei passi che restano (nuovo job: 5); una prenotazione ne prenota 1 | Non si spreca budget su retry e riprese; la formula dell'attesa resta a 5 |
| Posizione in coda | Parte da 1 e conta solo i `purchase` in stato `pending` con `enqueued_at` precedente; `wait_seconds = ceil(pos × 60 ÷ acquisti_per_finestra)`; `say` arrotonda i minuti per eccesso, minimo 1 | Stima semplice e spiegabile |
| Contratto delle risposte | Accept: `{order_id, status, position, wait_seconds, say}`. Status: `{order_id, status, position, wait_seconds, total, currency, price_from_total, total_differs, payment_url, booking_code, failure_reason, proposal_changed, proposal, say}`, con `null` quando non pertinente | Forma stabile per MCP, REST e test |
| REST accept | 202 Accepted, outcome `order_queued`, header `Location: /v1/orders/{id}`; un doppio accept risponde 200 `order_status` con lo stato attuale | Semantica HTTP corretta per il lavoro asincrono |

## 2026-09-25 — M5: verifiche di spec §8

Origine: Task 1 del piano `docs/plans/2026-09-25-m5-hofj-reale.md`, eseguito con l'utente su
staging (`https://staging.api.hofj.com`, brand `staging.weebora.com`). Forme osservate in
`docs/api/internal-checkout.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Chiamate usate | 9 HofJ (budget alzato da 8 a 9 con l'utente per il controllo dopo il booking) + 1 Stripe in modalità test (`PaymentIntent` 368,00 € `succeeded`) | Il valore 8 della roadmap non ha una motivazione registrata: 7 chiamate erano necessarie, 1 è stata spesa per il 404 in `locale=it`, 1 per verificare lo stato dopo il booking |
| §8 riga 1 (chiave interna) | Superata: `POST /v1/itineraries` risponde 200, nessun 403 | Carrello `dlp5lyj338uf` creato, customer e pax scritti |
| §8 riga 4 (quota) | `limitPerMinute` 120, finestra fissa di 60 s con `windowStartedAt`/`windowEndsAt` | Conferma il modello della finestra deciso nell'intervista |
| §8 riga 3 (pagamento sul nostro Stripe) | **Non dimostrata.** `POST /v1/bookings` con il nostro `paymentIntentId` risponde 200 ma con l'`itineraryId` invece di un codice `R-…`; `checkout.status` resta `BookingInitiated` (valori non documentati). Da DOCS/OAS il pagamento previsto è sul PaymentIntent creato dal brand site sul proprio account Stripe (`POST .../payment` → `client_secret` → Stripe.js); il nostro `pi_` vive su un altro account e viene solo inoltrato. Decisione sul fallback rinviata all'utente (cambia M6) | Il 200 dice solo che l'upsert è avvenuto; il brand site non può vedere un PaymentIntent del nostro account |
| Lingua del carrello | Il prodotto 118 in `locale=it` dà 502 con `detail` "returned 404"; in `locale=en` funziona. Rischio da annotare per la produzione (catalogo `it` di M1) | Un prodotto non tradotto fallisce al passo 0 e diventa errore del prodotto |
| Errore del prodotto nell'adapter | Il testo reale `... POST /itinerary returned 404: ...` entra nei test del Task 15 come caso di `ProductError` | Conferma il criterio "502 con upstream 4xx nel `detail`" |
| Codice di prenotazione | `POST /v1/bookings` restituisce `data: "<itineraryId>"`, non `R-…`: `booking_code` = quella stringa. La frase vocale andrà scandita | Forma osservata |
| Totale reale | Da decidere tra `checkout.total` (368, uguale a `totalPrice`) e `openAmount` (337, uguale a `originalTotal`): DOCS dice che `paymentType: "full"` addebita "the entire open amount". Origine della differenza di 31 € non nota | Il PaymentIntent di prova è stato creato su 368, probabilmente l'importo sbagliato |
| Pax | `pax-1` è precompilato dal customer: il `PUT pax` scrive comunque tutti i nomi preservando i `refId` | Nessun cambio al job |
| Pagamento (esito §8 riga 3) | ~~Pagamento sul PaymentIntent di HofJ invece del link~~ Superata dalla riga "Pagamento: scelta" della sezione "M5: integrazione con M6 e M9" | La seconda sonda ha mostrato che la chiave Stripe è di HofJ e che il flusso documentato dà lo stesso esito |
| Importo del link | `checkout.openAmount` (DOCS: `full` addebita "the entire open amount") | Il PaymentIntent di prova su `checkout.total` (368) era probabilmente l'importo sbagliato |

## 2026-09-25 — M5: seconda sonda sul pagamento (flusso documentato)

Origine: richiesta dell'utente dopo la rilettura di DOCS/OAS. 6 chiamate HofJ + 2 Stripe (test).

| Decisione | Scelta | Motivo |
|---|---|---|
| Esito del flusso documentato | `POST .../payment` → PaymentIntent del brand da 337 € (`openAmount`) con `metadata.checkoutRefId = itineraryId`, confermato `succeeded`; booking 200 con `data = itineraryId`; `checkout.status` resta `BookingInitiated` | Stesso comportamento della prima sonda: su staging il booking restituisce l'`itineraryId` e lo stato del carrello non cambia, pagamento o no |
| Conclusione sulla §8 riga 3 | La conclusione "HofJ ignora il nostro pagamento" è **ritirata**: la chiave Stripe è di HofJ, i due PaymentIntent stanno sullo stesso account, e dall'API non si distingue un booking pagato da uno non pagato. Differenze reali del nostro PaymentIntent: importo (`total` invece di `openAmount`) e assenza di `metadata.checkoutRefId` | Nessun segnale osservabile dall'API interna; `GET /v1/bookings/{id}` richiede il token dell'utente finale |
| Pagamento in M6 (da decidere in M6) | Due strade compatibili con quanto osservato: (a) usare il PaymentIntent del brand (`POST .../payment`) e confermarlo da una pagina nostra; (b) creare noi il PaymentIntent sullo stesso account con `amount = openAmount` e `metadata.checkoutRefId = itineraryId`. Da chiedere a HofJ quale riconcilia il pagamento lato brand | La chiave è ristretta e di HofJ: serve la loro conferma |
| Importo del link | Confermato `openAmount` (il PaymentIntent del brand è di 337 €) | Osservato |

## 2026-09-25 — M5: integrazione con M6 e M9

Origine: lettura di `task/m6` e di `master` (M9) prima del Task 2; decisioni prese con l'utente.
Dettagli nella sezione "Integrazione con M6 e M9" del piano M5.

| Decisione | Scelta | Motivo |
|---|---|---|
| Pagamento: scelta | Si resta sulla Checkout Session di M6 (account Stripe di HofJ), con `metadata.checkoutRefId = itineraryId` sul PaymentIntent (fatto su `task/m6`, commit `6aecb03`) e importo = `openAmount` (scritto dal job d'acquisto di M5). Conferma attesa da HofJ (`docs/hofj-questions.md`, domanda 1) | Compatibile con quanto osservato; il flusso con Stripe.js cambierebbe molto M6 e richiede la `pk_test` |
| `paymentIntentId` nel booking | Inoltrato con `paymentStatus` (inverte la regola del piano dopo il Task 1) | OAS lo inoltra al brand site: secondo modo con cui HofJ può riconoscere il pagamento |
| Notifica del pagamento a Vela | ~~Webhook principale, polling di riserva~~ Superata: vedi "M5: pagamento senza webhook" | — |
| Logica del pagamento | `OrderService.settle_payment`, usata dal job di verifica (Task 13b) | Una sola regola per importo, valuta e transizione |
| Eventi Stripe senza `order_id` | ~~Log `debug`~~ Superata: nessun webhook | — |
| Migrazione | `0004_jobs_quota` dopo `0003_stripe_events` di M6 | Numerazione lineare dopo il merge di M6 |
| Frasi | Ogni frase nuova in italiano e inglese | M9 ha reso le frasi bilingui |
| Modo live | Nessun rifiuto all'avvio: `live` usa `HofJHttp` e i pagamenti scelti da M6 | M6 esiste; la decisione "live in attesa di M6" dell'intervista è superata |

## 2026-09-25 — M5: pagamento senza webhook

Origine: indicazione di HofJ riportata dall'utente ("chiudere il pagamento sfruttando unicamente
le API di HofJ, senza webhook"; la chiave Stripe fornita permette di pagare passando dall'API
bookings), interpretazione confermata dall'utente.

| Decisione | Scelta | Motivo |
|---|---|---|
| Chiusura del pagamento | Il pagamento (Checkout Session creata con la chiave di HofJ) si chiude con `POST /v1/bookings` che inoltra `paymentIntentId` e `paymentStatus` | Indicazione di HofJ |
| Come Vela sa che il viaggiatore ha pagato | Job `payment_check` nel worker: legge la Checkout Session ogni 60 s e subito quando il viaggiatore chiede lo stato; `paid` → `settle_payment` → job `booking` | Nessun webhook; il booking non va chiamato alla cieca perché su staging risponde 200 anche senza pagamento |
| Spec | RF-20 riscritta (verifica per interrogazione), RF-51 e la voce Stripe di §2 adeguate | La spec descriveva il webhook |
| M6 | Da togliere: webhook `POST /webhooks/stripe`, tabella `stripe_events` (migrazione `0003`), obbligo di `STRIPE_WEBHOOK_SECRET`. Resta: Checkout Session, `checkoutRefId`, pagine di ritorno, scadenza. Modifica da concordare su `task/m6`, oppure rimozione nel Task 13b di M5 dopo il rebase | Coerenza con la nuova RF-20 |
| Domande a HofJ | Domanda 3 (webhook) chiusa; domanda 1 chiusa per la parte "come si chiude" (booking con `paymentIntentId`) | Risposta arrivata tramite l'utente |

## 2026-09-25 — M5: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m5-hofj-reale.md` in TDD, Task 2-19.

| Decisione | Scelta | Motivo |
|---|---|---|
| Ordine dei task | 11 → 12 → 13 → 13b → 14 → 10+17 → 15 → 16 → 18 → 19 (deciso con l'utente) | Con l'accettazione asincrona nessuno produce il link finché job, processore e worker non esistono: la suite resta verde a ogni commit |
| Contatore di quota su Postgres | Riga unica bloccata con `SELECT ... FOR UPDATE` per tutta la decisione, invece di un solo `UPDATE` condizionale | Stessa atomicità, e le regole restano funzioni pure in `vela/domain/quota.py` condivise da memoria e Postgres. Verificato con 8 thread sullo stesso contatore: concessi esattamente 87 acquisti |
| Percentuali della quota | Calcolate con `Decimal` | In float 100 × 0,29 = 28,999… e il floor sbaglia |
| Test dei job | Nel contratto dei repository, non in un file a parte | I job hanno una foreign key sugli ordini |
| Ordine di prelievo | `booking`, poi `payment_check`, poi `purchase` per `enqueued_at` | La verifica del pagamento non consuma quota HofJ e sblocca pagamenti già fatti |
| Quota non usata | Le chiamate prenotate e non usate da un job interrotto non tornano nel budget | Semplicità; il costo è al massimo un blocco per errore |
| Lettura della quota fallita | Si riprova solo nella finestra successiva; intanto si lavora con la finestra che si ha | Evita un ciclo di chiamate a `/v1/quota` (RF-47) |
| Proposta sostituita | Chiusa registrando un rifiuto con motivo "prodotto non prenotabile" | Altrimenti `_propose` riproporrebbe la stessa proposta aperta |
| Accept sulla proposta sostitutiva | Riusa i dati del viaggiatore dell'ordine sostituito | Trovato dai test: senza, Vela richiedeva dati già dati |
| Ordine in coda ma già in lavorazione | Niente posizione né attesa; frase "Sto preparando il pagamento con il fornitore" | L'attesa stimata vale solo per chi aspetta il proprio turno |
| Chiedere lo stato di un ordine da pagare | Anticipa a subito la verifica del pagamento, senza chiamate nel caso d'uso | Il viaggiatore che dice "ho pagato" non aspetta i 60 s del polling |
| Motivi di fallimento della prenotazione | Codici `booking_upstream` e `booking_rejected` con frasi it/en | Il piano non li elencava |
| Checkout di replay | Paga il link finto e applica subito l'esito (`settle_payment`), la prenotazione passa dal worker | Stesso percorso della verifica reale, risposta immediata in replay |
| `say_accept` | Rimossa con i suoi test | L'accettazione non dà più totale né link |
| Errore del fornitore di pagamento | Ripetuto dal job d'acquisto (3 tentativi, poi `failed`); la 503 `payments-unavailable` di REST e la frase MCP non sono più raggiungibili dall'accept (codice lasciato, riga tolta da `docs/rest.md`) | Il link lo crea il job, non l'accettazione |
| Modo live | Richiede `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND` e `STRIPE_SECRET_KEY`; il catalogo resta la fixture di M1 finché non c'è M10 | Con il pagamento finto il link punterebbe a `/replay/checkout`, che in live non esiste |
| Downgrade della `0005` | Cancella gli ordini senza totale (in coda) | Lo schema precedente non li rappresenta; alternativa era un totale falso |
| Smoke test MCP | `scripts/mcp_smoke.py` interroga lo stato finché il link è pronto, poi finché l'ordine è confermato; parametro `tick` per far avanzare la coda nei test | Il flusso ora è asincrono |
| Test Postgres | Eseguiti con l'External Database URL, passando al processo solo `DATABASE_URL` e isolando lo schema con `PGOPTIONS=-csearch_path=vela_test`: lo schema dell'app resta alla head di `master` | Il test della migrazione altrimenti porterebbe lo schema dell'app alla `0005` e il deploy di `master` non partirebbe |
| Da verificare in M7 | La fixture è il catalogo di produzione (`it`), le verifiche di §8 erano su staging (prodotto 118 solo in `en`) | Con `live` su staging gli id della fixture non esistono: M7 deve scegliere ambiente e catalogo coerenti |
| Suite finale | 709 test, 40 saltati senza `DATABASE_URL` (erano 390 a inizio M5, 513 dopo il rebase su M6 e M9) | — |


## 2026-09-25 — M7: prima prenotazione reale end-to-end

Origine: intervista sulla macro task M7, piano in
`docs/plans/2026-09-25-m7-prima-prenotazione-reale.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Ambiente live | HofJ staging (`https://staging.api.hofj.com`, brand `staging.weebora.com`) con un catalogo di staging registrato apposta | Un booking su staging non crea una prenotazione vera; è l'ambiente verificato in M5. La fixture di M1 è il catalogo di produzione e i suoi id non esistono su staging |
| Locale | Catalogo di staging registrato in `en`; `HofJHttp` usa il `locale` della fixture caricata, nessuna variabile d'ambiente nuova | Su staging il prodotto 118 dà 502 in `it` e funziona in `en`; le frasi `say` seguono comunque la lingua del viaggiatore |
| Catalogo sul DB | Una fixture per ambiente (`fixtures/catalog.json` di produzione per replay e test, `fixtures/catalog-staging.json`). In live si sceglie la fixture con `base_url` = `HOFJ_BASE_URL`, altrimenti l'app non parte. Al boot, se gli id attivi nel DB differiscono da quelli della fixture: upsert e prodotti assenti marcati `archived` | Il DB di Render ha il catalogo di produzione referenziato da proposte e ordini: niente DELETE. Il riallineo solo su differenza preserva i flag `bookable` di RF-33 tra un riavvio e l'altro |
| Criterio 4 | Prodotto trappola dichiarato nella fixture di staging: clone di un prodotto reale, id numerico inesistente su HofJ, prezzo più basso, `vela_trap: true` | Prova ripetibile; HofJ risponde con un vero errore di prodotto (502, upstream 404) |
| Criterio 3 e latenza | Nuovo `scripts/rest_flow.py` cronometrato | Misura ripetibile per M13 |
| Criterio 1 | Eseguito dall'utente in claude.ai col connector Vela; pagamento 4242 dall'utente; l'agente guida e registra | Lettura letterale di §10.1, ripetibile per il video |
| `render.yaml` | `VELA_UPSTREAM_MODE: value: live` | Un valore cambiato solo in dashboard può essere riportato a `replay` da una sincronizzazione del Blueprint |
| Allineamento del branch | `task/m7` portato a `master` (con M5) con un fast-forward | Nessun commit proprio sul branch, nessuna riscrittura della storia |

## 2026-09-25 — M7: decisioni prese durante l'esecuzione

Origine: esecuzione del piano `docs/plans/2026-09-25-m7-prima-prenotazione-reale.md` in TDD.

| Decisione | Scelta | Motivo |
|---|---|---|
| `build_hofj` | Restituisce l'adapter e il suo caricatore del catalogo; in live entrambi dalla fixture scelta per `HOFJ_BASE_URL`, i test la sostituiscono con `mock.patch("vela.app.FIXTURES_DIR")` | Un solo punto sceglie la fixture; nessun parametro in più da far passare per `create_app` |
| Riallineo del catalogo | `realign_catalog` al boot, `ProductRepository.archive_missing` (UPDATE, mai DELETE); `/health` invariato (conta anche gli archiviati) | Il riallineo si verifica dal log di boot (`catalog_loaded`, `catalog_archived`) |
| "Troppo caro" (Task 6b) | Dopo un rifiuto per prezzo (parole di RF-08 o una cifra nel motivo, `refine.is_price_reason`) il chooser esclude i prodotti con totale ≥ quello della proposta rifiutata: filtro `price` prima di `rejected`, tetto = totale più basso tra le proposte rifiutate per prezzo, ricavato dai rifiuti (`RejectionRepository.list_for_intent`). L'ordinamento non cambia (area prima), quindi può arrivare un altro paese, dichiarato dalla motivazione. Niente di più economico → `no_match` con `failed_criterion` `price` e frase it/en | Trovato da `scripts/rest_flow.py` contro il replay: con il chooser v2 (M11) la prima proposta è già la più economica dell'area, e dopo "troppo caro" arrivava la successiva nell'area, più cara (558 → 600 €), contro §10.1. Scelta dell'utente tra tetto di prezzo, budget come esclusione e nessun cambio. Il tetto non sta nei `Criteria` perché finiscono nella risposta pubblica `intent_created` |
| Test aggiornati dal Task 6b | `test_filter_order` (nuovo filtro `price`), `test_no_match_covers_every_criterion` e `test_no_match` (6 frasi), `test_reject_gives_a_different_product` (dopo "troppo caro" il prodotto 1 a 300 € invece del 4 a 390 €), `test_too_expensive_lowers_budget` (resta solo la verifica del budget, la scelta passa al nuovo test) | Fissavano il comportamento cambiato da questa decisione |
| Test Postgres | `archive_missing` e `list_for_intent` su Postgres non eseguiti in questo worktree (`DATABASE_URL` assente): 42 saltati | Da eseguire prima del merge dove l'URL è disponibile |
| Push di M5 e M7 | `origin/master` era fermo a M6: il merge di M7 (`d31e51e`) ha portato su GitHub e Render anche M5 (migrazione `0005`). Il push è riuscito solo con `git -c http.postBuffer=524288000 push` (il primo si interrompeva con "remote end hung up") | Pacchetto grande per i log jsonl delle sessioni |
| Primo deploy live fallito | `HOFJ_BASE_URL` su Render valeva `api.hofj.com/v1`: `select_fixture` ha rifiutato l'avvio. Corretto dall'utente in `https://staging.api.hofj.com` (senza `/v1`, l'adapter lo aggiunge) | Il controllo della fixture ha impedito di chiamare la produzione |
| Catalogo su Render | `/health` 197 prodotti: 110 di produzione + 88 di staging − 1 id in comune (`886`, sovrascritto dall'upsert) | Atteso; tornando in replay la fixture di produzione ripristina la riga |
| Frase dei criteri 1 e 3 su staging | "un weekend di padel a Barcellona a ottobre, siamo in due, massimo 1500 euro" invece della frase di §10.1 | Il 867 (unico più economico del 28 in Spagna) ha un errore di configurazione Nezasa lato HofJ; scelta dell'utente tra rilanciare, cambiare frase e chiedere a HofJ |
| Test Postgres prima del merge | Non eseguiti su richiesta dell'utente (esecuzione interrotta, solo schema `vela_test`) | `archive_missing` e `list_for_intent` su Postgres restano non verificati dai test; il riallineo su Render ha funzionato (`/health`) |
| Trappola del criterio 4 | Tolta dalla fixture di staging dopo l'esecuzione del 2026-09-26 (scelta dell'utente); `add_trap` e `--trap-from` restano per ripetere la prova. Al deploy il riallineo del catalogo archivia `900078` | Costando 249 €, dopo "troppo caro" diventava la più economica fuori area anche su intenti non su Firenze (Spagna a novembre): in demo, video e M12 non deve comparire |
| Criterio 1 | Accettata come esecuzione la conversazione dell'utente "Spagna, novembre, 800 €" invece della frase letterale di §10.1 | Contiene tutti i passi di §10.1 (proposta singola, "troppo costoso" → più economica, accept, link, pagamento, `confirmed` con codice); la frase di §10.1 su staging porta al 867, non prenotabile |
| Chiamate esterne di M7 | HofJ staging: 58 per la registrazione del catalogo; 1 per il carrello fallito del 867; 6 per il criterio 3 su Barcellona; 5 per la prova `--trap` finita sul 78; più 1 `/v1/quota` a ogni avvio del servizio. Stripe test: 2 Checkout Session create dall'agente (una pagata, una annullata) più le letture della sessione. Le conversazioni dell'utente in claude.ai ne hanno usate altre (2 ordini confermati, 1 sostituito) | Tetti dichiarati nel piano rispettati; la prova `--trap` ha speso 5 chiamate e 1 sessione non previste perché la trappola era già stata consumata |
| Suite finale | 773 test, 42 saltati senza `DATABASE_URL` (erano 709 a inizio M7) | — |

## 2026-09-26 — Contratto tra l'agente e i tool MCP

Origine: conversazione osservata in claude.ai. Il viaggiatore ha rifiutato una proposta ("troppo
caldo, vorrei un posto più freddo") e l'agente ha "riformulato" con `create_intent` invece di
`reject_proposal`: il nuovo intento non aveva rifiuti, il chooser è deterministico ed è tornata
la stessa proposta. "Più freddo" non era capito né da `intent.py` né da `refine.py`, e lo sport
non era mai stato chiesto (con il periodo presente la vecchia RF-04 non lo richiedeva).
Requisiti in `docs/spec.md` §4.11 (RF-52..55), casi d'uso in `docs/usecases/agente-tool.md`,
implementazione in roadmap M17.

| Decisione | Scelta | Motivo |
|---|---|---|
| Campi strutturati | Opzionali su `create_intent` e `reject_proposal`, MCP e REST con lo stesso contratto: `sport` (`padel` \| `tennis` \| `any`), `area`, `period_start`, `period_end`, `pax`, `budget`. `text` e `reason` restano e si passano sempre | L'agente ha già capito i criteri; farli ricostruire dal parser perde informazione. Modifica additiva: i client solo testo funzionano come prima |
| Precedenza | Sul server: campo strutturato valido > parser deterministico > fallback Haiku. Campo invalido (es. area sconosciuta a `geo`) scartato senza bloccare, e dichiarato nel `say`. Conflitto testo/campo: vince il campo, conflitto nei log | Il campo è la lettura dell'agente, più ricca del parser; lo scarto e il `say` evitano che un errore dell'agente blocchi il viaggiatore |
| `say` con i criteri capiti | Il `say` di `create_intent` e `reject_proposal` ripete sempre sport, area, periodo, persone, budget | Il viaggiatore sente e corregge eventuali campi inventati dall'agente |
| RF-04 | Lo sport è sempre indispensabile (non più "sport oppure periodo"). Se manca: `question` "Padel o tennis?" e nessun intento salvato. "Indifferente" / "tutti e due" è valido → `sport=any` → nessun filtro sport nel chooser | Senza sport la proposta è un tiro a caso tra due prodotti diversi |
| Descrizioni dei tool | Prima di `create_intent`, se il viaggiatore non ha detto padel, tennis o indifferente, l'agente lo chiede. Lo schema non rende `sport` obbligatorio | Con il campo obbligatorio l'agente indovinerebbe invece di chiedere; il server resta la rete di sicurezza |
| Cambiamenti dopo una proposta | Ogni cambiamento (luogo, periodo, sport, budget, "più fresco") passa da `reject_proposal` con i campi aggiornati, mai da un nuovo `create_intent`. Le descrizioni di `get_proposal` e `create_intent` non suggeriscono più di "riformulare" | Un nuovo intento perde i rifiuti e ripropone lo stesso prodotto: è il difetto osservato |
| Direzione | `reject_proposal` accetta `direction` (`north` \| `south`); l'agente traduce "più fresco" → `north`, "più caldo" → `south`; il server usa `geo.move` | Nessun dato climatico nel catalogo: la latitudine è l'approssimazione disponibile |
| Rappresentazione di "indifferente" | Valore `"any"` nei criteri (anche nella risposta pubblica `intent_created`, nel JSON di `intents.criteria` senza migrazione); `None` resta "non detto" | Con `None` il server non distinguerebbe "non chiesto" da "indifferente" |
| Periodo | Non più indispensabile: con lo sport e senza periodo l'intento si crea senza domanda. Se mancano sport e persone si chiede prima lo sport | Conseguenza della nuova RF-04; una sola domanda alla volta |
| "Niente di compatibile" dopo un rifiuto | La risposta di `reject_proposal` riporta l'id della proposta appena rifiutata; un secondo `reject_proposal` su quella proposta aggiorna i criteri e propone di nuovo senza registrare un nuovo rifiuto. Un "niente di compatibile" da `get_proposal` prima di ogni proposta si risolve con un nuovo `create_intent` | Il vincolo `uq_rejections_proposal_id` impedisce un secondo rifiuto; così non cambia lo schema e i rifiuti non si perdono |
| `area` e `direction` insieme | Vince `area`, conflitto nei log; una `direction` che `geo.move` non sa applicare viene scartata e dichiarata nel `say` | Il luogo esplicito è più preciso di una direzione |
| Fallback Haiku sul rifiuto | Nessuno: Haiku resta solo su `create_intent` | Come oggi; il rifiuto ha i campi strutturati |
| `docs/rest.md` | Aggiornato in M17, insieme al codice | Descrive il contratto implementato, non quello pianificato |
| Collocazione | Task nuova M17, ondata 5, parallela a M10 (unico file comune `chooser.py` per `sport=any`), M12, M13, M14 | M9 e M11 sono concluse |
| Decisioni aperte sul parser | Sinonimi, "padel e tennis", "beach tennis"/"paddle tennis", tornei, "più fresco" nel testo: opzioni e raccomandazioni in roadmap M17, da chiudere nel brainstorm di M17 | Non ancora decise |
