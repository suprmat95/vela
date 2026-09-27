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

Ora il giro da 10.000. Preparo l'override che toglie le porte host, per non entrare in conflitto con lo stack `master-*`:

- 🔧 Bash: Create override without host ports and check config

- 🔧 Bash: Build images and start the load test stack

- 🔧 Bash: Run the 10,000-traveler load test (about 10 minutes)

Mentre il giro gira (circa 10 minuti), aggiorno `loadtest/README.md`.

- 🔧 Bash: Show README run and scenario sections

- 🔧 Bash: Rewrite the run and scenario sections of the README

- 🔧 Bash: Fix the faults example and check run progress

Il giro è partito alle 17:19 con un catalogo di 190 prodotti (il README diceva 126, dato vecchio: lo correggo). Scrivo intanto la voce per `docs/decisions.md`.

- 🔧 Bash: Fix catalogue size in README, find decisions format

- 🔧 Bash: Append the decision record and check run progress

Il giro è in corso: la voce in `docs/decisions.md` è scritta e aspetto la fine del run (circa 9 minuti dall'avvio) per scrivere `RESULTS.md` con i numeri veri.

- 🔧 ToolSearch

Il giro da 10.000 è partito alle 17:19 e dura circa 9 minuti. `RESULTS.md` non è ancora scritto: lo compilo solo con i numeri misurati, appena il giro finisce.

**Già fatto e committato** (`c41a840`, 1698 test verdi, lint pulito):
- **Gruppi da riga di comando**: il test si lancia indicando le quattro quote. I default sono il tuo scenario, e chi paga è il resto fino a 100. Se le percentuali superano 100 il comando si ferma subito, prima di partire.
  ```sh
  docker compose run --rm locust --travelers 10000 --browse 50 --proposal 30 --link 18 \
      --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k
  ```
- **Numeri esatti per gruppo**: su 10.000 sono 5.000 / 3.000 / 1.800 / 200, mescolati lungo la finestra con il seme fisso. Il comando li stampa prima di partire.
- **Esiti del viaggiatore finto**: chi naviga solo il sito non fa richieste (`site_only`), chi chiede la proposta si ferma lì (`proposal_only`), chi arriva al link non paga (`link_unpaid`), chi paga arriva a `confirmed`. Nessuno dice "troppo caro". Marco e Anna restano come sentinelle in più.
- **Report**: una tabella per gruppo con proposta, link, pagati, confermati, esito raggiunto e ancora in corso.
- **Proiezione**: `projection.py` usa le stesse quattro quote e dà coda, attese, tempo di smaltimento, link e pagati entro la fine del giro e richieste REST al secondo.

**Da committare** (lo faccio insieme a `RESULTS.md`):
- `loadtest/README.md` aggiornato, con la tabella delle opzioni per chi rilancia il test.
- La voce in `docs/decisions.md` con le tue scelte.

**Da sapere:**
- Uno stack `master-*` occupa le porte 8000/8001. Ho lanciato il giro con un nome di progetto diverso e un override temporaneo nello scratchpad, senza fermare nulla e senza toccare il compose del repo.
- Il catalogo ora ha 190 prodotti, non 126: ho corretto il README.
- **Cosa mi aspetto**: 2.000 accettazioni in 5 minuti sono circa 400 al minuto, contro circa 47 link al minuto misurati dopo M19. Quindi la gran parte dei gruppi "link" e "paga" dovrebbe restare in coda a fine giro. Il report lo mostrerà per gruppo.

## Utente 19:23

Si nella tabella fai capire le persone dopo quanto tempo riescono a pagare

## Agente 19:23

- 🔧 Bash: Check load test progress

Il giro è a metà (log in UTC, ora 17:23). Intanto aggiungo i tempi al report. Si rigenera da `travelers.jsonl`, quindi posso applicarlo anche a questo giro.

- 🔧 Bash: Add arrival-to-link and arrival-to-payment times to report

Ora la proiezione: una colonna "attesa per poter pagare" con Marco, la mediana e l'ultimo.

- 🔧 Bash: Add time-to-pay columns to projection and test

- 🔧 Bash: Wait for the load test run to finish

Il giro è finito. Rigenero il report in locale con la versione finale di `report.py`, che ha i tempi:

- 🔧 Bash: Regenerate and print the 10k run report

- 🔧 Bash: Inspect REST failures and Vela error logs

- 🔧 Bash: Find database pool configuration

- 🔧 Bash: Project the measured rate to 10k and 50k

- 🔧 Bash: Add pay-within projection table and measure it on the run

- 🔧 Bash: Record machine specs and confirm vela code unchanged

Sto scrivendo il nuovo `RESULTS.md` con i numeri del giro e la proiezione a 50.000.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/last-load-test/loadtest/RESULTS.md

Controllo i numeri citati nel testo e attenuo una frase che era un'ipotesi, non una misura:

- 🔧 Bash: Soften unverified claim, run tests and lint

Test verdi e lint pulito. Aggiungo alla voce delle decisioni i tempi di pagamento e l'errore del pool, poi faccio due commit e spengo il mio stack.

- 🔧 Bash: Record decisions, commit, and tear down the load test stack
