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
