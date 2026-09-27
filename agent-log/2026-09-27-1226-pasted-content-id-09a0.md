# hotel-selection-dynamic-degradation

- Sessione: `28804719-2f61-41df-9d9d-3d8c120e5e43`
- Inizio: 2026-09-27 12:26

## Utente 12:26

<pasted_content id="09a0">
/superpowers:brainstorming

Task M22-a: scelta dell'hotel con degrado dinamico, parte documentale e sonda su HofJ.
Worktree dedicato, branch doc/m22-hotel da master aggiornato. Niente codice in vela/.

## Contesto
Oggi RF-15 dice che Vela accetta sempre l'hotel di default e il §7 della spec esclude la scelta
dell'hotel. Voglio cambiarlo: il viaggiatore può chiedere un hotel diverso quando non c'è coda;
quando c'è coda la scelta viene sacrificata e si tiene l'hotel di default, dicendolo.
M22 si implementa DOPO M21-D (camere: orders.rooms, create_itinerary con rooms) e M21-F
(classificazione dei rifiuti, tipo `hotel`, RF-71/72): M22 è un ramo del rifiuto `hotel`.
Leggi docs/spec.md (RF-15, §4.8, §4.10, §4.12 RF-65..75, §7), docs/usecases/scelta.md (UC-D,
UC-F), docs/roadmap.md (M21), docs/decisions.md ("Twist, seconda lettura", "M18",
"Prezzo effettivo prima del link"), docs/api/internal-checkout.md (accommodations),
docs/easter-eggs.md (chiave 4), vela/domain/quota.py.

## Vincoli non negoziabili
1. Mai una lista tra cui scegliere (premessa del brief). Il viaggiatore esprime una preferenza
   (più vicino al campo, più economico, più stelle, recensioni migliori) e Vela propone UN solo
   hotel alternativo, con la motivazione. Mai elencare gli hotel di /accommodations.
2. Priorità della quota: booking > purchase > hotel > sync.
   - booking (ordini pagati) resta sopra a tutto.
   - purchase ha precedenza ASSOLUTA su hotel e sync: con anche un solo job d'acquisto in
     attesa, hotel e sync non prendono gettoni.
   - hotel prende gettoni solo se nessun acquisto è in attesa E il bucket concede subito tutte
     le chiamate del cambio (mai un cambio lasciato a metà per mancanza di gettoni).
   - sync è l'ultimo, cede il passo anche a hotel. Rischio accettato: catalogo oltre 6 h se i
     cambi hotel sono continui a coda vuota (coperto da RF-17/RF-33). Nessun tetto di età.
3. La proposta resta a 0 chiamate HofJ; la latenza di /accommodations non entra mai nella
   conversazione (tutto in coda, come gli acquisti).
4. Solo prodotti con hotelSelection o allowAccommodationList; per gli altri l'hotel è fisso e
   Vela lo dice.

## Flusso da mettere nella bozza (verificalo e proponi alternative)
- Momento: ordine in `awaiting_confirmation` ("il totale è X con l'hotel Y").
- Il viaggiatore rifiuta per l'hotel → reject_proposal con reject_kind `hotel` (tipo di M21-F)
  più una preferenza sull'hotel (campo nuovo, da definire). Ramo nuovo di RF-72:
  a) ordine in awaiting_confirmation + prodotto che permette la scelta + nessun acquisto in
     attesa → job `hotel_change` (classe quota `hotel`): GET /v1/itineraries/{id}/accommodations
     con i filtri della preferenza, scelta di UN hotel, PATCH
     /v1/itineraries/{id}/accommodations/{accommodationId} con i roomIds per orders.rooms,
     rilettura del totale → di nuovo awaiting_confirmation con nuovo hotel e nuovo totale;
  b) coda non vuota → zero chiamate, say onesto ("adesso non posso cambiare hotel, ti tengo
     quello incluso: il totale resta X"), l'ordine resta in conferma;
  c) prodotto con hotel fisso, oppure ordine non ancora in conferma → comportamento RF-72 di
     M21-F (altro prodotto, escluso quell'hotel). Da confermare con me.
- Nessun tool MCP nuovo. Migrazione 0014 (dopo 0010-0013 di M21) per tipo di job, classe di
  quota ed eventuali campi hotel sull'ordine: solo proposta, da approvare in M22-b.

## Fasi (fermati a ogni fase per il mio OK)
1. Bozza in docs/plans/2026-09-27-m22-hotel.md, NON in docs/spec.md (ogni task di M21 la
   modifica): requisiti nuovi (testo di RF-15 riscritto, voce del §7 da togliere, RF-76 e
   seguenti), casi d'uso con dialoghi di esempio in it/en, bilancio della quota (cambio
   hotel ≈ 3 chiamate, solo a coda vuota), nuovo ordine di sacrificio (catalogo → scelta
   dell'hotel → attesa del link → mai le prenotazioni pagate), domande aperte con opzioni e
   raccomandazione. Aggiungi la riga M22 (a e b) a docs/roadmap.md e le decisioni accettate
   a docs/decisions.md.
2. Sonda su HofJ staging, script in scripts/ (modello: scripts/quota_probe.py). Prima dimmi
   quali chiamate e quante (stima 6-8, nessun pagamento, rispetta il limite di quota). Da
   scoprire: latenza reale di /accommodations (almeno 2 misure), formato e risposta del PATCH
   (roomIds per 2 persone in 1 camera, e se possibile in 2 camere), se il totale
   dell'itinerario cambia dopo il PATCH, cosa risponde un prodotto con hotelSelection=false.
   Risultati in docs/api/accommodations.md, differenze nuove in docs/api/differences.md.
3. Verdetto: M22-b si fa o no (se il PATCH non è affidabile, M22 si chiude qui con la
   motivazione in decisions.md). Prepara anche il testo per ARCHITECTURE.md §5.2 e §5.3 in
   entrambi i casi.
</pasted_content id="09a0">

## Agente 12:26

- 🔧 Skill superpowers:brainstorming

- 🔧 Bash: Inspect branch state and doc sizes

- 🔧 Bash: Map spec sections and hotel mentions

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m22-a/docs/spec.md

- 🔧 Bash: Read API notes, easter eggs, quota code, probe script

Sto leggendo i documenti indicati (spec fatto, ora API interne, quota e sonda) prima di proporre la bozza.

- 🔧 Bash: Extract accommodations notes and easter egg key 4

- 🔧 Bash: Read quota module, probe script, differences doc

- 🔧 Bash: Check hotelSelection flags in fixtures and docs

- 🔧 Bash: List headings in decisions, roadmap, scelta

- 🔧 Bash: Read the referenced decisions

- 🔧 Read /Users/matteodospina/.claude/projects/-Users-matteodospina-orca-workspaces-vela-task-m22-a/28804719-2f61-41df-9d9d-3d8c120e5e43/tool-results/b2pkvksrl.txt

Letto il budget di quota e le decisioni; ora UC-D/UC-F e la roadmap M21.

- 🔧 Bash: Read UC-D, UC-F and roadmap M21

- 🔧 Bash: Check quota classes, job types, architecture doc

- 🔧 Bash: Check jobs schema and ARCHITECTURE references

- 🔧 Bash: Read M15 scope and order model fields

- 🔧 Write /Users/matteodospina/.claude/plans/pasted-content-id-09a0-superpowers-brai-tender-wozniak.md

- 🔧 ToolSearch

- 🔧 ExitPlanMode

- 🔧 Bash: Create doc/m22-hotel from updated master

- 🔧 Bash: Unset upstream; read plan style and say/usecases hooks

- 🔧 Bash: Inspect HofJ port and purchase steps

- 🔧 Bash: Check how the link amount is sourced

- 🔧 Bash: Read roadmap matrix and an example section

Branch `doc/m22-hotel` creato da master aggiornato. Ora scrivo la bozza M22 in `docs/plans/`.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m22-a/docs/plans/2026-09-27-m22-hotel.md

- 🔧 Bash: Fix typos and an inconsistent sentence in the draft

- 🔧 Bash: Add M22 rows, section and matrix to roadmap

- 🔧 Bash: Append M22-a decisions; run lint and tests

- 🔧 Bash: Commit the three doc changes separately

La fase 1 è pronta sul branch `doc/m22-hotel`, creato da `origin/master` aggiornato e con l'upstream staccato, così un push non può finire su master. Ho fatto tre commit e nessun push. Lint e test sono verdi: 1209 test, 63 saltati perché manca `DATABASE_URL`.

## Cosa ho fatto
- **`docs/plans/2026-09-27-m22-hotel.md`**: contiene:
  - il nuovo testo di RF-15 e la voce di §7 da togliere;
  - i nuovi requisiti RF-76..RF-82: preferenza, i tre rami, job `hotel_change`, classe `hotel`, `say` con l'esito, un solo hotel, errori;
  - le modifiche a RF-16/25/37/39/41/47/49/52/72 e RNF-04;
  - i casi d'uso UC-G1..G5 con dialoghi in italiano e inglese;
  - il bilancio della quota, il nuovo ordine di sacrificio e la proposta di migrazione 0014;
  - 11 domande aperte, ognuna con la mia raccomandazione.
- **`docs/roadmap.md`**: M22-a e M22-b in ondata 8 (grafo, tabella, sezione con prompt, matrice). Il totale passa a 82 RF.
- **`docs/decisions.md`**: solo le decisioni già tue (i 4 vincoli, dove sta la bozza, 0014 come proposta).

## Cosa ho deciso io
- **Migrazione 0014 solo per l'ordine.** Il nuovo tipo di job e la classe di quota non la richiedono: `jobs.kind` è `String(16)` senza vincoli e la classe si ricava dal tipo nel codice. 0014 serve solo per cinque campi sull'ordine.
- **Il totale va aggiornato sull'ordine dopo il cambio.** Il link Stripe usa `order.total`, quindi dopo il `PATCH` il totale va riletto e salvato prima di ogni conferma (RF-82).
- **Il ramo c resta come l'hai descritto.** Non vedo un'alternativa migliore: con un ordine non ancora in conferma il carrello non esiste, e cambiare hotel costerebbe un acquisto intero.

## Le domande che pesano di più (§10)
1. **Cosa separa M22 da RF-72**: propongo la sola presenza di `hotel_preference`. Con la preferenza si cambia hotel nello stesso viaggio, senza si passa a un altro viaggio.
2. **Cosa risponde `reject_proposal` nel ramo a**: propongo che aspetti come `accept_proposal` (fino a 100 s) e restituisca l'ordine di nuovo in conferma. È un esito nuovo che rompe la compatibilità dei client (non additivo).
3. **Il rifiuto nei rami a e b**: propongo di non registrarlo e di non cancellare l'ordine, un'eccezione a RF-49 come quella di RF-75.
4. **Un acquisto arriva mentre il cambio aspetta i gettoni**: propongo che il cambio rinunci (esito `busy`), senza aspettare.
10. **Cosa conta come "acquisto in attesa"**: propongo solo gli acquisti prima del link. La conferma del prezzo non chiama HofJ e oggi bloccherebbe comunque il sync.

## Di cosa non sono sicuro
- Il significato di `rating` e `guestRating` e il punto da cui HofJ misura `distance` li dirà solo la sonda. Anche le preferenze "più stelle" e "recensioni migliori" dipendono da questi campi.
- Su `ARCHITECTURE.md` do per scontato che §5.2 sia il budget di quota e §5.3 cosa degrada, come nel piano di M15.

## Fase 2: le chiamate della sonda, da approvare prima di eseguirle
Tutte su HofJ staging, senza pagamenti, con pause tra una chiamata e l'altra:
- 1 × `GET /v1/quota`
- 1 × `POST /v1/itineraries` su un prodotto con `hotelSelection=true` (2 adulti, 1 camera)
- 1 × `GET` dell'itinerario
- 2 × `GET .../accommodations` (una ordinata per `distance`, una per `priceAsc`)
- 1 × `PATCH` sull'hotel scelto
- 1 × `GET` dell'itinerario, per vedere se il totale cambia
- 2 × `POST` + `GET .../accommodations` su un prodotto con `hotelSelection=false`

In tutto sono **9 chiamate**, più 3 facoltative per il caso con 2 camere, quindi 12. È sopra la tua stima di 6-8 perché il prodotto con hotel fisso richiede un suo itinerario. Resteranno 2-3 itinerari orfani, come nelle sonde di M5.

Aspetto il tuo OK sulla bozza e sulle domande aperte, e il via per la sonda (9 o 12 chiamate).

## Utente 12:37

<pasted_content id="09a0">
Bozza approvata, con queste modifiche e precisazioni. Aggiorna il piano
(docs/plans/2026-09-27-m22-hotel.md) e decisions.md di conseguenza, poi passa alla fase 2.

## Rifiuto dell'hotel (sostituisce la tua proposta su §10.1)
- Quando il viaggiatore rifiuta l'hotel (reject_kind `hotel`), con o senza preferenza, e valgono
  le condizioni del ramo a (ordine in awaiting_confirmation, prodotto con hotelSelection o
  allowAccommodationList, nessun acquisto pending), Vela propone UN altro hotel dello stesso
  viaggio. Cosa separa M22 da RF-72 non è più la presenza di hotel_preference ma queste
  condizioni.
- La preferenza, se c'è, orienta la scelta. Senza preferenza si prende il primo hotel in
</pasted_content id="09a0">

## Agente 12:38

Non vado avanti per ora: il messaggio si interrompe a metà, su *"Senza preferenza si prende il primo hotel in"*.

Della sezione "Rifiuto dell'hotel" ho ricevuto due punti:
- **Cosa separa M22 da RF-72.** Sono le condizioni del ramo a, non più la presenza di `hotel_preference`. Con queste condizioni, un rifiuto `hotel` con o senza preferenza porta a UN altro hotel dello stesso viaggio.
- **A cosa serve la preferenza.** Se c'è, orienta la scelta. La regola per quando manca è troncata.

Mi manca il resto del messaggio:
1. Come finisce la regola senza preferenza. Immagino "il primo hotel in ordine `recommended`", ma preferisco non indovinare.
2. Le altre sezioni, se ce ne sono. Parli di "modifiche e precisazioni" al plurale, quindi probabilmente riguardano le altre domande aperte (§10.2..§10.11) e il via alla sonda: 9 chiamate o 12 con il caso a 2 camere.

Incollami il testo completo. Poi aggiorno la bozza e `decisions.md` in un commit e passo alla fase 2, prima con lo script e le chiamate esatte da confermare.

## Utente 12:38

<pasted_content id="09a0">
Bozza approvata, con queste modifiche e precisazioni. Aggiorna il piano
(docs/plans/2026-09-27-m22-hotel.md) e decisions.md di conseguenza, poi passa alla fase 2.

## Rifiuto dell'hotel (sostituisce la tua proposta su §10.1)
- Quando il viaggiatore rifiuta l'hotel (reject_kind `hotel`), con o senza preferenza, e valgono
  le condizioni del ramo a (ordine in awaiting_confirmation, prodotto con hotelSelection o
  allowAccommodationList, nessun acquisto pending), Vela propone UN altro hotel dello stesso
  viaggio. Cosa separa M22 da RF-72 non è più la presenza di hotel_preference ma queste
  condizioni.
- La preferenza, se c'è, orienta la scelta. Senza preferenza si prende il primo hotel in ordine
  `recommended` di HofJ diverso dall'attuale e da quelli già rifiutati su questo ordine.
- Gli hotel rifiutati si salvano sull'ordine, così un secondo "non mi piace" non torna al primo:
  proponi il campo (nella 0014, o dentro i cinque già previsti).
- Motivazione e nuovo totale nel say ("ti propongo X, ...; il totale diventa Z").
- Nessuna alternativa (hotel fisso, lista vuota, tutti già rifiutati) → RF-72 di M21-F: altro
  viaggio, escludendo quell'hotel.
- Coda piena → ramo b: si tiene l'hotel incluso, detto nel say, ordine sempre in conferma.
- Ordine non ancora in conferma → ramo c (RF-72), come nella bozza.
- Nelle istruzioni MCP nessuna domanda preventiva sulla preferenza: l'agente chiama subito
  reject_proposal con il motivo hotel.

## Le altre domande principali
- §10.2: ok, reject_proposal nel ramo a aspetta fino a 100 s come accept_proposal e restituisce
  l'ordine di nuovo in awaiting_confirmation. La rottura di compatibilità è accettata (i client
  sono nostri). Nella stessa task (M22-b) aggiorna istruzioni del server MCP, descrizione di
  reject_proposal, docs/rest.md, scripts/rest_flow.py se serve, e annota che
  response_timeout_secs di ElevenLabs deve restare ≥ 120.
- §10.3: ok, nessun rifiuto registrato e nessuna cancellazione dell'ordine nei rami a e b.
- §10.4: più semplice: il job hotel_change non aspetta mai. Se al momento del run c'è un
  acquisto pending o non ottiene subito tutti i gettoni del cambio, esito busy (ramo b).
- §10.5: ok, contano solo i job d'acquisto in stato pending; quelli in lavorazione hanno già
  prenotato i loro gettoni.
- Sulle altre domande aperte segui le tue raccomandazioni e scrivile in decisions.md.

## Le tue scelte
- Migrazione 0014 solo per i campi dell'ordine: ok.
- Totale riletto dopo il PATCH e salvato sull'ordine prima di ogni conferma (RF-82): ok, è
  obbligatorio perché il link Stripe usa order.total.
- Ramo c: ok.

## Correzione su ARCHITECTURE.md
Nella bozza su doc/architecture §5.2 è il bilancio della quota (browse/cart/hotel/booking e cosa
si sacrifica per primo), §5.3 è cosa degrada (minuto sei, Marco e Anna). Il nuovo ordine di
sacrificio (catalogo → scelta dell'hotel → attesa del link → mai le prenotazioni pagate) va in
§5.2, l'esperienza del viaggiatore a coda piena in §5.3. Correggi i riferimenti nel piano.

## Fase 2: sonda approvata, 12 chiamate
- Tutte su HofJ staging, anche le 3 per il caso con 2 camere.
- Distribuiscile su almeno 2 minuti: la chiave è condivisa con il servizio su Render.
- Nessun POST /v1/bookings e nessuna Checkout Stripe.
- Script in scripts/ (modello scripts/quota_probe.py), risultati in docs/api/accommodations.md,
  differenze nuove in docs/api/differences.md, itinerari orfani registrati in decisions.md.
- Oltre a quanto già previsto, verifica sulle risposte (senza chiamate in più): se il primo hotel
  in ordine `recommended` coincide con quello preselezionato nel carrello, e cosa significano
  rating e guestRating.
- Poi fermati con il verdetto (fase 3: M22-b si fa o no) prima di scrivere codice.
</pasted_content id="09a0">

## Agente 12:38

Ho tutto. Aggiorno la bozza, la roadmap e `decisions.md`, poi preparo la sonda.

- 🔧 Bash: Locate ARCHITECTURE.md sections on doc/architecture

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m22-a/docs/plans/2026-09-27-m22-hotel.md

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m22-a/docs/plans/2026-09-27-m22-hotel.md

- 🔧 Bash: Update roadmap and decisions with review, commit

- 🔧 Bash: Check key presence and HofJ adapter request format

- 🔧 Bash: Inspect fixture structure and accepted products

Sto scegliendo i prodotti di staging per la sonda: uno con hotel sceglibile e uno con hotel fisso, entrambi con partenze future.

- 🔧 Bash: Inspect fixture product fields

- 🔧 Bash: List candidate products with future availability

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m22-a/scripts/accommodations_probe.py

- 🔧 Bash: Tweak probe script and lint it

Prima di consumare quota vera provo lo script contro un finto HofJ locale, con 0 chiamate esterne.

- 🔧 Bash: Dry-run the probe against a local fake server

- 🔧 Bash: Commit the probe script

Ho aggiornato la bozza e `decisions.md` con la tua revisione, e lo script della sonda è pronto. Non posso lanciarlo io: `HOFJ_API_KEY` non è impostata nella mia shell, e le regole del progetto mi vietano di aprire `.env`.

## Revisione applicata (commit `e2a6d7c`)
- **Bozza aggiornata.** Contiene la regola del rifiuto `hotel` con o senza preferenza, `recommended` quando la preferenza manca, i nuovi UC-G1..G5 e §10 con le decisioni prese. Anche i riferimenti a `ARCHITECTURE.md` §5.2 e §5.3 sono corretti.
- **Hotel rifiutati.** Li salvo nel campo `orders.rejected_accommodations`, sempre uno dei cinque di 0014. Contiene anche l'hotel di default.
- **Una scelta mia da confermare.** "Nessun hotel migliore per la preferenza" non tiene più l'hotel attuale: lo tratto come "nessuna alternativa" e passa a RF-72, come la lista vuota. La bozza prevedeva un esito `no_better` che teneva l'hotel incluso, ma ignorerebbe il rifiuto del viaggiatore. Dimmi se preferisci il comportamento di prima.
- **Acquisti in attesa.** Per il cambio contano solo quelli in stato `pending`, come hai chiesto. Il sync resta bloccato da ogni acquisto attivo, come oggi, e in più dai cambi di hotel attivi.
- **Messaggio del commit rovinato.** Il titolo di `e2a6d7c` contiene le sequenze `$'\n\n…'` invece dell'attribuzione. Non l'ho corretto perché servirebbe riscrivere la storia: se vuoi, lo sistemo con un amend, dato che il branch non è ancora pushato.

## La sonda (commit `e2c48b6`, `scripts/accommodations_probe.py`)
L'ho provata contro un finto HofJ locale e fa esattamente 12 chiamate, distanziate di 12 s (circa 2,5 minuti):

| # | Chiamata |
|---|---|
| 1 | `GET /v1/quota` |
| 2-6 | **A**, prodotto 124 "Magnificent Padel in Lanzarote" (`hotelSelection=true`), 8/10, 2 adulti, 1 camera: creazione, lettura, lista `recommended`, `PATCH` sul primo hotel diverso dal preselezionato, rilettura del totale |
| 7-8 | **B**, prodotto 28 "Nueva Alcantara" (hotel fisso), 15/10: creazione e lista |
| 9-12 | **C**, prodotto 124 con 2 camere: creazione, lista `distance`, `PATCH`, rilettura |

- **Cosa non fa.** Nessun `POST /v1/bookings` e niente Stripe.
- **Quando si ferma.** Al primo 401, 403 o 429, a un 5xx diverso da 502, o se la creazione di A fallisce.
- **Itinerari orfani.** Ne restano 3; li registro in `decisions.md`.
- **Locale.** Uso `en`, il locale della fixture di staging: in M5 il prodotto 118 in `it` aveva dato 404.
- **Le verifiche in più che hai chiesto.** Se il primo hotel `recommended` è quello preselezionato, e il significato di `rating` e `guestRating`, li leggo dalle risposte, senza chiamate aggiuntive.

Lancialo dal tuo terminale, con la chiave già nell'ambiente. Non incollarla nel prompt con `!`, perché finirebbe nella conversazione:

```bash
cd /Users/matteodospina/orca/workspaces/vela/task-m22-a
uv run python scripts/accommodations_probe.py --out /private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-task-m22-a/28804719-2f61-41df-9d9d-3d8c120e5e43/scratchpad/probe
```

Quando ha finito, dimmelo e leggo `findings.json`. Poi scrivo `docs/api/accommodations.md`, le differenze nuove (dal #28) e gli orfani, e mi fermo con il verdetto della fase 3.

## Utente 12:47

prova tu ho messo .env

## Agente 12:47

- 🔧 Bash: Check where .env exists, without reading it

Carico `.env` nell'ambiente del solo processo della sonda, senza aprirlo né stamparlo. Forzo `HOFJ_BASE_URL` su staging, così un eventuale URL di produzione nel file non viene usato.

- 🔧 Bash: Run the 12-call accommodations probe on HofJ staging

Solo 8 chiamate: nessun `PATCH`, perché lo script non ha trovato un hotel alternativo. Guardo le risposte.

- 🔧 Bash: Read probe findings

La lista è vuota su tutti e tre gli itinerari, anche su quello con `hotelSelection=true`: 200, `totalCount: 0`. Controllo le date dell'alloggio nell'itinerario prima di trarre conclusioni.

- 🔧 Bash: Inspect itinerary accommodation dates and list queries

Rimetto `no_better` come prima: l'hotel incluso resta, il totale non cambia, nessun RF-72.

- 🔧 Bash: Find no_better references to revert

- 🔧 Bash: Show RF-78 passage to edit

- 🔧 Bash: Restore no_better outcome in draft and decisions

- 🔧 Bash: Commit the no_better revert

Ho rimesso `no_better` come nella prima bozza (commit `94c39ac`). Se c'è una preferenza e nessuna alternativa è migliore dell'hotel attuale, l'ordine resta in conferma con lo stesso hotel e lo stesso totale. RF-72 scatta solo senza alternative: lista vuota o hotel tutti già rifiutati.

## Sonda: 8 chiamate su 12, poi mi sono fermato
Ho caricato `.env` solo nel processo della sonda, senza aprirlo né stamparlo, e con `HOFJ_BASE_URL` forzato su staging. `GET .../accommodations` ha restituito **una lista vuota su tutti e tre gli itinerari** (200, `totalCount: 0`), anche sul prodotto 124, che ha `hotelSelection=true`. Senza un hotel alternativo lo script ha saltato i due `PATCH` e le due riletture.

Cosa ho già scoperto:
- **Latenza.** La lista risponde in 2,0, 2,1 e 1,9 s. `POST /v1/itineraries` impiega da 2,2 a 4,1 s, la lettura dell'itinerario 1,8 s, `GET /v1/quota` addirittura 5,6 s.
- **Hotel fisso (prodotto 28).** Risponde **200 con lista vuota**, non con un errore. HofJ non distingue quindi "hotel fisso" da "nessuna alternativa": il flag del catalogo è l'unico modo per saperlo.
- **Filtri diversi dall'OAS.** Nella risposta i filtri si chiamano `guestRating`, `starsRating`, `price` e `distance` (da 1 a 40). L'OAS dice `stars` e `rating`: è una differenza nuova da registrare.
- **Itinerario.** Il 124 ha `hotelSelection: true`, `allowAccommodationList: false` e un campo non documentato `removableAccommodation`. L'hotel preselezionato ha `rating: 4`, probabilmente le stelle, e un `totalPrice` di 0,00 € perché è incluso nel pacchetto. Il totale del carrello è 1156 €.
- **Itinerari orfani.** Sono tre: `arjeuuuzzw9s`, `fcocq0pgspd1` e `p8htf0mqbarg`.

**Ipotesi.** Probabilmente la lista degli hotel esiste solo con `allowAccommodationList=true`. `hotelSelection` potrebbe riguardare la scelta della camera, non dell'hotel. Nelle fixture di staging pochi prodotti hanno quel flag, per esempio il 25 "Padel Travel Weekend Camps – Malaga", che ha entrambi i flag.

## Proposta: 5 chiamate in più sul prodotto 25
Farei, su un itinerario del 15/10 con 2 adulti e 1 camera:
1. creazione;
2. lettura;
3. lista `recommended`;
4. `PATCH` sul primo hotel diverso, solo se la lista non è vuota;
5. rilettura del totale, solo se la lista non è vuota.

Si arriva a 13 chiamate contro le 12 approvate, 11 se la lista è di nuovo vuota. Il caso con 2 camere resterebbe scoperto. Restano la stessa pausa di 12 s tra le chiamate, niente booking e niente Stripe.

Le procedo con queste 5 chiamate? Se la lista resta vuota anche sul 25, per me è già un elemento forte per il verdetto: su staging il `PATCH` non si può verificare.

## Utente 12:51

procedi

## Agente 12:51

- 🔧 Bash: Add --parts option to the probe script

- 🔧 Bash: Clean indentation and dry-run part A only

Sul finto sono 5 chiamate esatte. Lancio su staging il prodotto 25, il 15/10.

- 🔧 Bash: Run 5-call probe on product 25 on HofJ staging

- 🔧 Bash: Read product 25 itinerary and list

- 🔧 Bash: Inspect accommodation elements and room configs

- 🔧 Bash: Read ARCHITECTURE §5.2-5.3 and HofJ questions tail

- 🔧 Bash: Count products with hotel flags per fixture

Ora scrivo `docs/api/accommodations.md`.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m22-a/docs/api/accommodations.md

- 🔧 Bash: Fix probe doc wording, add differences #28-35

Aggiungo le domande per HofJ, poi scrivo il verdetto in `decisions.md`, la roadmap e la bozza.

- 🔧 Bash: Add HofJ questions, verdict, roadmap and draft status

Ora i testi per ARCHITECTURE.md §5.2 e §5.3, nelle due varianti.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m22-a/docs/plans/2026-09-27-m22-architecture.md

- 🔧 Bash: Lint, test, and commit probe results and verdict

Il mio verdetto è **M22-b non si fa**: la sonda non ha mai visto un `PATCH` possibile, quindi M22 si chiude qui secondo il tuo criterio. L'ho registrato in `decisions.md` e mi fermo in attesa del tuo OK prima di qualunque codice.

## Cosa ha trovato la sonda
Ho usato 11 chiamate HofJ su 13, senza booking né Stripe. Il `PATCH` non è partito nemmeno una volta: nessun hotel aveva camere da mandare.

| Itinerario | `GET .../accommodations` |
|---|---|
| 124, solo `hotelSelection`, 1 camera | lista vuota |
| 124, 2 camere | lista vuota |
| 28, hotel fisso | 200 con lista vuota, nessun errore |
| 25, `allowAccommodationList` (l'unico su staging) | 1 hotel, ma `roomsConfiguration: []`: nessun `roomId` da mandare |

- **Latenza.** La lista risponde in 1,5-2,1 s su 4 misure: un cambio di hotel starebbe comodamente sotto il tetto di 100 s.
- **`rating`** sono le stelle: l'aggregato lo chiama `starsRating`.
- **`guestRating`** vale sempre 0 su staging, senza recensioni.
- **Hotel `recommended` e preselezionato.** Non ho potuto confrontarli: dove c'è un hotel preselezionato la lista è vuota, e dove c'è la lista non c'è un preselezionato.
- **Restano senza risposta:** formato e risposta del `PATCH`, `roomIds` per 1 e 2 camere, e se il totale cambia dopo il cambio.

## Perché no
Costruire job, classe di quota, migrazione 0014 e contratto nuovo su una chiamata mai vista funzionare vorrebbe dire scoprire in produzione se regge. In più, la lista sembra esistere solo con `allowAccommodationList`, e i prodotti con quel flag sono 1 su 56 a staging e 8 su 126 in produzione.

La bozza, con la tua revisione e `no_better` rimesso com'era, resta come archivio. M22 si può riaprire se HofJ risponde alle domande 11-13 in `hofj-questions.md`, oppure con una sonda approvata su un prodotto di produzione con `allowAccommodationList`: 323, 326, 985, 1059 o 1065 per il padel, 372, 795 o 1007 per il tennis. Alla riapertura il vincolo 4 andrebbe ristretto ai prodotti con `allowAccommodationList`.

## Una scoperta da decidere, fuori da M22
Sul prodotto 25 l'itinerario appena creato **non ha un hotel preselezionato**: `accommodation` ha tutti i campi `null`, eppure il totale è 1798 €. Un acquisto fatto oggi su un prodotto con `allowAccommodationList` potrebbe quindi finire prenotato senza hotel. È la differenza #30 in `differences.md`. Non ho deciso niente; le opzioni che vedo:
1. escludere questi prodotti dal chooser;
2. controllare `accommodation` nel passo del totale e trattare l'hotel mancante come errore del prodotto (RF-17);
3. aspettare la risposta di HofJ alla domanda 13.

## Cosa ho scritto
- **`docs/api/accommodations.md`**: risultati della sonda.
- **`docs/api/differences.md`**: differenze nuove #28-#35.
- **`docs/hofj-questions.md`**: domande 11-13.
- **`docs/decisions.md`**: verdetto, i 4 itinerari orfani (`arjeuuuzzw9s`, `fcocq0pgspd1`, `p8htf0mqbarg`, `phtjys9d6rip`) e l'uso di `.env`, che ho caricato solo nel processo della sonda senza aprirlo, con host forzato su staging.
- **Roadmap e bozza**: M22-b segnata come "non si fa".
- **`docs/plans/2026-09-27-m22-architecture.md`**: testi per ARCHITECTURE.md §5.2 e §5.3 in due varianti, senza M22-b (quella che vale ora) e con M22-b.
- **`scripts/accommodations_probe.py`**: ora accetta `--parts` per lanciare solo una parte della sonda.

Lint e test sono verdi (63 test saltati senza `DATABASE_URL`). Il branch è `doc/m22-hotel`, con 9 commit e nessun push. Il titolo del commit `e2a6d7c` è ancora rovinato: se vuoi lo sistemo, ma serve riscrivere la storia locale.

## Utente 12:57

mi stai dicendo che non offre la possibilità di prenotare hotel-?

## Agente 12:57

No: gli hotel si prenotano. Quello che non sono riuscito a verificare è la possibilità di **cambiare** l'hotel dentro un viaggio.

- **Prenotare con l'hotel funziona.** Il prodotto HofJ è "esperienza + hotel": quando Vela crea l'itinerario, l'hotel di default è già dentro. Sul 124, per esempio, c'è THB Lanzarote Beach, a 4 stelle, incluso nel totale di 1156 €. Le prenotazioni reali fatte finora (M7, il 163 a Mallorca) passano da qui. Questo resta com'è.
- **Cambiare hotel non l'ho visto funzionare.** Serve a M22: si chiede a HofJ l'elenco degli hotel alternativi e si sostituisce quello incluso con il `PATCH`. Su staging la lista era vuota su 3 itinerari su 4, e sul quarto l'unico hotel non aveva camere selezionabili. Il `PATCH` quindi non è mai stato possibile. Può essere un limite dei dati di staging più che dell'API, ma senza vederlo funzionare non costruirei M22-b.
- **Un'anomalia da capire.** Sul prodotto 25, l'unico di staging che permette la lista degli hotel, l'itinerario appena creato non aveva nessun hotel preselezionato. Il totale però c'era (1798 €), quindi non so dire se sia un dato incompleto di staging o un caso in cui l'hotel va scelto per forza. È la domanda 13 per HofJ.

In breve: oggi Vela prenota viaggi con l'hotel incluso. Non si può ancora offrire "stesso viaggio, altro hotel". Per capire se il cambio funziona si può chiedere a HofJ (domande 11-13) oppure fare una sonda su un prodotto di produzione con la lista degli hotel.

## Utente 12:58

esiste la possibilità di prenotare l'esperienza sensa un'hote?

## Agente 12:58

- 🔧 Bash: Check removableAccommodation and brief hotel requirement

- 🔧 Bash: Count removableAccommodation products in fixtures

Sembra di sì, ma solo per pochissimi prodotti, e la prenotazione vera e propria senza hotel non l'ho vista.

**Cosa ho osservato**
- HofJ ha un flag non documentato, `removableAccommodation` ("hotel rimovibile"). Sta sia nel catalogo sia nell'itinerario.
- **Prodotto 124**: il flag è `false`, l'itinerario nasce con l'hotel incluso (THB Lanzarote Beach) e il totale è 1156 €.
- **Prodotto 25**: il flag è `true`, l'itinerario nasce **senza hotel** ma con un totale di 1798 €. Sembra proprio un'esperienza vendibile senza hotel.

**Quanti prodotti lo hanno**, contati sulle fixture senza chiamate:
- staging: solo il 25, su 69 prodotti attivi;
- produzione: solo il 795 (tennis), su 126 attivi.

**Cosa non so**
- Se un booking su un itinerario senza hotel va a buon fine: non l'ho mai provato.
- Se per quei prodotti l'hotel va aggiunto a parte. Nell'API non c'è una chiamata per aggiungerlo o toglierlo, solo il `PATCH` di sostituzione.

**Cosa significa per Vela**
Il brief dice "Padel or tennis experiences packaged with a hotel. That is the whole product." Un viaggio senza hotel quindi non è un'opzione da offrire. Per questi prodotti è piuttosto un rischio: oggi Vela potrebbe proporre il 795 e prenotarlo senza hotel. È la scoperta #30 che avevo lasciato aperta.

Ti propongo di escludere dal chooser i prodotti con `removableAccommodation: true` quando l'itinerario non ha un hotel, oppure tutti quelli con il flag, e di chiedere a HofJ come funzionano (domanda 13). È una piccola task a parte, non M22: la vuoi?

## Utente 13:01

ok quindi non è posisbile chambiare l'hotel e non ha senso farlo escludere. come procediamo?

## Agente 13:01

Sì: su HofJ oggi il cambio di hotel non è praticabile, e l'esclusione dei prodotti senza hotel non la facciamo. Io procederei così:

**1. Chiudere M22-a**
- In `decisions.md` segno la tua decisione sulla scoperta #30: nessuna esclusione dal chooser. Il rischio resta annotato, insieme alla domanda 13 per HofJ.
- Correggo il titolo rovinato del commit `e2a6d7c`. Serve riscrivere la storia del branch, che però non è pushato: mi basta il tuo sì.
- Mergio `doc/m22-hotel` su `master`. Contiene solo documenti e lo script della sonda: bozza e verdetto di M22, `accommodations.md`, differenze #28-#35, domande 11-13 e i testi per ARCHITECTURE.md.

**2. Mandare le domande a HofJ (facoltativo)**
Le 11-13 di `hofj-questions.md` chiariscono se il cambio di hotel funziona in produzione e cosa succede ai prodotti senza hotel. Se la risposta è buona, M22 si riapre dalla bozza già approvata, senza rifare il design.

**3. Tornare alla roadmap**
- **M21**, la scelta v3. M21-A è fatta, la prossima è **M21-E** (budget a testa o totale). Con M21-F arriva RF-72, che resta l'unica leva sull'hotel: "l'hotel non mi piace" porta a un altro viaggio con un hotel diverso.
- **M15**: in `ARCHITECTURE.md` §5.2 e §5.3 va la variante A dei testi (senza M22-b), già pronta in `docs/plans/2026-09-27-m22-architecture.md`.

Il mio consiglio è fare il punto 1 subito e poi partire con M21-E. Mi dai l'OK per il punto 1, compreso il rewrite locale del commit e il merge su `master`?

## Utente 13:06

ok vai con 1

## Agente 13:06

- 🔧 Bash: List worktrees and master refs

Ecco i passi del punto 1: prima la decisione in `decisions.md`, poi la correzione del commit, infine il merge su `master` (che è checkout nel worktree `master`).

- 🔧 Bash: Record no-exclusion decision and commit

Ora ricreo i commit da `e2a6d7c` in poi con il messaggio corretto, via cherry-pick, e verifico che il contenuto finale resti identico.

- 🔧 Bash: Save old HEAD and inspect before rewriting
