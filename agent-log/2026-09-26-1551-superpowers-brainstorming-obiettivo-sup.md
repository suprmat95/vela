# vela-landing-page-design

- Sessione: `ca44d875-66ad-4a44-bd45-90968a7d332a`
- Inizio: 2026-09-26 15:51

## Utente 15:51

/superpowers:brainstorming: obiettivo: supportare una landing page nella stessa repository. La landing sara una pagina statica che esporra il prodotto vela. sara deployata in un altro servizio render. Intervistami per capire cosa fare

## Agente 15:51

Uso la skill brainstorming. Classificazione: **architetturale**. Si tratta di un nuovo sottosistema (un sito statico con un proprio deploy su Render), non di una modifica a un flusso che esiste già. Quindi: domande, approcci, design a sezioni, spec scritta, piano. Prima guardo lo stato del repo.

- 🔧 Bash: List repo layout, docs and deploy config

- 🔧 Bash: Read README, brief, Docker setup and existing specs

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

Deciso: HTML + CSS scritti a mano, senza build. Ora il deploy. Su Render un sito statico è un servizio `runtime: static`.

- 🔧 AskUserQuestion

- 🔧 Bash: Check which channels exist and the public URL

- 🔧 Bash: Check ElevenLabs status in roadmap and decisions

Ho letto le superfici: MCP (Claude) e REST sono attive. L'agente vocale ElevenLabs è la milestone M12 della roadmap e non esiste ancora un `docs/elevenlabs.md`.

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 Bash: Check dependencies and test layout

Ho abbastanza per il design. Lo scrivo nel file di piano: contiene l'intesa raggiunta, il design e i prossimi passi del flusso (spec scritta, poi piano di implementazione).

- 🔧 Write /Users/matteodospina/.claude/plans/obiettivo-supportare-una-landing-twinkling-hickey.md

- 🔧 ExitPlanMode

Design approvato. Ora scrivo la spec seguendo il formato di quella di M10.

- 🔧 Bash: Read existing spec, decisions tail and docker test style

- 🔧 Bash: Show decisions.md section headers

- 🔧 Bash: Read M10 decisions section header

Scrivo la spec e la sezione delle decisioni.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-landingpage/docs/superpowers/specs/2026-09-26-landing-design.md

- 🔧 Bash: Append decisions and commit spec

Ho scritto la spec e l'ho committata in `docs/superpowers/specs/2026-09-26-landing-design.md` (commit `a1e55ac`). Nello stesso commit ho aggiunto la sezione "Landing: design" a `docs/decisions.md`. Rileggendola non ho trovato parti lasciate in sospeso, contraddizioni o punti ambigui.

**Cosa ho deciso**
- **Scopo:** la pagina è una guida per raggiungere Vela, non una vetrina. Non mostra viaggi, prezzi, liste o tabelle, per restare coerente con "no homepage" del brief. Un test controlla che non ci siano `<table>` né richieste dalla pagina all'API.
- **Struttura:** una cartella `landing/` con `index.html`, `styles.css`, `config.js`, `main.js` e `assets/`. Tutto scritto a mano, senza build e senza dipendenze.
- **Sezioni:** apertura con esempio di richiesta a parole, "Come funziona" in tre passi, "Con Claude" (passi per il connector e pulsante per copiare l'URL MCP), "A voce" (widget ElevenLabs), "Al telefono" (numero), footer con il link al repo.
- **Voce e telefono:** agent id e numero sono vuoti in `config.js`, quindi le due sezioni mostrano "In arrivo" e lo script ElevenLabs non viene caricato. Quando M12 è pronta basta compilare quei due campi.
- **Deploy:** in `render.yaml` c'è un nuovo servizio statico `vela-landing` che si ricostruisce solo per modifiche in `landing/`. `landing` viene anche escluso dall'immagine Docker dell'API.

**Su cosa non sono sicuro**
- Per evitare che le modifiche alla landing ridistribuiscano l'API, al servizio `vela` esistente va aggiunta una riga (`buildFilter.ignoredPaths`). Tocca la configurazione di un servizio già in produzione: confermami che va bene.
- L'URL MCP scritto nella pagina è quello del README (`vela-n506.onrender.com`). Se l'URL di produzione è diverso, dimmelo.
- Il nuovo servizio si crea con il "Sync" del blueprint dalla dashboard Render. Quel passo è tuo.

Rivedi la spec e dimmi se vuoi modifiche. Quando la approvi passo al piano di implementazione con `writing-plans`.

## Utente 15:59

/superpowers:writing-plans: docs/superpowers/specs/2026-09-26-landing-design.md (

## Agente 15:59

Uso la skill writing-plans per scrivere il piano di implementazione. Prima controllo come i test attuali leggono `render.yaml` e `.dockerignore`.

- 🔧 Bash: Find existing tests on render.yaml and dockerignore

- 🔧 Bash: Read render.yaml test, README deploy section, prior plan style

- 🔧 Bash: Get repo remote and plan conventions

Scrivo il piano in `docs/plans/`, dove stanno quelli di M0–M17.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-landingpage/docs/plans/2026-09-26-landing.md
