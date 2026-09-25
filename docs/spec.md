# Vela — specifica dei requisiti

Data: 2026-09-25. Stato: bozza da rivedere. Origine: `docs/brief.md` e intervista del 2026-09-25
(decisioni in `docs/decisions.md`).

## 1. Scopo e contesto

Vela permette a un viaggiatore di comprare un viaggio di padel o tennis con hotel esprimendo
un solo intento, a parole sue, all'assistente che usa già (Claude, un agente vocale
ElevenLabs, o qualunque client che parli MCP o REST). Vela non ha una homepage, non mostra
liste, non chiede di scegliere: propone un viaggio alla volta, lo prenota davvero sull'API
House of Journeys (HofJ) e restituisce il codice di prenotazione.

Il brief è una prova di 24 ore. Criteri di punteggio: prenotazione reale funzionante 25%,
architettura scalabile 25%, visione "fuori dal marketplace" 20%, metodo agentico evidenziato
15%, padronanza dell'API 10%, comunicazione 5%.

Vincoli che squalificano la consegna (dal brief, ripresi qui perché ogni requisito li rispetta):

- nessuna pagina di risultati, pannello filtri, griglia prodotti, tabella di confronto;
- il viaggiatore non riceve mai una lista tra cui scegliere;
- l'attenzione del viaggiatore non è sullo schermo per la maggior parte dell'interazione;
- l'intero acquisto è raggiungibile da un solo intento espresso in parole del viaggiatore;
- Vela non è una destinazione: arriva dove il viaggiatore è già;
- deve funzionare per chi non ha occhi, schermo o pazienza.

## 2. Glossario

| Termine | Significato |
|---|---|
| Intento | Testo libero del viaggiatore ("un weekend di padel a ottobre in Spagna, siamo in due, max 800 euro") e i criteri strutturati che Vela ne estrae. |
| Proposta | Un solo viaggio scelto da Vela per un intento: prodotto HofJ, date, pax, prezzo "a partire da", motivazione. |
| Ordine | L'acquisto avviato con il "sì" a una proposta: itinerario HofJ, totale reale, link di pagamento, stato, codice di prenotazione. |
| Superficie | Un adapter che espone i casi d'uso del dominio a un client esterno: REST, MCP, webhook Stripe, A2A. |
| Porta | Interfaccia del dominio verso un servizio esterno (HofJ, Stripe) con più implementazioni (reale, replay, fake). |
| Agente del viaggiatore | Il client che parla con il viaggiatore e chiama Vela: Claude via MCP, agente vocale ElevenLabs via MCP, o un client REST. |
| Replay | Modalità in cui le porte rispondono con risposte registrate dall'API reale, senza chiamate esterne. |

## 3. Attori e superfici

- **Viaggiatore.** Parla in italiano o inglese con il proprio agente. Non vede mai Vela.
- **Agente del viaggiatore.** Traduce la conversazione in chiamate ai casi d'uso di Vela e
  legge al viaggiatore le risposte. Ha già il proprio modello linguistico.
- **Vela core.** Un servizio FastAPI che espone gli stessi cinque casi d'uso su REST e MCP.
- **House of Journeys.** Unica fonte di catalogo, disponibilità, itinerari e prenotazioni.
- **Stripe (test mode).** Incasso tramite Payment Link e notifica via webhook.
- **Giudici.** Usano l'URL live, leggono il repo, lanciano il load test, guardano il video.

## 4. Requisiti funzionali

### 4.1 Intento

- **RF-01** Vela accetta un intento come testo libero, in italiano o in inglese, più un profilo
  viaggiatore opzionale (nome, cognome, email, telefono, numero di persone).
- **RF-02** Da un intento Vela estrae: sport (padel, tennis), area geografica (paese, regione o
  città, se presente), periodo (data o intervallo, mese, stagione, "weekend"), numero di
  persone, budget totale massimo, lingua dell'intento.
- **RF-03** L'estrazione avviene con un parser deterministico (regole e dizionari it/en). Se il
  parser non ricava almeno lo sport oppure il periodo, e la variabile `ANTHROPIC_API_KEY` è
  presente, Vela invoca un modello piccolo e veloce (Claude Haiku 4.5) per compilare lo stesso
  schema. Se la variabile manca, il fallback è disattivato e non produce errore.
- **RF-04** Se dopo l'estrazione manca ancora un'informazione indispensabile, Vela restituisce
  una sola domanda chiara per l'agente da porre al viaggiatore. Indispensabili: sport oppure
  periodo (almeno uno), numero di persone (default 1 se il profilo lo indica, altrimenti chiesto).
- **RF-05** Ogni intento è persistito con un identificativo e i criteri estratti, così che
  proposte e rifiuti successivi vi si riferiscano.

### 4.2 Proposta

- **RF-06** Per un intento Vela restituisce sempre **una sola** proposta: titolo del viaggio,
  destinazione, struttura alberghiera, date proposte, numero di persone, prezzo "a partire da"
  con valuta, una motivazione di una o due frasi che lega la scelta all'intento.
- **RF-07** La scelta è deterministica: si scartano i prodotti archiviati, non prenotabili,
  già rifiutati per lo stesso intento, con sport diverso, con date non compatibili con
  `minDate`/`maxDate` e disponibilità, con pax fuori da `minPax`/`maxPax`; tra i restanti si
  ordina per aderenza all'area geografica, rispetto del budget, prezzo crescente.
- **RF-08** Il viaggiatore può rifiutare una proposta con un motivo in testo libero. Vela
  aggiorna i criteri dell'intento con il motivo ("troppo caro" abbassa il budget, "più a sud"
  o "a novembre" cambiano area o periodo) e restituisce un'altra proposta singola.
- **RF-09** Non esiste un limite al numero di proposte per intento. Quando non resta nessun
  prodotto compatibile, Vela dice quale criterio non riesce a soddisfare e chiede di
  riformulare l'intento; non propone mai un prodotto già rifiutato.
- **RF-10** Nessuna risposta di Vela contiene mai più di un prodotto. Le risposte non
  contengono elenchi di alternative, tabelle, né inviti a "scegliere tra".
- **RF-11** Le proposte si leggono solo dal catalogo in cache locale (sezione 4.6). Nessuna
  proposta provoca chiamate a HofJ.

### 4.3 Accettazione e dati del viaggiatore

- **RF-12** Il viaggiatore accetta una proposta tramite il proprio agente. All'accettazione Vela
  richiede, se non già nel profilo: nome, cognome, email, telefono del viaggiatore principale;
  nome e cognome di ogni altro partecipante. Nient'altro viene chiesto.
- **RF-13** Indirizzo, paese e altri campi richiesti da HofJ ma non chiesti al viaggiatore sono
  compilati con valori di default dichiarati nella configurazione e documentati in
  `ARCHITECTURE.md` come vincolo del prototipo.
- **RF-14** All'accettazione Vela crea l'itinerario HofJ (`POST /v1/itineraries` con prodotto,
  data di inizio, adulti, camere, valuta EUR), imposta il cliente (`PUT .../customer`), legge
  gli slot pax (`GET .../pax`) e li aggiorna preservando ogni `refId` (`PUT .../pax`).
- **RF-15** Vela accetta la sistemazione di default dell'itinerario. Non sceglie hotel
  alternativi né aggiunge attività: il prodotto HofJ è già "esperienza + hotel".
- **RF-16** Vela legge il totale reale dall'itinerario. Se differisce dal prezzo "a partire da"
  della proposta, la risposta di accettazione lo dichiara esplicitamente prima del link di
  pagamento. Il link porta sempre il totale reale.
- **RF-17** Se la creazione dell'itinerario fallisce per un errore del prodotto (4xx/5xx da
  HofJ riconducibile al prodotto, non alla quota o alla rete), Vela segna il prodotto come non
  prenotabile, sceglie la proposta successiva per lo stesso intento e la restituisce con la
  stessa forma di RF-06, senza esporre l'errore al viaggiatore. L'agente riceve un flag che
  indica che la proposta è cambiata.

### 4.4 Pagamento

- **RF-18** Il pagamento avviene con uno Stripe Payment Link (Checkout) sull'account Stripe di
  test del progetto, per l'importo totale reale in EUR, con `metadata` contenente l'id
  dell'ordine e dell'itinerario HofJ.
- **RF-19** La risposta di accettazione contiene l'URL del link, l'importo, l'id ordine e una
  frase pronta da leggere al viaggiatore. È compito dell'agente consegnare il link nel canale
  del viaggiatore (messaggio, SMS, lettura ad alta voce dell'importo con link inviato via
  testo).
- **RF-20** Vela riceve la conferma di pagamento tramite webhook Stripe firmato
  (`checkout.session.completed`), verifica la firma con `STRIPE_WEBHOOK_SECRET`, aggiorna
  l'ordine a `paid_pending_booking` e avvia la prenotazione. Eventi duplicati non producono
  effetti doppi.
- **RF-21** Vela non riceve, memorizza né inoltra dati di carta. Il link scade dopo 24 ore;
  un ordine con link scaduto passa a `expired`.
- **RF-22** Un solo pagamento per ordine, tipo `full`. Nessun pagamento a rate, nessun promo
  code, nessuna valuta diversa da EUR.

### 4.5 Prenotazione e consegna del codice

- **RF-23** Dopo il pagamento Vela chiama `POST /v1/bookings` con `itineraryId`,
  `paymentType: "full"`, `paymentIntentId` e `paymentStatus` ricevuti da Stripe. Il codice
  restituito viene salvato e l'ordine passa a `confirmed`.
- **RF-24** La chiamata di prenotazione è ripetibile: HofJ tratta `POST /v1/bookings` come
  upsert per itinerario, e Vela ripete la chiamata su errore di rete o 5xx con backoff, fino a
  un numero massimo configurato, poi marca l'ordine `booking_failed` con il motivo.
- **RF-25** L'agente del viaggiatore ottiene il codice interrogando lo stato dell'ordine.
  La risposta contiene lo stato, il codice di prenotazione se presente, e una frase pronta da
  leggere ("La tua prenotazione è confermata, codice R-789012"). Stati possibili:
  `awaiting_payment`, `paid_pending_booking`, `confirmed`, `booking_failed`, `expired`.
- **RF-26** Il codice di prenotazione resta disponibile tramite `get_order_status` senza
  limite di tempo, così il viaggiatore può richiederlo al proprio agente anche in seguito.
  L'invio del codice via email non è nelle 24 ore (richiederebbe un servizio non concordato)
  ed è elencato in `ARCHITECTURE.md` tra i prossimi passi.
- **RF-27** All'avvio Vela riprende gli ordini in stato `paid_pending_booking` e completa la
  prenotazione (RF-23, RF-24).

### 4.6 Catalogo e sincronizzazione

- **RF-28** Vela mantiene in Postgres una copia del catalogo HofJ limitata ai prodotti di
  padel e tennis non archiviati, con: id, titolo, slug, descrizione breve, categoria,
  destinazione, venue, hotel di default, prezzo e valuta, `minPax`/`maxPax`,
  `minDate`/`maxDate`, disponibilità, durata, `updatedAt` di HofJ, JSON grezzo del dettaglio,
  `fetched_at`, `bookable` e `bookable_checked_at`.
- **RF-29** Solo il job di sincronizzazione chiama `GET /v1/products` e
  `GET /v1/products/{id}` (locale `it`, brand da configurazione). Il job scorre la lista con
  `limit=100` e `cursor`, poi richiede il dettaglio solo dei prodotti nuovi o con `updatedAt`
  cambiato.
- **RF-30** Il job gira all'avvio se il catalogo è vuoto o più vecchio di 6 ore, poi ogni
  6 ore. Con più istanze, un advisory lock Postgres garantisce un solo sync alla volta. Un
  comando `python -m vela.sync` lo forza a mano.
- **RF-31** Il job scrive per lotti: un'interruzione lascia un catalogo parziale ma coerente.
- **RF-32** Il repo contiene `fixtures/catalog.json`, snapshot delle risposte di catalogo
  registrate dall'API reale, senza credenziali. Serve alla modalità replay, all'avvio a
  freddo senza consumare quota e alla demo se la quota è esaurita. Un comando lo rigenera.

### 4.7 Prodotti non prenotabili

- **RF-33** Un prodotto diventa `bookable=false` al primo fallimento di
  `POST /v1/itineraries` riconducibile al prodotto (RF-17). Il chooser lo esclude da quel
  momento per tutti gli intenti.
- **RF-34** Dopo 24 ore dal `bookable_checked_at` il prodotto torna candidato: il primo nuovo
  tentativo lo riconferma o lo riabilita.
- **RF-35** Vela non verifica preventivamente la prenotabilità dell'intero catalogo: costerebbe
  una quota per prodotto.

### 4.8 Gestione della quota HofJ

- **RF-36** Ogni chiamata a HofJ passa da un guardiano della quota: contatore condiviso in
  Postgres per finestra mobile di 60 secondi, inizializzato da `GET /v1/quota` all'avvio e
  aggiornato a ogni chiamata (inclusa quella di quota).
- **RF-37** Quando la finestra è quasi esaurita (soglia configurabile), le chiamate non urgenti
  (sync) attendono la fine della finestra; le chiamate urgenti (accettazione, prenotazione)
  restano possibili fino all'esaurimento, poi falliscono con un errore esplicito che l'agente
  può leggere al viaggiatore ("riprovo tra un minuto") e Vela riprova da sé per la
  prenotazione (RF-24).
- **RF-38** Una risposta 429 da HofJ aggiorna il contatore e non viene mai ripetuta
  immediatamente.

### 4.9 Superfici: casi d'uso, REST, MCP

- **RF-39** Il dominio espone cinque casi d'uso, identici su ogni superficie:

  | Caso d'uso | Ingresso | Uscita |
  |---|---|---|
  | `create_intent` | testo, profilo opzionale | id intento, criteri estratti, oppure la domanda mancante (RF-04) |
  | `get_proposal` | id intento | una proposta (RF-06) oppure "niente di compatibile" (RF-09) |
  | `reject_proposal` | id proposta, motivo | la proposta successiva (RF-08) |
  | `accept_proposal` | id proposta, dati viaggiatore mancanti | id ordine, totale reale, link di pagamento, frase da leggere; oppure una proposta sostitutiva (RF-17) |
  | `get_order_status` | id ordine | stato, codice, frase da leggere (RF-25) |

- **RF-40** REST: `POST /v1/intents`, `GET /v1/intents/{id}/proposal`,
  `POST /v1/proposals/{id}/reject`, `POST /v1/proposals/{id}/accept`,
  `GET /v1/orders/{id}`. JSON, errori in formato RFC 7807, `GET /health` senza autenticazione.
- **RF-41** MCP: server remoto con trasporto Streamable HTTP su `/mcp`, cinque tool con gli
  stessi nomi di RF-39, descrizioni scritte per un modello che parla con un umano a voce:
  ogni tool dice esplicitamente di non elencare alternative e di leggere la frase pronta.
  Compatibile con Claude (claude.ai, Claude Desktop) ed ElevenLabs Conversational AI.
- **RF-42** Ogni risposta dei casi d'uso include un campo `say`: una frase in lingua
  dell'intento, pronta per essere letta ad alta voce, senza markdown, senza URL letti per
  esteso (l'URL sta in un campo separato).
- **RF-43** L'autenticazione delle superfici REST e MCP è un bearer token statico da
  configurazione (`VELA_API_TOKEN`), sufficiente per il prototipo. Il webhook Stripe usa la
  firma Stripe. `/health` è pubblico.
- **RF-44** A2A (Agent2Agent) non è nelle 24 ore. Il dominio non deve impedirlo: le superfici
  sono adapter separati che chiamano le stesse funzioni, e `ARCHITECTURE.md` descrive come
  aggiungere l'adapter A2A (agent card, mapping dei task sui cinque casi d'uso). Se resta
  tempo, si implementa come quarta superficie senza toccare il dominio.

## 5. Requisiti non funzionali

- **RNF-01 Stateless.** Il processo non tiene stato tra richieste: intenti, proposte, ordini,
  catalogo, contatore quota e lock stanno in Postgres. Più istanze su Render funzionano senza
  configurazione aggiuntiva.
- **RNF-02 Un processo.** Una sola app FastAPI serve REST, MCP e webhook; i task post-pagamento
  girano in background nello stesso processo (RF-27 copre il crash).
- **RNF-03 Idempotenza.** Webhook duplicati, ripetizioni di `POST /v1/bookings`, doppio
  `accept` sulla stessa proposta non creano ordini o prenotazioni doppie.
- **RNF-04 Timeout.** Le chiamate a HofJ hanno timeout di 15 secondi; il caso d'uso
  `accept_proposal` risponde entro 30 secondi o restituisce un errore leggibile.
- **RNF-05 Latenza.** `create_intent`, `get_proposal`, `reject_proposal`, `get_order_status`
  non chiamano servizi esterni (eccetto il fallback LLM di RF-03) e rispondono sotto i
  500 ms al 95° percentile in modalità replay sul load test.
- **RNF-06 Osservabilità.** Log strutturati JSON su stdout con id intento/ordine, chiamate
  HofJ con esito e quota residua. `GET /health` riporta stato DB, età del catalogo, quota
  residua nota.
- **RNF-07 Sicurezza.** Segreti solo in variabili d'ambiente; `.env` in `.gitignore` e mai
  letto, stampato o loggato dagli agenti. Nessun dato di carta. Dati personali limitati a
  RF-12 e cancellabili con un comando.
- **RNF-08 Modalità replay.** `VELA_UPSTREAM_MODE=replay` sostituisce HofJ e Stripe con
  implementazioni che leggono `fixtures/` e simulano il pagamento; usata da test e load test.
- **RNF-09 Test.** `python3 -m unittest discover -s tests` copre parser, chooser,
  orchestratore (con porte fake), webhook, superfici REST e MCP. Nessun test chiama servizi
  esterni.
- **RNF-10 Load test.** `loadtest/locustfile.py` esercita il flusso completo in replay contro
  l'URL live o locale. `loadtest/RESULTS.md` riporta utenti simulati, RPS, p50/p95/p99, errori,
  più i numeri reali di `GET /v1/quota` (limite per minuto) e la latenza misurata di un
  flusso di prenotazione reale.
- **RNF-11 Deploy.** Dockerfile, deploy su Render con Postgres gestito, migrazioni al boot,
  variabili d'ambiente documentate in `README.md`.

## 6. Vincoli di progetto

- 24 ore reali già iniziate, una persona che delega agli agenti AI; ogni sessione finisce in
  `agent-log/` (rinominato da `agents-log/` con `git mv` per rispettare il brief).
- Stack: Python 3, FastAPI, Postgres, Render. Nessuna dipendenza nuova senza accordo.
- Prodotto: solo padel o tennis con hotel. Voli, transfer, auto e altri componenti sono
  esclusi e costerebbero punti.
- Nessuna interfaccia utente propria: niente pagine di ricerca, liste, filtri, griglie,
  confronti. La sola pagina web coinvolta è il Checkout di Stripe.
- Lingue degli intenti: italiano e inglese. Catalogo HofJ in locale `it`.
- Dati personali: solo quelli di RF-12.
- Variabili d'ambiente: `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND`, `DATABASE_URL`,
  `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `VELA_API_TOKEN`, `VELA_UPSTREAM_MODE`,
  `ANTHROPIC_API_KEY` (opzionale), `VELA_PUBLIC_URL`.
- Chiamate esterne a pagamento o con limiti (HofJ, Stripe, Anthropic) vanno dichiarate prima
  di eseguirle, con il numero di chiamate previsto.

## 7. Fuori scope

Voli, transfer, noleggio auto; interfaccia web o app propria; scelta di hotel alternativi o
attività aggiuntive nell'itinerario; pagamento a rate, promo code, valute diverse da EUR;
autenticazione dell'utente finale HofJ (`X-End-User-Authorization`) e quindi `GET /v1/trips`;
cancellazioni e modifiche dopo la prenotazione; multi-tenant o più brand; A2A entro le 24 ore
(RF-44).

## 8. Rischi e verifiche della prima ora

Prima di scrivere il dominio, con al massimo cinque chiamate a HofJ e nessuna a Stripe oltre
la creazione di un link di test:

| Rischio | Verifica | Se fallisce |
|---|---|---|
| La chiave non è valida o non è di profilo interno: `POST /v1/itineraries` risponde 403 | `GET /v1/quota` e una `POST /v1/itineraries` sul prodotto dell'esempio della documentazione (`t0054825`) | Chiedere la chiave interna a chi ha scritto il brief; costruire tutto in replay nel frattempo |
| Catalogo grande o lista povera di campi: il sync iniziale dura troppo | `GET /v1/products?limit=100` e un `GET /v1/products/{id}`: contare i prodotti padel/tennis e confrontare i campi | Ridurre i campi estratti alla lista, dettagli solo in accettazione |
| HofJ non accetta un pagamento fatto sul nostro Stripe (`POST /v1/bookings` rifiuta o ignora `paymentIntentId`) | Un booking completo su un itinerario di test dopo un Checkout di test | Fallback: pagina minima con Stripe.js che conferma il `client_secret` restituito da `POST .../payment` di HofJ; il link a quella pagina prende il posto del Payment Link |
| Il limite di quota è molto basso | Leggere `limitPerMinute` da `/v1/quota` | Alzare la soglia di attesa del sync e abbassare la frequenza |
| ElevenLabs non regge il flusso con il link | Prova con un agente ElevenLabs collegato all'MCP | Demo vocale fino al link, link consegnato via testo, conferma finale a voce |

## 9. Consegne e struttura del repo

Consegne dal brief: URL live su Render; repository pubblico con storia; `ARCHITECTURE.md`
(decisioni, compromessi, prossimi passi, inclusi A2A e email); `agent-log/`; load test
eseguibile con numeri; video di 3-5 minuti con un acquisto reale completo (una parte con
Claude, una con ElevenLabs a voce).

Struttura prevista:

```
vela/domain/      intent.py chooser.py orders.py models.py
vela/ports/       hofj.py payments.py
vela/adapters/    hofj_http.py hofj_replay.py stripe_links.py stripe_fake.py db.py
vela/surfaces/    rest.py mcp.py webhooks.py
vela/app.py       vela/sync.py
fixtures/         catalog.json
loadtest/         locustfile.py RESULTS.md
tests/
docs/             brief.md spec.md decisions.md agents-log.md
agent-log/
ARCHITECTURE.md README.md Dockerfile
```

## 10. Criteri di accettazione end-to-end

1. Con `VELA_UPSTREAM_MODE=live`, da Claude collegato all'MCP: l'intento "un weekend di
   padel in Spagna a ottobre, siamo in due, massimo 800 euro" produce una proposta singola;
   "troppo caro" ne produce un'altra singola più economica; "sì" produce un link Stripe;
   pagando con la carta di test `4242 4242 4242 4242` lo stato dell'ordine diventa
   `confirmed` con il codice di prenotazione reale restituito da `POST /v1/bookings`.
2. Lo stesso flusso funziona da un agente vocale ElevenLabs, a voce, con il link consegnato
   per testo.
3. Lo stesso flusso funziona via REST con `curl`, con il token di RF-43.
4. Un prodotto che fallisce al carrello non interrompe il flusso: il viaggiatore riceve una
   proposta diversa senza vedere l'errore.
5. Con `VELA_UPSTREAM_MODE=replay`, `python3 -m unittest discover -s tests` passa e il load
   test gira senza toccare HofJ o Stripe; `GET /v1/quota` reale non cambia durante il load
   test.
6. Nessuna risposta di Vela, su nessuna superficie, contiene più di un prodotto.
7. `git grep` sulle chiavi note non trova nulla nel repo; `.env` non è mai stato letto dagli
   agenti (verificabile in `agent-log/`).
