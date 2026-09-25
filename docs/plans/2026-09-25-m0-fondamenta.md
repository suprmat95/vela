# Piano di esecuzione M0 — Fondamenta del repo e deploy vuoto su Render

Data: 2026-09-25. Origine: `docs/roadmap.md` (M0, su `master`), `docs/spec.md` (§5 RNF-11, §6, §9),
intervista del 2026-09-25. Branch: `task/m0` (worktree `orca/workspaces/vela/task-m0`).

## 1. Contesto

Il repo contiene solo documentazione, gli script stdlib (`scripts/agents_log.py`,
`scripts/api_explore.py`) e i loro test. M0 crea le fondamenta su cui M1..M16 lavorano in
worktree paralleli: struttura `vela/`, toolchain, app FastAPI vuota con `GET /health`,
Postgres via SQLAlchemy Core + psycopg 3, Alembic al boot, Dockerfile, Blueprint Render,
rinomina `agents-log/` → `agent-log/`. Nessuna logica di dominio.

Fatti verificati che condizionano il piano:

- `python3` di sistema è 3.7.9; esistono 3.10-3.13, `uv 0.9`, `docker 27`. L'hook
  `.claude/settings.json` lancia `python3 scripts/agents_log.py` con il 3.7: lo script resta
  compatibile 3.7. La suite del progetto gira nel venv 3.12 creato da `uv sync`.
- `docs/roadmap.md` non è su `task/m0` (branch nato prima del merge di `doc/roadmap`).
  Decisione: non mergiare `master` ora; il piano cita la roadmap da `master`. Alla fine
  `docs/decisions.md` andrà in conflitto (entrambi i branch appendono in coda): risolvere
  tenendo entrambe le sezioni.
- I 32 test esistenti sono verdi con il 3.7.
- Test correnti: `python3 -m unittest discover -s tests` (da CLAUDE.md). Con il venv attivo
  (`source .venv/bin/activate`) `python3` è il 3.12; equivalente `uv run python3 -m unittest discover -s tests`.

## 2. Decisioni dell'intervista (da riportare in `docs/decisions.md`)

| Decisione | Scelta | Motivo |
|---|---|---|
| Toolchain | `uv` + `pyproject.toml` + `uv.lock`, Python 3.12 (`.python-version`, `requires-python >= 3.12`) | Il `python3` di sistema è 3.7; `uv` è già installato, il lock rende identici locale e Docker. |
| Dipendenze | Tutte quelle concordate: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `httpx`, `mcp`, `stripe`; dev: `locust` | Un solo lock condiviso: le task parallele M2-M6 non toccano `pyproject.toml`. |
| Render | `render.yaml` Blueprint: web service Docker + Postgres, piano free, regione Frankfurt, `healthCheckPath: /health` | Infrastruttura nel repo; il Postgres free basta per le 24 h (scade dopo 30 giorni). |
| Migrazioni | `docker-entrypoint.sh`: `alembic upgrade head` poi `exec uvicorn` | Funziona in locale e su Render, anche sul piano free (senza `preDeployCommand`). |
| `/health` | 200 `{"status":"ok","db":"ok"}`; 503 `{"status":"degraded","db":"error"}` quando il DB manca o non risponde | Render non instrada traffico a un'istanza senza DB; il test senza `DATABASE_URL` verifica il 503. |
| Accesso DB | Engine SQLAlchemy Core sincrono (psycopg sync), endpoint FastAPI `def` nel threadpool | Semplice e testabile; pattern che M2-M6 ereditano. |
| Branch | `task/m0` non mergia `master` durante la task | Scelta dell'utente; merge solo alla fine. |
| Lingua | `README.md` in italiano | Coerente con `docs/`. |
| Config | `vela/config.py` legge le variabili di spec §6 con `os.environ`, nessuna libreria extra; `DATABASE_URL` normalizzata (`postgres://`, `postgresql://` → `postgresql+psycopg://`) | Render fornisce `postgres://`; SQLAlchemy 2 con psycopg 3 vuole il driver esplicito. Niente `.env` letto dal codice. |
| Rinomina log | Solo la cartella `agents-log/` → `agent-log/`; `scripts/agents_log.py` e `docs/agents-log.md` mantengono il nome (spec §9) | Minimo cambiamento; il brief chiede solo la cartella. |

## 3. Design

### 3.1 Struttura finale del repo dopo M0

```
.python-version            3.12
pyproject.toml             [project] deps, [dependency-groups] dev, [tool.setuptools] packages vela
uv.lock
Dockerfile  .dockerignore  docker-entrypoint.sh
render.yaml
alembic.ini
alembic/env.py  alembic/script.py.mako  alembic/versions/0001_initial.py   (migrazione vuota)
vela/__init__.py
vela/config.py             Settings (dataclass) + Settings.from_env() + normalize_database_url()
vela/app.py                create_app(settings=None) -> FastAPI; app = create_app()
vela/adapters/__init__.py
vela/adapters/db.py        metadata, make_engine(url), check_db(engine) -> bool
vela/surfaces/__init__.py
vela/surfaces/health.py    router GET /health
vela/domain/__init__.py  vela/ports/__init__.py          (vuoti)
fixtures/.gitkeep  loadtest/.gitkeep
agent-log/                 (git mv da agents-log/)
tests/test_config.py  tests/test_db.py  tests/test_health.py  tests/test_migrations.py
tests/test_agents_log.py   (path aggiornati)
README.md
docs/plans/2026-09-25-m0-fondamenta.md   docs/decisions.md (sezione M0)
```

### 3.2 Configurazione (`vela/config.py`)

`@dataclass(frozen=True) class Settings` con i campi di spec §6: `database_url`,
`hofj_api_key`, `hofj_base_url`, `hofj_brand`, `stripe_secret_key`, `stripe_webhook_secret`,
`vela_api_token`, `vela_upstream_mode` (default `"replay"`), `anthropic_api_key`,
`vela_public_url`. Tutti `str | None` tranne il mode. `Settings.from_env(environ=os.environ)`
accetta il mapping per i test. `normalize_database_url(url)` riscrive lo schema per psycopg 3
e lascia invariato tutto il resto (incluso `sqlite://`). Nessuna validazione oltre a questo:
le task successive aggiungono i controlli sui campi che usano.

### 3.3 DB (`vela/adapters/db.py`)

- `metadata = MetaData()` condiviso: M2 vi registra le tabelle.
- `make_engine(url)`: `create_engine(url, pool_pre_ping=True, future=True)`; se il dialetto è
  `postgresql`, `connect_args={"connect_timeout": 3}` così `/health` non resta appeso.
- `check_db(engine) -> bool`: `SELECT 1` in `engine.connect()`, `True` se riesce, `False` su
  qualunque `SQLAlchemyError`/`OSError` (mai eccezione verso l'endpoint).

### 3.4 App e `/health`

- `create_app(settings=None)`: `settings = settings or Settings.from_env()`; crea l'engine solo
  se `database_url` è presente e lo mette in `app.state.engine` (altrimenti `None`);
  `app.state.settings = settings`; include il router di `vela/surfaces/health.py`.
- `GET /health`: `db_ok = engine is not None and check_db(engine)`. Risposta
  `{"status": "ok", "db": "ok"}` con 200, oppure `{"status": "degraded", "db": "error"}` con
  503 (`JSONResponse(status_code=503)`). Nessuna autenticazione. Endpoint `def` sincrono.
- `app = create_app()` a livello modulo per `uvicorn vela.app:app`.

### 3.5 Alembic

- `alembic.ini` senza URL; `alembic/env.py` legge `DATABASE_URL` dall'ambiente tramite
  `Settings.from_env()` (quindi già normalizzata) e usa `vela.adapters.db.metadata` come
  `target_metadata`. Offline e online mode standard.
- `alembic/versions/0001_initial.py`: revision `0001`, `down_revision = None`, `upgrade()` e
  `downgrade()` con `pass`. Crea solo `alembic_version`: è la prova che le migrazioni girano al
  boot (log di Render).

### 3.6 Docker

- `Dockerfile` da `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`: copia `pyproject.toml`,
  `uv.lock`, `uv sync --frozen --no-dev --no-install-project`; copia il resto; `uv sync --frozen --no-dev`;
  utente non root; `ENV PATH=/app/.venv/bin:$PATH`; `EXPOSE 8000`; `ENTRYPOINT ["./docker-entrypoint.sh"]`.
- `docker-entrypoint.sh`: `set -e`; `alembic upgrade head`; `exec uvicorn vela.app:app --host 0.0.0.0 --port "${PORT:-8000}"`.
- `.dockerignore`: `.git`, `.venv`, `agent-log`, `docs`, `tests`, `__pycache__`, `.env*`.
- Smoke locale senza Postgres: `docker run -e DATABASE_URL=sqlite:////tmp/vela.db -p 8000:8000 vela` →
  la migrazione vuota gira anche su SQLite e `/health` risponde 200.

### 3.7 Render (`render.yaml`)

```yaml
services:
  - type: web
    name: vela
    runtime: docker
    region: frankfurt
    plan: free
    healthCheckPath: /health
    envVars:
      - key: DATABASE_URL
        fromDatabase: { name: vela-db, property: connectionString }
      - key: VELA_UPSTREAM_MODE
        value: replay
      - { key: HOFJ_API_KEY, sync: false }
      - { key: HOFJ_BASE_URL, sync: false }
      - { key: HOFJ_BRAND, sync: false }
      - { key: STRIPE_SECRET_KEY, sync: false }
      - { key: STRIPE_WEBHOOK_SECRET, sync: false }
      - { key: VELA_API_TOKEN, sync: false }
      - { key: VELA_PUBLIC_URL, sync: false }
      - { key: ANTHROPIC_API_KEY, sync: false }
databases:
  - name: vela-db
    region: frankfurt
    plan: free
```

`sync: false` = valore inserito a mano in dashboard, mai nel repo. La creazione del Blueprint
(New → Blueprint → repo `suprmat95/vela`, branch `task/m0` o `master` dopo il merge) la fa
l'utente: non esistono credenziali Render in questa sessione.

### 3.8 Rinomina `agents-log/` → `agent-log/`

- `git mv agents-log agent-log` (storia con `git log --follow`).
- `scripts/agents_log.py`: costante `LOG_DIR = "agent-log"` usata in `run_hook` e in `main`
  (default `--out-dir`); docstring.
- `tests/test_agents_log.py`: `"agents-log"` → `"agent-log"` nei path attesi (TranscribeTest,
  HookEndToEndTest).
- `docs/agents-log.md`, `CLAUDE.md` ("Where things live"), `.claude/settings.json` (il
  comando dell'hook non contiene il path: verificare e lasciare invariato).

### 3.9 README.md (italiano)

Sezioni: cosa è Vela (3 righe, rimando a `docs/spec.md`); requisiti (uv, Python 3.12, Docker);
avvio locale (`uv sync`, `alembic upgrade head`, `uvicorn vela.app:app --reload`); test;
variabili d'ambiente (tabella di spec §6 con obbligatoria/opzionale e default); Docker
(build e run); deploy su Render (Blueprint, variabili `sync: false`, dove leggere il log della
migrazione); `agent-log/` (rimando a `docs/agents-log.md`).

## 4. Microtask

Ogni microtask: TDD (test prima, rosso, poi verde), suite intera verde, un commit con il
messaggio indicato. Comando test: `python3 -m unittest discover -s tests` nel venv 3.12
(dal task 1 in poi). Prima di ogni `git commit` l'hook rigenera `agent-log/`.

### T0 — Piano nel repo
- Copiare questo file in `docs/plans/2026-09-25-m0-fondamenta.md`; aggiungere a
  `docs/decisions.md` la sezione "2026-09-25 — M0: toolchain, deploy e health" con la tabella §2.
- Test: nessuno. Verifica: i due file esistono, `git status` pulito dopo il commit.
- Commit: `Add M0 execution plan and record decisions`.

### T1 — Toolchain uv e Python 3.12
- File: `.python-version` (`3.12`), `pyproject.toml` (nome `vela`, versione `0.1.0`,
  `requires-python = ">=3.12"`, deps runtime e gruppo dev come §2, `[tool.setuptools.packages.find] include = ["vela*"]`),
  `uv.lock` (da `uv lock`), `.gitignore` (+ `.venv/`), `vela/__init__.py` vuoto (serve al build).
- Comandi: `uv lock`, `uv sync`, `uv run python3 --version` → 3.12.
- Test: la suite esistente (32 test) verde con `uv run python3 -m unittest discover -s tests`.
  Aggiungere `tests/test_toolchain.py::test_runs_on_python_312` che asserisce `sys.version_info >= (3, 12)`
  (fallisce se qualcuno lancia la suite col 3.7 di sistema, con messaggio esplicito).
- Commit: `Add uv toolchain with pyproject and lock on Python 3.12`.

### T2 — Rinomina `agents-log/` → `agent-log/`
- Test prima: aggiornare `tests/test_agents_log.py` (path `agent-log`) → rosso.
- `git mv agents-log agent-log`; `scripts/agents_log.py` (`LOG_DIR`); `docs/agents-log.md`;
  `CLAUDE.md`; verificare `.claude/settings.json`.
- Test: `test_agents_log.py` verde (TranscribeTest e HookEndToEndTest usano `agent-log/`);
  verifica manuale `git log --follow --oneline agent-log/ | head` mostra la storia;
  `python3 scripts/agents_log.py --help`-style docstring aggiornata; lo script gira ancora col 3.7
  (`/usr/local/bin/python3 -m unittest tests.test_agents_log`).
- Difetto trovato durante la stesura del piano, da correggere qui perché si tocca lo script:
  una sessione avviata con uno slash command (primo messaggio `<command-message>...` con
  `<command-args>`) e proseguita solo con risposte ad `AskUserQuestion` (tool_result, non
  testo) non ha alcun messaggio utente "puro": `session_filename` restituisce `None` e il
  commit non produce nessun log (è successo alla sessione di brainstorm di M0, commit
  `95da837`). Correzione: in `parse_transcript`, se il messaggio inizia con
  `<command-message>`/`<command-name>` ma contiene `<command-args>...</command-args>`, usare
  quel contenuto come testo utente (`/nome-skill: args`). Test: fixture con un messaggio di
  slash command con args → entry utente e nome file con lo slug degli args.
- Commit: `Rename agents-log to agent-log and update script, docs and tests`.

### T3 — Configurazione da ambiente
- File: `vela/config.py`.
- Test `tests/test_config.py`:
  - `from_env` con mapping vuoto → tutti `None`, `vela_upstream_mode == "replay"`;
  - `from_env` con tutte le variabili di §6 → campi valorizzati;
  - `normalize_database_url`: `postgres://u:p@h/db` → `postgresql+psycopg://u:p@h/db`;
    `postgresql://` → `postgresql+psycopg://`; `postgresql+psycopg://` e `sqlite://` invariati;
  - `from_env` applica la normalizzazione a `database_url`;
  - il modulo non importa `dotenv` né apre file (`assertNotIn("open(", source)` sul sorgente, e nessun riferimento a `.env`).
- Commit: `Add Settings loaded from environment variables`.

### T4 — Engine e check del DB
- File: `vela/adapters/db.py`, `vela/adapters/__init__.py`.
- Test `tests/test_db.py`:
  - `make_engine("sqlite://")` + `check_db` → `True`;
  - `check_db` su engine con URL Postgres non raggiungibile (`postgresql+psycopg://u:p@127.0.0.1:1/x`) → `False` senza eccezione e in meno di 5 s;
  - `make_engine` con URL Postgres imposta `connect_timeout` (ispezione di `engine.dialect`/`connect_args` tramite `engine.pool._creator` è fragile: verificare invece con `create_engine` mock/`engine.url` + `assertEqual(engine.dialect.name, "postgresql")` e un test del helper `connect_args_for(url)` puro);
  - `test_postgres_roundtrip`: `skipUnless(os.environ.get("DATABASE_URL"))`, `check_db` → `True`.
- Commit: `Add SQLAlchemy engine factory and database check`.

### T5 — App FastAPI e `GET /health`
- File: `vela/app.py`, `vela/surfaces/__init__.py`, `vela/surfaces/health.py`,
  `vela/domain/__init__.py`, `vela/ports/__init__.py`, `fixtures/.gitkeep`, `loadtest/.gitkeep`.
- Test `tests/test_health.py` (TestClient di `httpx`/`fastapi.testclient`):
  - `create_app(Settings(database_url=None, ...))` → `GET /health` 503, body `{"status":"degraded","db":"error"}`;
  - `Settings(database_url="sqlite://")` → 200, body `{"status":"ok","db":"ok"}`;
  - `Settings(database_url="postgresql+psycopg://u:p@127.0.0.1:1/x")` → 503 (DB configurato ma giù);
  - `GET /health` senza header di autenticazione risponde (pubblico);
  - `vela.app.app` esiste ed è un `FastAPI` (import per uvicorn);
  - `create_app()` senza argomenti e senza `DATABASE_URL` nell'ambiente non solleva (`patch.dict(os.environ, {}, clear=True)`).
- Commit: `Add FastAPI app skeleton with GET /health reporting database status`.

### T6 — Alembic con prima migrazione vuota
- File: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`.
- Test `tests/test_migrations.py`:
  - `ScriptDirectory.from_config(Config("alembic.ini")).get_heads()` → esattamente `["0001"]` (senza DB);
  - `alembic upgrade head` su SQLite file temporaneo via `alembic.command.upgrade` con
    `DATABASE_URL` patchato → la tabella `alembic_version` contiene `0001`; `downgrade base` la svuota;
  - `test_upgrade_on_postgres`: `skipUnless(DATABASE_URL)`, `upgrade head` idempotente (due volte di fila).
- Commit: `Add Alembic setup with empty initial migration`.

### T7 — Dockerfile ed entrypoint
- File: `Dockerfile`, `.dockerignore`, `docker-entrypoint.sh` (eseguibile).
- Test automatico: `tests/test_docker_files.py` verifica che `docker-entrypoint.sh` sia
  eseguibile, contenga `alembic upgrade head` prima di `exec uvicorn`, e che `.dockerignore`
  escluda `.env`, `.venv`, `agent-log`.
- Verifica manuale (registrata nel messaggio di fine task): `docker build -t vela .` riesce;
  `docker run --rm -e DATABASE_URL=sqlite:////tmp/vela.db -p 8000:8000 vela` stampa la
  migrazione `0001` e `curl -s localhost:8000/health` → 200 `db: ok`; senza `DATABASE_URL`
  l'entrypoint fallisce in modo esplicito (Alembic senza URL) e il container esce.
- Commit: `Add Dockerfile and entrypoint running migrations before uvicorn`.

### T8 — Blueprint Render e README
- File: `render.yaml` (§3.7), `README.md` (§3.9).
- Test: `tests/test_render_yaml.py` con parsing minimale (nessuna libreria YAML: verifiche
  testuali) che `render.yaml` contenga `healthCheckPath: /health`, `runtime: docker`,
  `fromDatabase`, e che ogni variabile di spec §6 compaia (`DATABASE_URL` da database, le
  altre `sync: false` o valore); README elenca le stesse variabili (test che ogni nome di §6 sia
  nel README).
- Commit: `Add Render blueprint and README with environment variables`.

### T9 — Deploy su Render (manuale, con l'utente)
- L'utente: push di `task/m0` su `origin` (chiede conferma: `git push` è in `ask`), crea il
  Blueprint dalla dashboard scegliendo il branch, inserisce le variabili `sync: false` (per M0
  bastano `VELA_UPSTREAM_MODE=replay` già nel file; le altre possono restare vuote).
- Verifica: `curl https://<render>/health` → 200 `{"status":"ok","db":"ok"}`; il log di deploy
  mostra `Running upgrade  -> 0001`; annotare l'URL in `README.md` e l'esito in
  `docs/decisions.md` (riga "Deploy M0 verificato il ...").
- Commit: `Record Render deployment URL and health check outcome`.

### T10 — Chiusura
- Suite completa verde nel venv 3.12; `git status` pulito; report finale: cosa fatto, cosa
  deciso, cosa incerto. Merge su `master` solo dopo l'OK dell'utente (conflitto atteso su
  `docs/decisions.md`: tenere entrambe le sezioni).

## 5. Copertura dei test di completamento della roadmap

| Test di completamento M0 | Come è coperto |
|---|---|
| Suite verde, test esistenti al nuovo path, test `/health` che tollera DB assente | T1, T2, T5 (`test_health.py`: 503 senza DB, 200 con sqlite) |
| `curl https://<render>/health` → 200 con `db: "ok"` | T9 manuale |
| `docker build .` riesce; log Render mostra la migrazione | T7 manuale (build + run locale), T9 (log) |
| `git log --follow agent-log/` mostra la storia | T2 manuale |
| RNF-11 (Dockerfile, Render, migrazioni al boot, variabili nel README) | T6, T7, T8, T9 |
| RNF-06 parte `/health` | T5 |
| RNF-07 segreti solo in env | T3 (nessuna lettura di `.env`), T8 (`sync: false`), `.dockerignore` |
| spec §6 `agent-log/` | T2 |

Nessun test automatico chiama servizi esterni; i test Postgres sono `skipUnless(DATABASE_URL)`.

## 6. Verifica end-to-end finale

```bash
uv sync && source .venv/bin/activate
python3 -m unittest discover -s tests            # tutto verde, N test, alcuni skipped senza DATABASE_URL
docker build -t vela . && docker run --rm -e DATABASE_URL=sqlite:////tmp/vela.db -p 8000:8000 vela
curl -s localhost:8000/health                     # {"status":"ok","db":"ok"}
git log --follow --oneline agent-log/ | tail -3   # storia preservata
curl -s https://<render>/health                   # dopo T9
```

## 7. Fuori scope e rischi

- Nessuna logica di dominio, nessuna superficie REST/MCP oltre `/health`, nessuna tabella
  applicativa: arrivano con M2/M3/M4.
- Se `uv lock` non risolve `mcp` con le altre dipendenze, fermarsi e proporre (non abbassare
  versioni a caso).
- Piano free di Render: il web service va in sleep dopo inattività (prima richiesta lenta);
  accettato per il prototipo, da annotare in README.
- `docs/decisions.md` andrà in conflitto al merge finale con `master`: risoluzione manuale.
