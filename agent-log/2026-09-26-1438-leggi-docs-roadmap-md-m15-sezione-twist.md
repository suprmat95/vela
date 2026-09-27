# ARCHITECTURE.md draft

- Sessione: `98c26ba5-70cf-45fd-bbeb-5dc3ab81dbbc`
- Inizio: 2026-09-26 14:38

## Utente 14:38

Leggi docs/roadmap.md M15 (sezione twist) e docs/plans/2026-09-26-twist-seconda-lettura.md sezioni 3-7. Scrivi la bozza di ARCHITECTURE.md; al posto dei numeri del load test metti "[numeri da M13b]". Solo documenti, non mergiare finché M13b non è su master.

## Agente 14:38

- 🔧 Bash: List docs and locate roadmap sections

- 🔧 Bash: Read M15 section and search for twist plan

- 🔧 Bash: Locate the twist plan commit and M13b status

- 🔧 Bash: Read master's M15 and plan outline

- 🔧 Bash: Read plan sections 1, 3-7 and 9

Ho letto il materiale; controllo al volo lo stato del branch rispetto a master prima di proporti l'approccio.

- 🔧 Bash: Compare branch with master and check load test results

Ho letto M15 e le sezioni 3-7 del piano. Il progetto chiede di proporre l'approccio e aspettare il tuo OK, quindi non ho ancora scritto niente.

**Una cosa da sapere prima.** `doc/architecture` è indietro di 6 commit rispetto a `master` e non ha commit suoi. Il piano `docs/plans/2026-09-26-twist-seconda-lettura.md` e la sezione twist di M15 esistono solo su `master`. Qui c'è ancora la versione vecchia di M15, senza la parte twist. Ho letto entrambi i file con `git show master:…`. Nemmeno `loadtest/RESULTS.md` esiste ancora: c'è solo `.gitkeep`. Quindi mancano i numeri sia di M13a sia di M13b.

**Approccio proposto**

1. **Branch:** fast-forward di `doc/architecture` su `master` (`git merge --ff-only master`). Non riscrive la storia e non crea merge commit, visto che il branch non ha commit suoi.
2. **`ARCHITECTURE.md` nella root**, in italiano come gli altri documenti. Scheletro seguendo M15:
   - Panoramica, decisioni e compromessi (da `docs/decisions.md`), vincoli del prototipo (RF-13), prossimi passi: A2A (RF-44), email del codice (RF-26), OAuth per REST.
   - **Sezione twist** con le 5 richieste del brief:
     - (1) architettura e diff nel pensiero: i tre momenti e la tabella, dalla §4;
     - (2) budget di quota e cosa si sacrifica per primo, dalla §5;
     - (3) cosa degrada e cosa no, con il minuto sei visto da Marco e Anna, dalla §6;
     - (4) upsert idempotente di `POST /v1/bookings`, i tre punti in cui ci contiamo con riferimento a `BookingJob.run`, e il caso non idempotente di `POST /v1/itineraries`, dalla §3.3;
     - (5) load test: il confine da dimostrare (§3.5), con **"[numeri da M13b]"** al posto dei numeri.
   - Precedenti documentati (§7), più la §3.7 (l'ipotesi sbagliata e corretta) come parte del diff.
3. **Convenzioni del piano:** tengo i marcatori [misurato] / [previsto] / [proposta]. Le previsioni (deriva della §3.1, circa 12 acquisti/min della §3.2) restano marcate "da confermare con il load test". Le correzioni di M18 e M19 restano "proposta", non fatti.
4. **Verifiche:** controllo nel codice di `master` i riferimenti citati (`BookingJob.run`, `job_lease_seconds`, `TIMEOUT_SECONDS`, `rolled()`), così il documento non riporta nomi sbagliati. Nessuna chiamata esterna, nessun cambio di codice. Alla fine lancio la suite di test.
5. **Git:** commit piccoli, una voce in `docs/decisions.md` e push del branch. Niente merge su `master` finché M13b non è lì.

**Due cose da decidere:**

- **Numeri "prima" (M13a):** anche questi non esistono ancora. Propongo di usare "[numeri da M13a]" per la colonna "prima" e "[numeri da M13b]" per la colonna "dopo". Vuoi invece un solo segnaposto "[numeri da M13b]" per entrambe?
- **Solo la sezione twist o tutto il documento?** Consiglio tutto lo scheletro di M15, con la sezione twist completa e le altre sezioni scritte dalle fonti che hai indicato (decisions.md, spec). Se preferisci limitarmi a quello che mi hai fatto leggere, scrivo solo la sezione twist e lascio le altre come intestazioni vuote.

Procedo così?

## Utente 14:40

si

## Agente 14:40

- 🔧 Bash: Fast-forward branch to master

- 🔧 Bash: Read brief and decisions outline

- 🔧 Bash: Read decisions: architecture, twist, M2-M6

- 🔧 Bash: Read decisions M9 through twist second reading

- 🔧 Bash: Read M5, payment, M7, contract, M10 decisions

- 🔧 Bash: Read accept-wait and twist second reading decisions, plan §2

Ho letto le decisioni. Ora leggo spec (§9, §10, RF-13/26/44) e M13a/M13b/M18/M19, poi verifico i riferimenti nel codice.

- 🔧 Bash: Outline spec and locate requirements

- 🔧 Bash: Read spec sections 1-2 and 4.10

- 🔧 Bash: Read spec sections 5-10

- 🔧 Bash: Read roadmap graph, M13a/b, M18-M20

Ora verifico i riferimenti nel codice.

- 🔧 Bash: Verify code references cited in the plan

- 🔧 Bash: Read BookingJob, rolled() and booking job enqueue

- 🔧 Bash: Check booking job enqueue for race protection

- 🔧 Bash: Verify purchase job retry and app modes

- 🔧 Bash: Read RF-13 and check OAuth and HofJ questions

- 🔧 Bash: Read remaining traveler defaults

Riferimenti verificati nel codice (tutti corretti; il punto 3 della §3.3 del piano ora è confermato dalla lettura). Scrivo `ARCHITECTURE.md`.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/doc-architecture/ARCHITECTURE.md

- 🔧 Bash: Check HofJ question numbering

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/doc-architecture/ARCHITECTURE.md

- 🔧 Bash: Check tests touching docs and run suite

Suite verde. Aggiungo la voce in `docs/decisions.md` e faccio i commit.

- 🔧 Bash: Append decision entry and commit

- 🔧 Bash: Show committed files and push the branch

La bozza di `ARCHITECTURE.md` è nel branch `doc/architecture`, pubblicato su origin. Non ho fatto merge né aperto una PR: si aspetta M13b.

**Cosa ho fatto**
- Ho allineato il branch a `master` con un fast-forward: senza, piano e sezione twist di M15 non c'erano. Nessuna storia riscritta.
- Ho scritto `ARCHITECTURE.md` con tutte le parti chieste da M15:
  - panoramica e forma del sistema, con il percorso di un acquisto;
  - decisioni e compromessi;
  - vincoli del prototipo, con i valori di default di RF-13 presi dal codice;
  - la sezione twist, con le 5 richieste (§5.1-5.5), l'ipotesi sbagliata e corretta, e i precedenti (§5.6);
  - prossimi passi: A2A, email del codice, OAuth per REST, seconda chiave, M19, domande a HofJ.
- La tabella del load test ha "[numeri da M13a]" nella colonna "prima" e "[numeri da M13b]" nella colonna "dopo". Al posto dei comandi di lancio c'è "[comandi da `loadtest/README.md`, M13a]".
- Ho tenuto le etichette [misurato] / [previsto] / [proposta]: le correzioni di M18 e M19 restano proposte, non fatti.
- Ho aggiunto una voce in `docs/decisions.md` e fatto due commit (l'agent-log è stato generato dall'hook). La suite di test passa: 916 test, 47 saltati.

**Da sapere**
- **Il punto 3 della §3.3 del piano ora è confermato dal codice.** Prima del job di prenotazione, `_enqueue_booking` (`vela/domain/orders.py`) controlla se ne esiste già uno e poi accoda. Non c'è né un lock né un vincolo unico sulla tabella `jobs`, quindi due verifiche di pagamento contemporanee possono creare due job. L'ho letto nel codice, non l'ho riprodotto. L'upsert di HofJ rende innocua la seconda `POST`, ma potrebbe valere la pena aggiungerlo allo scope di M18.
- **Il mapping degli stati A2A l'ho proposto io**, perché non era nei documenti: per esempio link da pagare → `input-required`, `confirmed` → `completed`. È marcato "[proposta, da confermare]": dimmi se lo tieni.
- Il brief non contiene la sezione "The twist" citata da M15. Il testo del twist l'ho preso dalla §1 del piano.
- Il documento è in italiano come il resto di `docs/`. I valutatori però sono anglofoni: forse per la consegna serve una versione inglese.

Quando M13b è su `master` restano da fare: riempire la tabella, inserire i comandi di lancio, togliere la riga "bozza", rebase su `origin/develop` e PR.

## Utente 19:11

riallineati con il master

## Agente 19:11

- 🔧 Bash: Fetch and compare branch with master

- 🔧 Bash: Inspect new master commits and overlapping files

Il branch è già su origin, quindi un rebase richiederebbe un force push, che le regole del progetto vietano senza chiedere. Faccio un merge di `master` nel branch, come per `task/21f`.

- 🔧 Bash: Merge master into the branch without committing

- 🔧 Bash: Inspect local changes and master history of log files

- 🔧 Bash: Check how master touches this session's log files

Le modifiche locali sono gli agent-log di questa sessione, aggiornati dall'hook. Li metto da parte con uno stash con etichetta, faccio il merge e poi li ripristino.

- 🔧 Bash: Set aside agent-log changes and start the merge

- 🔧 Bash: Locate conflict markers in decisions log

- 🔧 Bash: Resolve conflict keeping both sides, ours last

Conflitto risolto: entrambe le parti tenute, la mia voce in fondo. Chiudo il merge dopo test e lint.

- 🔧 Bash: Run test suite and lint on merged tree
