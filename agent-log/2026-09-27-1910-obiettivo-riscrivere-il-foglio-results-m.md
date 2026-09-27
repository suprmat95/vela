# RESULTS.md load test rewrite

- Sessione: `8b41ecb3-b325-474d-ad00-d7aa1b2ec28e`
- Inizio: 2026-09-27 19:10

## Utente 19:10

Obiettivo: riscrivere il foglio RESULTS.md in load test completamente. voglio fare in modo che sia possibile lanciare un loadtest indicando il numero di utenti e la percentuale che naviga solo il sito, la percentuale che richiede la proposta, la percentuale che accetta la proposta e arriva al link e poi la restentante che paga. Voglio lanciare questo test con 10k utenti e fare delle proiezioni su 50000

## Agente 19:10

- 🔧 Bash: List load test files and read README

- 🔧 Bash: Read scenario, journey, runner, projection and RESULTS outline

- 🔧 Bash: Inspect surfaces, report, rest of RESULTS, roadmap

- 🔧 Bash: Check how the landing is served and what it calls

Ho letto il banco (`loadtest/`: scenario, journey, locustfile, run, report, projection) e l'attuale `RESULTS.md`. Come da working agreement, ecco l'approccio. Aspetto il tuo OK prima di toccare il codice.

**Approccio proposto**

1. **Scenario a quattro gruppi** (`loadtest/scenario.py`): al posto dell'imbuto attuale (20% accetta, 60% di chi ha il link paga) ogni viaggiatore finisce in **uno solo** di quattro gruppi, con percentuali sul totale:
   - `browse`: naviga solo il sito;
   - `proposal`: `create_intent` + `get_proposal` e si ferma;
   - `link`: accetta, conferma il prezzo, arriva al link e non paga;
   - `pay`: il resto (100 − gli altri tre), paga.
   Il seme resta fisso, così i giri si possono confrontare.
2. **CLI** (`run.py`, `locustfile.py`): `--travelers 10000 --browse 40 --proposal 40 --link 15`, e `pay` è il resto. Se la somma supera 100 il comando dà errore. Il vecchio `--pay` (quota di chi ha il link) sparisce.
3. **Report** (`report.py`): conteggi e esiti per gruppo, attesi contro raggiunti (quanti del gruppo `link` hanno davvero visto il link entro il giro, quanti del gruppo `pay` sono confermati), più le misure di oggi su quota, p95 e coda.
4. **Proiezione** (`projection.py`): stesso modello a coda satura, alimentato dalle percentuali dei gruppi e dal ritmo di link misurato nel giro da 10k. Produce la tabella per 50.000 (coda, attese, smaltimento, req/s REST), marcata **[proiezione]**.
5. **Giro**: 10.000 viaggiatori in locale con `docker compose`, niente HofJ vero né Stripe. Nessuna chiamata esterna a pagamento.
6. **`RESULTS.md` riscritto da zero** con banco, parametri, criteri, misure del giro da 10k e proiezione a 50k. La storia di M13a, M18 e M19 resta in git e in `docs/decisions.md`. Aggiorno anche `loadtest/README.md`, scrivo i test di scenario, run, report e proiezione e registro la decisione in `decisions.md`.

**Una cosa da sapere prima di scegliere:** la landing è un sito statico separato su Render (`vela-landing` in `render.yaml`) e non chiama le API di Vela. Chi "naviga solo il sito" quindi non genera carico su Vela: il suo peso è zero per quota e coda.

Mi servono tre decisioni:

- 🔧 AskUserQuestion

Le percentuali indicate (50/40/18/2) sommano a **110%**, e manca la durata. Prima di procedere ti chiedo come leggerle:

- 🔧 AskUserQuestion

Tutto chiaro: **50/30/18/2**, 5 + 3 minuti, chi naviga viene solo contato, nessun rifiuto. Parto dal codice.

- 🔧 Bash: Read report and existing load test tests

- 🔧 Bash: Read report/run tests, decisions tail, compose locust

Parto dallo scenario, poi viaggiatore, CLI, report e proiezione, ognuno con i suoi test.

- 🔧 Bash: Find Funnel usages and running containers

- 🔧 Bash: Rewrite scenario with four-group mix

- 🔧 Bash: Update journey and locustfile for groups

Ora `run.py`: le percentuali vengono validate subito, prima di aspettare il catalogo, e il comando stampa lo scenario.

- 🔧 Bash: Add group percentage options to run.py

Ora il report: una tabella per gruppo con cosa ha raggiunto ognuno.

- 🔧 Bash: Add per-group measures to the report

Ora la proiezione, generalizzata sui quattro gruppi:

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/last-load-test/loadtest/projection.py

Ora i test. Scenario e viaggiatore:

- 🔧 Bash: Update scenario and journey tests, run them

- 🔧 Bash: Show failing test details

Questi errori erano attesi: i test di run e proiezione descrivono ancora il vecchio imbuto. Li riscrivo e aggiungo il test dei gruppi nel report.

- 🔧 Bash: Rewrite projection tests, update run/report tests, run them

- 🔧 Bash: Run full suite, lint, look for stale references

Suite verde (1698 test, 78 saltati per Postgres), lint pulito. Faccio un commit del codice prima del giro.

- 🔧 Bash: Commit the load test changes
