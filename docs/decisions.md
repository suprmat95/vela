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
