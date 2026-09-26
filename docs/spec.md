# Vela — specifica dei requisiti

Data: 2026-09-25. Stato: bozza da rivedere; RF-43 e RNF-09 aggiornati il 2026-09-25 con la
roadmap (`docs/roadmap.md`); §4.10, RF-14, RF-16, RF-17, RF-19, RF-25, RF-27, RF-37, RF-39,
RF-41, RNF-04, RNF-05, RNF-10, RNF-12, RNF-13 e §10.1 aggiornati il 2026-09-25 per il twist
(50.000 viaggiatori in dieci minuti). RF-01..04, RF-08, RF-09, RF-39..42 e §4.11 (RF-52..55)
aggiornati il 2026-09-26 per il contratto agente-tool (roadmap M17). RF-28..32, §6, §7 e RF-56
aggiornati il 2026-09-26 per il catalogo multi-brand (roadmap M10). Origine: `docs/brief.md` e
intervista del 2026-09-25 (decisioni in `docs/decisions.md`).

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
- **Stripe (test mode).** Incasso tramite Checkout Session sull'account fornito da HofJ;
  pagamento verificato per interrogazione e chiuso con `POST /v1/bookings` (nessun webhook).
- **Giudici.** Usano l'URL live, leggono il repo, lanciano il load test, guardano il video.

## 4. Requisiti funzionali

### 4.1 Intento

- **RF-01** Vela accetta un intento come testo libero, in italiano o in inglese, più un profilo
  viaggiatore opzionale (nome, cognome, email, telefono, numero di persone) e i campi
  strutturati opzionali di RF-52 (sport, area, periodo, persone, budget).
- **RF-02** Da un intento Vela estrae: sport (`padel`, `tennis`, oppure `any` quando il
  viaggiatore dice che gli va bene l'uno o l'altro), area geografica (paese, regione o
  città, se presente), periodo (data o intervallo, mese, stagione, "weekend"), numero di
  persone, budget totale massimo, lingua dell'intento.
- **RF-03** L'estrazione avviene con un parser deterministico (regole e dizionari it/en), dopo
  i campi strutturati passati dall'agente (precedenza di RF-53). Se dopo campi e parser manca
  ancora lo sport, e la variabile `ANTHROPIC_API_KEY` è presente, Vela invoca un modello
  piccolo e veloce (Claude Haiku 4.5) per compilare lo stesso schema. Se la variabile manca, il
  fallback è disattivato e non produce errore.
- **RF-04** Se dopo l'estrazione manca ancora un'informazione indispensabile, Vela restituisce
  una sola domanda chiara per l'agente da porre al viaggiatore, e nessun intento viene
  salvato. Indispensabili: lo sport, sempre ("Padel o tennis?"; "indifferente" o "tutti e due"
  è una risposta valida e vale `any`, cioè nessun filtro sport), poi il numero di persone
  (default 1 se il profilo lo indica, altrimenti chiesto). Se mancano entrambi si chiede prima
  lo sport. Il periodo non è indispensabile: senza periodo il chooser considera tutte le date
  disponibili.
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
- **RF-08** Il viaggiatore può rifiutare una proposta con un motivo in testo libero, più i
  campi strutturati di RF-52 e una direzione (`north`, `south`). Vela aggiorna i criteri
  dell'intento con campi e motivo, con la precedenza di RF-53 ("troppo caro" abbassa il budget,
  "più a sud" o "a novembre" cambiano area o periodo, `direction` sposta l'area con `geo.move`)
  e restituisce un'altra proposta singola. Ogni cambiamento dopo una proposta passa da qui
  (RF-55).
- **RF-09** Non esiste un limite al numero di proposte per intento. Quando non resta nessun
  prodotto compatibile, Vela dice quale criterio non riesce a soddisfare e chiede quale
  criterio cambiare; non propone mai un prodotto già rifiutato. Il cambiamento passa da
  `reject_proposal` sull'ultima proposta rifiutata (RF-55); solo un "niente di compatibile"
  restituito da `get_proposal` prima di ogni proposta si risolve con un nuovo `create_intent`.
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
- **RF-14** Il job d'acquisto (RF-46) crea l'itinerario HofJ (`POST /v1/itineraries` con prodotto,
  data di inizio, adulti, camere, valuta EUR), imposta il cliente (`PUT .../customer`), legge
  gli slot pax (`GET .../pax`) e li aggiorna preservando ogni `refId` (`PUT .../pax`).
- **RF-15** Vela accetta la sistemazione di default dell'itinerario. Non sceglie hotel
  alternativi né aggiunge attività: il prodotto HofJ è già "esperienza + hotel".
- **RF-16** Vela legge il totale reale dall'itinerario. Se differisce dal prezzo "a partire da"
  della proposta, la risposta di stato (RF-25) lo dichiara esplicitamente prima del link di
  pagamento. Il link porta sempre il totale reale.
- **RF-17** Se la creazione dell'itinerario fallisce per un errore del prodotto (4xx/5xx da
  HofJ riconducibile al prodotto, non alla quota o alla rete), il job d'acquisto segna il
  prodotto come non prenotabile, sceglie la proposta successiva per lo stesso intento e porta
  l'ordine in stato `replaced` con la proposta sostitutiva. `get_order_status` la restituisce
  con la stessa forma di RF-06 e un flag `proposal_changed`, senza esporre l'errore al
  viaggiatore. Un nuovo `accept_proposal` sulla proposta sostitutiva crea un ordine che entra
  in testa alla coda (posizione ereditata dall'ordine sostituito).

### 4.4 Pagamento

- **RF-18** Il pagamento avviene con uno Stripe Payment Link (Checkout) sull'account Stripe di
  test del progetto, per l'importo totale reale in EUR, con `metadata` contenente l'id
  dell'ordine e dell'itinerario HofJ.
- **RF-19** La risposta di `get_order_status` per un ordine `awaiting_payment` contiene l'URL
  del link, l'importo, l'id ordine e una frase pronta da leggere al viaggiatore. La risposta di
  accettazione contiene solo id ordine, stato `queued`, attesa stimata e frase (RF-45). Vela manda
  il link con il riepilogo via SMS al telefono del viaggiatore principale appena l'ordine è
  `awaiting_payment` (decisione del 2026-09-26, `docs/sms.md`); l'agente non interroga lo stato
  di sua iniziativa e chiama `get_order_status` solo quando il viaggiatore lo chiede.
- **RF-20** Vela verifica il pagamento per interrogazione, senza webhook: un job del worker legge
  con la chiave Stripe fornita da HofJ lo stato della Checkout Session di ogni ordine
  `awaiting_payment` (ogni 60 s, e subito quando il viaggiatore chiede lo stato). A pagamento
  riuscito, con importo e valuta dell'ordine, l'ordine passa a `paid_pending_booking` e parte la
  prenotazione, che chiude il pagamento su HofJ inoltrando `paymentIntentId` e `paymentStatus` a
  `POST /v1/bookings`. Una verifica ripetuta non produce effetti doppi (decisione del
  2026-09-25, M5).
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
- **RF-25** L'agente del viaggiatore ottiene link e codice interrogando lo stato dell'ordine.
  La risposta contiene lo stato, l'attesa stimata se `queued` (RF-48), link e importo se
  `awaiting_payment`, la proposta sostitutiva se `replaced` (RF-17), il codice di prenotazione
  se `confirmed`, il motivo leggibile se `failed` o `booking_failed`, e una frase pronta da
  leggere ("La tua prenotazione è confermata, codice R-789012"). Stati possibili: `queued`,
  `awaiting_payment`, `paid_pending_booking`, `confirmed`, `replaced`, `cancelled`, `failed`,
  `booking_failed`, `expired`.
- **RF-26** Il codice di prenotazione resta disponibile tramite `get_order_status` senza
  limite di tempo, così il viaggiatore può richiederlo al proprio agente anche in seguito.
  L'invio del codice via email non è nelle 24 ore (richiederebbe un servizio non concordato)
  ed è elencato in `ARCHITECTURE.md` tra i prossimi passi.
- **RF-27** All'avvio Vela riprende gli ordini in stato `paid_pending_booking` e completa la
  prenotazione (RF-23, RF-24), e riprende i job d'acquisto degli ordini `queued` dal primo
  passo non completato (RF-46), senza ricreare itinerari già creati.
- **RF-57** Quando l'ordine è `confirmed`, Vela manda al viaggiatore principale un SMS con
  titolo, date, persone e codice di prenotazione. L'esito dell'invio di un SMS non cambia mai
  lo stato dell'ordine (decisione del 2026-09-26, `docs/sms.md`).

### 4.6 Catalogo e sincronizzazione

- **RF-28** Vela mantiene in Postgres una copia del catalogo HofJ limitata ai prodotti di
  padel e tennis non archiviati, con: id, brand, titolo, slug, descrizione breve, categoria,
  destinazione, venue, hotel di default, prezzo e valuta, `minPax`/`maxPax`,
  `minDate`/`maxDate`, disponibilità, durata, `updatedAt` di HofJ, JSON grezzo del dettaglio,
  `fetched_at`, `bookable` e `bookable_checked_at`. Su HofJ ogni brand ha un catalogo separato:
  la configurazione `HOFJ_BRANDS` associa a ogni sport il suo brand (padel = Weebora, tennis =
  Terrarossa; su staging `staging.weebora.com` e `staging.tennis.weebora.com`), e tutti i brand
  finiscono nella stessa tabella. Lo sport di un prodotto si ricava dal suo brand; la ricerca
  di `padel`/`tennis` nei testi del prodotto resta solo come riserva per un brand fuori dalla
  mappa. L'id HofJ resta la chiave del prodotto: se lo stesso id arrivasse da due brand, il
  sync si ferma con un errore esplicito. Il chooser propone solo viaggi in cui si gioca: esclude
  le gift card di ogni brand e la categoria dei pacchetti evento (guardare un torneo,
  hospitality), identificata per nome di categoria.
- **RF-29** Solo il job di sincronizzazione chiama `GET /v1/products` e
  `GET /v1/products/{id}` (locale `it`), una volta per ogni brand di `HOFJ_BRANDS` con
  `?brand=<brand>`. Per ogni brand il job scorre la lista con `limit=100` e `cursor`, poi
  richiede il dettaglio solo dei prodotti nuovi o con `updatedAt` cambiato.
- **RF-30** Il job gira all'avvio se il catalogo è vuoto o più vecchio di 6 ore, poi ogni
  6 ore. Con più istanze, un advisory lock Postgres garantisce un solo sync alla volta. Un
  comando `python -m vela.sync` lo forza a mano.
- **RF-31** Il job scrive per lotti: un'interruzione lascia un catalogo parziale ma coerente.
  Un prodotto sparito dalla lista di un brand viene archiviato (mai cancellato) solo tra i
  prodotti di quel brand; un brand il cui sync fallisce non archivia nulla e non tocca gli
  altri.
- **RF-32** Il repo contiene una fixture per ogni coppia (host, brand) (`fixtures/catalog*.json`),
  snapshot delle risposte di catalogo registrate dall'API reale, senza credenziali. Servono
  alla modalità replay (che carica tutti i brand dell'host) e ai test; in live il catalogo
  viene dal sync. Un comando le rigenera con lo stesso codice del sync.
- **RF-56** Ogni chiamata del carrello (RF-14) e della prenotazione (RF-23) di un ordine parte
  con il brand del prodotto dell'ordine, ricavato da ordine → prodotto → `brand` a ogni
  esecuzione del job, così il brand sopravvive a riavvii (RF-27) e retry (RF-24). Un prodotto
  senza brand registrato usa il brand del suo sport in `HOFJ_BRANDS`.

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
- **RF-37** Il guardiano è lo scheduler della quota di RF-47: nessuna chiamata a HofJ parte
  senza un blocco di budget prenotato nella finestra corrente. Le chiamate di prenotazione
  degli ordini pagati hanno una riserva garantita per finestra; i job d'acquisto usano il
  resto in ordine di arrivo; il sync gira solo a coda vuota e sopra la soglia. Nessuna
  chiamata del viaggiatore fallisce per quota esaurita: l'ordine aspetta in coda e l'attesa è
  dichiarata (RF-48).
- **RF-38** Una risposta 429 da HofJ aggiorna il contatore e non viene mai ripetuta
  immediatamente.

### 4.9 Superfici: casi d'uso, REST, MCP

- **RF-39** Il dominio espone cinque casi d'uso, identici su ogni superficie:

  | Caso d'uso | Ingresso | Uscita |
  |---|---|---|
  | `create_intent` | testo, profilo opzionale, campi strutturati opzionali (RF-52) | id intento, criteri estratti, oppure la domanda mancante (RF-04) |
  | `get_proposal` | id intento | una proposta (RF-06) oppure "niente di compatibile" (RF-09) |
  | `reject_proposal` | id proposta, motivo, campi strutturati e direzione opzionali (RF-52) | la proposta successiva (RF-08) oppure "niente di compatibile" con l'id della proposta da cui ripartire (RF-55) |
  | `accept_proposal` | id proposta, dati viaggiatore mancanti | id ordine, stato `queued`, posizione e attesa stimata, frase da leggere (RF-45) |
  | `get_order_status` | id ordine | stato, attesa stimata oppure link e importo oppure codice oppure proposta sostitutiva, frase da leggere (RF-25) |

- **RF-40** REST: `POST /v1/intents`, `GET /v1/intents/{id}/proposal`,
  `POST /v1/proposals/{id}/reject`, `POST /v1/proposals/{id}/accept`,
  `GET /v1/orders/{id}`. JSON, errori in formato RFC 7807, `GET /health` senza autenticazione.
  I corpi di `POST /v1/intents` e `POST /v1/proposals/{id}/reject` accettano i campi
  strutturati di RF-52, con gli stessi nomi e valori del tool MCP.
- **RF-41** MCP: server remoto con trasporto Streamable HTTP su `/mcp`, cinque tool con gli
  stessi nomi di RF-39, descrizioni scritte per un modello che parla con un umano a voce:
  ogni tool dice esplicitamente di non elencare alternative e di leggere la frase pronta.
  La descrizione di `create_intent` dice di chiedere lo sport prima di chiamarlo se il
  viaggiatore non ha detto padel, tennis o indifferente; lo schema non rende `sport`
  obbligatorio (l'agente indovinerebbe invece di chiedere) e RF-04 fa da rete di sicurezza. Le
  descrizioni di `get_proposal`, `create_intent` e `reject_proposal` dicono che dopo una
  proposta ogni cambiamento passa da `reject_proposal` con i campi aggiornati (RF-55) e non
  invitano mai a riformulare con un nuovo `create_intent`.
  La descrizione di `accept_proposal` dice che la risposta è un'attesa, non un link, e che il
  link va letto con `get_order_status` dopo l'attesa dichiarata o quando il viaggiatore lo
  chiede. Compatibile con Claude (claude.ai, Claude Desktop) ed ElevenLabs Conversational AI.
- **RF-42** Ogni risposta dei casi d'uso include un campo `say`: una frase in lingua
  dell'intento, pronta per essere letta ad alta voce, senza markdown, senza URL letti per
  esteso (l'URL sta in un campo separato). Il `say` di `create_intent` e `reject_proposal`
  segue anche RF-54.
- **RF-43** La superficie REST usa un bearer token statico da configurazione
  (`VELA_API_TOKEN`). La superficie MCP usa OAuth 2.1 (authorization server nella stessa app:
  metadata, registrazione dinamica, PKCE, token in Postgres), perché i connector custom di
  claude.ai accettano OAuth o nessuna autenticazione; accetta inoltre `VELA_API_TOKEN` come
  token statico per i client che non fanno OAuth (ElevenLabs). Finché l'OAuth non esiste,
  `/mcp` resta senza autenticazione (decisione del 2026-09-25, roadmap M3 e M8). Il webhook
  Stripe usa la firma Stripe. `/health` è pubblico.
- **RF-44** A2A (Agent2Agent) non è nelle 24 ore. Il dominio non deve impedirlo: le superfici
  sono adapter separati che chiamano le stesse funzioni, e `ARCHITECTURE.md` descrive come
  aggiungere l'adapter A2A (agent card, mapping dei task sui cinque casi d'uso). Se resta
  tempo, si implementa come quarta superficie senza toccare il dominio.

### 4.10 Coda d'acquisto e scheduler della quota

Origine: twist del 2026-09-25 ("Vela ha appena chiuso un accordo di distribuzione": 50.000
viaggiatori in dieci minuti). Analisi e decisioni in `docs/decisions.md`. Il vincolo che non
si sposta è la quota HofJ: con 120 chiamate al minuto e 5 chiamate per acquisto prima del link
più una per la prenotazione, Vela completa al massimo 20 acquisti al minuto per client. Il
design trasforma questo tetto in attesa dichiarata invece che in errori.

- **RF-45** `accept_proposal` è sempre asincrono: valida i dati del viaggiatore (RF-12), crea
  l'ordine in stato `queued` con posizione in coda e attesa stimata, e risponde senza chiamare
  HofJ né Stripe. La frase `say` dichiara l'attesa in minuti, arrotondata per eccesso.
- **RF-46** Un job d'acquisto per ordine esegue in sequenza: creazione itinerario, cliente,
  lettura pax, scrittura pax, lettura del totale reale, creazione del link di pagamento; poi
  l'ordine passa a `awaiting_payment`. Ogni passo salva il proprio esito (`itineraryId`
  compreso) così che un'interruzione riprenda dal passo successivo. Un passo fallito per rete,
  timeout o 5xx viene ripetuto fino a tre volte nelle finestre successive; poi l'ordine passa a
  `failed` con un motivo leggibile. Un errore del prodotto segue RF-17.
- **RF-47** Lo scheduler della quota è unico per il cluster: un contatore per finestra di 60 s
  in Postgres (RF-36), tre classi in ordine di priorità: `booking` (prenotazioni di ordini
  pagati, riserva garantita del 20% della finestra, configurabile), `purchase` (job
  d'acquisto, il resto della finestra, in ordine di arrivo), `sync` (solo a coda `purchase`
  vuota e sopra la soglia di RF-37). Un job prenota atomicamente il blocco di chiamate che gli
  serve (5 per un acquisto, 1 per una prenotazione) oppure attende la finestra successiva. Una
  risposta 429 azzera il budget residuo della finestra (RF-38). `GET /v1/quota` si chiama al
  boot e dopo un 429, mai in ciclo.
- **RF-48** Attesa stimata = posizione in coda × 60 s ÷ acquisti per finestra, con acquisti
  per finestra = (limite − riserva `booking`) ÷ 5. Ricalcolata a ogni `get_order_status`. Non
  esiste un tetto: un'attesa di ore viene dichiarata, non rifiutata.
- **RF-49** `reject_proposal` sulla proposta di un ordine `queued` porta l'ordine a
  `cancelled`, lo toglie dalla coda e restituisce la proposta successiva (RF-08).
- **RF-50** I job girano in ogni istanza del processo (RNF-02): ogni istanza preleva job dalla
  tabella in Postgres con lock non bloccante (`FOR UPDATE SKIP LOCKED`), con concorrenza per
  istanza configurabile (default 4). Un job è idempotente e ripartibile (RF-27).
- **RF-51** Un ordine pagato viene prenotato entro la finestra successiva alla verifica del
  pagamento (RF-20), salvo
  errori di RF-24: la riserva `booking` garantisce che la prenotazione avvenga anche a coda
  d'acquisto piena.

### 4.11 Contratto agente-tool

Origine: conversazione osservata il 2026-09-26. Il viaggiatore rifiuta una proposta ("troppo
caldo, vorrei un posto più freddo"); l'agente "riformula" con un nuovo `create_intent` invece di
`reject_proposal`, il nuovo intento non ha rifiuti, il chooser è deterministico e torna la
stessa proposta. "Più freddo" non era capito, e lo sport non era mai stato chiesto. Decisioni in
`docs/decisions.md` (2026-09-26), casi d'uso in `docs/usecases/agente-tool.md`.

- **RF-52** `create_intent` e `reject_proposal` accettano, su MCP e REST con lo stesso
  contratto, campi strutturati opzionali: `sport` (`padel` | `tennis` | `any`), `area` (nome
  di un luogo), `period_start` e `period_end` (date ISO), `pax` (intero), `budget` (totale in
  EUR). `reject_proposal` accetta inoltre `direction` (`north` | `south`). `text` e `reason`
  restano e vanno sempre passati con le parole del viaggiatore. La modifica è additiva: un
  client che manda solo testo funziona come prima (parser e fallback), più la domanda sullo
  sport di RF-04.
- **RF-53** Precedenza sul server, campo per campo: campo strutturato valido > parser
  deterministico > fallback Haiku (solo su `create_intent`, RF-03). Un campo invalido (sport
  fuori dai tre valori, area sconosciuta a `geo`, date impossibili o passate, pax fuori da
  1..20, budget non positivo) viene scartato senza bloccare la richiesta, e il `say` lo dice.
  Se testo e campo valido indicano valori diversi vince il campo, e il conflitto va nei log
  (RNF-06). Se in un rifiuto ci sono sia `area` sia `direction`, vince `area` e il conflitto va
  nei log; una `direction` che `geo.move` non sa applicare viene scartata e dichiarata.
- **RF-54** Il `say` di `create_intent` (intento creato) e di `reject_proposal` ripete sempre i
  criteri capiti: sport (o "padel o tennis indifferente"), area, periodo, persone, budget. Così
  il viaggiatore sente, e può correggere, anche un campo inventato dall'agente. Dichiara inoltre
  i campi scartati (RF-53) e, per un motivo di rifiuto che non si traduce in nessun criterio
  ("hotel con spa"), che Vela non sa filtrare per quel motivo e ha escluso solo la proposta
  rifiutata.
- **RF-55** Dopo una proposta ogni cambiamento (luogo, periodo, sport, budget, persone, "più
  fresco") passa da `reject_proposal` sulla proposta corrente con i campi aggiornati, mai da un
  nuovo `create_intent`: l'intento conserva i rifiuti. "Più fresco" si traduce in `north`,
  "più caldo" in `south`; il server usa `geo.move` e il catalogo non contiene dati climatici.
  Un "niente di compatibile" restituito da `reject_proposal` riporta l'id della proposta appena
  rifiutata: un nuovo `reject_proposal` su quella proposta aggiorna i criteri e propone di
  nuovo, senza registrare un secondo rifiuto (nessuna modifica di schema).

## 5. Requisiti non funzionali

- **RNF-01 Stateless.** Il processo non tiene stato tra richieste: intenti, proposte, ordini,
  catalogo, contatore quota e lock stanno in Postgres. Più istanze su Render funzionano senza
  configurazione aggiuntiva.
- **RNF-02 Un processo.** Una sola app FastAPI serve REST, MCP e webhook; i task post-pagamento
  girano in background nello stesso processo (RF-27 copre il crash).
- **RNF-03 Idempotenza.** Webhook duplicati, ripetizioni di `POST /v1/bookings`, doppio
  `accept` sulla stessa proposta non creano ordini o prenotazioni doppie.
- **RNF-04 Timeout.** Le chiamate a HofJ hanno timeout di 15 secondi. Nessun caso d'uso
  aspetta HofJ: il job d'acquisto (RF-46) assorbe i 2-6 secondi della ricerca di
  disponibilità live e i timeout, con ripetizione per passo e stato `failed` come esito
  finale leggibile.
- **RNF-05 Latenza.** I cinque casi d'uso non chiamano servizi esterni (eccetto il fallback
  LLM di RF-03) e rispondono sotto i 500 ms al 95° percentile in modalità replay sul load
  test.
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
  esterni. Il dominio si testa con repository in memoria; i test che toccano Postgres girano
  solo se `DATABASE_URL` è impostata (Render Postgres) e altrimenti vengono saltati.
- **RNF-10 Load test.** `loadtest/locustfile.py` esercita il flusso completo in replay contro
  l'URL live o locale. `loadtest/RESULTS.md` riporta utenti simulati, RPS, p50/p95/p99, errori,
  più i numeri reali di `GET /v1/quota` (limite per minuto) e la latenza misurata di un
  flusso di prenotazione reale. Uno scenario "twist" simula 50.000 viaggiatori in dieci
  minuti in replay, con HofJ finto che impone 120 chiamate al minuto e 2-6 secondi di latenza
  per chiamata: riporta p95 dei casi d'uso, acquisti completati al minuto (atteso ≈ 20),
  scarto tra attesa stimata e reale, tempo tra pagamento simulato e prenotazione (atteso
  < 60 s), errori di quota (atteso 0).
- **RNF-11 Deploy.** Dockerfile, deploy su Render con Postgres gestito, migrazioni al boot,
  variabili d'ambiente documentate in `README.md`.
- **RNF-12 Degradazione sotto carico.** Il fallback LLM di RF-03 ha un interruttore a
  concorrenza limitata (configurabile): oltre il limite, Vela pone la domanda di RF-04 invece
  di chiamare il modello. Il catalogo è tenuto in memoria per istanza e ricaricato da Postgres
  ogni minuto, così la proposta non legge il DB.
- **RNF-13 MCP stateless.** La superficie MCP non tiene sessioni in memoria: ogni richiesta è
  servibile da qualunque istanza.

## 6. Vincoli di progetto

- 24 ore reali già iniziate, una persona che delega agli agenti AI; ogni sessione finisce in
  `agent-log/` (rinominato da `agents-log/` con `git mv` per rispettare il brief).
- Stack: Python 3, FastAPI, Postgres, Render. Nessuna dipendenza nuova senza accordo.
- Prodotto: solo padel o tennis con hotel. Voli, transfer, auto e altri componenti sono
  esclusi e costerebbero punti.
- Nessuna interfaccia utente propria: niente pagine di ricerca, liste, filtri, griglie,
  confronti. Le sole pagine web coinvolte sono il Checkout di Stripe e le due pagine statiche
  di ritorno servite da Vela (`/checkout/success`, `/checkout/cancel`; decisione M6), che non
  mostrano dati dell'ordine.
- Lingue degli intenti: italiano e inglese. Catalogo HofJ in locale `it`.
- Dati personali: solo quelli di RF-12.
- Variabili d'ambiente: `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRANDS` (sport → brand,
  es. `padel=weebora.com,tennis=terrarossa.com`), `DATABASE_URL`,
  `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `VELA_API_TOKEN`, `VELA_UPSTREAM_MODE`,
  `ANTHROPIC_API_KEY` (opzionale), `VELA_PUBLIC_URL`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
  `TWILIO_FROM` (opzionali, SMS).
- Chiamate esterne a pagamento o con limiti (HofJ, Stripe, Anthropic, Twilio) vanno dichiarate prima
  di eseguirle, con il numero di chiamate previsto.

## 7. Fuori scope

Voli, transfer, noleggio auto; interfaccia web o app propria; scelta di hotel alternativi o
attività aggiuntive nell'itinerario; pagamento a rate, promo code, valute diverse da EUR;
autenticazione dell'utente finale HofJ (`X-End-User-Authorization`) e quindi `GET /v1/trips`;
cancellazioni e modifiche dopo la prenotazione; multi-tenant (i brand HofJ di padel e tennis
sono invece in scope, RF-28); A2A entro le 24 ore
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
   "troppo caro" ne produce un'altra singola più economica; "sì" produce uno stato `queued`
   con attesa dichiarata e, interrogando lo stato dell'ordine, un link Stripe con il totale
   reale; pagando con la carta di test `4242 4242 4242 4242` lo stato dell'ordine diventa
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
