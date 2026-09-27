# M19 meno chiamate per link e ordini silenziosi

- Sessione: `f41d7e06-bf67-416a-ba5e-b916796d24d0`
- Inizio: 2026-09-27 16:59

## Utente 16:59

<pasted_content id="e633">
Task M19 — Meno chiamate per link e ordini silenziosi (condizionata). Su master ci sono la
  conferma del prezzo prima del link (2026-09-26), M21-A..E, RF-83 e la cache del prezzo con
  fanout (RF-84, migrazione 0015). Il giro C-2500 con la cache (loadtest/RESULTS.md, "Dopo la
  cache del prezzo") misura 17,8 link al minuto: il limite è la quota, ogni link costa 5 chiamate
  HofJ prima del link e 1 dopo il pagamento.

  Leggi docs/roadmap.md M19, docs/decisions.md (2026-09-26 "Twist, seconda lettura" riga "Spendere
  su chi paga", "Prezzo effettivo prima del link", 2026-09-27 "Cache del prezzo con fanout" e "Load
  test dopo la cache"), docs/plans/2026-09-26-twist-seconda-lettura.md §3.4, docs/hofj-questions.md
  (domanda 10), docs/api/internal-checkout.md, docs/api/differences.md, scripts/accommodations_probe.py
  (modello per la sonda), vela/domain/purchase.py, vela/domain/booking.py, vela/domain/quotes.py,
  vela/domain/usecases.py (accept_proposal, _confirm, _await_progress), vela/domain/quota.py,
  vela/config.py, loadtest/fake_hofj, loadtest/journey.py, loadtest/RESULTS.md.

  Obiettivo, in due passi con un mio OK in mezzo.

  Passo 1, la verifica (domanda 10). Una sonda scripts/m19_probe.py su HofJ staging, lanciata da me
  dal terminale, con l'elenco delle chiamate dichiarato prima e rispettato: POST /v1/itineraries su
  un prodotto di staging, GET del totale subito, PUT customer, PUT pax, GET del totale di nuovo (5
  chiamate, un itinerario orfano, nessun pagamento e nessun booking). Esito in docs/api/ (file
  nuovo sul modello di accommodations.md), differenze in docs/api/differences.md, risposta alla
  domanda 10 e verdetto in docs/decisions.md. Poi fermati: decido io se M19 va avanti. La parte
  "PUT dopo un pagamento vero" non è verificabile su staging: dichiaralo e lasciala al primo giro
  live con la carta di test.

  Passo 2, solo con il mio OK. Job d'acquisto a 2 chiamate: itinerario + totale, poi il link; cliente
  e passeggeri passano nel job di prenotazione (4 chiamate per ordine pagato: customer, get_pax,
  set_pax, booking), con la riserva della quota per i booking ricalcolata (booking_reserve,
  purchases_per_minute e l'attesa dichiarata di RF-48). Tieni coerente la cache: il leader pubblica
  il prezzo al passo del totale, la conferma senza carrello accoda un job da 2 chiamate. Ordini
  silenziosi: un ordine in coda senza richieste di stato da N minuti scade senza spendere chiamate,
  con lo stato e la frase del say; N è una decisione aperta (proponi con l'attesa dichiarata come
  riferimento). Il finto HofJ del load test deve modellare quello che la sonda ha verificato.
  Rilancio del giro C-2500 con gli stessi parametri di RESULTS.md e nuova sezione con link al
  minuto, chiamate per link e per ordine pagato, coda alla fine; proiezione a 50.000 rifatta con il
  ritmo misurato. Docs: spec (RF-46, RF-47, RF-51, e RF-25 se nasce uno stato nuovo), rest.md e
  descrizioni MCP dove cambiano, decisions.md, roadmap M19.

  Decisioni aperte, con le mie preferenze (confermale o proponi di meglio prima di scrivere codice):
  - Sonda: 5 chiamate su staging come sopra, prodotto scelto tra quelli con allowAccommodationList
    false; nessuna chiamata in più senza chiedere.
  - Se il totale cambia dopo i passeggeri: M19 si chiude con il solo trade-off in ARCHITECTURE.md,
    niente codice.
  - Cliente e pax nel job di booking prima di POST /v1/bookings, nello stesso job, con la ripresa per
    passo di RF-27.
  - Scadenza degli ordini silenziosi: nessuna migrazione se basta lo stato esistente; se serve una
    colonna, mostrami lo schema e aspetta il mio OK.

  Vincoli:
  - Nessuna chiamata a servizi esterni oltre alle 5 della sonda, che lancio io; mai leggere .env.
  - Il chooser e le proposte restano a zero chiamate (RF-11); il link porta sempre il totale del
    carrello (RF-16).
  - I test che fissano i 5 passi del job d'acquisto (test_purchase_job, test_queue_flow,
    test_booking_job, test_loadtest_journey, test_fake_hofj_*) si aggiornano senza indebolire le
    asserzioni e si elencano in decisions.md.
  - TDD, suite e ruff verdi, commit piccoli, fermati per il mio OK prima del merge su master.
</pasted_content id="e633">

## Agente 16:59

I'll read the material you listed before proposing anything.

- 🔧 Bash: git log --oneline -3 && awk '/M19/,0' docs/roadmap.md | head -60 && echo ---- &&…

- 🔧 Bash: grep -n "^### M19" -A40 docs/roadmap.md; echo ----; sed -n 648,700p docs/decisio…

- 🔧 Bash: grep -n "M19" docs/roadmap.md | head; grep -n "^## " docs/decisions.md | tail -8…

- 🔧 Bash: sed -n 710,745p docs/roadmap.md; echo ----; sed -n 147,185p docs/plans/2026-09-2…

- 🔧 Bash: grep -n "^#" loadtest/RESULTS.md; grep -rln "17,8" docs loadtest; git branch -a …

Master has one merge more than this branch (`task/loadtest-cache`, which holds the RESULTS section you cite). I'll read it from master.

- 🔧 Bash: git diff --stat 526459e master; git show master:docs/decisions.md | awk '/Load t…

- 🔧 Bash: wc -l vela/domain/purchase.py vela/domain/booking.py vela/domain/quotes.py vela/…

- 🔧 Bash: cat vela/domain/booking.py vela/domain/quota.py; grep -n "booking_reserve\|purch…

- 🔧 Bash: cat scripts/accommodations_probe.py; sed -n 1,60p docs/api/accommodations.md; ca…

- 🔧 Bash: ls fixtures/ | head; grep -rl "allowAccommodationList" fixtures | head -3; ls lo…

- 🔧 Bash: python3 -c " import json d=json.load(open('fixtures/catalog-staging.json')) ps=d…

- 🔧 Bash: python3 -c " import json d=json.load(open('fixtures/catalog-staging.json')) ps=d…

Still reading: I'm checking which staging product the probe should use.

- 🔧 Bash: python3 -c " import json d=json.load(open('fixtures/catalog-staging.json')) prin…

Ho letto tutto quello che hai elencato. Prima di scrivere codice ti propongo l'approccio per il **Passo 1** e le risposte alle decisioni aperte.

**Prima una nota sul branch.** `task/m19` è fermo a `526459e`. `master` ha un merge in più (`task/loadtest-cache`), che contiene la voce "Load test dopo la cache" in `decisions.md` e la sezione "Dopo la cache del prezzo" in `RESULTS.md`. Le ho lette da `master`. Propongo di allinearmi con `git merge --ff-only master`, che è un avanzamento e non riscrive la storia.

## Passo 1: come lo farei

- **`scripts/m19_probe.py`**, sul modello di `accommodations_probe.py`: stessa `call()`, una chiamata ogni 12 s, stop al primo 401/403/429/5xx, risposte grezze in `probe-m19/`, chiave da `HOFJ_API_KEY` mai stampata. Le chiamate sono esattamente 5, senza `GET /v1/quota`:
  1. `POST /v1/itineraries`: prodotto **124** "Magnificent Padel in Lanzarote" (`allowAccommodationList: false`), 2026-10-08, 2 adulti, 1 camera, EUR, `locale=en`.
  2. `GET /v1/itineraries/{id}`: totale subito.
  3. `PUT .../customer`, con un corpo come quello di `PurchaseJob` e dati di test.
  4. `PUT .../pax`: i due `refId` di staging sono noti dalla sonda di M5 (`pax-1`, `pax-2`), quindi il `GET pax` non serve. Se i `refId` non combaciano, lo script si ferma e non aggiunge chiamate.
  5. `GET /v1/itineraries/{id}`: totale di nuovo.
- **Perché il 124.** È proponibile (il 118 di M5 ora è escluso come torneo). Ha l'hotel preselezionato e un totale già misurato il 27/09 per la stessa data e le stesse persone (1156 €), quindi c'è un terzo punto di confronto.
- **Cosa confronto tra la chiamata 2 e la 5.** Sia `checkout.openAmount` (l'importo del link) sia `checkout.total`, `originalTotal` e `totalPrice`. Nella sonda di M5, dopo customer e pax, `total` valeva 368 e `openAmount` 337: la differenza c'era già, ma non sappiamo se nasce dai passeggeri. È proprio il punto da chiarire.
- **Test.** Un `--dry-run` che stampa il piano senza rete, e un test che fissa esattamente 5 chiamate, in quest'ordine, senza `bookings`, `payment` o `quota`.
- **Dopo il tuo giro:**
  - `docs/api/customer-pax.md`, sul modello di `accommodations.md`;
  - le righe nuove in `differences.md` (dalla #36);
  - la risposta alla domanda 10 in `hofj-questions.md`;
  - il verdetto in `decisions.md`.
  
  Dichiaro non verificabile su staging il caso "PUT dopo un pagamento vero": resta al primo giro live con la carta di test. Poi mi fermo.

## Decisioni aperte

- **Sonda: confermo.** Le 5 chiamate come sopra, nessuna in più; se serve altro te lo chiedo.
- **Il totale cambia dopo i passeggeri: confermo.** Solo il trade-off in `ARCHITECTURE.md`, niente codice. Criterio: se cambia `openAmount` il verdetto è "no". Se cambiano solo campi che non sono importi, lo scrivo come differenza e il verdetto resta "sì".
- **Cliente e pax nel job di prenotazione: confermo.** I passi sarebbero customer → pax (`get_pax` + `set_pax` come unità unica, come oggi) → booking, ognuno salvato per la ripresa di RF-27. C'è un rischio da decidere nel Passo 2: un 4xx su `PUT customer` dopo il pagamento porta a `booking_failed` con i soldi già presi. È lo stesso percorso di un booking rifiutato, ma diventerebbe più frequente.
- **Scadenza degli ordini silenziosi: confermo "nessuna migrazione se basta".** Oggi però non vedo un campo che registri l'ultima richiesta di stato: `updated_at` lo toccano anche i job. Le due strade sono:
  - `get_order_status` aggiorna `updated_at`: niente migrazione, ma cambia il significato del campo;
  - una colonna nuova, e in quel caso ti mostro lo schema.
  
  La scelta la porto al Passo 2, insieme a N.

Mi dai l'OK per il fast-forward e per scrivere la sonda?

## Utente 17:01

ok

## Agente 17:01

- 🔧 Bash: git merge --ff-only master && git log --oneline -1 && grep -n "probe" .gitignore…

- 🔧 Bash: cat .gitignore; git ls-files | grep -i probe; grep -n "street1\|postal\|DEFAULT\…

- 🔧 Bash: grep -n "class TravelerDefaults" -A12 vela/domain/models.py; ls tests | head -80…

- 🔧 Bash: sed -n 1,40p tests/test_api_explore.py

Branch allineato a `master` (`686001f`). Scrivo prima il test della sonda (TDD).

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m19/tests/test_m19_probe.py

- 🔧 Bash: uv run python3 -m unittest tests.test_m19_probe 2>&1 | tail -3

Fails as expected (module missing). Now the script.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m19/scripts/m19_probe.py

- 🔧 Bash: uv run python3 -m unittest tests.test_m19_probe 2>&1 | tail -3 && uv run python3…

Tutto verde. Faccio il commit.

- 🔧 Bash: git add scripts/m19_probe.py tests/test_m19_probe.py && git commit -q -m "Add th…

La sonda è pronta: `scripts/m19_probe.py`, commit `b40fb8f` su `task/m19`, già allineato a `master`. Non ho fatto nessuna chiamata a HofJ. I 9 test della sonda, la suite completa (1546 test, 73 saltati) e ruff sono verdi.

**Come lanciarla** (con `HOFJ_API_KEY` nell'ambiente; lo script non stampa mai la chiave):
```bash
uv run python3 scripts/m19_probe.py --dry-run   # solo il piano, nessuna chiamata
uv run python3 scripts/m19_probe.py             # il giro vero, circa 50 s
```

**Le 5 chiamate**, sul prodotto 124, 2026-10-08, 2 adulti, 1 camera, EUR, `locale=en`, una ogni 12 s:
1. `POST /v1/itineraries`
2. `GET /v1/itineraries/{id}`
3. `PUT .../customer`
4. `PUT .../pax` con `pax-1` e `pax-2`, senza `GET pax`
5. `GET /v1/itineraries/{id}`

Niente quota, pagamento o booking; l'itinerario resta orfano.

**Quando si ferma:**
- se la creazione fallisce;
- a ogni 401, 403, 429 o 5xx.

Un 4xx su customer o pax non la ferma: la rilettura del totale parte lo stesso, sempre dentro le 5 chiamate. Un controllo interno impedisce comunque una sesta chiamata.

**Cosa produce:** le risposte grezze e `findings.json` in `probe-m19/`. Il file ha gli importi prima e dopo (`openAmount`, `total`, `originalTotal`, `totalPrice`, valuta, `checkout.status`) e l'elenco `changed` di quelli cambiati. L'ultima riga a terminale riassume l'esito.

**Cosa ho deciso da solo:**
- **Pax come li manda Vela.** Il corpo contiene solo `refId`, nome e cognome, come fa `HofJHttp.set_pax` in produzione.
- **Customer come quello di Vela.** L'indirizzo è quello di default di `TravelerDefaults`; nome, cognome, email e telefono sono di prova.
- **`probe-m19/` non è versionata**, come la cartella della sonda di M22-a. Non l'ho aggiunta a `.gitignore`: attenzione a non committarla per sbaglio.

**Il dubbio principale:** i `refId` `pax-1` e `pax-2` vengono dalla sonda di M5 su un altro prodotto. Se sul 124 fossero diversi, la chiamata 4 dà un 4xx, la rilettura parte comunque e lo scriviamo come differenza. Non aggiungo un `GET pax` senza il tuo OK.

Quando l'hai lanciata, dimmi che ha finito oppure incollami l'output. Da `probe-m19/` scrivo `docs/api/customer-pax.md`, le differenze in `differences.md` (dalla #36), la risposta alla domanda 10 e il verdetto in `decisions.md`. In quei documenti "PUT dopo un pagamento vero" risulterà non verificabile su staging, da rimandare al primo giro live con la carta di test. Poi mi fermo.

## Utente 17:05

ho messo la chiave nel .env lancia tu

## Agente 17:05

Lancio la sonda con la chiave del `.env`. Il file non lo leggo e non lo stampo: lo carica `uv run --env-file`. Forzo `HOFJ_BASE_URL` su staging, così anche se nel `.env` ci fosse un altro host le 5 chiamate vanno comunque su staging.

- 🔧 Bash: ls -la .env >/dev/null && echo ".env presente" && uv run --env-file .env env HOF…

Non ho lanciato la sonda: il permesso per il comando è stato negato, quindi a HofJ non è partita nessuna chiamata. Non riprovo per altre strade, visto che il comando caricava il `.env` e le regole del progetto e della task dicono di non aprirlo.

Puoi lanciarla tu da qui con il prefisso `!`, così l'output arriva direttamente in conversazione:

```
! uv run --env-file .env env HOFJ_BASE_URL=https://staging.api.hofj.com python3 scripts/m19_probe.py
```

- `--env-file .env` carica la chiave senza mostrarla; lo script non la stampa.
- `HOFJ_BASE_URL` è forzato su staging, anche se nel `.env` ci fosse un altro host.
- Fa le 5 chiamate dichiarate, una ogni 12 s, quindi dura circa un minuto.

Se invece preferisci che la lanci io, autorizza il comando quando te lo ripropongo.

Appena vedo l'output, leggo `probe-m19/` e scrivo `docs/api/customer-pax.md`, le differenze, la risposta alla domanda 10 e il verdetto. Poi mi fermo.

## Utente 17:06

<bash-input> uv run --env-file .env env HOFJ_BASE_URL=https://staging.api.hofj.com python3 scripts/m19_probe.py</bash-input>

<bash-stdout>host: staging.api.hofj.com brand: staging.weebora.com
 1 create    POST  /v1/itineraries                          200   7138 ms
 2 before    GET   /v1/itineraries/deimmovsayfq             200   1949 ms
 3 customer  PUT   /v1/itineraries/deimmovsayfq/customer    200   2065 ms
 4 pax       PUT   /v1/itineraries/deimmovsayfq/pax         200   1010 ms
 5 after     GET   /v1/itineraries/deimmovsayfq             200   1965 ms
chiamate HofJ: 5, esiti in probe-m19/findings.json
importi cambiati dopo customer e pax: nessuno</bash-stdout><bash-stderr></bash-stderr>

## Agente 17:07

- 🔧 Bash: python3 -c " import json;f=json.load(open('probe-m19/findings.json'));f.pop('cal…

- 🔧 Bash: python3 -c " import json a=json.load(open('probe-m19/02-before.json'))['response…

- 🔧 Bash: grep -n "Risposta\|risposta\|Esito" docs/hofj-questions.md | head; sed -n 60,97p…

- 🔧 Bash: sed -n 939,997p docs/decisions.md | cut -c1-400; sed -n 1,20p docs/hofj-question…

La sonda è andata: 5 chiamate, tutte 200, e nessun importo cambiato. Tra la lettura prima e quella dopo cambiano solo `customer` e `passengers`. Ora scrivo i documenti.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m19/docs/api/customer-pax.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/task-m19/docs/api/customer-pax.md

- 🔧 Bash: cat >> docs/api/differences.md <<'EOF'  ## Cliente e passeggeri (sonda M19, 2026…

- 🔧 Bash: cat >> docs/decisions.md <<'EOF'  ## 2026-09-27 — M19 passo 1: sonda di cliente …
