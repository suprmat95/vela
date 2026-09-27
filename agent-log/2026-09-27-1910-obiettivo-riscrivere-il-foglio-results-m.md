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

Il giro da 10.000 è fatto e `loadtest/RESULTS.md` è riscritto da zero attorno a quel giro e alla proiezione a 50.000. Il test è verde su 4 criteri su 5: il quinto fallisce per **3 errori HTTP 500** su 26.408 richieste REST.

**Da riga di comando** si sceglie tutto: numero di viaggiatori, le percentuali dei primi tre gruppi (chi paga è il resto fino a 100) e la durata. I default sono il tuo scenario. In `loadtest/README.md` c'è la tabella di tutte le opzioni.
```sh
docker compose run --rm locust --travelers 10000 --browse 50 --proposal 30 --link 18 \
    --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k
```

**Dopo quanto si riesce a pagare, misurato a 10.000:**
- Dei 200 paganti, entro gli 8 minuti del giro hanno pagato solo in 30 (15%), 17 dei quali entro 5 minuti dall'arrivo.
- Tra chi ce l'ha fatta, dall'arrivo al pagamento sono passati in mediana 3,9 minuti, al massimo 7,1.
- Chi paga lo fa appena vede il link: il collo di bottiglia è la coda del link. Accettano 400 persone al minuto e Vela produce 44,4 link al minuto, perché è ferma sulla quota di HofJ.
- A fine giro restavano in coda 172 paganti su 200 e 1.519 su 1.800 del gruppo "arriva al link".

**Proiezione (tempo di attesa del link, cioè prima di poter pagare):**

| Viaggiatori in 5 min | Primi in coda (chi accetta al minuto 1) | Mediana | Ultimo | Paganti che possono pagare entro 1 ora |
|---|---|---|---|---|
| 10.000 | 8 min | 20 min | 40 min | 100% |
| 50.000 | 44 min | 110 min | 220 min | 27% |

Il modello regge il confronto con il giro a 10.000: coda a fine arrivi 1.778 prevista contro 1.809 misurata, stesse 86,8 richieste al secondo. Sul totale è un po' ottimista: prevedeva 355 link entro la fine del giro, ne sono arrivati 311.

**Criteri:**
- **Quota:** 0 risposte 429 da HofJ e massimo 107 chiamate in 60 secondi, sotto il limite di 108.
- **Marco:** confermato a 247 secondi, dentro i 7 minuti.
- **Doppie prenotazioni:** nessuna.
- **Errori:** i 3 500 vengono dal pool di connessioni al database, esaurito al picco di 87 richieste al secondo. È quello di default di SQLAlchemy, 5 + 10 connessioni, in `vela/adapters/db.py:32`.
- **Tempi di risposta:** al picco il p95 sale a 0,8-1,1 secondi, contro al massimo 0,2 secondi a 34 richieste al secondo nei giri precedenti.

**Cosa ho deciso io:**
- Le percentuali producono numeri esatti per gruppo (su 10.000: 5.000, 3.000, 1.800, 200) invece di quote approssimate.
- Marco e Anna restano come sentinelle, fuori dai gruppi.
- I giri precedenti escono da `RESULTS.md` ma restano nella storia git (`git show 5ec87aa:loadtest/RESULTS.md`).

Tutto è registrato in `docs/decisions.md`.

**Cosa non so:**
- Chi arriva per primo ha aspettato meno del previsto: Marco ha avuto il link dopo 3 minuti, il modello ne dava 8. Ho un'ipotesi (nella coda iniziale ci sono persone che non hanno ancora confermato il prezzo), ma non l'ho verificata.
- Le 454 richieste al secondo a 50.000 sono solo stimate.

**Decisione per te:** gli errori del pool li ho riportati senza toccare il codice. Per chiuderli vedo tre strade:
- alzare il pool, la più semplice;
- configurarlo per istanza tramite `Settings`;
- più processi uvicorn, che serviranno comunque a 50.000.

Consiglio la seconda, poi un nuovo giro per verificarla. Dimmi quale preferisci.

Sono 3 commit su `suprmat95/last-load-test` (`c41a840`, `8a58313`, `281e1c1`), non pushati. Test verdi (1698, 78 saltati perché senza database Postgres), lint pulito. Il mio stack Docker è spento e lo stack `master-*` non l'ho toccato.

## Utente 19:33

indicami entro quanto tempo ricevono il link

## Agente 19:33

- 🔧 Bash: Compute time-to-link distribution from the run and projection

Chi è arrivato nel primo minuto ha avuto il link in circa 4 minuti; chi è arrivato dopo il primo minuto non l'ha avuto entro gli 8 minuti del giro, tranne una persona. Il conto è su tutti i 2.000 che accettano (gruppi "link" e "paga" insieme), e questi tempi non entrano nella media di `RESULTS.md`, perché lì conto solo chi il link l'ha ricevuto.

**Misurato a 10.000**, tempo dall'arrivo al link:

| Entro | 1 min | 2 min | 3 min | 4 min | 5 min | 6 min | 7 min | 8 min (fine giro) |
|---|---|---|---|---|---|---|---|---|
| Hanno il link | 0 | 57 (2,9%) | 103 (5,2%) | 147 (7,4%) | 192 (9,6%) | 253 (12,7%) | 296 (14,8%) | 310 (15,5%) |

- Il più veloce l'ha avuto in 65 secondi, la mediana è 4,2 minuti, il più lento 7,5 minuti.
- La coda serve chi arriva prima. Per minuto di arrivo:

| Arrivati nel minuto | Hanno accettato | Link entro il giro | Mediana (min) |
|---|---|---|---|
| 1 | 398 | 309 | 4,2 |
| 2 | 411 | 1 | 6,9 |
| 3-5 | 1.190 | 0 | — |

- Chi ha il link lo riceve a circa 4 minuti dall'arrivo; gli altri restano in coda anche per ore.

**Proiezione**, quota di chi accetta che ha il link entro X minuti dall'arrivo:

| Viaggiatori in 5 min | Entro 5 min | 15 min | 30 min | 1 ora | 2 ore | 4 ore | L'ultimo |
|---|---|---|---|---|---|---|---|
| 10.000 | 12% | 37% | 75% | 100% | 100% | 100% | 40 min |
| 50.000 | 2% | 7% | 14% | 27% | 54% | 100% | 3 ore e 40 min |

Qui il modello è un po' ottimista. Entro 5 minuti prevede il 12% a 10.000, mentre il giro ha dato 9,6%, perché nel primo minuto non esce nessun link.

Vuoi che aggiunga queste tabelle a `RESULTS.md` e i tempi di arrivo al link per minuto di arrivo anche al report automatico?

## Utente 19:35

ma com'è possibile? prima non ci voleva cosi tanto tempo

## Agente 19:35

Non è Vela che è diventata più lenta: il ritmo dei link è quasi lo stesso di prima. È cambiato il numero di persone in coda. Il confronto con l'ultimo giro misurato (C-2500 dopo M19, stessa finestra di 5 + 3 minuti, numeri dalla versione precedente di `RESULTS.md`):

| | C-2500 dopo M19 (prima) | 10k a quattro gruppi (ora) |
|---|---|---|
| Viaggiatori in 5 min | 2.500 | 10.000 |
| Accettano | 487 (20%) | 2.001 (20%: 18% link + 2% paga) |
| Accettazioni al minuto | ~97 | ~400 |
| **Link al minuto (ritmo di Vela)** | **47,4** | **44,4** |
| Chiamate a HofJ al minuto | ~100 | ~100 |
| Chiamate per link | 2,11 | 2,11 |
| In coda a fine giro | 159 | 1.690 |
| Il più vecchio in coda (s) | 287 | 445 |
| Marco: link a | 90 s | 241 s |

1. **Il collo di bottiglia è lo stesso**: la quota di HofJ, cioè ~100 chiamate al minuto e 2 per link, quindi ~45 link al minuto. Qualunque sia il numero di viaggiatori, Vela non ne produce di più.
2. **La domanda è 4 volte più grande.** Prima arrivavano ~97 accettazioni al minuto contro 47 link: la coda cresceva di ~50 persone al minuto. Ora ne arrivano 400: la coda cresce di ~355 al minuto, 7 volte più in fretta. Marco accetta al minuto 1 con ~400 persone già davanti invece di ~100, e il link gli arriva a 241 secondi invece che a 90.
3. **Il ritmo scende di poco, da 47,4 a 44,4**, per i pagamenti. Prima pagava il 2% di chi riceveva il link (14 pagamenti), ora il 2% di tutti, cioè il 10% di chi accetta (31 pagamenti). Ogni pagamento costa 3 chiamate a HofJ (cliente, passeggeri, booking): 93 chiamate invece di 42, circa 6 al minuto in più, che corrispondono a circa 3 link al minuto in meno.

Anche prima, del resto, il link arrivava solo a chi arrivava presto: a fine giro 159 persone erano ancora in coda. Con 2.500 viaggiatori la coda restava di qualche minuto; con 10.000 diventa di decine di minuti, e a 50.000 di ore.

Per accorciare l'attesa bisogna aumentare i link al minuto, perché il codice di Vela non è il limite. Le strade sono più quota su HofJ (un'altra chiave o un limite più alto) oppure meno chiamate per link. Posso scriverti le opzioni con i numeri, o aggiungere questo confronto a `RESULTS.md`.

## Utente 19:36

ok riportalo in architecture e scrivilo

## Agente 19:36

- 🔧 Bash: Look for an architecture document

- 🔧 Bash: Inspect the architecture file and spec sections

- 🔧 Bash: Locate the architecture document

- 🔧 Bash: Inspect the doc-architecture worktree and its ARCHITECTURE.md

## Utente 19:36

[Request interrupted by user]

scusa riportalo in results

## Agente 19:36

Nessun problema, lo scrivo in `RESULTS.md`.

- 🔧 Bash: Find insertion points and old run numbers

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/last-load-test/loadtest/RESULTS.md

- 🔧 Bash: Add link timing and comparison sections to RESULTS.md

`RESULTS.md` era cambiato su disco dopo il mio ultimo commit. Controllo cosa c'è di diverso prima di committare:

- 🔧 Bash: Review uncommitted changes to RESULTS.md

- 🔧 Bash: Check new sections and commit RESULTS.md
