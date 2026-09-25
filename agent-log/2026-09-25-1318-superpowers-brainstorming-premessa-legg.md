# vela-roadmap-macrotasks

- Sessione: `6b6beb49-0ac2-4826-a91d-760234d3341e`
- Inizio: 2026-09-25 13:18

## Utente 13:18

❯ /superpowers:brainstorming Premessa: leggi tutti i file in docs, soprattutto spec.m Obiettivo: Dobbiamo suddividere questo progetto in macro task. Intervistami per capire come intendo farlo, chiedi sempre quando hai un dubbio. Vincoli: 1) le macro task verranno lanciate con superpowers da cui poi verrà generato un piano con microtask 2) Le macro task devono essere umanamente comprensibili 3) dovrai indicare le dipendenze di ogni task e quali possono essere svolte in worktree paralleli 4) intendo dare priorità al raggiungimento di un prototipo funzionante con mcp claude, il prima possibile in modo da testare subito 5) per ogni macrotask indica i test che verificano il corretto completamento. Valutiamo l'ingestion completa e il raffinamento della scelta del prodotto solo in seguito Stop: Verifica che tutti i requisiti sono soddisfatti dalle macrotask.

## Agente 13:18

Using superpowers:brainstorming to run the interview before proposing anything.

- 🔧 Skill superpowers:brainstorming

Questa è una richiesta **architetturale**: decomposizione di un progetto nuovo in macro task. Seguo il percorso completo: prima leggo tutti i docs, poi ti intervisto una domanda alla volta.

- 🔧 Bash: List repository files and doc sizes

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/spec.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/brief.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/decisions.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/agents-log.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/README.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/differences.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/counts.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/products.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/recommendations.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/quota-health.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-roadmap/docs/api/internal-checkout.md

- 🔧 AskUserQuestion

Bene: macro task 1 = replay end-to-end. Seconda domanda: da dove chiami l'MCP, perché cambia se il deploy su Render deve venire prima o dopo il prototipo.

- 🔧 AskUserQuestion

Deploy su Render entra quindi nella prima macro task. Terza domanda: il database in locale, perché la spec impone Postgres ma non dice come lo usi nei test e in sviluppo.

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

Restano tre dubbi indipendenti, poi propongo la decomposizione.

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

Ho tutte le decisioni. Scrivo ora il piano completo con la roadmap nel file di piano, poi te lo sottopongo per approvazione.

- 🔧 Write /Users/matteodospina/.claude/plans/superpowers-brainstorming-premessa-legg-cached-quill.md

- 🔧 ToolSearch

- 🔧 ExitPlanMode

Piano approvato. Scrivo ora `docs/roadmap.md`, la sezione in `docs/decisions.md` e i due ritocchi a `docs/spec.md`, poi verifico e committo.

- 🔧 Bash: Generate docs/roadmap.md from the approved plan body

- 🔧 Bash: Write decisions and spec updates, verify matrix coverage and dependency graph, run tests

- 🔧 Bash: Check RNF coverage in matrix and commit the roadmap

Fatto. La roadmap è scritta, verificata e committata sul branch `doc/roadmap` (commit `3c7d152`, con l'agent-log della sessione aggiunto dall'hook).

**Cosa ho scritto**
- `docs/roadmap.md`: 16 macro task (M0-M15, più M16 A2A opzionale) in 7 ondate. Per ognuna: risultato, scope, test di completamento, requisiti coperti e un prompt pronto da incollare in `/superpowers:brainstorming`. In testa il grafo delle dipendenze e la tabella di parallelismo per worktree; in coda la matrice requisiti → task.
- `docs/decisions.md`: sezione "Roadmap in macro task" con le 11 decisioni dell'intervista.
- `docs/spec.md`: RF-43 riscritto (OAuth 2.1 su MCP, token statico per ElevenLabs, ponte senza auth fino a M8) e RNF-09 esteso (test Postgres saltati senza `DATABASE_URL`).

**Verifiche eseguite**
- Tutti i 44 RF e gli 11 RNF della spec compaiono nella matrice, più §6, §8, §9 e i 7 criteri di §10.
- Il grafo delle dipendenze non ha cicli e ogni dipendenza citata esiste.
- La suite `unittest` esistente resta verde (32 test).

**I due traguardi**
- Traguardo A, prototipo replay su Render testato da claude.ai: M0 ‖ M1 → M2 → M3.
- Traguardo B, prima prenotazione reale: M4, M5 ‖ M6 ‖ M8 → M7.

**Cosa sono meno sicuro e ho lasciato al brainstorm della singola task**
- M6: Payment Link contro Checkout Session con `expires_at`, perché i Payment Link non scadono da soli come chiede RF-21.
- M8: la pagina minima di consenso OAuth è l'unica pagina web di Vela oltre a Stripe; va confermato che non contraddica il vincolo "nessuna interfaccia propria".
- M8: che i connector custom di claude.ai richiedano davvero OAuth o nessuna auth; M3 lo verifica di fatto con `/mcp` aperto.

**Prossimo passo**: lanciare M0 e M1 in due worktree con i prompt di `docs/roadmap.md`.

## Utente 13:55

ok mergia in master

## Agente 13:55

Verifico lo stato di `master` e come sono stati fatti i merge precedenti prima di procedere.

- 🔧 Bash: Show worktrees, master history and whether a fast-forward is possible

- 🔧 Bash: Merge doc/roadmap into master in the main checkout with a merge commit, if its tree is clean

Merge fatto su `master` nel checkout principale, con merge commit come per i branch precedenti.

- Commit di merge: `10ba4eb Merge branch 'doc/roadmap'`.
- Contenuto: `docs/roadmap.md`, la sezione in `docs/decisions.md`, i ritocchi a `docs/spec.md` e l'agent-log della sessione.
- Il working tree di `master` era pulito prima del merge; nessun conflitto.

Non ho fatto push né cancellato il branch `doc/roadmap`, come da regole del repo. Il worktree `doc-roadmap` resta disponibile finché non lo rimuovi.

## Utente 16:52

/superpowers:brainstorming: abbiamo ricevuto il twist: Il contenuto del twist: "Vela ha appena chiuso un accordo di distribuzione"

La mattina del lancio il tuo agente riceve 50.000 viaggiatori in una finestra di dieci minuti. Non distribuiti nella giornata: dieci minuti. Tra te e quel traguardo ci sono i vincoli su cui stai già lavorando da stamattina:

- La API HOFJ impone una quota per client su finestra mobile di 60 secondi, senza header Retry-After né RateLimit-*. GET /v1/quota è l'unico modo per sapere a che punto sei, e interrogarlo consuma budget.
- Le chiamate upstream vanno in timeout a 15 secondi.
- La ricerca alloggi, inevitabile nel flusso d'acquisto, richiede da due a sei secondi perché interroga la disponibilità live.
- Nonostante tutto, il prototipo deve comunque concludere una prenotazione al minuto sei. Obiettivo: per come è stata progettata l'infrastruttura è in grado di reggere?

## Agente 16:54

Classifico: è uno **spike**. La domanda è di fattibilità e l'output è un'analisi, non codice. La sonda è un calcolo sulla carta contro `docs/spec.md`, `docs/api/quota-health.md` e la roadmap, senza chiamate esterne. Se il verdetto è "non regge", il seguito è architetturale: modifiche a spec e roadmap, con la tua approvazione.

Ho fatto subito il calcolo, perché non costa nulla.

**I numeri del design attuale**

| Grandezza | Valore | Origine |
|---|---|---|
| Quota HofJ osservata | 120 chiamate/min per client | `docs/api/quota-health.md` |
| Chiamate HofJ per acquisto | 6: itinerario, cliente, pax ×2, lettura totale, booking | RF-14, RF-16, RF-23 |
| Acquisti completabili | 20 al minuto, 200 in dieci minuti | 120 / 6 |
| Chiamate HofJ per conversazione | 0: intento, proposta, rifiuto leggono solo il catalogo locale | RF-11 |
| Traffico conversazionale | ~83 viaggiatori/s, ~300 richieste/s a Vela | 50.000 / 600 s × 3-4 chiamate |
| Latenza seriale di un acquisto | 10-30 s (5 chiamate a 2-6 s l'una) | vincolo del twist |

**Verdetto: regge la conversazione, non regge l'acquisto così com'è.**

- **Lo strato conversazionale regge.** Il design tiene intento, proposta e rifiuto fuori da HofJ. Con processo stateless (RNF-01) e stato in Postgres, si scala aggiungendo istanze su Render. Trecento richieste al secondo con un catalogo di 92 prodotti sono gestibili se il chooser lavora su una copia in memoria e Postgres riceve solo scritture, con un pool di connessioni per istanza.
- **Lo strato d'acquisto è murato dalla quota.** Venti acquisti al minuto è un tetto fisico del client HofJ. Nessuna scelta nostra lo alza. Se anche solo il 2% dei 50.000 accetta, sono 1.000 acquisti contro 200 possibili: gli ultimi aspettano 40 minuti. Al 10% aspettano quattro ore.
- **Il punto debole è RF-37.** Oggi, a quota esaurita, `accept_proposal` fallisce con "riprovo tra un minuto". Con mille agenti che ritentano ogni minuto, l'80% fallisce a ogni finestra e i tentativi si accumulano. Il design trasforma il sovraccarico in errori, non in attesa.
- **RNF-04 non tiene.** Cinque chiamate seriali a 2-6 s superano i 30 s di risposta sincrona nei casi peggiori, prima ancora di contare la quota.
- **La prenotazione al minuto sei è raggiungibile** solo se il guardiano riserva a ogni finestra una fetta per le chiamate di booking degli ordini già pagati e nessun sync gira durante il lancio. Il design attuale distingue urgente da non urgente, ma non dà priorità ai booking sugli itinerari.
- **Due rischi secondari.** Il fallback Haiku (RF-03) a 83 intenti/s finisce nei rate limit di Anthropic e va spento o protetto da un interruttore. Le sessioni MCP Streamable HTTP devono essere stateless, altrimenti la scalabilità orizzontale si rompe al primo bilanciamento.

**Cosa cambierebbe nel design**

1. L'accettazione diventa asincrona: risponde subito con stato `queued`, posizione e attesa stimata, e una frase `say` onesta ("ti mando il link tra circa dodici minuti"). Il link arriva tramite `get_order_status`.
2. Un solo scheduler della quota per tutto il cluster, in Postgres, con tre classi di priorità: booking di ordini pagati, itinerari in coda, sync. Riserva per finestra ai booking.
3. Attesa stimata calcolata da lunghezza coda e ritmo (20/min), così l'agente non ritenta a vuoto.
4. Nell'accordo di distribuzione: quota più alta o più client HofJ. Con N client lo scheduler distribuisce i lavori su N budget, senza cambiare il dominio.

Questo tocca RF-37, RNF-04, gli stati di RF-25 e la macro task M5 della roadmap. Prima di scrivere qualcosa, una domanda sulla direzione.

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

Ho quello che serve. Due note sulle scelte appena fatte, poi le alternative e il design.

- **Sempre asincrono** cambia il criterio §10.1: al "sì" l'agente riceve stato `queued` e attesa, poi interroga `get_order_status` per leggere il link. Le descrizioni dei tool MCP devono dirlo esplicitamente.
- **Nessun tetto** implica che la rinuncia esista: un rifiuto sull'ordine in coda lo cancella.

**Tre modi per fare coda e scheduler**

- **A. Coda in Postgres, worker in ogni istanza (raccomandato).** Tabella `jobs` presa con `SELECT … FOR UPDATE SKIP LOCKED`, contatore di quota per finestra in Postgres con prenotazione atomica di blocchi di chiamate. Nessun servizio nuovo, coerente con la variante A già decisa, scala con le istanze, sopravvive a un crash. Costo: il contatore condiviso è un punto di contesa, ma a 120 chiamate al minuto è irrilevante.
- **B. Coda esterna (Redis o Celery) e worker separato.** Strumenti nati per questo, ma un secondo servizio da deployare e un secondo processo: contraddice la decisione "un processo" del 2026-09-25.
- **C. Un solo drenatore eletto con advisory lock.** Contabilità della quota banale perché la fa un solo processo. Costo: nessuna alta disponibilità durante il cambio di leader, e la ripresa al boot va comunque persistita in Postgres.

**Design, assumendo A**

1. **Accettazione.** `accept_proposal` valida i dati, crea l'ordine in `queued` con posizione e attesa stimata, risponde in meno di 500 ms senza toccare HofJ. `say` dichiara l'attesa in minuti per eccesso.
2. **Job d'acquisto.** Un job per ordine: itinerario, cliente, pax, totale reale, link Stripe. Ogni passo salva il proprio esito, così un crash riprende dal passo successivo senza ricreare itinerari. Timeout 15 s per chiamata, tre tentativi per passo; poi ordine `failed` con motivo leggibile.
3. **Scheduler della quota.** Sostituisce il guardiano di RF-36..38. Un contatore per finestra in Postgres, tre classi in ordine di priorità: `booking` (ordini pagati, riserva garantita del 20% della finestra), `purchase` (il resto, FIFO), `sync` (solo a coda vuota e sopra la soglia). Un job prenota il suo blocco di chiamate in modo atomico oppure aspetta la finestra successiva. Un 429 azzera il budget residuo della finestra. `/v1/quota` si chiama al boot e dopo un 429, mai in ciclo.
4. **Attesa stimata.** Posizione × 60 s ÷ acquisti per finestra, con acquisti per finestra = (limite − riserva) ÷ 5. Ricalcolata a ogni `get_order_status`.
5. **Sostituzione in coda.** Se l'itinerario fallisce per il prodotto, il job marca il prodotto, calcola la proposta sostitutiva e mette l'ordine in `replaced`. `get_order_status` restituisce la nuova proposta con il flag; un nuovo `accept_proposal` rientra in testa alla coda. Il viaggiatore riacconsente perché prezzo e hotel cambiano.
6. **Rinuncia.** `reject_proposal` su un ordine `queued` lo porta a `cancelled` e restituisce la proposta successiva come oggi.
7. **Stati ordine.** `queued`, `awaiting_payment`, `paid_pending_booking`, `confirmed`, `replaced`, `cancelled`, `failed`, `booking_failed`, `expired`.
8. **Degradazione sotto carico.** Fallback Haiku con interruttore a concorrenza limitata, oltre il quale si pone la domanda di RF-04. MCP stateless, senza sessioni in memoria. Catalogo in memoria per istanza, ricaricato ogni minuto.
9. **Load test.** Nuovo scenario "twist": 50.000 viaggiatori in dieci minuti in replay, con HofJ finto che simula latenza 2-6 s e quota 120 al minuto. Misure: p95 delle chiamate locali, acquisti al minuto, attesa stimata contro reale, primo booking entro 60 s dal pagamento simulato, zero errori di quota.
10. **Dove finisce.** Nuova sezione 4.10 della spec, ritocchi a RF-17, RF-25, RF-37, RNF-04, RNF-10 e §10.1; roadmap: M2 prende stati e coda con porte finte, M5 prende scheduler e worker reali, M13 lo scenario twist; decisioni registrate.

- 🔧 AskUserQuestion

- 🔧 Bash: Show master history, tree and roadmap table to see what M2 produced

- 🔧 Bash: Inspect M2's domain: order states, ports, accept use case, background worker, and doc diffs since the roadmap

- 🔧 Bash: Create branch doc/twist-scale from master and apply the twist changes to docs/spec.md

Spec aggiornata. Ora la roadmap (M5, M6, M13 e nota in testa) e le decisioni.

- 🔧 Bash: Update roadmap M3/M5/M6/M9/M13/M14 and matrix, append twist decisions, verify coverage and tests

- 🔧 Bash: Identify why tests fail in this worktree (likely missing dependencies)

- 🔧 Bash: Run the test suite with the project's Python 3.12 venv
