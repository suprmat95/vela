# Documentazione scelta v3 e nuovi requisiti

- Sessione: `ff99749d-8101-4e5d-95e4-87ccb41c9115`
- Inizio: 2026-09-26 19:09

## Utente 19:09

<pasted_content id="dff5">
Lavora su un nuovo worktree da `master` chiamato `task/m21-docs`.

Contesto. Il chooser (`vela/domain/chooser.py`) sceglie oggi così: filtri duri in sequenza
(archived, bookable, trip, sport, dates, pax, price, rejected) e poi ordinamento per
(-area_score, non entro budget, prezzo crescente, id). Il parser (`vela/domain/intent.py`)
estrae sport, area, periodo, pax, budget, lingua. Il rifiuto (`vela/domain/refine.py`)
riconosce budget, direzione, luogo, periodo, sport, pax; un motivo non riconosciuto lascia i
criteri invariati ed esclude solo il product_id. L'acquisto (`vela/domain/purchase.py`) crea
l'itinerario con `rooms=1` fisso. Il catalogo HofJ ha campi che ignoriamo:
`defaultDurationInDays`, `maxPaxPerRoom`, `hotels`/`hotelSelection`, `isSpecialOffer`,
`featured`, e nelle descrizioni compaiono livello di gioco ("principianti", "tutti i livelli"),
"clinic/coach/lezioni", "hotel 4 stelle".

Obiettivo di questa sessione: SOLO documentazione, nessun codice. Scrivi:

1. `docs/usecases/scelta.md`, nello stesso formato di `docs/usecases/agente-tool.md`
   (utente / agente / server / agente legge), con questi sei casi:

   UC-A Durata. "Un weekend di padel in Spagna a ottobre" → la durata (weekend, ponte,
   una settimana, N giorni/notti) diventa un criterio morbido; se nessun viaggio la rispetta
   il `say` lo dichiara ("Non ho weekend compatibili: questo dura 5 notti").

   UC-B Ordinamento. Senza budget dichiarato il prezzo non deve essere il criterio dominante.
   Nuovo ordine: area → entro budget → durata compatibile → partenza più vicina all'inizio del
   periodo → featured/isSpecialOffer → prezzo → id. Caso esplicito: la trappola 900078
   (prezzo -1) non deve più vincere quando esiste un prodotto vero equivalente.

   UC-C Livello e lezioni. "Siamo principianti, vorremmo lezioni" → `level` e
   `wants_coaching` estratti dalla frase; i prodotti vengono etichettati in fase di sync
   leggendo la descrizione (levels: {beginner, intermediate, advanced, all}, coaching: bool).
   Filtro duro solo quando la descrizione esclude esplicitamente ("solo avanzati"), altrimenti
   preferenza nell'ordinamento e frase nel `say`.

   UC-D Persone e camere. "Siamo in cinque" → il numero di camere entra nel contratto:
   parametro `rooms` su `create_intent` e `accept_proposal` (MCP e REST). Quando pax > 2 e
   `rooms` manca, il server risponde con una `question` ("In quante camere?"), come oggi fa per
   lo sport, e l'agente la pone prima di procedere; con pax ≤ 2 il default è 1 camera. Il
   chooser rispetta `maxPaxPerRoom` (camere ≥ ceil(pax / maxPaxPerRoom)) e lo dice nel `say`;
   l'acquisto passa `rooms` reale a `POST /v1/itineraries` invece di 1. Caso "da solo" con
   prodotti a minPax=2 → NoChoice("pax") con `say` esplicativo.

   UC-E Budget a testa o totale. "Massimo 600 euro" in tre → regole: "a testa/a persona/each"
   = per persona; "in tutto/totale/in total" = totale; cifra sola con pax > 1 → per persona se
   cifra × pax non copre neanche il prodotto più economico compatibile, altrimenti totale; il
   `say` dichiara sempre l'interpretazione ("ho inteso 600 euro a persona"). Parametro
   strutturato `budget_scope: per_person | total` su create_intent e reject_proposal.

   UC-F Rifiuti con motivo sempre capito. Ogni rifiuto viene classificato in una di queste
   categorie: price, place, hotel, dates, duration, sport, pax, level, direction, other.
   Comportamenti: `hotel` → esclusi tutti i prodotti con lo stesso hotel; `place` ("Marbella
   no, ma la Spagna va bene") → `excluded_areas`, area padre mantenuta; `dates` con "tieni
   questo viaggio" ("questo mi piace ma non posso in quelle date", "quando altro è
   disponibile?") → STESSO prodotto, finestra proposta esclusa, prossima partenza disponibile
   compatibile con i criteri (o con il nuovo periodo detto nel motivo); `other` (motivo non
   riconosciuto, es. "non mi convince") → il server NON sceglie alla cieca ma risponde con una
   `question` a scelta chiusa ("Cosa non ti convince: il posto, l'hotel, le date o il
   prezzo?") e la proposta resta aperta finché l'agente non richiama reject_proposal con la
   risposta. Parametri strutturati per l'agente: `reject_kind` (le categorie sopra) e
   `keep_product: bool`.

   Per ogni caso: 2-3 varianti di frase in italiano e in inglese, il comportamento con solo
   testo e con campi strutturati, e la lista dei test di dominio/MCP/REST da scrivere.

2. `docs/spec.md`: nuovi requisiti numerati a partire da RF-57, uno per comportamento
   osservabile, con rimando al caso d'uso. Aggiorna la sezione dei criteri (`Criteria`) e il
   contratto dei tool (§4.11) con i nuovi parametri: `duration_min_nights`,
   `duration_max_nights`, `level`, `wants_coaching`, `rooms`, `budget_scope`, `reject_kind`,
   `keep_product`. Segnala esplicitamente quali sono cambi di interfaccia pubblica.

3. `docs/roadmap.md`: milestone M21 "Scelta v3" con sei task nell'ordine A, E, B, D, C, F,
   dipendenze, e la matrice dei requisiti aggiornata.

4. `docs/decisions.md`: registra le decisioni prese qui (data di oggi), in particolare:
   durata/livello/budget-scope sono criteri morbidi e mai escludono da soli; `rooms` entra nel
   contratto e viene chiesto solo con pax > 2; il rifiuto "other" produce una domanda chiusa
   invece di una nuova proposta (eccezione dichiarata a RF-08).

Prima di scrivere, proponimi in poche righe: la lista degli RF che intendi aggiungere, i
punti in cui vedi conflitti con la spec attuale (RF-06, RF-07, RF-08, RF-09, RF-52, RF-53) e
le 2-3 decisioni su cui vuoi il mio OK. Aspetta la mia risposta. Non toccare codice né test.
</pasted_content id="dff5">

## Agente 19:09

- 🔧 Bash: List worktrees and check master state

- 🔧 Bash: Create task/m21-docs worktree from master and list docs

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21-docs/docs/spec.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21-docs/docs/usecases/agente-tool.md

Il worktree è creato, ma la lettura fuori dalla directory corrente è bloccata. Per ora leggo dalla cartella corrente, che è sullo stesso commit `7a01c59`, quindi i contenuti sono identici.

- 🔧 Bash: Read use case format and spec requirement index

- 🔧 Bash: Read relevant spec sections and search for Criteria references

- 🔧 Bash: Read roadmap structure and requirements matrix

Now the code: criteria, chooser, refine, and the persisted data model.

- 🔧 Bash: Inspect Criteria dataclass and chooser structure

- 🔧 Bash: Read chooser filters and refine module

- 🔧 Bash: Check trap fixture, schema, Product and Proposal models

- 🔧 Bash: Check table columns and catalogue field usage

- 🔧 Bash: Check which catalogue fields are kept in raw

Prima di tutto: ho creato il worktree `task/m21-docs` da `master` (`7a01c59`) in `/Users/matteodospina/orca/workspaces/vela/task-m21-docs`. Però la regola `blockReadsOutsideWorkingDirectories` mi impedisce di leggere e scrivere lì. Per l'analisi ho letto i file della cartella corrente, che è sullo stesso commit. Prima di scrivere mi serve un `/add-dir /Users/matteodospina/orca/workspaces/vela/task-m21-docs`.

Non ho toccato codice né test.

## RF che intendo aggiungere

**RF-57 è già occupato** dall'SMS di conferma (§4.5). Parto quindi da **RF-58**. Correggo anche la matrice della roadmap, che si ferma a RF-56 e dice ancora "56 RF".

| Caso | RF | Comportamento osservabile |
|---|---|---|
| UC-A | RF-58 | Dalla frase si estrae la durata ("weekend", "ponte", "una settimana", "N giorni/notti") e diventa `duration_min_nights`/`duration_max_nights`. È un criterio morbido. |
| | RF-59 | Se nessun viaggio rispetta la durata, il `say` lo dice. |
| UC-B | RF-60 | Nuovo ordinamento: area → entro budget → durata → partenza più vicina all'inizio del periodo → featured/specialOffer → prezzo → id. |
| | RF-61 | Tra prodotti "equivalenti" vince quello vero: la trappola 900078 non passa più davanti al 78. |
| UC-C | RF-62 | `level` e `wants_coaching` si estraggono dalla frase. |
| | RF-63 | Etichette `levels`/`coaching` sui prodotti, ricavate dalla descrizione durante la sync. |
| | RF-64 | Il livello esclude un prodotto solo se la descrizione lo esclude esplicitamente; altrimenti conta come preferenza e compare nel `say`. |
| UC-D | RF-65 | `rooms` su `create_intent` e `accept_proposal`. Con pax > 2 e senza `rooms` il server risponde con una `question`; con pax ≤ 2 si assume 1 camera. |
| | RF-66 | Il chooser rispetta `maxPaxPerRoom` e il `say` lo dice. |
| | RF-67 | L'acquisto passa a HofJ le camere reali. |
| | RF-68 | "Da solo" con prodotti a minPax 2 dà `NoChoice("pax")` con un `say` che spiega. |
| UC-E | RF-69 | `budget_scope` e regole per decidere tra budget a persona e totale. |
| | RF-70 | Il `say` dichiara sempre l'interpretazione. |
| UC-F | RF-71 | Ogni rifiuto viene classificato in `reject_kind` (dieci categorie). |
| | RF-72 | `hotel`: esclusi tutti i prodotti con lo stesso hotel. |
| | RF-73 | `place`: nasce `excluded_areas`, l'area padre resta. |
| | RF-74 | `dates` + `keep_product`: stesso prodotto, finestra successiva. |
| | RF-75 | `other`: domanda chiusa, la proposta resta aperta. |

Aggiorno anche RF-02, RF-39, RF-40, RF-41, RF-52, RF-53 e RF-54, con i cambi di interfaccia pubblica segnalati uno per uno.

## Conflitti con la spec attuale

- **Nella spec non esiste una sezione "Criteria".** I criteri sono in RF-02 e RF-52; la classe `Criteria` è in `models.py` e finisce nella risposta pubblica `intent_created` (decisione M7). Quindi ogni campo nuovo dei criteri è un cambio pubblico anche in uscita. Propongo una nuova §4.12 "Criteri" con la tabella completa.
- **RF-06.** La proposta non mostra camere né durata. Con UC-D e UC-A deve mostrarle.
- **RF-07.** Cambia l'ordinamento. Nascono filtri duri nuovi (livello escluso esplicitamente, camere, hotel escluso, `excluded_areas`). Il filtro `rejected` diventa per coppia prodotto+finestra, non più per prodotto, quando c'è `keep_product`.
- **RF-08.** Oggi dice "restituisce un'altra proposta". Si rompe in due punti: `other` restituisce una domanda (eccezione dichiarata), `dates`+`keep_product` restituisce lo stesso prodotto. Collegati: RF-49 (un rifiuto su un ordine `queued` lo cancella; con `other` non deve succedere) e RF-55 (quando si registra il rifiuto).
- **RF-09.** "Non propone mai un prodotto già rifiutato" è in contrasto con `keep_product`. Servono anche nuovi `failed_criterion` (`rooms`, `hotel`, `level`, `place`).
- **RF-52.** Oggi dice "`budget` (totale in EUR)", e anche RF-02 dice "budget totale massimo": UC-E cambia il significato. I parametri nuovi sono additivi, ma `rooms` su `accept_proposal` va oltre RF-52.
- **RF-53.** Servono regole di validità e precedenza per ogni campo nuovo, per esempio `rooms` fuori da 1..pax, o `rooms` sotto il minimo richiesto da `maxPaxPerRoom`.
- **Altri conflitti fuori dalla lista che mi hai dato:**
  - **RF-54** prevede "motivo non tradotto → escludo solo la proposta", che UC-F sostituisce.
  - **RF-04** dovrà includere la domanda sulle camere, nell'ordine sport → persone → camere.
  - **RF-12** dice "nient'altro viene chiesto" all'accettazione.
  - **§10.4:** oggi la prova del prodotto che fallisce al carrello si ripete con la trappola. Con UC-B la trappola arriva solo dopo aver rifiutato il 78, e la procedura va riscritta.
- **Dati da verificare.** `defaultDurationInDays` non è ignorato, lo usiamo già come `duration_days`. Dalle note in `docs/api/products.md`:
  - `isSpecialOffer` è false su tutti i 123 prodotti, quindi oggi non pesa;
  - `maxPaxPerRoom` è valorizzato solo su 12 prodotti, `featured` su 19.

  Inoltre la proiezione `CATALOG_FIELDS` non conserva `maxPaxPerRoom`, `featured` né la descrizione lunga. Implementare UC-C e UC-D probabilmente richiede di registrare di nuovo le fixture, con chiamate a HofJ live, e `catalog.json` è già al 96% del limite di dimensione. Nei documenti lo scrivo come rischio di M21. In questa sessione non chiamo nulla.

## Decisioni su cui mi serve il tuo OK

1. **Come far perdere la trappola (UC-B).**
   - a) Prodotti "equivalenti" (stesso hotel, stesso titolo normalizzato, stessa destinazione, prezzo entro il 5%): vince l'id più vecchio.
   - b) Prezzo per fasce (arrotondato) prima dell'id.
   - c) Nessuna regola: la trappola perde già se il 78 è featured.

   **Consiglio a):** è l'unica che funziona per costruzione, senza sapere quale dei due è la trappola.
2. **Schema del database.** Servono una colonna `rooms` sugli ordini, `kind`, `keep_product` e la finestra esclusa sui rifiuti, e le etichette prodotto (`levels`, `coaching`, `max_pax_per_room`, `featured`).
   - a) Una migrazione `0010` in M21, scritta nei documenti come cambio di schema da approvare al task.
   - b) Evitare lo schema: `rooms` nel JSON `traveler`, etichette calcolate a ogni lettura da `raw`, tipo di rifiuto nel testo.

   **Consiglio a):** b) nasconde i dati in campi con un altro significato.
3. **Rifiuto `other` (UC-F).** Consiglio che la prima chiamata **non registri il rifiuto, non cancelli un ordine `queued`** (eccezione a RF-49) e restituisca `question` con lo stesso `proposal_id`. Solo la seconda chiamata, con la risposta, registra il rifiuto. L'alternativa (registrare subito e aggiornare dopo) rende il rifiuto una cosa a metà nel database.

**Scelte minori che adotto, salvo obiezioni:**
- `rooms` su `accept_proposal` vale solo come correzione e deve rispettare il minimo di camere.
- "Hotel 4 stelle" resta fuori da M21.
- Il `say` di `create_intent` ripete anche durata, livello, camere e l'interpretazione del budget, estendendo RF-54.

Aspetto la tua risposta e l'`/add-dir`.

## Utente 19:11

proce

## Agente 19:11

- 🔧 Bash: Check access to the new worktree

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m21-docs/docs/usecases/agente-tool.md

Non ho ancora scritto nulla. Mi mancano due cose:

1. **Accesso al worktree.** `Read`/`Write`/`Edit` su `/Users/matteodospina/orca/workspaces/vela/task-m21-docs` sono ancora bloccati da `blockReadsOutsideWorkingDirectories`. Potrei passare dalla shell, ma vorrebbe dire aggirare una regola che hai messo tu, quindi non lo faccio. Esegui:
   ```
   /add-dir /Users/matteodospina/orca/workspaces/vela/task-m21-docs
   ```
   In alternativa dimmi di scrivere i documenti in questo worktree (`doc/selection-improvements`), che è sullo stesso commit di `master`.

2. **Conferma.** "proce" lo leggo come "procedi" con le tre soluzioni che ti ho consigliato:
   - la trappola perde grazie alla regola dei prodotti equivalenti;
   - lo schema cambia con una migrazione `0010` da approvare al task;
   - il rifiuto `other` non registra nulla e non cancella l'ordine.

   Valgono anche le scelte minori. Se è così, basta l'`/add-dir` e parto.

## Utente 19:12

scrivi in questo worktree

## Agente 19:12

- 🔧 Bash: Read roadmap header, graph, table and M17/M20

- 🔧 Bash: Read decisions.md structure and latest entries

- 🔧 Bash: Read decision format, spec header and acceptance criteria

- 🔧 Bash: Inspect use case response types and geo coverage

- 🔧 Bash: Read response models, geo entries, purchase rooms

- 🔧 Bash: Inspect fixture structure

Scriverò in questo worktree. Prima verifico nelle fixture quali campi ci sono davvero (durata, camere, livello, hotel), così i casi d'uso usano dati reali.

- 🔧 Bash: Count optional catalogue fields and description keywords in fixtures

- 🔧 Bash: Gather fixture stats on rooms, pax, durations, level phrases

- 🔧 Bash: Check REST contract for question and status codes

- 🔧 Bash: Check how parser handles weekend and budget today

- 🔧 Bash: Read weekend period logic and per-person budget handling

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/doc-selection-improvements/docs/usecases/scelta.md

Il caso d'uso è scritto. Correggo tre esempi che citavano nomi di prodotti inventati, poi passo a `docs/spec.md`.

- 🔧 Bash: Replace invented product names with placeholders

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-selection-improvements/docs/spec.md

- 🔧 Bash: Update existing spec requirements for M21

Ora la nuova §4.12, con la tabella dei criteri, RF-58..75 e l'elenco dei cambi di interfaccia pubblica.

- 🔧 Bash: Insert new spec section 4.12 before non-functional requirements

- 🔧 Bash: Note RF-49 exception and clarify out-of-scope hotels

- 🔧 Bash: Update spec header list of changed requirements

`docs/spec.md` è fatto. Passo alla roadmap: sezione M21 con sei task, grafo, tabella e matrice.

- 🔧 Bash: Add M21 milestone, graph, table rows and matrix updates to roadmap

Allineo i riferimenti alle migrazioni in spec e casi d'uso: una per task, dalla 0010 alla 0013.

- 🔧 Bash: Find migration references to align

- 🔧 Bash: Align migration numbers across spec and use cases

- 🔧 Bash: Check for stray replacement artefact

Aggiungo le decisioni in `docs/decisions.md`.

- 🔧 Bash: Append M21 decisions to decisions.md

- 🔧 Bash: Correct two catalogue statistics and check whitespace

- 🔧 Bash: Fix total product count in decision note

Ho scritto i quattro documenti in `doc/selection-improvements`. Non ho toccato codice né test e non ho fatto commit. Sono modificati `docs/spec.md`, `docs/roadmap.md` e `docs/decisions.md`; `docs/usecases/scelta.md` è nuovo.

**Cosa contiene**
- **`docs/usecases/scelta.md`**: i sei casi UC-A..UC-F nel formato di `agente-tool.md`. Per ognuno ci sono le varianti it/en, il comportamento con solo testo e con i campi, e i test di dominio, MCP e REST. UC-F è diviso in quattro sottocasi: hotel, luogo escluso, altre date, motivo non capito.
- **`docs/spec.md`**: nuova §4.12 con RF-58..75. Contiene la tabella dei criteri (nella spec non esisteva una sezione "Criteria"), le etichette dei prodotti, la tabella dei cambi di interfaccia pubblica (additivi e non) e le migrazioni. Ho aggiornato RF-02, 04, 06..09, 12, 14, 39..41, 49, 52..54 e §7, marcando "(M21)" le parti non ancora implementate.
- **`docs/roadmap.md`**: M21 "Scelta v3" in ondata 7, con sei task in sequenza A → E → B → D → C → F. Ognuna ha scope, dipendenze, taglia e le decisioni da prendere nel brainstorm. Ho aggiornato anche il grafo, la tabella riassuntiva e la matrice, che ora arriva a 75 RF.
- **`docs/decisions.md`**: sezione "2026-09-26 — Scelta v3 (M21)" con le tue tre decisioni e le altre che ho preso.

**Cosa ho deciso**
- **Numerazione:** parto da RF-58, perché RF-57 è già l'SMS di conferma. Mancava dalla matrice e l'ho aggiunto.
- **Cambi non additivi**, segnalati come tali:
  - un client che manda pax 5 senza camere riceve una domanda invece dell'intento;
  - `reject_proposal` può restituire una domanda;
  - `accept_proposal` risponde con una domanda se le camere sono sotto il minimo del prodotto;
  - "un weekend" diventa una durata e non più un periodo;
  - un luogo negato diventa un'esclusione;
  - il nuovo ordinamento può cambiare la proposta per lo stesso intento.
- **Una modifica rispetto a quanto avevi approvato:** le migrazioni sono quattro, una per task (0010-0013), invece di una sola 0010. Le task si mergiano una alla volta. È scritto nelle decisioni.

**Dove non sono sicuro**
- **Regola del budget:** hai scritto "cifra × pax non copre". Presa alla lettera, la regola non scatta mai quando serve, quindi l'ho letta come "la cifra, presa come totale, non copre prezzo × pax del prodotto più economico". Verificala.
- **Livello e lezioni** non erano nel tuo ordinamento. Li ho messi subito dopo la durata.
- **Criterio §10.4:** con la regola dei prodotti equivalenti la trappola non vince più da sola, quindi la prova del prodotto che fallisce al carrello va rifatta. Ho lasciato la scelta aperta in M21-B, con tre opzioni.
- **"Marbella no":** Marbella non è nel dizionario `geo`, quindi negli esempi uso Estepona; aggiungere Marbella è nello scope di M21-F.

**Da sapere**
- **Fixture:** prima ti avevo detto che servivano nuove registrazioni HofJ. Non è così: `description`, `maxPaxPerRoom` e `featured` sono già nelle fixture, e M21 non richiede chiamate esterne. `isSpecialOffer` invece è falso su tutti i prodotti, quindi oggi non pesa.
- **Worktree vuoto:** `/Users/matteodospina/orca/workspaces/vela/task-m21-docs` (branch `task/m21-docs`) è rimasto inutilizzato. Lo rimuovo insieme al branch?
- **Commit:** vuoi un commit per documento o uno solo?

## Utente 19:23

ok mergia in master

## Agente 19:23

- 🔧 Bash: Run lint and tests, check master worktree state
