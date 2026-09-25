# Task m11 execution plan

- Sessione: `6c47ab9d-e23a-4141-b21a-16d31d3b4d9b`
- Inizio: 2026-09-25 16:29

## Utente 16:29

❯ /superpowers:brainstorming Leggi la task m11 in docs/roadmap.md. Obiettivo: intervistami e scrivi il
      piano di esecuzione in un file in docs/plans/ Il piano dovrà indicare i microtask e i test che
  coprono il codice prodotto. Dopodiché lancerò l'esecuzione del piano

## Agente 16:29

- 🔧 Skill superpowers:brainstorming

- 🔧 Bash: List docs and read task M11 from roadmap

- 🔧 Bash: Read spec section 4.2 and M2 roadmap

Now the existing domain code.

- 🔧 Bash: List code files and recent decisions

- 🔧 Bash: Read chooser, geo and chooser tests

- 🔧 Bash: Read models and catalog parsing

- 🔧 Bash: Read say templates, usecase usage, test support

- 🔧 Bash: Inspect fixture for geohierarchy fields

- 🔧 Bash: Tabulate geohierarchy, durations and windows in fixture

- 🔧 Bash: Read spec 4.1 and analyse availability windows

Sto leggendo il codice di M2 (chooser, geo, fixture) per preparare le domande dell'intervista; ancora un controllo sul parser e poi parto.

- 🔧 Bash: Check parser periods and branches

Ho letto M11 in `docs/roadmap.md`, RF-06/07/09 in `docs/spec.md`, il chooser v1 (`vela/domain/chooser.py`), `vela/domain/geo.py`, i test e la fixture.

**Tipo di lavoro.** M11 modifica un flusso che esiste già (il chooser v1), ma cambia regole di dominio e tocca più file. Lo tratto come lavoro architetturale leggero. Visto che vuoi un piano in `docs/plans/`, scrivo un solo documento: le decisioni dell'intervista più i microtask con i test. Niente spec separata in `docs/superpowers/specs/`. Correggimi se preferisci altro.

**Cosa ho capito.**
- **Obiettivo:** chooser v2 deterministico con l'ordinamento completo di RF-07. L'aderenza all'area segue la gerarchia città > regione > paese. Il budget si confronta con il totale, cioè prezzo × pax. Le date escono dall'intersezione tra il periodo richiesto e le finestre di disponibilità, tenendo conto della durata. La motivazione, di 1-2 frasi, cita il criterio soddisfatto. Il messaggio di RF-09 dice quale criterio manca.
- **Vincoli:** nessuna dipendenza nuova senza accordo; niente modifiche allo schema DB o alle interfacce pubbliche senza chiedere. Cerco di non toccare `vela/domain/intent.py`, che è anche di M9.
- **Criterio di successo:** tabelle di test sulla fixture reale (stesso intento → prodotto atteso, rifiuti in sequenza, nessun match su area, budget o periodo) e test di proprietà (mai un prodotto archiviato, non prenotabile o rifiutato; mai più di un prodotto).

**Cosa ho trovato nei dati.** Tre punti cambiano il design:
1. **`geohierarchy` non è una gerarchia.** È solo `PAESE_geonameid`, per esempio `ES_6297189` per Lanzarote. Non c'è nessuna catena città → regione. Ci sono anche errori nei dati: Nicosia (CY) ha `IT_2591221`, e Toscana e Firenze hanno lo stesso id.
2. **Due tipi di finestre di disponibilità.** Circa 400 sono partenze fisse, lunghe più o meno quanto `defaultDurationInDays`. Invece 16 finestre sono aperte, per esempio Lanzarote dal 26/09/2026 al 02/01/2027 con durata di 7 giorni: lì la data di inizio va calcolata. Oggi v1 propone l'intera finestra come date del viaggio, e per quei 16 prodotti è sbagliato.
3. **Area e budget servono solo a ordinare, non a escludere.** Per RF-07 non tolgono prodotti dalla lista, quindi "nessun match su area/budget" non può essere un rifiuto nel senso attuale.

Prima domanda, sul punto 3:

- 🔧 AskUserQuestion

Ok: area e budget restano soft, e la motivazione dichiara il compromesso.

Seconda domanda, da dove prendere la gerarchia (punto 1):

- 🔧 AskUserQuestion

Ok: la gerarchia sta in `geo.py`.

Terza domanda, su come calcolare le date proposte (punto 2):

- 🔧 AskUserQuestion

Ok: conta la partenza dentro il periodo.

Quarta domanda, sui test di proprietà (tocca le dipendenze):

- 🔧 AskUserQuestion

- 🔧 Bash: Find usages of chooser/geo helpers

- 🔧 AskUserQuestion

- 🔧 Bash: Check windows fall within min/max dates

Nella fixture tutte le finestre stanno dentro `[minDate, maxDate]` e tutti i prodotti attivi hanno una durata, quindi le regole sotto non scartano nessun dato reale per errore.

## Design, parte 1: algoritmo del chooser v2

L'interfaccia pubblica non cambia: `choose(products, criteria, rejected_ids, today) -> Choice | NoChoice`. Anche `usecases.py`, lo schema DB e `Criteria` restano come sono, e `intent.py` non si tocca.

**1. Filtri duri, con un ordine nuovo:** archiviati → non prenotabili → sport → date → pax → **rifiutati per ultimi**.
- Oggi i rifiutati vengono filtrati per terzi. Se l'utente rifiuta l'unico prodotto di padel, a svuotare la lista è il filtro sport, e la risposta dice "nessun viaggio per lo sport chiesto". È falso.
- Con i rifiutati in fondo, `NoChoice("rejected")` compare solo quando esistevano prodotti compatibili e sono stati scartati tutti. È la lettura corretta di RF-09.

**2. Date: nuova funzione `departure(product, period, today) -> (inizio, fine) | None`**, che sostituisce `window_for`. Le finestre si esaminano in ordine.
- **Finestra fissa** (lunghezza ≤ `duration_days`): il viaggio è la finestra intera. Va bene se l'inizio è oggi o dopo e cade nel periodo.
- **Finestra aperta**: inizio = max(inizio finestra, oggi, inizio periodo); fine = inizio + durata − 1. Va bene se la fine è entro la finestra e l'inizio è entro la fine del periodo.
- In entrambi i casi il viaggio deve stare dentro `[minDate, maxDate]`. Vale la prima partenza valida.

**3. Aderenza all'area, `area_score` da 0 a 3.** La destinazione del prodotto si risolve con `geo.area_of_destination` e si risale la catena dei genitori, che aggiungo in `PLACES`, fino al paese di `product.country`.
- **3 = dentro l'area chiesta.** Esempi: chiedi Canarie, il prodotto è a Lanzarote; chiedi Maiorca, il prodotto è a Palma; chiedi Spagna, il prodotto è in qualsiasi città spagnola.
- **2 = stessa regione.** Esempi: chiedi Lanzarote, il prodotto è a Tenerife; chiedi Palma, il prodotto è a Minorca (entrambe nelle Baleari).
- **1 = stesso paese.**
- **0 = altrove.**

I genitori stanno solo tra le voci che esistono già in `geo.py`: Lanzarote, Tenerife e Fuerteventura → Canarie; Palma → Maiorca → Baleari; Minorca e Ibiza → Baleari; Firenze e Pietrasanta → Toscana.

`geohierarchy` non lo uso. È piatto, ha errori (Nicosia, Toscana/Firenze) e usarlo richiederebbe un campo nuovo in `Product`. Registro la scelta in `decisions.md`.

**4. Ordinamento:** (−area_score, fuori budget, prezzo, id).
- Totale = prezzo × (pax o 1), confrontato con il budget.
- Tra i prodotti fuori budget vince il più economico, cioè quello più vicino al budget.
- Area prima del budget, come nell'ordine di RF-07: un Lanzarote fuori budget batte un Tenerife dentro il budget.

**5. `Choice` si arricchisce** con `area_score` e `within_budget`, che servono alla motivazione. Resta un tipo interno al dominio.

Ti torna questa parte? Dopo passo alla parte 2: motivazioni, messaggi di RF-09, microtask e test.

## Utente 16:48

si

## Agente 16:48

## Design, parte 2: motivazione, RF-09 e test

**Motivazione (RF-06): al massimo 2 frasi, generate in `chooser._reason`.**

Frase 1, l'area. Se c'è un compromesso lo dichiara (è la tua scelta "soft + dichiarato"):
- **Punteggio 3:** «È a Lanzarote, come hai chiesto.» / «È in Spagna, come hai chiesto.»
- **Punteggio 2:** «Non ho partenze compatibili a Lanzarote: questa è a Tenerife, alle Canarie.»
- **Punteggio 1:** «Non ho partenze compatibili a Lanzarote: questa è a Madrid, sempre in Spagna.»
- **Punteggio 0:** «Non ho partenze compatibili in Grecia: questa è a Madrid, in Spagna.»
- **Nessuna area chiesta:** «È a Madrid.»

Frase 2, date e budget:
- «Parte il 1 ottobre 2026, nel periodo che hai chiesto» (senza periodo: «Parte il…»).
- Poi, secondo il caso:
  - entro budget: «e costa 700 euro in totale, dentro il tuo budget di 800 euro»;
  - fuori budget: «e costa 900 euro in totale: supera il tuo budget di 800 euro, ma è la più economica compatibile»;
  - senza budget: «ed è la più economica compatibile».

Per le preposizioni aggiungo in `geo.py` una piccola funzione `where(area)`: «a Lanzarote», «in Spagna», «alle Canarie», «in Sardegna», «in Toscana». Sistema anche il «a Sardegna» di oggi.

**Messaggi di RF-09.** `say_no_match(criterion, criteria)` riceve anche i criteri e cita il valore che manca. Esempi:
- «Non trovo partenze tra il 1 e il 31 ottobre 2026: prova con un altro periodo.»
- «…per 8 persone…»
- «…di tennis…»

È un cambio di firma interno al dominio: lo chiama solo `usecases.py` (una riga). Il campo `failed_criterion` di `NoMatch` e il resto del contratto non cambiano.

**Test (tutti unittest, nessuna dipendenza nuova):**
- `tests/test_geo.py`
  - ogni destinazione della fixture ha una catena che arriva al suo paese;
  - nessun ciclo tra i genitori;
  - `where()` restituisce la preposizione giusta.
- `tests/test_chooser.py` (unitari, prodotti sintetici)
  - `departure` su finestre fisse e aperte, oggi, periodo, fine finestra, min/max;
  - `area_score` su ogni livello da 0 a 3;
  - ordine dei filtri (il caso "rifiutato l'unico padel" dà `rejected`);
  - ordinamento;
  - motivazione: ≤ 2 frasi, cita il criterio soddisfatto o il compromesso.
- `tests/test_chooser_fixture.py` (nuovo), sulla fixture reale con `TODAY=2026-09-25`:
  - **tabella** intento → prodotto atteso, con i valori ricavati eseguendo il codice e poi controllati a mano;
  - **rifiuti in sequenza**: prima, seconda e terza scelta attese;
  - **casi limite**: area assente dal catalogo (per esempio Grecia a novembre → dichiarato), budget impossibile (dichiarato), periodo senza partenze → `NoChoice("dates")`;
  - **proprietà esaustiva**: per ogni intento della tabella si rifiuta in sequenza fino a `NoChoice("rejected")`. A ogni passo si verifica che il prodotto non sia rifiutato, archiviato o non prenotabile, che non compaia mai due volte e che le date siano coerenti con finestra e periodo. Alla fine si verifica di aver visitato tutti i compatibili.
- Test di `usecases`/`say` aggiornati alle nuove frasi. Invariante RF-10 invariato.

**Microtask previsti** (TDD, un commit ciascuno):
1. `geo`: genitori + `where()`.
2. `departure()` (date).
3. `area_score` v2.
4. Ordine dei filtri e ordinamento.
5. Motivazione.
6. `say_no_match` con i valori.
7. Tabelle e proprietà sulla fixture.
8. Aggiornamento di `decisions.md` e della docstring.

Ti torna? Se sì, scrivo il piano in `docs/plans/2026-09-25-m11-chooser-v2.md` e aggiungo le decisioni a `docs/decisions.md`.

## Utente 16:49

vai

## Agente 16:49

- 🔧 Skill superpowers:writing-plans

Uso la skill writing-plans per scrivere il piano. Prima guardo il formato dei piani precedenti e i test che dipendono dalle frasi.

- 🔧 Bash: Read M2 plan format and dependent tests

- 🔧 Bash: Read say and usecase tests

Per scrivere nel piano gli id attesi reali, provo l'algoritmo approvato con un prototipo usa-e-getta nello scratchpad, sulla fixture. Nel repo non scrivo nulla.

- 🔧 Bash: Read acceptance example and period parser

- 🔧 Bash: Prototype chooser v2 on fixture in scratchpad

- 🔧 Bash: Look for non-trip products like gift cards

- 🔧 AskUserQuestion

- 🔧 Bash: Export clean copy of repo to scratchpad

- 🔧 Bash: Copy code, tests and fixture to scratchpad

Scrivo nella copia il codice che andrà nel piano.

- 🔧 Bash: Apply geo changes to scratch copy

- 🔧 Bash: Write chooser v2 and is_trip in scratch copy

- 🔧 Bash: Apply say and usecases changes to scratch copy

- 🔧 Bash: Run domain tests on scratch copy

- 🔧 Bash: Run full test suite on scratch copy

- 🔧 Bash: Run full suite on scratch copy with PYTHONPATH

You've hit your session limit · resets 6pm (Europe/Rome)

## Utente 17:04

continua

## Agente 17:04

Sto verificando il codice del piano su una copia nello scratchpad. Gli errori sopra dipendono solo dalla copia parziale (mancano Dockerfile, script e alembic). Controllo i test del dominio.

- 🔧 Bash: Run domain tests affected by the change

Tutti verdi. Ora scrivo i test nuovi nella copia e ricavo gli id attesi.

- 🔧 Bash: Compute expected fixture choices and reasons

- 🔧 Bash: Add on_date helper in scratch copy

- 🔧 Bash: Write and run v2 chooser unit tests in scratch

Tutti verdi. Ora i test per geo, say e la fixture.

- 🔧 Bash: Write and run geo hierarchy and say tests

- 🔧 Bash: Write and run fixture chooser tests in scratch

- 🔧 Bash: Run all domain tests and show diffs

- 🔧 Bash: Add fallback and usecase tests, run

- 🔧 Bash: Add is_trip test and run

- 🔧 Bash: Use dataclasses.replace in tests and rerun

Il codice e i test del piano sono verificati sulla copia: 161 test verdi. Ora scrivo il file del piano.

- 🔧 Bash: Extract code snippets for the plan

- 🔧 Write /private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-task-m11/6c47ab9d-e23a-4141-b21a-16d31d3b4d9b/scratchpad/plan_template.md

- 🔧 Bash: Render plan into docs/plans with verified code

Il piano è scritto. Lo committo; solo il file del piano.

- 🔧 Bash: Commit the M11 plan

Ho scritto il piano in `docs/plans/2026-09-25-m11-chooser-v2.md` e l'ho committato (`f93df22`). Il codice e i test che contiene li ho provati prima su una copia del repo nello scratchpad: 161 test del dominio verdi. Nel repo ho aggiunto solo il file del piano.

**Microtask** (TDD, un commit ciascuno):
1. **`geo.py`:** gerarchia statica `PARENTS` (Canarie, Baleari/Maiorca, Toscana) e le funzioni `ancestors`, `common_region`, `country_area` e `where` («alle Canarie», «in Sardegna»). Test in `tests/test_geo_hierarchy.py`.
2. **`say.py`:** `on_date` («l'8 ottobre»), preposizioni corrette, `say_no_match(criterion, criteria)` che cita il valore mancante; una riga in `usecases.py`.
3. **`is_trip`:** esclude la Weebora Gift Card (282), l'unico non-viaggio attivo nella fixture.
4. **Chooser v2:** filtri con i rifiutati per ultimi, `departure()` per finestre fisse e aperte, punteggio d'area 0-3, ordinamento (area, budget sul totale, prezzo, id), motivazione di al massimo 2 frasi che dichiara i compromessi. Firma pubblica invariata.
5. **Test sulla fixture reale:** tabella di 11 intenti con le prime tre scelte attese, casi limite (Grecia, budget di 50 €, tennis, marzo 2028) e le proprietà controllate rifiutando tutto in sequenza. Include un passo che rompe apposta l'ordine dei filtri per verificare che i test se ne accorgano.
6. **Chiusura:** decisioni in `docs/decisions.md` e verifica finale. Il diff non deve toccare `intent.py`, `models.py`, adapter, porte, superfici, migrazioni e dipendenze.

**Da sapere prima di approvare:**
- **Id attesi:** li ho ricavati eseguendo il codice sulla fixture registrata il 2026-09-25 e li ho controllati a mano. Nella demo §10.1 la prima proposta è ora Torre del Mar a 558 € in totale. Se la fixture viene rigenerata, la tabella va rivista; i test di proprietà no.
- **Weekend e finestre aperte:** un «weekend» a Lanzarote propone il prodotto 186 dal 10 al 16 ottobre. È la regola che hai scelto (partenza nel periodo, ritorno anche dopo); segnalo il caso perché può sembrare strano.
- **Prodotti senza destinazione:** per 323 e 326 l'area si ricava dal titolo. È un default che ho aggiunto io durante il prototipo e non era tra le domande: è registrato tra le decisioni del piano.

Il piano indica `superpowers:subagent-driven-development` come metodo consigliato; l'alternativa è eseguirlo io in questa sessione con una revisione finale. Ti consiglio subagent-driven: le 6 task sono sequenziali e le interfacce tra una e l'altra sono scritte nel piano, quindi un revisore per task costa poco e intercetta subito una regola applicata male. Ti torna il piano, e con quale metodo vuoi eseguirlo?

## Utente 17:23

/superpowers:test-driven-development: docs/plans/2026-09-25-m11-chooser-v2.md

## Agente 17:24

Eseguo il piano in questa sessione, in TDD, una task alla volta: prima il test, lo vedo fallire, poi il codice. Parto dalla Task 1: gerarchia in `geo.py`.

- 🔧 Bash: Add geo hierarchy test and watch it fail

- 🔧 Bash: Show failure reason

Fallisce per il motivo atteso. Ora il codice, come scritto nel piano.

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m11/vela/domain/geo.py

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m11/vela/domain/geo.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m11/vela/domain/geo.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m11/vela/domain/geo.py

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m11/vela/domain/geo.py

- 🔧 Bash: Run geo tests and full suite

- 🔧 Bash: Commit task 1

Task 1 committata. Task 2: frasi. Prima i test.

- 🔧 Bash: Add say/usecase tests and watch them fail

Falliscono tutti per i motivi attesi. Ora il codice in `say.py` e `usecases.py`.

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/task-m11/vela/domain/say.py

- 🔧 Bash: Implement say changes and run full suite

- 🔧 Bash: Commit task 2

Task 3: `is_trip`.

- 🔧 Bash: Add is_trip test and watch it fail
