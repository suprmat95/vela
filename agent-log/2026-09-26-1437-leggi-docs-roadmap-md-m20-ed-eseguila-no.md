# Docs/roadmap.md M20

- Sessione: `5d48fd4b-9ec7-4a8f-94c4-da3d678a3fa4`
- Inizio: 2026-09-26 14:37

## Utente 14:37

Leggi docs/roadmap.md M20 ed eseguila. Non mergiare: va su master solo dopo M13b.

## Agente 14:37

- 🔧 Bash: Read M20 section of the roadmap

- 🔧 Bash: Search roadmap for M20 and M13b references

- 🔧 Bash: List roadmap headings and look for M20 on other branches

- 🔧 Bash: Compare task/m20 with master and locate M20 on master

- 🔧 Bash: Read the M20 section from master

Il branch `task/m20` è indietro rispetto a `master` locale: M20 esiste solo lì. Faccio un fast-forward (nessuna riscrittura) e leggo il codice coinvolto.

- 🔧 Bash: Fast-forward branch to master and read the decision

- 🔧 Bash: Read accept_proposal and get_order_status

- 🔧 Bash: Read Settings, say phrases, surfaces and spec refs

- 🔧 Bash: Inspect usecase constructor, say_queued, REST reply and MCP descriptions

- 🔧 Bash: Check how Vela is constructed and wired

Ho letto M20 (su `master`, non ancora su questo branch: ho fatto un fast-forward di `task/m20` a `master`, senza riscrivere la storia), la decisione del 2026-09-26 e il codice coinvolto. Come chiede il CLAUDE.md, prima di implementare ti propongo l'approccio e chiudiamo le decisioni aperte.

**Approccio proposto**
- **Dominio** (`vela/domain/usecases.py`): `Vela.__init__` riceve due parametri nuovi, `accept_wait_seconds` (default 0) e `sleep` (default `time.sleep`). Il default 0 serve perché i test esistenti non restino fermi 10 s; il valore reale arriva da `Settings`. In `accept_proposal`, dopo l'accodamento:
  - **posizione 1**: rilegge l'ordine ogni 0,5 s finché non scade `accept_wait_seconds`.
    - Se diventa `awaiting_payment`, `replaced` o `failed`, restituisce subito `get_order_status(...)`, che include link, proposta nuova o motivo.
    - Se allo scadere è ancora `queued`, restituisce `OrderQueued` con la frase nuova.
  - **posizione > 1**: risponde subito come oggi.
  - **Doppio accept**: resta com'è, cioè restituisce lo stato dell'ordine esistente senza attendere.
- **Config** (`vela/config.py`, `vela/app.py`): nuovo campo `Settings.accept_wait_seconds: float = 10`, senza variabile d'ambiente, passato a `Vela` in `app.py`.
- **Frase**: nuova `say_preparing(lang)` in `say.py`, in it/en, con il testo della roadmap.
- **Superfici**:
  - REST: nessuna modifica al codice, perché `reply` già risponde 200 `order_status` e 202 `order_queued`. Aggiorno la docstring e `docs/rest.md`.
  - MCP: aggiorno la descrizione di `accept_proposal` ("il link può arrivare subito o con `get_order_status`").
- **Spec e decisioni**: aggiorno RF-45 (righe 139, 249 e 293) e RNF-04. Registro in `docs/decisions.md` le scelte che mi confermi.
- **Test** (TDD, con `sleep` finto che fa avanzare un worker finto): i casi della roadmap tranne l'ultimo.
  - Il confronto con "il p95 di M13b" non si può fare adesso, perché M13b non esiste ancora. Propongo di annotarlo in M13b come verifica da fare lì.
- **Git**: piccoli commit su `task/m20` e **nessun merge** su `master`. Aggiungo in M20 una nota che si mergia dopo M13b. Il push lo faccio solo se me lo chiedi.

**Decisioni aperte**
1. **Durata dell'attesa.** Consiglio **A) 10 s per tutti**. L'agente vocale (M12) oggi non ha un canale separato, quindi B aggiungerebbe una distinzione per superficie che non esiste. Se in M12 il silenzio si rivela un problema, basta cambiare il valore in `Settings`.
2. **Condizione.** Consiglio **A) posizione 1**. Con B il quarto in coda aspetterebbe 10 s e quasi sempre riceverebbe comunque "in coda": la risposta arriverebbe più lenta proprio sotto picco, cioè il caso che M13b misura.
3. **Intervallo tra le riletture** (non è nella roadmap). Consiglio **0,5 s come costante nel codice**, senza campo in `Settings`: al massimo 20 letture dal DB per ogni accept in posizione 1. In alternativa si può fare un campo in `Settings`, oppure 1 s.

Confermi A / A / 0,5 s e l'approccio?

## Utente 14:39

a a 0,5

## Agente 14:39

- 🔧 Bash: Find existing accept_proposal tests

- 🔧 Bash: Read the queue flow test setup

- 🔧 Bash: Read replacement test and HofJ-not-called test

- 🔧 Bash: Find RF-45 tests and run baseline suite

- 🔧 Bash: Summarize baseline test failures

Il `python3` di sistema è la 3.7 e non ha le dipendenze. Cerco il virtualenv del progetto.

- 🔧 Bash: Look for a project virtualenv

- 🔧 Bash: Create venv with uv and run baseline tests

- 🔧 Bash: Read OrderStatus, OrderQueued and say_status

Baseline con il venv: 916 test OK. Scrivo prima i test (TDD).

- 🔧 Bash: Add M20 tests to queue flow and check repo API

- 🔧 Bash: Find existing preparing phrase

- 🔧 Bash: Add say test and run new tests (expect failures)

- 🔧 Bash: Run say and queue tests to see red

Test rossi per il motivo atteso. Ora l'implementazione.

- 🔧 Bash: Read usecases header and imports

- 🔧 Bash: Implement the accept wait and the new phrase, rerun tests

- 🔧 Bash: Check line length conventions

Verde. Ora `Settings` e `app.py`.

- 🔧 Bash: Add Settings field and wire it in app

- 🔧 Bash: Find REST accept tests and docs

- 🔧 Bash: Read REST test setup and flow test

- 🔧 Bash: Read how rest_flow handles accept

- 🔧 Bash: Read expect helper and loadtest accept handling

- 🔧 Bash: Check loadtest accept handling

Il dominio è fatto e i test sono verdi. Adeguo lo script `rest_flow.py`: oggi fallisce se l'accept restituisce subito il link, e con M20 può succedere.

- 🔧 Bash: Let rest_flow accept an immediate order_status

Riavvolgo la docstring che ho reso troppo lunga e aggiungo un test.

- 🔧 Bash: Fix docstring wrap, add rest_flow test and run it

- 🔧 Bash: Fix docstring and run rest_flow tests from tests dir

- 🔧 Bash: Run the full test suite

- 🔧 Bash: Find app-level Settings in tests and DB availability

Diversi test di app vengono saltati senza `DATABASE_URL`. Li provo con un SQLite nella scratchpad, per vedere se l'attesa di 10 s li rallenta o li rompe.

- 🔧 Bash: Run suite against a scratch SQLite DB

- 🔧 Bash: Run suite against a scratch SQLite DB

Servono Postgres veri. Avvio un'istanza temporanea nella scratchpad, su una porta libera.

- 🔧 Bash: Start a throwaway local Postgres in scratchpad

- 🔧 Bash: Diagnose initdb

Qui c'è solo libpq, senza server. Provo con Docker (`postgres:16`, locale).

- 🔧 Bash: Check Docker daemon and local postgres images

- 🔧 Bash: Start a throwaway Postgres container

- 🔧 Bash: Run full suite against local Postgres

Tutto verde anche con Postgres: 924 test, nessuno saltato. Aggiungo un test REST sul 200 `order_status` con il link.

- 🔧 Bash: Read REST test fixtures

- 🔧 Bash: Add REST test for 200 with link

- 🔧 Bash: Run REST tests

- 🔧 Bash: Find config defaults test

- 🔧 Bash: Read M5 defaults tests

- 🔧 Bash: Add Settings default test

## Utente 15:06

[Request interrupted by user for tool use]

si ho sbagliat

## Agente 15:06

Nessun problema, riprendo da dove mi ero fermato.

- 🔧 Bash: Add Settings default test and run it

Primo commit con il codice e i test.

- 🔧 Bash: Commit code and tests

Il commit ha incluso `tests/agent-log/…`: il log automatico è finito dentro `tests/` perché la shell era rimasta in quella directory. Controllo.

- 🔧 Bash: Inspect commit contents and agent-log script paths

Il hook di `scripts/agents_log.py` scrive in `<cwd>/agent-log`, e il cwd della sessione era `tests/`. Per non riscrivere la storia, sposto i file con un commit successivo invece di fare un amend.

- 🔧 Bash: Move misplaced session log into agent-log

- 🔧 Bash: Remove stale log copy from tests

Ora la documentazione. Leggo le righe da aggiornare nella spec.

- 🔧 Bash: Read spec sections for RF-45 and RNF-04

- 🔧 Bash: Update spec RF-19, RF-45, table and RNF-04

Ora `docs/rest.md`, la docstring REST e la descrizione del tool MCP.

- 🔧 Bash: Read REST docstring, docs and MCP description tests

- 🔧 Bash: Check tests on MCP descriptions and REST endpoint table

- 🔧 Bash: Read MCP accept description test

- 🔧 Bash: Update MCP description, REST docs and test

- 🔧 Bash: Commit docs and description updates

Ora il registro delle decisioni e la roadmap.

- 🔧 Bash: Read M13b test section

- 🔧 Bash: Read full M13b section

- 🔧 Bash: Record decisions and close M20 open points

- 🔧 Bash: Commit docs, run full suite on Postgres, stop container

M20 è implementata su `task/m20`, in 5 commit locali. Non ho fatto merge né push. La suite passa: `OK`, 926 test, anche contro un Postgres locale temporaneo in Docker (poi fermato).

**Cosa fa adesso**
- **Accettazione**: quando l'ordine è il primo in coda, `accept_proposal` aspetta fino a 10 s rileggendo l'ordine ogni 0,5 s.
  - Se il job porta l'ordine a `awaiting_payment`, `replaced` o `failed`, restituisce subito lo stato dell'ordine: il link, la proposta nuova o il motivo.
  - Se allo scadere l'ordine è ancora in coda, risponde "in coda" con la frase nuova ("Sto preparando il pagamento con il fornitore, ci vogliono pochi secondi…").
  - Dalla posizione 2 in poi risponde subito come prima. Non chiama né HofJ né Stripe.
- **Configurazione**: `Settings.accept_wait_seconds = 10`, senza variabile d'ambiente, passato a `Vela` in `vela/app.py`. Nel dominio il default è 0, così chi costruisce `Vela` a mano non aspetta; l'attesa passa da un `sleep` sostituibile nei test.
- **REST**: 200 `order_status` quando il link è pronto, 202 come prima negli altri casi. Non è servito cambiare codice.
- **MCP**: aggiornata la descrizione di `accept_proposal`.
- **`scripts/rest_flow.py`**: ora accetta anche un 200 dall'accept, altrimenti con la coda vuota si sarebbe rotto.
- **Documenti**: spec (RF-19, RF-45, RNF-04 e tabella di §4.10), `docs/rest.md`, e le decisioni registrate in `docs/decisions.md`.
- **Test**: coperti tutti i casi della roadmap tranne l'ultimo. Il job che finisce durante l'attesa restituisce il link, il job lento dà la frase nuova, dalla posizione 2 non c'è attesa, la sostituzione restituisce la proposta nuova. Coperti anche il fallimento e il doppio accept (stesso ordine, un solo job), più i test REST, `rest_flow`, config e frasi.

**Cosa ho deciso io**
- Prima di iniziare ho portato `task/m20` avanti fino a `master` locale, senza riscrivere la storia: M20 esisteva solo lì.
- L'ultimo test ("sotto picco nessun accept supera il p95 di M13b") non si può fare finché M13b non c'è. Nella roadmap l'ho segnato come verifica da fare dopo M13b, rilanciando lo scenario.

**Cosa è andato storto**
- Il hook che scrive il log della sessione usa la directory corrente della shell, che in quel momento era `tests/`. Il primo commit ha quindi incluso `tests/agent-log/…`.
- L'ho corretto con due commit successivi invece di riscrivere la storia. Il messaggio del primo ("Move…") è impreciso: in realtà ha aggiunto la copia aggiornata del log in `agent-log/`, e la copia vecchia l'ha tolta il commit dopo.
- Il difetto è in `scripts/agents_log.py` (riga 221). Non l'ho toccato perché non fa parte di M20: se vuoi, lo sistemo a parte.

**Dubbi**
- **RNF-05** chiede che i casi d'uso rispondano sotto i 500 ms al 95° percentile. Un accept in posizione 1 ora può durare fino a 10 s. Non l'ho modificato: è una questione di come si misura, quindi tocca a M13b. Dimmi se preferisci escludere l'accept in posizione 1 oppure aggiungere una nota.
- Sul branch non c'è `loadtest/`, che arriva con M13a. Se lo scenario di M13a si aspetta sempre 202 dall'accept, andrà adeguato quando rimetto M20 sopra `master` dopo M13b.

Prima di aprire la PR, e comunque dopo M13b, rimetto il branch sopra `master` e faccio push con `--force-with-lease`, come dicono le tue istruzioni globali. Quando è il momento, dimmi se procedere: il CLAUDE.md del progetto chiede di chiedere prima di riscrivere la storia.

## Utente 15:34

devo aspettare m13a o posso mergiare?

## Agente 15:34

- 🔧 Bash: Check whether M13a, M18, M13b are merged

- 🔧 Bash: Check whether task/m18 has work

No: non basta nemmeno M13a, bisogna aspettare **M13b**. La roadmap mette M20 in "mergiare dopo M13b" e lo spiega così: le misure di M13b sono confrontabili con quelle di M13a solo se M20 arriva dopo. Se l'accept in posizione 1 inizia ad aspettare fino a 10 s, cambiano i tempi di risposta misurati. La differenza tra "prima" e "dopo" in `RESULTS.md` non sarebbe più dovuta solo a M18.

Ecco a che punto sono i rami su cui M20 aspetta:
- **M13a**: non è ancora su `master`, perché `task/m13a` ha 6 commit non mergiati.
- **M18**: risulta già su `master`, dato che l'ultimo commit di `task/m18` (`2aca1e7`, "Drop the unused quota_window.used column") è nella sua storia.
- **M13b**: non esiste ancora un branch.

C'è una cosa da controllare prima di andare avanti. Secondo la roadmap M13a va mergiato **prima** di M18, perché la colonna "prima" deve misurare il codice senza M18. Se M18 è davvero già su `master`, M13a misurerebbe il codice con M18 e il confronto di M13b perderebbe senso. Conviene verificarlo prima di lanciare M13a, oppure lanciarlo su un commit di `master` precedente a M18.

L'ordine è quindi: M13a (misurato senza M18), poi M13b, poi rimetto M20 sopra `master`, verifico il p95 e mergio.

## Utente 15:38

ok master è tornato indietro controlla

## Agente 15:38

- 🔧 Bash: Inspect master's current state and reflog

- 🔧 Bash: Check origin/master and M13a base

Confermo, ora è tutto a posto:

- **`master` locale** è tornato a `21db1fa` ("Merge branch 'doc/accept-wait-2'"). Il reflog mostra i due merge di `task/m18` (`f20ca0c`, `85b6700`) seguiti dal reset.
- **M18** non è più su `master` e non è mai finito su `origin/master`, che è ancora fermo a `9a1a903`. Non è stato pubblicato niente.
- **`task/m13a`** parte da `21db1fa` e non contiene M18, quindi misurerà il codice senza M18 come previsto.
- **`task/m20`** parte esattamente da `21db1fa` e ha i suoi 5 commit sopra. Non devo toccare niente.

`origin/master` è rimasto indietro di 6 commit rispetto al `master` locale (tra cui l'aggiunta di M20 nella roadmap), perché non hai ancora pushato. Non è un problema, ma lo dico nel caso tu te lo aspettassi già su GitHub.

L'ordine resta quello di prima: M13a, poi M18, poi M13b, e solo dopo M20.

## Utente 15:39

una volta mergiato m13a devo lanciare qualcosa?

## Agente 15:39

- 🔧 Bash: Read M13a roadmap and loadtest README on its branch

- 🔧 Bash: Check M13a worktree for RESULTS.md and runs

Sì, però va fatto **prima** di mergiare M13a, non dopo. Su `task/m13a` manca ancora `loadtest/RESULTS.md`, e nella sua worktree `loadtest/out/` contiene solo `smoke` e un `calls.jsonl` sparso. Secondo la roadmap M13a è completa solo quando lo scenario è stato eseguito e `RESULTS.md` ha la colonna "prima", anche se i numeri sono cattivi. Quei numeri vanno misurati sul codice senza M18, e il branch di M13a è l'unico posto dove oggi questa condizione è garantita.

**Su `task/m13a`, prima del merge** (dalla worktree `task-m13a`, tutto in locale con Docker, senza HofJ vero, Render o Stripe):

```sh
docker compose up -d --build
docker compose run --rm locust --travelers 1000  --label 1k
docker compose down -v
# ripetere up / run / down con --travelers 10000 --label 10k e --travelers 50000 --label 50k
```

Poi c'è il giro con i guasti, con i comandi della sezione dedicata in `loadtest/README.md`:

```sh
FAKE_HOFJ_LATENCY=pessimistic FAKE_HOFJ_FAULTS="…" docker compose up -d --build
docker compose run --rm locust --travelers 50000 --label 50k-guasti
docker compose down -v
```

La roadmap chiede anche le due finestre: il default `anchored` e `FAKE_HOFJ_WINDOW=rolling`, perché M13b le confronta entrambe.

Quanto dura:
- Ogni giro richiede circa 17-18 minuti: 1-2 di sync del catalogo, 10 di arrivi e 5 di coda.
- Tre taglie per due finestre, più il giro con i guasti, fanno circa 7 giri, cioè 2 ore abbondanti.

Con i report in `loadtest/out/<label>/` si compila `loadtest/RESULTS.md` e lo si committa. A quel punto M13a si può mergiare.

**Dopo il merge di M13a** non devi lanciare niente. Poi vengono:
1. il merge di M18;
2. M13b, che rilancia gli stessi giri senza cambiare lo scenario e compila la colonna "dopo";
3. M20: rimetto il branch sopra `master`, verifico che l'accept stia sotto il p95 di M13b e mergio.

Se vuoi, i giri di M13a li lancio io dalla sua worktree. Li avvio in background e ti avviso quando finiscono.

## Utente 19:19

ma è andata in prod?

## Agente 19:19

- 🔧 Bash: Check deploy branch and what's on origin

`origin/master` si è mosso da quando l'ho controllato poco fa: prima era `9a1a903`, ora è `7a01c59`. Vedo cosa contiene.

- 🔧 Bash: List what landed on origin/master and check M18/M13a/M20

- 🔧 Bash: Check M13b results and overlap with M20 files

**M20 no**: non è su `origin/master`, quindi non è in produzione. È solo sul branch locale `task/m20` e non l'ho mai pushato.

Su GitHub però `master` è andato avanti molto rispetto a quello che avevo visto prima. `origin/master` ora è `7a01c59`, pushato oggi alle 18:19, e contiene:
- **M13a**, poi **M18** (mergiato dopo M13a, quindi nell'ordine giusto);
- **M13b**: `loadtest/RESULTS.md` ha anche la colonna "dopo" (`17b3447`) e le decisioni del rilancio (`1c78e8d`);
- SMS con Twilio, landing page con ElevenLabs, la correzione della gara sui booking, ruff e il nuovo CLAUDE.md.

Se sia davvero **in produzione** non posso verificarlo da qui, perché non ho accesso a Render. `render.yaml` non indica un branch, quindi Render usa quello impostato nella dashboard, di solito `master` con deploy automatico. Se è così, tutto questo è online, ma M20 no. Puoi controllarlo nella sezione Events del servizio `vela` su Render.

Due conseguenze per M20:
1. **M13b è fatto, quindi M20 si può mergiare.** Il riferimento per l'ultimo test esiste: il p95 di `accept_proposal` nel giro più carico è 130 ms "dopo" (era 16 ms "prima").
2. **Il rebase avrà conflitti.** Il lavoro sugli SMS ha modificato gli stessi file di M20: `usecases.py`, `say.py`, `mcp.py` e la spec. Un commit si intitola "Tell the traveler the link arrives by SMS and stop the agent from polling", e questo si sovrappone al senso di M20. Con gli SMS attivi, conviene ancora aspettare il link nell'accept? E quale frase si dice?

Propongo di leggere prima cosa hanno cambiato gli SMS e poi farti una proposta su come combinarli con M20, prima di toccare il branch. Procedo?

## Utente 19:20

vai merge e push

## Agente 19:20

Prima faccio il rebase di `task/m20` su `origin/master`, come dicono le tue istruzioni globali, e risolvo i conflitti con gli SMS. Poi lancio i test, faccio il merge e il push.

- 🔧 Bash: Check status and master worktree

- 🔧 Bash: Back up branch and rebase onto origin/master

- 🔧 Bash: Show app.py conflict

- 🔧 Bash: Resolve app.py and show usecases conflict

- 🔧 Bash: Read SMS-aware say_queued and say_preparing

- 🔧 Bash: Resolve usecases conflict and make say_preparing SMS-aware

Sto risolvendo i conflitti del rebase. Ora aggiungo i test per la frase con l'SMS.

- 🔧 Bash: Read SMS say tests and usecase SMS tests

- 🔧 Bash: Add SMS preparing test and read SMS flow harness

- 🔧 Bash: Find SMS flow test classes

- 🔧 Bash: Add SMS accept-wait test and run suite

- 🔧 Bash: Show the failing test

- 🔧 Bash: Show rest of traceback

Resta un solo test rosso dopo il rebase. Sto leggendo il traceback completo.

- 🔧 Bash: Run failing test from tests dir

Il commit sul lint in `origin/master` ha tolto da `test_queue_flow.py` l'import di `replace`, allora inutilizzato; il mio test ora lo usa. Lo ripristino.

- 🔧 Bash: Show imports in test_queue_flow

- 🔧 Bash: Restore replace import, run tests and ruff

- 🔧 Bash: Continue the rebase

- 🔧 Bash: Show MCP description conflict

- 🔧 Bash: Read _ACCEPT and _STATES and test state

- 🔧 Bash: Resolve MCP conflict and show spec conflict

Risolvo il conflitto nella spec, poi rilancio i test e continuo il rebase.

- 🔧 Bash: Resolve spec conflicts and run tests and lint

- 🔧 Bash: Show failing test

- 🔧 Bash: Read the pre-SMS text test

Quel test fissa il testo senza SMS alla versione precedente, e M20 lo cambia apposta. Aggiorno la costante.

- 🔧 Bash: Update test, run suite, continue rebase

Il rebase è finito. Registro la decisione sulla frase con l'SMS e verifico tutto, anche con Postgres.

- 🔧 Bash: Record SMS decision and commit

- 🔧 Bash: Run full suite against Postgres and lint

Suite verde anche con Postgres e lint pulito. Controllo che `origin/master` non si sia mosso, poi faccio il merge nella worktree `master` e il push.

- 🔧 Bash: Verify origin/master and master worktree state

`origin/master` si è mosso di nuovo: è stato mergiato M21 (`27de0e0`). Rifaccio il rebase su quello.

- 🔧 Bash: See what M21 changed

C'è una novità che tocca M20: "Ask the traveler to confirm the actual price before the payment link". Controllo come funziona prima di fare il rebase.

- 🔧 Bash: Inspect price confirmation change

Su `master` c'è già un'attesa nell'accettazione, introdotta con la conferma del prezzo: fino a 100 s. Si sovrappone direttamente a M20. Leggo il codice.

- 🔧 Bash: Read master's accept_proposal with its wait

- 🔧 Bash: Check master decisions about accept wait and M20

Mi fermo qui: **non ho fatto né il merge né il push.** Mentre facevo il rebase, `origin/master` si è mosso di nuovo, a `27de0e0` (M21 e conferma del prezzo). Quel lavoro ha già implementato un'attesa nell'accettazione più ampia di M20 e con regole diverse da quelle decise per M20.

**Cosa c'è già su `master`** (decisione "L'agente non si sveglia", `docs/decisions.md` riga 894):
- `accept_proposal` attende **per ogni posizione in coda**, non solo la prima.
- Attende fino a **100 s** (`accept_wait_seconds = 100`), rileggendo l'ordine ogni 1 s (`accept_poll_seconds`).
- Il motivo: il server MCP è stateless e l'agente non si può risvegliare, quindi l'unica via è una chiamata che non risponde subito.
- La stessa attesa vale anche alla conferma del prezzo (nuovo stato `awaiting_confirmation`).

Se rimettessi sopra M20 com'è (10 s, solo posizione 1, 0,5 s), romperei quel flusso: chi non è primo in coda non sentirebbe mai il prezzo effettivo nella stessa chiamata. Il campo si chiama perfino uguale, `accept_wait_seconds`, con default 10 contro 100.

**Opzioni**
1. **Non mergiare M20: segnarla come superata** (consigliata). In roadmap e in `decisions.md` scrivo che la conferma del prezzo ha assorbito M20, con il rimando alla riga 894. `task/m20` resta come archivio.
   - È la scelta più sicura: la decisione più recente è tua e copre già il caso.
2. **Mergiare solo quello che manca a `master`**, adattato al suo comportamento:
   - i test su sostituzione, fallimento e doppio accept durante l'attesa;
   - la risposta REST 200 con il link;
   - le correzioni alla spec (RNF-04).
   - Nessun cambio di comportamento: prima verifico cosa copre già `master`. Costo: circa 1 h.
3. **Imporre le regole di M20** (10 s, solo posizione 1). Non la consiglio: contraddice la decisione più recente e rompe la conferma del prezzo.

**Stato attuale**
- `task/m20` contiene M20 già rimesso sopra `7a01c59` (con gli SMS risolti e i test verdi, anche su Postgres), ma non ancora sopra `27de0e0`. È solo in locale.
- Il vecchio stato del branch, prima del rebase, è salvato in `backup/task-m20-pre-rebase`.
- `master` e `origin` non sono stati toccati.

Quale scegli?

## Utente 12:22

procedi solo con    - i test su sostituzione, fallimento e doppio accept durante l'attesa;
   - la risposta REST 200 con il link;
   - le correzioni alla spec (RNF-04).

## Agente 12:22

Creo un branch nuovo da `origin/master` (`task/m20-tests`) invece di riscrivere `task/m20`, così quel branch resta com'è. Poi controllo cosa copre già `master`.

- 🔧 Bash: Create new branch from origin/master and inspect wait tests

- 🔧 Bash: Find existing tests of the accept wait

- 🔧 Bash: Read existing accept-wait tests on master

- 🔧 Bash: Read test harness for accept wait

`master` copre già l'attesa del prezzo, la conferma che restituisce il link e il tetto. Mancano sostituzione, fallimento e doppio accept durante l'attesa. Controllo la parte REST e RNF-04.

- 🔧 Bash: Read REST end-to-end test, spec RNF-04, REST docs

- 🔧 Bash: Read master's RNF-04, RNF-05, RF-45 and Vela defaults

Su `master` RNF-04 dice ancora "Nessun caso d'uso aspetta HofJ", ma ora l'accettazione aspetta il job fino a 100 s: è quella la frase da correggere. Scrivo i tre test nel dominio.

- 🔧 Bash: Check imports and FakeHofJ API

- 🔧 Bash: Add replacement, failure and double-accept wait tests

I test passano subito, com'è giusto: fissano un comportamento che `master` ha già. Ora il test REST.

- 🔧 Bash: Add REST 200-with-link test

Ora RNF-04 nella spec.

- 🔧 Bash: Update RNF-04 in spec

Per il CLAUDE.md registro anche la decisione: M20 è assorbita dalla conferma del prezzo e da lei restano solo test e spec. Aggiungo una nota in roadmap.

- 🔧 Bash: Check decisions layout and M20 header

- 🔧 Bash: Record decision, roadmap note; run tests and lint

Faccio due commit: uno per i test, uno per la documentazione.

- 🔧 Bash: Commit tests and docs
