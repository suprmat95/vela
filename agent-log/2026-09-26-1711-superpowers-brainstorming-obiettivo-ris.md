# /superpowers:brainstorming: obiettivo: riscrivi claude.md come se un senior stes

- Sessione: `6bd97d83-df8e-4be3-8350-7a721319c9d5`
- Inizio: 2026-09-26 17:11

## Utente 17:11

/superpowers:brainstorming: obiettivo: riscrivi claude.md come se un senior stesse spiegando ad uno junior il progetto, riportando il folding e - How to run test
- How to build
- How to lint

## Agente 17:11

Uso la skill brainstorming. Mi sembra un lavoro **bounded**: il file esiste già, va riscritto. Quindi ti presento un breve design qui in chat, senza scrivere una spec. Prima guardo com'è fatto il progetto.

- 🔧 Bash: List tracked files and docs

- 🔧 Bash: Read rest of README, pyproject, layout, build files

- 🔧 Bash: Search for any lint configuration or mentions

Ho letto README, `pyproject.toml`, Dockerfile, compose, `render.yaml` e l'albero del codice.

**Cosa ho capito**
- **Cosa mi hai chiesto:** riscrivere `CLAUDE.md` con il tono di un senior che spiega il progetto a uno junior. Dentro devono esserci la struttura delle cartelle e tre sezioni: come si lanciano i test, come si fa il build, come si fa il lint.
- **Cosa sto supponendo** (correggimi se sbaglio):
  - Con "folding" intendi la struttura delle cartelle (`vela/domain`, `ports`, `adapters`, `surfaces`, `alembic/`, `fixtures/`, `loadtest/`, `landing/`…), spiegata con il perché di ogni pezzo e non solo come elenco.
  - Il "Working agreement" e le altre regole attuali (Git, Secrets, Scope, agent-log) restano tutte, con lo stesso significato. Cambiano solo tono e ordine.
  - Resto in inglese come il file attuale, e rimando al README per i dettagli invece di copiarlo.
  - **Test:** `uv sync` e poi `uv run python3 -m unittest discover -s tests`, con la nota sui test Postgres che vengono saltati se manca `DATABASE_URL`.
  - **Build:** non c'è compilazione. Il "build" è `uv sync` in locale e `docker build -t vela .` per l'immagine. La landing è statica e non ha build.

**Il punto aperto: il lint.** Nel repo oggi non c'è nessun linter: niente ruff, flake8, mypy, né config in `pyproject.toml`. Aggiungerlo vorrebbe dire una nuova dipendenza, e il `CLAUDE.md` chiede di non aggiungerne senza accordo. Le opzioni:

1. **Scrivere onestamente "non c'è un linter"**, e che per ora il controllo è la suite di test più `python -m compileall vela`. *(La mia raccomandazione: documenta lo stato reale senza cambiare lo scope.)*
2. **Proporre ruff come dev dependency**, in un task separato con una sua voce in `docs/decisions.md`. Nel `CLAUDE.md` scriverei `uv run ruff check .` solo dopo che l'hai approvato.
3. **Lasciare la sezione Lint come placeholder** "da decidere".

Quale preferisci? E se una delle supposizioni sopra è sbagliata, dimmelo adesso.

## Utente 17:13

2

## Agente 17:13

Ok, ruff. Il `CLAUDE.md` dice "un task alla volta", quindi li separo così:

**Task A — ruff come dev dependency (prima)**
- Aggiungo `ruff` al gruppo `dev` di `pyproject.toml` e aggiorno `uv.lock` con `uv add --dev ruff`. È un download da PyPI, senza costi.
- Config minima in `pyproject.toml` sotto `[tool.ruff]`: `target-version = "py312"` e le regole di default (`E`, `F`). Niente formatter e niente regole extra, per non allargare lo scope.
- Lancio `uv run ruff check .` e ti riporto quante violazioni trova. Se sono poche le correggo in un commit separato. Se sono tante mi fermo e decidiamo insieme: correggerle, escluderle o ridurre le regole.
- Aggiungo una voce in `docs/decisions.md` (data, decisione, motivo) e una riga nella sezione Test del README.

**Task B — riscrittura di `CLAUDE.md` (dopo)**
- Tono da senior a junior, in inglese. Le sezioni:
  1. **What Vela is**, in 3-4 righe.
  2. **How the code is laid out**: le cartelle con il perché di ognuna.
  3. **How to run tests**
  4. **How to build**: `uv sync`, `docker build` e la landing senza build.
  5. **How to lint**: `uv run ruff check .`.
  6. **Working agreement**, **Git**, **Secrets**, **Scope** e **agent-log**: stesso significato di oggi, scritte più chiare.
- I dettagli restano nel README e il `CLAUDE.md` rimanda lì, così non c'è niente di duplicato che possa andare fuori sincrono.
- Un commit per task, sul branch `task/claude-md` da `master`. Niente push senza chiedere.

Va bene partire dal Task A così?

## Utente 17:13

yes

## Agente 17:13

- 🔧 Bash: Create branch and add ruff as dev dependency

- 🔧 Bash: Add ruff config and count violations

- 🔧 Bash: Count violations with ruff default rules and line lengths

Mi fermo qui, come avevamo detto. Ho creato il branch `task/claude-md`, aggiunto ruff 0.16.9 al gruppo dev (`pyproject.toml` e `uv.lock`) e messo una config provvisoria. Non ho ancora corretto niente e non ho fatto commit.

**Una correzione su quello che avevo scritto:** avevo detto "regole di default (`E`, `F`)", ma non è esatto. Il default vero di ruff è `E4, E7, E9, F` e non comprende il controllo sulla lunghezza delle righe (E501). Il codice del repo sta intorno ai 100 caratteri, quindi quel controllo da solo genera quasi tutte le violazioni.

| Regole | Violazioni |
|---|---|
| `E` + `F`, righe max 88 | 2241, di cui 2205 righe troppo lunghe |
| default ruff (`E4, E7, E9, F`) | **36** |
| default + righe max 100 | 36 + 431 |
| default + righe max 120 | 36 + 15 |

Le 36 del default sono:
- 16 import inutilizzati e 1 riga con più import, che ruff corregge da solo;
- 8 import non in cima al file;
- 5 lambda assegnate a una variabile;
- 4 istruzioni multiple sulla stessa riga;
- 2 nomi ambigui come `l`.

**Opzioni**
1. **Default di ruff, senza limite di lunghezza delle righe.** Correggo le 36 a mano o con `--fix`, controllando gli E402: alcuni potrebbero essere voluti, e in quel caso metto `# noqa` motivato. *(Raccomandata: diff piccolo, ruff trova bug veri come gli import morti, e non si impone uno stile di righe che il progetto non ha mai seguito.)*
2. **Default più righe max 120**: 51 correzioni, con un tetto alle righe molto lunghe.
3. **`E` + `F` a 88**: 2241 correzioni, cioè riformattare quasi tutto il repo. Te la sconsiglio.

Quale scegli?

## Utente 17:15

1

## Agente 17:15

- 🔧 Bash: Use ruff default rules and apply safe fixes

Questa versione di ruff (0.16) ha un default diverso da quello che ho misurato prima: include anche regole `UP` (pyupgrade). Controllo cosa ha già modificato `--fix`:

- 🔧 Bash: Show files changed by fix and remaining rule stats

- 🔧 Bash: Revert ruff fixes except pyproject and lockfile

Adesso fisso le regole in modo esplicito, così non dipendono dalla versione di ruff:

- 🔧 Bash: Pin ruff rules and list violations

Siamo tornati alle 36 previste. Prima di toccare qualcosa guardo i casi non automatici:

- 🔧 Bash: Show the non-auto-fixable violation sites

- 🔧 Bash: Apply safe fixes with pinned rules and view file headers

- 🔧 Bash: Fix remaining violations by hand and rerun ruff

Ruff ora è pulito. Lancio la suite di test:

- 🔧 Bash: Run the full unittest suite

1045 test OK; i 56 saltati sono quelli Postgres, perché `DATABASE_URL` non è impostata. Ora la voce in `docs/decisions.md` e la riga nel README:

- 🔧 Bash: Show last decisions entry format

- 🔧 Bash: Add decision entry and README lint line

Faccio due commit piccoli: prima lo strumento, poi le correzioni.

- 🔧 Bash: Commit ruff setup and violation fixes
