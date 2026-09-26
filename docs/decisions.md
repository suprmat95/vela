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

## 2026-09-26 — M10: sync multi-brand del catalogo

Origine: su claude.ai il tennis non si trova mai. Vela usa un solo brand HofJ (`HOFJ_BRAND`,
Weebora = padel) e carica il catalogo dalla fixture al boot (decisione M7); su HofJ ogni brand ha
un catalogo separato e le due fixture registrate non contengono nessun prodotto di tennis.
Requisiti in `docs/spec.md` (RF-28..32, RF-56, §6, §7), casi d'uso in
`docs/usecases/multi-brand.md`, implementazione in roadmap M10.

| Decisione | Scelta | Motivo |
|---|---|---|
| Portata di M10 | M10 diventa "Sync multi-brand del catalogo da HofJ", taglia L (era M): sync incrementale più config, migrazione, router del carrello e fixture per brand, in una task sola | Il sync è il punto in cui entrano i brand; separarli avrebbe riscritto due volte lo stesso codice |
| Config | `HOFJ_BRANDS="padel=weebora.com,tennis=terrarossa.com"` (sport → brand) al posto di `HOFJ_BRAND`. Sport in {padel, tennis}, brand distinti, almeno una voce; una sola voce è valida (l'altro sport dà il `no_match` esistente). `HOFJ_BRAND` senza `HOFJ_BRANDS` → l'app non parte e lo dice | Una sola variabile e una sola chiave in `render.yaml`; nessuna compatibilità silenziosa. Scartate: due variabili per sport (una nuova a ogni sport), JSON (scomodo da quotare) |
| Chiave degli id | L'id HofJ resta la chiave primaria di `products`, più la colonna `brand`; nessuna FK cambia. Se lo stesso id arriva da due brand il sync di quel brand si ferma con un errore esplicito. Se un giorno capita, si passa a un id con prefisso corto (`t:`/`p:`, `String(32)`) | Verificato il 2026-09-26 con 4 chiamate (2 `/v1/quota`, 2 pagine di lista): produzione `terrarossa.com` `it` 80 prodotti (id 340-1087, `channelId` 2), staging `staging.tennis.weebora.com` `en` 36 prodotti (id 12-641); zero id in comune con `fixtures/catalog.json` (110) e `fixtures/catalog-staging.json` (88). Gli id sembrano venire da un'unica tabella CMS. La chiave composta avrebbe toccato 4 tabelle; il prefisso avrebbe cambiato id pubblici e righe esistenti |
| `products.brand` | Colonna nullable, migrazione `0006`; il sync la scrive; lo sport si ricava dal brand tramite la mappa, `detect_sport` solo come riserva. Righe già su Render con `brand` NULL finché il primo sync non le riscrive | Nessuna migrazione di dati con valori indovinati; il sync è la fonte. Nella verifica `detect_sport` classifica padel 9 prodotti tennis su 49 attivi in Terrarossa e 3 su 13 in staging ("Rafa Nadal Academy", "Laver Cup", "Coppa Davis": nessuna parola "tennis") |
| Router del carrello | `HofJPort` invariata; nuova porta `HofJRouter` (`client(brand) -> HofJPort`, `get_quota()`), un `HofJHttp` per brand. `PurchaseJob` e `BookingJob` ricavano il brand da ordine → prodotto → `products.brand` a ogni esecuzione. Brand NULL → brand dello sport del prodotto. In replay tutti i brand puntano allo stesso `ReplayHofJ` | 5 metodi della porta su 7 ricevono solo `itinerary_id`: un router dietro la porta invariata dovrebbe interrogare il DB dall'adapter, con il rischio di cercare un itinerario non ancora salvato. Il brand letto dal DB a ogni esecuzione regge riavvii e retry |
| Quota | Una sola: la quota è per chiave API, letta da un client qualsiasi | Stessa chiave e stesso host per tutti i brand |
| Archiviazione | Per brand: un prodotto sparito dalla lista di un brand si archivia solo tra i prodotti di quel brand; un brand che fallisce non archivia nulla | Altrimenti il sync di un brand archivierebbe il catalogo dell'altro |
| Catalogo in live | Il sync sostituisce `realign_catalog` e la fixture al boot; le fixture, una per (host, brand), servono solo a replay e test e si rigenerano con lo stesso codice del sync | Supera la decisione M7 "Catalogo sul DB" per il live |
| Chooser, MCP, REST | Invariati in M10: il filtro sport basta, `sport=any` = nessun filtro (M17). M10 non tocca `chooser.py`; il file comune possibile con M17 è `usecases.py` | Supera la nota "unico file comune `chooser.py`" della decisione del contratto agente-tool |
| Fuori scope | Il §7 della spec non esclude più "più brand"; resta escluso il multi-tenant. Tolto "multi-brand" dai prossimi passi di M15 | Il multi-brand serve a vendere il tennis |
| Parser | Sinonimi, "padel e tennis", beach/paddle tennis, tornei restano decisioni di M17; M10 assume lo sport già `padel`, `tennis` o `any` | Una decisione in un posto solo |

## 2026-09-26 — M10: pacchetti evento esclusi

Origine: nella verifica degli id il catalogo Terrarossa è risultato contenere pacchetti per
assistere a eventi ("Watch & Stay", "Hospitality… Finals", Coppa Davis). Letto dalle risposte
già salvate, senza nuove chiamate.

| Decisione | Scelta | Motivo |
|---|---|---|
| Pacchetti evento | `is_trip` esclude l'intera categoria dei pacchetti evento (Terrarossa: `categoryId` 23 in produzione, 12 prodotti attivi; 15 su staging, 1), identificata per nome di categoria. Persi di proposito i Watch & Play (Torino, Vienna, Dubai) e i tornei amatoriali MT100/MT400, circa 5 prodotti | Vela vende viaggi per giocare: proporre "guarda la finale" a chi vuole giocare è peggio di qualche prodotto in meno. Scartate: categoria con eccezioni per titolo ("Play", "Masters Tour"), parole chiave nei titoli (fragili). I tornei amatoriali potranno rientrare più avanti (tornei di M17) |
| Nome della categoria | Letto dai dettagli quando M10 registra le fixture Terrarossa; nessuna chiamata `/v1/categories` ora | Gli id di categoria cambiano tra produzione e staging; il nome è già nel dettaglio (`products.category`) |

## 2026-09-26 — M17: decisioni aperte sul parser (brainstorm)

Chiude le "Decisioni aperte sul parser" del contratto agente-tool. Piano in
`docs/plans/2026-09-26-m17-contratto-agente-tool.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Sinonimi dello sport | Dizionario fisso in `intent.py`: "terra rossa", "terrarossa", "clay" → tennis; "paddle", "pádel", "weebora" → padel. Haiku resta la riserva quando lo sport manca ancora e il suo prompt conosce gli stessi sinonimi | Deterministico e testabile, non lega il parser al catalogo né al sync di M10 |
| "padel e tennis" | Entrambi gli sport nel testo → `any`; frasi di indifferenza ("indifferente", "tutti e due", "entrambi", "non importa", "either", "both sports", "doesn't matter") → `any` | È quello che il viaggiatore ha detto; il `say` lo ripete e si può correggere |
| "beach tennis", "paddle tennis" | Esclusioni controllate prima dei sinonimi → sport non riconosciuto → domanda "Padel o tennis?"; il prompt di Haiku li tratta come null | Non li vendiamo; nessuna frase dedicata finché il caso non capita davvero |
| Nomi di tornei | Fuori da M17: li risolve l'agente col campo `sport`, Haiku come riserva | Lista fissa o nomi dal catalogo restano tra i prossimi passi |
| "più fresco", "più freddo", "cooler" / "più caldo", "warmer" nel rifiuto | `refine.py` li traduce in `north` / `south` con `geo.move` | Rete di sicurezza per i client solo testo |
| Id dopo un `no_match` da rifiuto | Campo `rejected_proposal_id` nella risposta `no_match`, presente solo quando arriva da `reject_proposal` | Nelle altre risposte `proposal_id` è la proposta corrente: un nome distinto evita confusione |
| Tipi dei campi strutturati | `sport`, `area`, `direction`, `period_start`, `period_end` stringhe libere nello schema MCP/REST; `pax` intero, `budget` numero. Valori fuori dominio scartati e dichiarati nel `say` | RF-53: un campo invalido non blocca. Un tipo JSON sbagliato resta un errore di validazione |
| Periodo parziale | Servono `period_start` e `period_end`; una sola data → periodo scartato e dichiarato. Validazione: inizio ≤ fine, fine ≥ oggi (come il fallback Haiku) | Una data sola non dice la durata |
| `pax` su MCP | L'argomento `pax` di `create_intent` (prima nel profilo) diventa il campo strutturato: vince sul testo. Su REST `profile.pax` resta il default e `pax` al primo livello è il campo | Stesso nome e stesso contratto su MCP e REST |
| Fallback Haiku | Parte quando manca lo sport dopo campi e parser; riempie solo i criteri ancora vuoti (prima sovrascriveva il parser) | RF-03 e precedenza di RF-53 |
| `say` del rifiuto | Ordine annullato (RF-49), campi scartati, motivo non traducibile (solo se il motivo non è vuoto e nessun criterio cambia), "Ho capito: …", proposta o `no_match` | RF-54 |
| Frasi di `no_match` | "prova a riformulare la richiesta" → "dimmi cosa vuoi cambiare" | RF-09: non spingere l'agente verso un nuovo `create_intent` |
| Interprete dei test | `uv run python -m unittest discover -s tests` (3.12); il `python3` di sistema è 3.7 e non ha le dipendenze | Come da M0; base di partenza 773 test, 42 saltati |

## 2026-09-26 — M17: decisioni prese durante l'esecuzione

| Decisione | Scelta | Motivo |
|---|---|---|
| Test aggiornati (RF-04, RF-03) | In `tests/test_intent.py`: `test_missing_sport_and_period_asks_sport_or_period` → `test_missing_sport_asks_sport`; `test_only_period_is_enough` → `test_period_without_sport_asks_sport`; `FallbackTest.test_not_called_when_period_found` → `test_called_when_sport_missing_even_with_period`; `test_called_when_both_missing_and_overrides` → `test_fills_only_missing_criteria` (area e pax restano quelli del parser); `QUESTION_SPORT_OR_PERIOD(_EN)` → `QUESTION_SPORT(_EN)` negli altri test. Nessun test di casi d'uso, MCP o REST dipendeva da "periodo senza sport" | Fissavano la vecchia RF-04 "sport oppure periodo" e il fallback che sovrascriveva il parser |
| "troppo caldo" / "troppo freddo" | Anche "troppo caldo", "too hot" → north e "troppo freddo", "too cold" → south in `refine.py` | È la frase letterale del caso osservato |
| "either" | Vale `any` solo in "either is/one/sport/will do/way"; "both of us" non è "both sports" | "either Spain or Portugal" e "for both of us" non parlano dello sport |
| Frase dell'area scartata | "Non conosco il luogo X." senza "cerco ovunque" | Vale anche nel rifiuto, dove l'area di prima resta; la riga "Ho capito" che segue dice quale area si usa |
| Campi scartati e domanda | Le frasi dei campi scartati precedono anche la domanda "Padel o tennis?" (es. `sport=golf`) | Il viaggiatore sente perché gli si chiede lo sport |
| `pax` MCP | L'argomento va sia nel profilo (come prima) sia nei campi strutturati | Il test esistente sul profilo resta valido; nei criteri vince il campo |
| `say` del rifiuto | La riga "Ho capito: …" precede anche un `no_match` | RF-54: i criteri capiti si ripetono sempre |
| Secondo rifiuto della stessa proposta | Il motivo del secondo rifiuto non viene salvato (resta il primo, vincolo invariato). Un "troppo caro" detto al secondo rifiuto abbassa il budget ma non crea il tetto di prezzo della decisione M7 | Nessun cambio di schema; caso raro, da rivedere se capita |
| Conflitto `direction` / luogo nel testo | Se il campo `direction` sostituisce un luogo esplicito del motivo, il conflitto non va nei log (va solo quello `area` / `direction`) | Caso raro; il `say` ripete comunque l'area risultante |
| Suite finale | 848 test, 42 saltati (Postgres), verde con `uv run python` (erano 773 a inizio M17). Nessuna chiamata ad Anthropic | — |

## 2026-09-26 — M10: design del sync

Origine: brainstorming di M10. Design in
`docs/superpowers/specs/2026-09-26-m10-multibrand-sync-design.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Test di `sport=any` | M10 verifica il chooser con criteri senza filtro sport (`None`): candidati di entrambi i brand. Il valore letterale `"any"` lo testa M17. Nessun file di M17 (`intent.py`, `usecases.py`, `mcp.py`, `rest.py`, `chooser.py`) toccato | M17 lavora su quei file in parallelo; `None` è già "nessun filtro" nel chooser. Scartate: una riga in `chooser.py` (conflitto con M17), normalizzare `"any"` in `usecases.py` (contraddice `"any"` distinto da "non detto") |
| Fixture padel | Le due fixture esistenti si adattano offline (rinomina, `brand` e `sport` nei metadati); si registrano solo le due tennis | Nessuna chiamata e nessun cambio ai dati attesi dai test. Scartata: registrare di nuovo tutte e quattro (~136 chiamate in più) |
| Lettura del catalogo | Porta nuova `CatalogSource` (`list_page`, `detail`), implementata da `HofJHttp` e dalle fixture; `HofJPort` invariata | Il sync e la registrazione delle fixture usano lo stesso codice; i test del sync non fanno chiamate |
| Registrazione fixture | `python -m vela.sync --record` sostituisce `scripts/record_catalog.py` | Un solo codice per sync e fixture (RF-32) |
| Righe con `brand` NULL | Al primo sync, se `updatedAt` è invariato si scrivono solo `brand` e sport, senza dettaglio | Circa 77 chiamate in meno sul primo sync in produzione |
| Metadati delle fixture | Ogni fixture porta `brand` e `sport`; il replay non ha bisogno di `HOFJ_BRANDS` | Il replay resta senza configurazione HofJ |
| Annotazione in `usecases.py` | `Vela` riceve il router nell'argomento `hofj`; l'annotazione `HofJPort` resta fino al merge di M17 | Non toccare i file di M17; l'attributo è solo passato ai job |

## 2026-09-26 — M10: esecuzione

Decisioni prese durante l'implementazione; il design aggiornato è in
`docs/superpowers/specs/2026-09-26-m10-multibrand-sync-design.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Nomi delle fixture | Restano `catalog.json` e `catalog-staging.json` (padel); le nuove sono `catalog-tennis.json` e `catalog-staging-tennis.json` (`vela.fixtures.fixture_name`) | La rinomina `catalog-<ambiente>-<sport>.json` prevista nel design avrebbe toccato geo, chooser, loadtest e molti test senza benefici |
| Brand di `catalog.json` | `weebora.com`, aggiunto a mano con `sport: padel` | Registrata senza `?brand=` (brand `null`): il default del server è Weebora. Nessun prodotto cambia sport |
| Prodotti invariati | Il sync scrive `brand`, `sport` e `fetched_at` anche sui prodotti invariati (`mark_seen`), senza dettaglio | Senza `fetched_at` aggiornato `/health` mostrerebbe un'età vecchia e lo scheduler rifarebbe il sync a ogni avvio; copre anche le righe pre-M10 con brand NULL |
| Prodotto ricomparso | Un prodotto archiviato nel DB che torna attivo nella lista si riscarica anche con `updatedAt` invariato (`sync_state` riporta `archived`) | Altrimenti resterebbe archiviato per sempre |
| Lista vuota | Un brand senza prodotti attivi è un errore del brand: niente archiviazione | Una risposta vuota per errore archivierebbe tutto il catalogo del brand |
| Lotti | 25 prodotti per scrittura; un errore a metà scrive il lotto parziale già scaricato | La spec non fissa il numero; ogni lotto è una transazione coerente |
| Router | `HofJRouter` ha anche `client_for(product)` (brand del prodotto, o dello sport se NULL); `SingleClientRouter` per replay e test | La regola del brand NULL sta in un posto solo; i test esistenti con un client finto restano validi |
| Scheduler | Thread daemon per istanza; al boot sincronizza se il catalogo è vuoto o ha più di 6 h, poi ogni 6 h; dopo un giro fallito o saltato riprova dopo 15 minuti | Con l'advisory lock gira una sola istanza; il ritardo breve evita di restare 6 h senza catalogo dopo un errore |
| Locale in live | Resta quello delle fixture registrate sull'host (`it` in produzione, `en` su staging) | L'elenco delle variabili di §6 resta chiuso; stesso comportamento di M7 |
| Script di registrazione | `scripts/record_catalog.py` e i suoi test rimossi; `add_trap` (criterio 4) passa in `vela/fixtures.py` con i test | Un solo codice per sync e fixture (RF-32) senza perdere la trappola |
| Categoria dei pacchetti evento | `is_trip` esclude le categorie di nome "Tornei" (`it`) e "Tournaments" (`en`) **per tutti i brand**, non solo Terrarossa (scelta dell'utente il 2026-09-26). Escono anche 6 prodotti padel di produzione (323, 326, 991 Watch & Stay/Play; 923, 962 viaggi con le finali; 1062 clinic) e 4 di staging (14, 118, 760, 867) | Il nome è lo stesso nei due brand; i pacchetti da spettatore padel sono dello stesso tipo. Cambiano due aspettative: in "ottobre ovunque" la terza scelta è il 210 invece del 323; su staging la frase di §10.1 finisce dopo il 28 (il 867 è escluso) |
| Registrazione delle fixture tennis | 2026-09-26: `catalog-tennis.json` 51 chiamate (1 quota, 1 pagina, 49 dettagli; 80 prodotti, 49 attivi), `catalog-staging-tennis.json` 15 chiamate (1 quota, 1 pagina, 13 dettagli; 36 prodotti, 13 attivi). Nessun 429 | Numeri uguali a quelli dichiarati prima delle chiamate |
| Rebase su M17 | 2026-09-26: `task/m10` riportato su `master` dopo il merge di M17 (unico conflitto: le sezioni in coda a questo file). Annotazione di `hofj` in `usecases.py` e `orders.py` corretta in `HofJRouter`; MB5 testato anche con `sport="any"` vero. Suite 916 test | I file di M17 si toccano solo dopo il suo merge |
| Postgres nei test | Suite eseguita anche su un Postgres 16 usa e getta (container `vela-m10-test-pg`, porta 5439, rimosso a fine task): advisory lock, archiviazione per brand e migrazione `0006` verificati | I container Postgres già presenti sulla macchina sono di altri progetti |

## 2026-09-26 — Accettazione con attesa breve

Origine: discussione sul twist. Con la coda vuota l'accettazione risponde comunque "ti ho
messo in coda" e l'agente deve chiedere lo stato per avere il link, anche quando il job lo
prepara in pochi secondi. Roadmap M20.

| Decisione | Scelta | Motivo |
|---|---|---|
| Strategia | B: un solo percorso; in posizione 1 `accept_proposal` attende fino a `accept_wait_seconds` (default 10 s) il link preparato dal job, poi risponde come oggi | Stesso risultato per chi è solo, costo 1-2 h, nessuna regola cambiata. Scartata A (con budget libero l'accept fa subito le 5 chiamate): rompe RF-45, richiesta di 10-30 s, errori gestiti in due posti, e sotto picco girerebbe il percorso meno usato in demo |
| RF-45 | Resta: l'accettazione non chiama HofJ né Stripe | La decisione del twist del 2026-09-25 ("un solo percorso da testare") vale ancora |
| Limite noto | Con HofJ reale le 5 chiamate richiedono 10-20 s: l'attesa di 10 s non sempre basta | Accettato: nel caso peggiore la risposta è quella di oggi, con una frase più adatta |


## 2026-09-26 — Twist, seconda lettura

Origine: rilettura del testo dettagliato del twist (`docs/brief.md`, "The twist", richieste
1-5) in una conversazione fuori dal repo, rilettura del codice di M5 e M10, e la sonda della
finestra di quota (`scripts/quota_probe.py`, 6 chiamate a `GET /v1/quota` su staging,
`docs/api/quota-health.md`). Contesto completo e numeri in
`docs/plans/2026-09-26-twist-seconda-lettura.md`. La prima lettura ("Twist: 50.000 viaggiatori
in dieci minuti", 2026-09-25) resta valida; questa ne è il seguito.

Etichette: **[misurato]** = verificato con chiamate reali o leggendo il codice; **[previsto]** =
deduzione da confermare con il load test (M13a); **[proposta]** = scelta di design non ancora
implementata.

| Decisione | Scelta | Motivo |
|---|---|---|
| Finestra di quota di HofJ | **[misurato]** Fissa di 60 s, ancorata alla prima chiamata dopo la scadenza della precedente; non scorrevole, non a griglia; nessun header di rate limit. Spec RF-36 corretta ("finestra mobile" tolto) | Sonda del 2026-09-26: la chiamata a S + 63 s vede `used=1` e una finestra che parte al suo istante. Brief e OAS dicono "rolling": domanda 8 in `docs/hofj-questions.md` |
| Ritmo della quota | **[proposta, M18]** Token bucket condiviso in Postgres, ritmo r e capienza B con B + 60·r ≤ 108 (es. B = 8, r = 100/60): nessun intervallo di 60 s supera 108 chiamate, qualunque sia la regola di HofJ | **[misurato il codice]** `rolled()` in `vela/domain/quota.py` fa ripartire la finestra su una griglia di 60 s, HofJ alla prima chiamata dopo la scadenza. **[previsto, da confermare con M13a]** Sotto carico i worker ripartono insieme all'azzeramento di Vela e la raffica cade nella coda della finestra di HofJ → 429 quasi a ogni finestra, ritmo dimezzato. Copiare la regola di HofJ non basta: non si osserva senza pagare quota |
| Concorrenza dei worker | **[proposta, M18]** `worker_concurrency` ~10, con il ritmo deciso dal bucket e non dal numero di thread | **[previsto, da confermare con M13a]** Con 5 chiamate in serie da 2-6 s un acquisto occupa un worker ~20 s: con 4 thread e una sola istanza ~12 acquisti/min, sotto i 17,4 consentiti dalla quota. Legge di Little: 1,45 chiamate/s × 4-6 s ≈ 6-9 chiamate contemporanee |
| Timeout come esito incerto | **[misurato il codice]** Ci contiamo già sull'upsert di `POST /v1/bookings`: `BookingJob.run` ripete la stessa `POST` con lo stesso `itinerary_id` (5 tentativi, 5-10-20-40 s) e un job con lease scaduto viene rieseguito. **[verificato nel codice, M18]** Un solo job di prenotazione attivo per ordine: `_enqueue_booking` (`vela/domain/orders.py`) non accoda se `active_for_order` ne trova uno. Resta una corsa teorica, perché controllo e inserimento non sono atomici (due `mark_paid` concorrenti); è resa innocua dall'upsert di `POST /v1/bookings`, che restituisce lo stesso codice. **[proposta, M18]** Client a 20 s invece di 15; timeout su `POST /v1/itineraries` contato come itinerario orfano; lease rivisto per 5 × 20 s | HofJ rinuncia verso il brand dopo 15 s: con il client a 15 s chiudiamo un attimo prima della risposta. `POST /v1/itineraries` non è idempotente: un retry dopo timeout crea un secondo itinerario (domanda 9 in `docs/hofj-questions.md`) |
| Spendere su chi paga | **[proposta, M19, condizionata]** Link con 2 chiamate (itinerario + totale); cliente e pax dopo il pagamento, nel job di booking; scadenza degli ordini silenziosi | Look-to-book: oggi ogni accettazione costa 5 chiamate prima di sapere se il viaggiatore pagherà. **[previsto]** Link al minuto da ~17 a ~43. Condizionata alla verifica su staging (domanda 10 in `docs/hofj-questions.md`) |
| Load test | **[proposta, M13a, M13b]** Solo contro un finto HofJ che applica le regole di HofJ (finestra ancorata di default, scorrevole come opzione); modo `VELA_UPSTREAM_MODE=loadtest` con pagamenti finti, che rifiuta host diversi da localhost/`fake-hofj`; M13a misura il codice di oggi ("prima"), M18 corregge, M13b rilancia ("dopo"). Spec RNF-10 corretta ("contro l'URL live" tolto) | **[misurato il codice]** `render.yaml` punta a HofJ staging in modo `live` e `live` richiede `STRIPE_SECRET_KEY`: un load test contro Render porterebbe il carico a HofJ. Il test dimostra un confine: chiamate a HofJ al minuto piatte, sotto 108, da 1k a 50k viaggiatori |
| Sync nel budget | **[misurato il codice]** Il sync di M10 chiama HofJ al boot e ogni 6 h come classe `sync` e si ferma se ci sono acquisti in attesa (`vela/sync.py`); padel e tennis usano la stessa chiave. È la prima cosa sacrificata sotto picco | Il sync consuma la stessa quota degli acquisti |
| Ipotesi "rolling" | Il 2026-09-26 si era preso per buono il "rolling" del brief e proposto il token bucket per quel motivo; la sonda l'ha smentito. Il token bucket resta, per un motivo diverso: la deriva del contatore e il fatto che non possiamo osservare HofJ gratis | Il twist chiede di leggere "come rispondete a un cambio di requisiti sotto pressione": l'errore e la correzione vanno scritti |
| Documenti aggiornati | `docs/api/quota-health.md`, `docs/api/differences.md` (#8), `docs/hofj-questions.md` (8-10), `docs/spec.md` (RF-36, RF-47, nota su RF-48, RNF-04, RNF-10), `docs/roadmap.md` (M13a, M13b, M18, M19, M15, riga di M20). RF-48 resta invariato fino a M18. Nessun test da aggiornare: nessun test legge roadmap o spec | Solo documenti; le correzioni al codice sono di M18 e M19 |

### Il diff nel pensiero

1. **Prima del twist (mattina del 2026-09-25).** La quota era un errore da gestire:
   accettazione sincrona entro 30 s (vecchia RNF-04), "riprova tra un minuto" a quota finita
   (vecchia RF-37).
2. **Prima lettura (sera del 2026-09-25).** La quota diventa capacità da pianificare: coda in
   Postgres, scheduler unico per il cluster, accettazione sempre asincrona con attesa
   dichiarata, riserva per le prenotazioni, nessun tetto all'attesa. Scartati Redis/Celery,
   drenatore unico eletto, ibrido sincrono.
3. **Seconda lettura (2026-09-26).** L'impianto regge; cambiano cinque idee:

| Prima pensavamo | Ora pensiamo | Cosa ce l'ha fatto cambiare |
|---|---|---|
| Bisogna copiare la finestra di HofJ e allinearsi | Bisogna essere sicuri con qualunque finestra: ritmo costante | Il brief dice "rolling", la sonda misura una finestra ancorata, il nostro contatore va a griglia. Non potendo osservare HofJ gratis, ci si protegge da tutti i modelli |
| Il limite è la quota | Il limite può essere la latenza: ~12 acquisti/min con 4 thread invece di 17,4 (**[previsto]**, da confermare con M13a) | La ricerca dell'alloggio da 2-6 s; legge di Little |
| Un timeout è un errore: si riprova | Un timeout è un esito incerto: si riprova solo dove è idempotente | Il timeout a 15 s: booking upsert sicuro, itinerario no (orfani); precedenti Expedia e Brandur |
| Le chiamate si spendono in ordine d'arrivo | Le chiamate vanno spese su chi pagherà | Look-to-book: 5 chiamate per link che magari nessuno paga |
| Il load test misura le prestazioni | Il load test dimostra un confine: chiamate a HofJ piatte da 1k a 50k utenti | Il vincolo "mai contro HofJ"; il finto deve applicare le regole di HofJ, non le nostre |

Non cambia: coda in Postgres, accettazione asincrona con un solo percorso, riserva per le
prenotazioni, nessun servizio in più.

### Budget di quota

Limite 120/min per chiave (padel e tennis insieme). Margine 10% per gli altri usi della chiave
→ 108. Riserva `booking` 20% → 21. Acquisti → 87, cioè 17,4 al minuto.

| Voce del brief | Chiamate HofJ | Classe | Note |
|---|---|---|---|
| Browse (intento, proposta, rifiuto) | 0 | — | Catalogo nel DB, sincronizzato da M10 |
| Cart | 5 per ordine: itinerario, cliente, lettura pax, scrittura pax, totale | `purchase` | Una sola volta per ordine; ripetizioni solo su rete/5xx, massimo 3 finestre |
| Hotel | Dentro `POST /v1/itineraries` (hotel di default, RF-15) | `purchase` | È la chiamata da 2-6 s; nessuna chiamata a `/accommodations` |
| Booking | 1 per ordine pagato | `booking` | Dalla riserva di 21/min: non aspetta la coda d'acquisto |
| Lettura quota | 1 al boot e dopo un 429 | `booking` | Mai in ciclo |
| Verifica del pagamento | 0 HofJ | — | Interroga Stripe |
| Sync del catalogo | pagine + dettagli dei due brand, ogni 6 h | `sync` | Solo a coda d'acquisto vuota |

Cosa si sacrifica, in ordine: 1) il sync; 2) l'attesa degli acquisti, che cresce, dichiarata,
senza tetto; 3) mai le prenotazioni degli ordini pagati.

## 2026-09-26 — M13a: banco di prova

Piano in `docs/plans/2026-09-26-m13a-banco-di-prova.md`. Intervista del 2026-09-26.

| Decisione | Scelta | Motivo |
|---|---|---|
| Durata di un giro | 10 min di arrivi + 5 min di coda; chi è ancora in coda alla fine è contato, non atteso | A 50k la coda (~10.000 accettazioni) si smaltisce in ore: il confine sulla quota si vede già a regime |
| Catalogo in modo `loadtest` | Sync M10 vero contro il finto; lo scenario parte a sync finito | Stesso percorso del live; il sync resta nel registro del finto (M10 entra nel budget) |
| Lancio di Locust | Servizio compose `locust` (profilo `loadtest`) da uno stage del Dockerfile con le dipendenze dev; lo stage finale resta l'immagine di oggi | Al valutatore basta Docker; Render continua a costruire lo stesso stage |
| Giri della colonna "prima" | 1k, 10k, 50k puliti (finestra ancorata, latenza standard, `--background-rpm 12`, nessun guasto) + un 50k con guasti e latenza `pessimistic` | I giri puliti mostrano il confine sulla quota; quello con guasti conta 429, orfani e prenotazioni per itinerario |
| Sentinella Marco | Accetta a 60 s come scritto; il report dice se è confermato entro il minuto 7 e in che posizione era | A 50k ha ~1.000 accettazioni davanti: se fallisce è una previsione della seconda lettura (§6) smentita, da scrivere, non da aggiustare |
| Latenza del finto | `POST /v1/itineraries` 2-6 s, altri endpoint 0,3-1,5 s **[previsto]**; `pessimistic` = 2-6 s ovunque | `docs/acceptance.md` ha solo il totale "accept → link" (53 s), non il dettaglio per endpoint; misurarlo richiederebbe chiamate a HofJ |
| 429 nel finto | La chiamata respinta conta nella finestra | Ipotesi pessimista: il comportamento di HofJ non è noto |
| `POST /v1/bookings` nel finto | `{data: "<itineraryId>"}`, upsert per `itineraryId` | È la forma osservata su staging in due sonde (`docs/api/internal-checkout.md`), non quella di OAS |
| Test di contratto | Il vero `HofJHttp` contro il finto con il transport sincrono del `TestClient` di Starlette | `HofJHttp` usa httpx sincrono; `httpx.ASGITransport` è solo asincrono |
| Modello aperto | Scheduler degli arrivi in `test_start`, un greenlet per viaggiatore con `FastHttpSession` | `LoadTestShape` è a modello chiuso (numero di utenti), non ad arrivi |
| Locale in modo `loadtest` | Quello della fixture registrata per il brand, su qualunque host | Il finto non è un host con fixture registrate |
| `OPENSSL_armcap=0` nel compose | Variabile impostata sui servizi del compose di M13a | Su Apple M4 la VM di Docker Desktop (kernel 6.10) espone SME/SVE2 e l'OpenSSL di `cryptography` 50 (importato da `mcp`) termina con SIGILL all'avvio di Vela. La variabile spegne le estensioni CPU di OpenSSL su ARM, è ignorata su x86, e il compose non usa TLS: nessun effetto sulle misure. Nessuna dipendenza cambiata |
| Catalogo in modo `loadtest` (rivista il 2026-09-26) | Al boot dalle fixture dei brand configurati (le stesse che serve il finto HofJ) con `realign_catalog`, come in replay; lo scheduler del sync resta e trova il catalogo fresco. Sostituisce "sync M10 vero contro il finto" | Richiesta dell'utente dopo il primo giro: il sync completo da DB vuoto costava ~130 chiamate e ~2 minuti a giro (chiamate in serie da 0,3-1,5 s). Dentro un picco di 10 minuti il sync (al boot e ogni 6 h) comunque non gira, quindi le misure dello scenario non cambiano; il sync resta coperto dai test di M10 |
| Giri della colonna "prima" (rivista il 2026-09-26) | Quattro giri ridotti da 5 min di arrivi + 3 di coda: 500, 1.000, 2.500 viaggiatori puliti e 1.000 con guasti e latenza pessimistica; 1k/10k/50k in 10 minuti diventano una **proiezione** in `RESULTS.md`. Anna arriva al 60% della finestra degli arrivi (minuto 6 di 10, minuto 3 di 5). Sostituisce "1k, 10k, 50k puliti + 50k con guasti" | Richiesta dell'utente: numeri più bassi che consentano proiezioni. Con il 20% che accetta la coda satura oltre ~85 arrivi/min, e da lì chiamate HofJ/min e acquisti/min non dipendono dal numero di viaggiatori: a 50k cresce solo la coda, che si calcola dai ritmi misurati. Il carico REST sulla conversazione a 50k resta una proiezione lineare, non una misura. Tempo: ~40 minuti invece di ~70 |
| Durata di un giro (rivista il 2026-09-26) | `run.py --duration` (minuti, default 10) è il tetto dell'intero giro: 2/3 di arrivi e 1/3 di coda, oppure la divisione data con `--arrival-minutes`/`--tail-minutes`, rifiutata se la supera. Sostituisce "10 min di arrivi + 5 di coda" | Richiesta dell'utente: load test configurabile con un massimo di 10 minuti |
| Giro con finestra scorrevole | Un quinto giro, E-1000-rolling (1.000 viaggiatori, finestra `rolling`), nella colonna "prima" | I giri con finestra ancorata superano 120 chiamate in 60 s senza nessun 429: serviva vedere cosa succede con la finestra descritta da brief e OAS. Esito: 3 429 alla prima raffica, un minuto a metà ritmo, poi 111 chiamate in 60 s. Dettagli in `loadtest/RESULTS.md` |

## 2026-09-26 — Landing: design

Origine: brainstorming di `task/landingpage`. Design in
`docs/superpowers/specs/2026-09-26-landing-design.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Scopo della landing | Guida ai canali ("come si usa Vela"): nessun viaggio, prezzo, lista o tabella | Il brief dice "In 2029 Vela has no homepage"; la pagina spiega come arrivare a Vela dove il viaggiatore è già. Scartate: vetrina per i valutatori, pagina marketing |
| Stack | HTML, CSS e JS a mano in `landing/`, nessun build e nessuna dipendenza | Una sola pagina; Render la pubblica così com'è. Scartati: static site generator (Node, `package.json`, build), Tailwind da CDN |
| Deploy | Servizio `vela-landing` (`runtime: static`, `staticPublishPath: landing`) nello stesso `render.yaml`; `buildFilter` separati tra landing e API; `landing` in `.dockerignore` | Configurazione versionata; un cambio alla landing non ridistribuisce l'API e viceversa. Scartati: servizio creato a mano in dashboard, secondo blueprint |
| Canali mostrati | Claude via MCP, widget ElevenLabs, numero di telefono. REST escluso | Il token REST non è pubblico; la pagina è per il viaggiatore |
| Agent id e numero | Placeholder vuoti in `landing/config.js`; finché sono vuoti le sezioni mostrano "In arrivo" e lo script ElevenLabs non viene caricato. La creazione resta in M12 | M12 non è fatta; attivarli poi costa una riga |
| Lingua | Solo italiano | Scelta dell'utente |
| Comandi del servizio statico | `buildCommand: echo "Landing statica, nessun build"` e `staticPublishPath: ./landing` | Non è certo che il Blueprint accetti un `buildCommand` vuoto; `./` segue gli esempi della documentazione Render |

## 2026-09-26 — Landing: design grafico

Origine: design fornito dall'utente (`index_1.html`, non versionato). Spec aggiornata in
`docs/superpowers/specs/2026-09-26-landing-design.md`.

| Decisione | Scelta | Motivo |
|---|---|---|
| Aspetto | Il design dell'utente, portato in `styles.css` e `index.html`; `config.js` e `main.js` restano. Solo tema chiaro, come il design | Scelta dell'utente; la struttura a file resta quella testata |
| Dati negli esempi | I segnaposto del design ([DESTINAZIONE], [DATE], [PREZZO]) diventano i `say` reali di Vela, accorciati, ottenuti in memoria sulle fixture del 2026-09-25 (prodotti 688, 695, 369, 1023, 1044), senza chiamate esterne. Scartati: dati inventati, testo generico | Scelta dell'utente: tutto ciò che si mostra viene da HofJ. Prezzi e date possono cambiare con il catalogo |
| Frasi degli esempi | Cambiate il minimo perché il parser di oggi le capisca: "siamo in due" invece di "in due", "novembre" invece di "Pasqua", "Preferisco in Italia/Spagna" invece di "più fresco" e "spostare di una settimana", "per 2 persone" nella frase del connettore; tolto "al caldo" | Con le frasi originali Vela chiedeva il numero di persone, leggeva "più fresco" come Malaga o ignorava il periodo. I limiti del parser restano da trattare in un task a parte |
| Esempio del calendario | Riscritto: è Claude, con un suo connettore, a leggere e scrivere il calendario; Vela propone il viaggio | Vela non ha una funzione calendario; scelta dell'utente |
| Nome del connettore | `Pacchetti Viaggio di Padel Tennis` sulla landing e nel README | Scelta dell'utente |

## 2026-09-26 — M18: quota a ritmo costante

Origine: roadmap M18 e `docs/plans/2026-09-26-twist-seconda-lettura.md` (3.1-3.3). Le prime tre
scelte sono state prese con l'utente prima di scrivere codice.

| Decisione | Scelta | Motivo |
|---|---|---|
| Riserva `booking` nel bucket | Un solo bucket con soglia: `purchase` e `sync` prendono gettoni solo se ne restano almeno 2 (`quota_floor`), `booking` arriva a zero. La riserva del 20% diventa una precedenza. L'attesa dichiarata (RF-48) conta l'80% del ritmo: 16 acquisti/min | Le prenotazioni degli ordini pagati non aspettano mai gli acquisti. Senza prenotazioni gli acquisti usano tutto il ritmo (fino a 20/min), senza sprecare la riserva. Scartati i due bucket separati: più stato, e gli acquisti fermi a 16/min anche a riserva inutilizzata. Spec allineata dopo M18: RF-36..38, RF-47, RF-48, RF-50, RF-51 |
| Parametri | B = 8 (`quota_burst`), r = (limite effettivo − B)/60 = 100/60 gettoni/s, quindi B + 60·r = 108 per costruzione; il limite viene da `/v1/quota` | Con B = 8 ci stanno un acquisto (5) più la soglia (2) |
| Schema | Migrazione 0007: `tokens` (float, può essere negativo) e `refilled_at` sulla riga di `quota_window`. La riga esistente viene cancellata e ricreata piena con `needs_refresh`. La colonna `used` (sempre a 0) è tolta dalla migrazione 0008, approvata dall'utente dopo il merge | Nessuna tabella nuova |
| Orfani | Colonna `orders.orphan_itineraries` (0007). `PurchaseJob` la incrementa su `UpstreamTimeout` al passo dell'itinerario e scrive il log `orphan_itinerary`. `/health` → `queue.orphan_itineraries` (somma) | Scelta dell'utente. La chiamata è già nel budget: i gettoni presi non si restituiscono |
| `UpstreamTimeout` | Nuova sottoclasse di `UpstreamError`: timeout del nostro client e 5xx il cui `detail` parla di timeout (HofJ che rinuncia verso il brand). Si ripete come prima | Sono i due esiti incerti; solo sull'itinerario creano un orfano |
| 429 | Bucket a 0 e `needs_refresh`. Il job riparte quando il bucket può dargli i gettoni, mai subito. Una sola rilettura per il cluster: `claim_refresh` prende il gettone `booking` e spegne la richiesta nello stesso lock. Se `/v1/quota` risponde "esaurito", il bucket va in negativo fino alla fine della finestra HofJ. Un 429 sulla rilettura blocca il bucket per 60 s | Dopo un 429 non sappiamo quando HofJ riapre: la rilettura lo dice, e senza rilettura si aspetta una finestra intera |
| Porta `QuotaStore` | Nuovi `claim_refresh` e `mark_refresh_needed`; `on_429` con `hold_seconds`; `sync_from_snapshot` riceve `now`; `next_window_start(now, cls, n)` (nome storico) dice quando `cls` potrà prendere `n` gettoni | Porta interna: nessuna superficie MCP/REST cambia. `/health` aggiunge campi (`quota` descrive il bucket, nuovo `queue`) |
| Ripetizioni su rete/5xx | Il job d'acquisto si ripete non prima di 60 s (`max(bucket, now + 60 s)`) | Senza finestre, "la finestra successiva" sarebbe diventata "subito": dopo un timeout sull'itinerario avrebbe creato un secondo orfano all'istante |
| Concorrenza, timeout, lease | `worker_concurrency` 10; `TIMEOUT_SECONDS` 20; `job_lease_seconds` 180 (5 × 20 s più link e margine) | Plan 3.2 e 3.3. Il pool di SQLAlchemy (5 + 10) basta per 10 worker: nessuna connessione resta aperta durante le chiamate HofJ |
| Coda in `/health` | `queue.oldest_purchase_age_seconds`: età del più vecchio acquisto `pending` o `running` | Dice quanto aspetta chi è in fondo alla coda |
| Test aggiornati | Contratto della quota riscritto (`tests/quota_contract.py`), con finestra scorrevole, ancorata e a griglia simulate; `test_quota_rules`, `test_job_processor`, `LaunchBurstTest` (attesa 750 s / 13 minuti, attesa reale ≤ dichiarata e ≥ 75%), `test_usecases` (8 s), `test_health`, `test_config`, `test_hofj_http`, `test_migrations` (head 0007), `test_payment_check`, `test_fixtures_record`, `test_purchase_job` (orfani). In alcuni test l'orologio avanza qualche secondo tra un acquisto e l'altro | Fissavano la finestra a griglia e i numeri 87/108/17,4 |
| Suite finale | 946 test, 56 saltati senza `DATABASE_URL`; verde anche su un Postgres locale usa e getta. Nessuna chiamata esterna | — |

## 2026-09-26 — M13b: rilancio dopo M18

Origine: roadmap M13b. Risultati in `loadtest/RESULTS.md` (colonne "prima" e "dopo").

| Decisione | Scelta | Motivo |
|---|---|---|
| Giri del "dopo" | Gli stessi cinque giri del "prima", con gli stessi comandi dello script di M13a (recuperato dall'agent-log): A-500, B-1000, C-2500, D-1000-guasti, E-1000-rolling, `--duration 8 --arrival-minutes 5 --tail-minutes 3`, seme 13, compose pulito a ogni giro, immagini ricostruite una volta sul commit `a9d1f57`. 1k/10k/50k in 10 minuti restano una proiezione, ricalcolata con il ritmo del "dopo" (17,8 link/min) | Richiesta dell'utente: stesso numero di viaggiatori di M13a. `git diff 14ddd31..a9d1f57` su `loadtest/`, compose, Dockerfile ed entrypoint è vuoto: cambia solo `vela/` |
| Criterio fallito | Tutti i giri si completano comunque; un criterio fallito si scrive con il numero, senza toccare test o codice, e si segnala all'utente prima del commit | Scelta dell'utente. Esito: nessun criterio fallito |
| "Prenotazioni doppie" | Il criterio conta i booking distinti per `itineraryId` sul finto (upsert), non le `POST /v1/bookings`; le POST ripetute si riportano a parte | Le POST ripetute dopo un timeout sono una scelta di M5/M18 (upsert idempotente); il rischio è un secondo booking |
| POST di booking doppie senza guasti | Riportate in `RESULTS.md` come regressione trovata (1, 4, 2 itinerari in A, C, E); la causa, due job `booking` per ordine da `mark_paid` concorrenti, è stata verificata sul DB di Vela in sola lettura durante D ed E. Correzione in una task separata (`task/booking-race`), approvata dall'utente: passaggio di stato atomico dell'ordine più indice unico parziale sui job `booking` attivi | M13b non cambia il codice. La corsa era annotata in M18 come teorica; con 10 worker è frequente |
| p95 REST più alto dopo M18 | Riportato come misura con un'ipotesi (10 worker nello stesso processo uvicorn), senza indagare | Fuori scope; 0 errori e proposta sempre sotto 15 ms per Anna |

## 2026-09-26 — Un solo job di prenotazione per ordine (task/booking-race)

Origine: regressione misurata da M13b (`loadtest/RESULTS.md`, "Cosa cambia con M18", punto 6).
Scelta dell'utente tra tre opzioni: A (passaggio di stato atomico) più B (indice unico); scartata
C (`SELECT ... FOR UPDATE` in una transazione condivisa tra repository, cambio di architettura).

| Decisione | Scelta | Motivo |
|---|---|---|
| Passaggio di stato atomico (A) | Nuovo `OrderRepository.save_if_status(order, expected) -> bool`: su Postgres un solo `UPDATE ... WHERE id = ? AND status = ?`, in memoria sotto il lock. `mark_paid` ed `expire` lo usano; chi perde rilegge l'ordine e non accoda nulla | Corregge la causa: due conferme di pagamento concorrenti leggevano entrambe `awaiting_payment`. Sistema anche la corsa tra pagato e scaduto, in cui una scadenza letta prima del pagamento lo annullava. Porta interna: nessuna superficie MCP/REST cambia |
| Indice unico (B) | Migrazione 0009: indice unico parziale `uq_jobs_active_booking` su `jobs(order_id)` per `kind = 'booking'` e `status` `pending` o `running` (Postgres e SQLite). `JobRepository.enqueue` solleva `DuplicateJob` (in memoria lo stesso controllo sotto il lock); `_enqueue_booking` lo tratta come "c'era già" | La garanzia sta nel database e vale anche con più istanze, per esempio `resume_bookings` al boot di due istanze. I job `done` e `dead` non contano: un ordine può riavere un job dopo un fallimento |
| Doppioni già in tabella | La 0009, prima di creare l'indice, porta a `dead` i job `booking` attivi doppi, tenendo il più vecchio (`enqueued_at`, poi `id`), con `last_error` che lo dice | Senza questo passo la creazione dell'indice fallirebbe al boot su un DB che ha già la corsa. I doppioni prenotano lo stesso itinerario: tenerne uno non perde nulla |
| Test | Contratto memoria/Postgres: `save_if_status`, secondo job `booking` attivo rifiutato (anche `running`), `dead`/`done` non bloccano, 8 thread su `save_if_status`, su `enqueue` e su `OrderService.mark_paid` (quest'ultimo falliva su Postgres prima della correzione). Dominio: letture vecchie in `mark_paid`, `expire` e `resume_bookings`. Migrazione: head 0009, indice, downgrade, doppioni a `dead` | I test di concorrenza sono passati 10 volte su 10 su un Postgres locale usa e getta |
| Verifica sul banco | A-500 e C-2500 rilanciati identici sul commit `49cc1cb`: 0 itinerari con `POST /v1/bookings` ripetuta (erano 1 e 4), una POST per itinerario prenotato (67/67, 85/85), criteri di M13b tutti passati. Tabella in `loadtest/RESULTS.md` | Il test di contratto dice che la corsa è chiusa; il banco dice che era quella la causa delle POST doppie |
