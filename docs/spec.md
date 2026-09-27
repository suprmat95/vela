# Vela — specifica dei requisiti

Data: 2026-09-25. Stato: bozza da rivedere; RF-43 e RNF-09 aggiornati il 2026-09-25 con la
roadmap (`docs/roadmap.md`); §4.10, RF-14, RF-16, RF-17, RF-19, RF-25, RF-27, RF-37, RF-39,
RF-41, RNF-04, RNF-05, RNF-10, RNF-12, RNF-13 e §10.1 aggiornati il 2026-09-25 per il twist
(50.000 viaggiatori in dieci minuti). RF-01..04, RF-08, RF-09, RF-39..42 e §4.11 (RF-52..55)
aggiornati il 2026-09-26 per il contratto agente-tool (roadmap M17). RF-28..32, §6, §7 e RF-56
aggiornati il 2026-09-26 per il catalogo multi-brand (roadmap M10). RF-36, RF-47, RNF-04,
RNF-10 aggiornati il 2026-09-26 per la seconda lettura del twist
(`docs/plans/2026-09-26-twist-seconda-lettura.md`). RF-36..38, RF-47, RF-48 e RF-50 aggiornati il
2026-09-26 con M18 (token bucket con soglia per le prenotazioni). RF-02, RF-04, RF-06..09,
RF-12, RF-14, RF-39..41, RF-49, RF-52..54, §7 e §4.12 (RF-58..75) aggiornati il 2026-09-26 per la scelta
v3 (roadmap M21, `docs/usecases/scelta.md`): descrivono il comportamento dopo M21; le parti
marcate "(M21)" sono implementate (M21 completata il 2026-09-27 con M21-F: RF-08, RF-09, RF-65,
RF-71..75 e lo schema di §4.12 aggiornati quel giorno). RF-06, RF-16, RF-19, RF-25, RF-39, RF-45,
RF-46, RF-49 e RNF-05 aggiornati il 2026-09-26 per la conferma del prezzo effettivo prima
del link. RNF-04 aggiornato il 2026-09-27 per l'attesa dell'accettazione (roadmap M20). RF-84
aggiunto e RF-14, RF-16, RF-45, RF-46, RF-48, RF-49 aggiornati il 2026-09-27 per la cache del
prezzo con fanout (roadmap M23,
`docs/superpowers/specs/2026-09-27-cache-prezzo-fanout-design.md`). Origine: `docs/brief.md` e
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
  strutturati opzionali di RF-52 (sport, area, periodo, persone, budget e, da M21, durata,
  livello, lezioni, camere, lettura del budget).
- **RF-02** Da un intento Vela estrae: sport (`padel`, `tennis`, oppure `any` quando il
  viaggiatore dice che gli va bene l'uno o l'altro), area geografica (paese, regione o
  città, se presente), periodo (data o intervallo, mese, stagione, "questo/prossimo
  weekend"), numero di persone, budget massimo, lingua dell'intento. (M21) Estrae inoltre:
  durata in notti (RF-58; "un weekend" è una durata, non più un periodo), livello di gioco e
  desiderio di lezioni (RF-62), numero di camere (RF-65), lettura del budget a persona o
  totale (RF-69). I criteri completi sono nella tabella di §4.12.
- **RF-03** L'estrazione avviene con un parser deterministico (regole e dizionari it/en), dopo
  i campi strutturati passati dall'agente (precedenza di RF-53). Se dopo campi e parser manca
  ancora lo sport, e la variabile `ANTHROPIC_API_KEY` è presente, Vela invoca un modello
  piccolo e veloce (Claude Haiku 4.5) per compilare lo stesso schema. Se la variabile manca, il
  fallback è disattivato e non produce errore.
- **RF-04** Se dopo l'estrazione manca ancora un'informazione indispensabile, Vela restituisce
  una sola domanda chiara per l'agente da porre al viaggiatore, e nessun intento viene
  salvato. Indispensabili: lo sport, sempre ("Padel o tennis?"; "indifferente" o "tutti e due"
  è una risposta valida e vale `any`, cioè nessun filtro sport), poi il numero di persone
  (default 1 se il profilo lo indica, altrimenti chiesto), poi (M21) il numero di camere
  quando le persone sono più di 2 ("In quante camere?", RF-65; con 1 o 2 persone il default è
  1 camera). Una domanda alla volta, in quest'ordine: sport, persone, camere. Il periodo non è indispensabile: senza periodo il chooser considera tutte le date
  disponibili.
- **RF-05** Ogni intento è persistito con un identificativo e i criteri estratti, così che
  proposte e rifiuti successivi vi si riferiscano.

### 4.2 Proposta

- **RF-06** Per un intento Vela restituisce sempre **una sola** proposta: titolo del viaggio,
  destinazione, struttura alberghiera, date proposte, numero di persone, (M21) numero di
  camere e di notti, prezzo "a partire da" con valuta, una motivazione di una o due frasi che
  lega la scelta all'intento e dichiara i criteri morbidi non rispettati (area, budget, durata,
  livello).
- **RF-07** La scelta è deterministica: si scartano i prodotti archiviati, non prenotabili,
  già rifiutati per lo stesso intento, con sport diverso, con date non compatibili con
  `minDate`/`maxDate` e disponibilità, con pax fuori da `minPax`/`maxPax`; (M21) anche i
  prodotti che richiedono più camere di quelle chieste (RF-66), in un'area esclusa (RF-73),
  con l'hotel di un rifiuto `hotel` (RF-72), riservati a un livello diverso (RF-64). Un
  prodotto rifiutato con `keep_product` resta candidato senza le finestre rifiutate (RF-74).
  Tra i restanti si ordina come in RF-60 (dal 2026-09-26 in poi: area, budget, durata,
  livello, partenza, `featured`, prezzo, id), un solo candidato per gruppo di prodotti
  equivalenti (RF-61).
- **RF-08** Il viaggiatore può rifiutare una proposta con un motivo in testo libero, più i
  campi strutturati di RF-52 e una direzione (`north`, `south`). Vela aggiorna i criteri
  dell'intento con campi e motivo, con la precedenza di RF-53 ("troppo caro" abbassa il budget,
  "più a sud" o "a novembre" cambiano area o periodo, `direction` sposta l'area con `geo.move`)
  e restituisce un'altra proposta singola. Ogni cambiamento dopo una proposta passa da qui
  (RF-55). (M21) Ogni rifiuto ha un tipo (RF-71). Due eccezioni dichiarate: con
  `keep_product` la proposta successiva è lo stesso prodotto con altre date (RF-74); un motivo
  che non si classifica, senza `reject_kind`, non produce una proposta ma una domanda chiusa, e
  il rifiuto non viene registrato (RF-75).
- **RF-09** Non esiste un limite al numero di proposte per intento. Quando non resta nessun
  prodotto compatibile, Vela dice quale criterio non riesce a soddisfare e chiede quale
  criterio cambiare; non propone mai un prodotto già rifiutato, salvo con altre date dopo un
  rifiuto con `keep_product` (RF-74, M21). Criteri che possono fallire (`failed_criterion`):
  quelli di RF-07, più `rooms`, `place`, `hotel`, `level` (M21). Il cambiamento passa da
  `reject_proposal` sull'ultima proposta rifiutata (RF-55); solo un "niente di compatibile"
  restituito da `get_proposal` prima di ogni proposta si risolve con un nuovo `create_intent`.
- **RF-10** Nessuna risposta di Vela contiene mai più di un prodotto. Le risposte non
  contengono elenchi di alternative, tabelle, né inviti a "scegliere tra".
- **RF-11** Le proposte si leggono solo dal catalogo in cache locale (sezione 4.6). Nessuna
  proposta provoca chiamate a HofJ.

### 4.3 Accettazione e dati del viaggiatore

- **RF-12** Il viaggiatore accetta una proposta tramite il proprio agente. All'accettazione Vela
  richiede, se non già nel profilo: nome, cognome, email, telefono del viaggiatore principale;
  nome e cognome di ogni altro partecipante. Nient'altro viene chiesto. (M21) Il numero di
  camere non è un dato del viaggiatore: arriva con l'intento (RF-65) e `accept_proposal` lo
  accetta solo come correzione facoltativa.
- **RF-13** Indirizzo, paese e altri campi richiesti da HofJ ma non chiesti al viaggiatore sono
  compilati con valori di default dichiarati nella configurazione e documentati in
  `ARCHITECTURE.md` come vincolo del prototipo.
- **RF-14** Il job d'acquisto (RF-46) crea l'itinerario HofJ (`POST /v1/itineraries` con prodotto,
  data di inizio, adulti, camere dell'ordine (RF-67, M21; prima era sempre 1), valuta EUR),
  imposta il cliente (`PUT .../customer`), legge
  gli slot pax (`GET .../pax`) e li aggiorna preservando ogni `refId` (`PUT .../pax`). Il
  carrello di un ordine servito dalla cache del prezzo nasce dopo il sì (RF-84).
- **RF-15** Vela accetta la sistemazione di default dell'itinerario. Non sceglie hotel
  alternativi né aggiunge attività: il prodotto HofJ è già "esperienza + hotel".
- **RF-16** Vela legge il totale reale dall'itinerario. La proposta dice il prezzo "a partire da"
  come prezzo minimo e annuncia che il totale effettivo arriva prima del link. Dopo la lettura
  del totale l'ordine passa a `awaiting_confirmation`: la risposta (RF-25) dà il totale reale,
  la stima della proposta e la differenza, e chiede conferma. Il link nasce solo dopo la
  conferma, cioè una seconda `accept_proposal` sulla stessa proposta, e porta sempre il totale
  reale (decisione del 2026-09-26). Con il prezzo dalla cache (RF-84) si conferma prima che il
  carrello esista; se il carrello costa un'altra cifra serve un nuovo sì.
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
  accettazione è lo stato dell'ordine dopo l'attesa di RF-45 (`awaiting_confirmation` alla prima
  chiamata, `awaiting_payment` alla conferma) o, se l'attesa scade, id ordine, stato `queued`,
  attesa stimata e frase. Vela manda
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
  La risposta contiene lo stato, l'attesa stimata se `queued` (RF-48), totale reale e stima se
  `awaiting_confirmation` (RF-16), link e importo se `awaiting_payment`, la proposta sostitutiva se `replaced` (RF-17), il codice di prenotazione
  se `confirmed`, il motivo leggibile se `failed` o `booking_failed`, e una frase pronta da
  leggere ("La tua prenotazione è confermata, codice R-789012"). Stati possibili: `queued`,
  `awaiting_confirmation`, `awaiting_payment`, `paid_pending_booking`, `confirmed`, `replaced`, `cancelled`, `failed`,
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

- **RF-36** Ogni chiamata a HofJ passa da un guardiano della quota, che distribuisce le
  chiamate a ritmo costante (token bucket condiviso in Postgres) in modo che nessun intervallo
  di 60 secondi superi il limite effettivo; inizializzato da `GET /v1/quota` all'avvio e
  aggiornato a ogni chiamata (inclusa quella di quota). Nota: la finestra di HofJ misurata è
  fissa e ancorata alla prima chiamata dopo la scadenza (`docs/api/quota-health.md`); il ritmo
  costante è sicuro anche se fosse scorrevole. Implementazione: roadmap M18 (capienza 8,
  100 gettoni al minuto con il limite di 120).
- **RF-37** Il guardiano è lo scheduler della quota di RF-47: nessuna chiamata a HofJ parte
  senza i gettoni presi dal token bucket. Le chiamate di prenotazione degli ordini pagati hanno
  la precedenza (soglia di RF-47); i job d'acquisto usano il resto in ordine di arrivo; il sync
  gira solo a coda vuota e sopra la soglia. Nessuna
  chiamata del viaggiatore fallisce per quota esaurita: l'ordine aspetta in coda e l'attesa è
  dichiarata (RF-48).
- **RF-38** Una risposta 429 da HofJ svuota il bucket e non viene mai ripetuta
  immediatamente; segue una sola rilettura di `GET /v1/quota` per il cluster.

### 4.9 Superfici: casi d'uso, REST, MCP

- **RF-39** Il dominio espone cinque casi d'uso, identici su ogni superficie (più
  `get_proposal_details`, di sola lettura, RF-83):

  | Caso d'uso | Ingresso | Uscita |
  |---|---|---|
  | `create_intent` | testo, profilo opzionale, campi strutturati opzionali (RF-52) | id intento, criteri estratti, oppure la domanda mancante (RF-04) |
  | `get_proposal` | id intento | una proposta (RF-06) oppure "niente di compatibile" (RF-09) |
  | `get_proposal_details` (RF-83) | id proposta | programma e dettagli del prodotto proposto, frase da leggere |
  | `reject_proposal` | id proposta, motivo, campi strutturati, direzione, tipo di rifiuto e `keep_product` opzionali (RF-52) | la proposta successiva (RF-08) oppure "niente di compatibile" con l'id della proposta da cui ripartire (RF-55) oppure (M21) una domanda chiusa con l'id della proposta, che resta aperta (RF-75) |
  | `accept_proposal` | id proposta, dati viaggiatore mancanti, camere opzionali (M21, RF-65) | lo stato dell'ordine dopo l'attesa: prezzo effettivo da confermare, oppure link dopo la conferma (RF-16), oppure `queued` con posizione e attesa stimata; frase da leggere (RF-45) |
  | `get_order_status` | id ordine | stato, attesa stimata oppure link e importo oppure codice oppure proposta sostitutiva, frase da leggere (RF-25) |

- **RF-40** REST: `POST /v1/intents`, `GET /v1/intents/{id}/proposal`,
  `GET /v1/proposals/{id}/details` (RF-83), `POST /v1/proposals/{id}/reject`, `POST /v1/proposals/{id}/accept`,
  `GET /v1/orders/{id}`. JSON, errori in formato RFC 7807, `GET /health` senza autenticazione.
  I corpi di `POST /v1/intents` e `POST /v1/proposals/{id}/reject` accettano i campi
  strutturati di RF-52, con gli stessi nomi e valori del tool MCP; (M21) il corpo di
  `POST /v1/proposals/{id}/accept` accetta `rooms`.
- **RF-41** MCP: server remoto con trasporto Streamable HTTP su `/mcp`, sei tool con gli
  stessi nomi di RF-39, descrizioni scritte per un modello che parla con un umano a voce:
  ogni tool dice esplicitamente di non elencare alternative e di leggere la frase pronta.
  La descrizione di `create_intent` dice di chiedere lo sport prima di chiamarlo se il
  viaggiatore non ha detto padel, tennis o indifferente; lo schema non rende `sport`
  obbligatorio (l'agente indovinerebbe invece di chiedere) e RF-04 fa da rete di sicurezza. Le
  descrizioni di `get_proposal`, `create_intent` e `reject_proposal` dicono che dopo una
  proposta ogni cambiamento passa da `reject_proposal` con i campi aggiornati (RF-55) e non
  invitano mai a riformulare con un nuovo `create_intent`. (M21) La descrizione di
  `create_intent` dice di chiedere il numero di camere prima di chiamarlo quando le persone
  sono più di 2 e il viaggiatore non l'ha detto; quella di `reject_proposal` dice di passare il
  tipo di rifiuto quando è chiaro, di porre la domanda chiusa se il server la restituisce e di
  passare `reject_kind="other"` se il viaggiatore non sa dire cosa non va.
  La descrizione di `accept_proposal` dice che la risposta è un'attesa, non un link, e che il
  link va letto con `get_order_status` dopo l'attesa dichiarata o quando il viaggiatore lo
  chiede. Compatibile con Claude (claude.ai, Claude Desktop) ed ElevenLabs Conversational AI.
- **RF-83** `get_proposal_details` restituisce, per la proposta indicata (anche già
  rifiutata), il prodotto della proposta e i suoi dettagli letti dal dettaglio esteso salvato dal
  sync, senza chiamate a HofJ e senza cambiare stato: `description`, `why_this_trip`, `program`
  (`travelProgram`: descrizione e sezioni di giorni con titolo, descrizione ed eventi
  `{time, text}`; `null` se il fornitore non ha un programma), `hotel` (nome, stelle, descrizione
  in testo semplice, indirizzo), `venue` (nome, descrizione breve), `playing_hours`, `style`,
  `goal`, `best_for_level`, `accepts_companions`. I testi restano nella lingua del catalogo del
  brand; il `say` è una frase breve nella lingua dell'intento che dice se il programma c'è. La
  descrizione MCP dice di chiamarlo solo quando il viaggiatore chiede dettagli, di rispondere in
  poche frasi senza leggere tutto e senza aggiungere nulla che i campi non dicano, e che ogni
  cambiamento passa ancora da `reject_proposal`. Il sync conserva `travelProgram` nel `raw`;
  `python -m vela.sync --full` riscarica anche i dettagli invariati.
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

- **RF-45** `accept_proposal` valida i dati del viaggiatore (RF-12), crea l'ordine in stato
  `queued` con posizione in coda e attesa stimata, senza chiamare HofJ né Stripe. Poi aspetta
  che il job d'acquisto porti l'ordine al prezzo effettivo, rileggendo l'ordine ogni secondo,
  fino a un tetto configurabile (100 s, sotto i 120 s massimi di un tool MCP su ElevenLabs);
  sulla conferma del prezzo aspetta allo stesso modo il link. Se il tetto scade risponde
  `queued` e la frase `say` dichiara l'attesa in minuti, arrotondata per eccesso. In modalità
  `loadtest` il tetto è zero (decisione del 2026-09-26). Con un prezzo in cache risponde subito
  `awaiting_confirmation`; con un prezzo in volo per la stessa chiave l'ordine si aggancia al
  leader senza job suo (RF-84).
- **RF-46** Un job d'acquisto per ordine esegue in sequenza: creazione itinerario, cliente,
  lettura pax, scrittura pax, lettura del totale reale; qui l'ordine passa a
  `awaiting_confirmation` e il job si chiude. La conferma (RF-16) accoda un job d'acquisto che
  riparte dalla creazione del link di pagamento; poi l'ordine passa a `awaiting_payment`. Ogni passo salva il proprio esito (`itineraryId`
  compreso) così che un'interruzione riprenda dal passo successivo. Un passo fallito per rete,
  timeout o 5xx viene ripetuto fino a tre volte nelle finestre successive; poi l'ordine passa a
  `failed` con un motivo leggibile. Un errore del prodotto segue RF-17. Alla lettura del totale
  il job aggiorna la cache del prezzo e sblocca gli ordini agganciati; per un ordine già
  confermato sul prezzo in cache, con lo stesso totale prosegue fino al link (RF-84).
- **RF-47** Lo scheduler della quota è unico per il cluster: un token bucket condiviso
  in Postgres (RF-36), tre classi in ordine di priorità: `booking` (prenotazioni di ordini
  pagati), `purchase` (job d'acquisto, in ordine di arrivo), `sync` (solo a coda `purchase`
  vuota). La riserva per le prenotazioni è una soglia: `purchase` e `sync` prendono gettoni
  solo se nel bucket ne restano almeno 2 (configurabile), `booking` può arrivare a zero, quindi
  una prenotazione non aspetta mai gli acquisti. Un job prende atomicamente i gettoni che gli
  servono (5 per un acquisto, 1 per una prenotazione) oppure attende che il bucket li abbia.
  Una risposta 429 svuota il bucket (RF-38). `GET /v1/quota` si chiama al boot e dopo un 429,
  mai in ciclo.
- **RF-48** Attesa stimata = posizione in coda × 60 s ÷ acquisti al minuto, con acquisti al
  minuto = ritmo al minuto × 80% ÷ 5 (16 con il limite di 120): il 20% del ritmo si lascia
  alle prenotazioni, così la stima è prudente. Ricalcolata a ogni `get_order_status`. Non
  esiste un tetto: un'attesa di ore viene dichiarata, non rifiutata. Un ordine agganciato
  (RF-84) ha la posizione del suo leader.
- **RF-49** `reject_proposal` sulla proposta di un ordine `queued`, `awaiting_confirmation` o
  `awaiting_payment` porta l'ordine a `cancelled`, lo toglie dalla coda e restituisce la proposta
  successiva (RF-08). Un rifiuto per prezzo dopo il prezzo effettivo usa il totale reale come
  tetto della proposta successiva (decisione M7, aggiornata il 2026-09-26). (M21) Non vale per
  la domanda chiusa di RF-75: senza rifiuto registrato l'ordine resta com'è. Se l'ordine
  cancellato era il leader di un prezzo in volo, gli agganciati tornano ordini normali (RF-84).
- **RF-84** Il prezzo effettivo si mette in cache per chiave (prodotto, data di inizio, adulti,
  camere, valuta) per 15 minuti (`price_quote_ttl_seconds`, 0 = cache e fanout spenti). Con un
  prezzo in cache, e il prodotto ancora prenotabile, `accept_proposal` risponde subito
  `awaiting_confirmation`, senza coda né chiamate a HofJ, e il carrello si crea dopo il sì. Con
  un prezzo in volo per la stessa chiave l'ordine si aggancia al leader, senza job suo, e riceve
  il prezzo quando il leader lo legge. Se il carrello creato dopo il sì costa un'altra cifra,
  l'ordine torna `awaiting_confirmation` e serve un nuovo sì; il link porta sempre il totale del
  carrello. Se il leader esce senza prezzo (`failed`, `replaced`, `cancelled`), gli agganciati
  tornano ordini normali al loro posto in coda. Migrazione 0015: `price_quotes`,
  `orders.follows_quote`, `orders.confirmed_total` (decisione del 2026-09-27).
- **RF-50** I job girano in ogni istanza del processo (RNF-02): ogni istanza preleva job dalla
  tabella in Postgres con lock non bloccante (`FOR UPDATE SKIP LOCKED`), con concorrenza per
  istanza configurabile (default 10, M18). Un job è idempotente e ripartibile (RF-27).
- **RF-51** Un ordine pagato viene prenotato entro la finestra successiva alla verifica del
  pagamento (RF-20), salvo
  errori di RF-24: la soglia di RF-47 garantisce che la prenotazione avvenga anche a coda
  d'acquisto piena.

### 4.11 Contratto agente-tool

Origine: conversazione osservata il 2026-09-26. Il viaggiatore rifiuta una proposta ("troppo
caldo, vorrei un posto più freddo"); l'agente "riformula" con un nuovo `create_intent` invece di
`reject_proposal`, il nuovo intento non ha rifiuti, il chooser è deterministico e torna la
stessa proposta. "Più freddo" non era capito, e lo sport non era mai stato chiesto. Decisioni in
`docs/decisions.md` (2026-09-26), casi d'uso in `docs/usecases/agente-tool.md`.

- **RF-52** `create_intent` e `reject_proposal` accettano, su MCP e REST con lo stesso
  contratto, campi strutturati opzionali: `sport` (`padel` | `tennis` | `any`), `area` (nome
  di un luogo), `period_start` e `period_end` (date ISO), `pax` (intero), `budget` (cifra in
  EUR come detta dal viaggiatore, mai moltiplicata o divisa per le persone; da M21-E letta a
  persona o in totale come in RF-69). (M21) Inoltre: `duration_min_nights`,
  `duration_max_nights` (interi 1..30), `level` (`beginner` | `intermediate` | `advanced`),
  `wants_coaching` (booleano), `rooms` (intero 1..pax), `budget_scope` (`per_person` |
  `total`). `reject_proposal` accetta inoltre `direction` (`north` | `south`) e, (M21),
  `reject_kind` (RF-71) e `keep_product` (booleano). `accept_proposal` accetta (M21) `rooms`.
  `text` e `reason`
  restano e vanno sempre passati con le parole del viaggiatore. La modifica è additiva: un
  client che manda solo testo funziona come prima (parser e fallback), più la domanda sullo
  sport di RF-04.
- **RF-53** Precedenza sul server, campo per campo: campo strutturato valido > parser
  deterministico > fallback Haiku (solo su `create_intent`, RF-03). Un campo invalido (sport
  fuori dai tre valori, area sconosciuta a `geo`, date impossibili o passate, pax fuori da
  1..20, budget non positivo; da M21 anche durata fuori da 1..30 o con minimo oltre il
  massimo, `level`, `budget_scope` o `reject_kind` fuori elenco, `rooms` fuori da 1..pax)
  viene scartato senza bloccare la richiesta, e il `say` lo dice.
  Se testo e campo valido indicano valori diversi vince il campo, e il conflitto va nei log
  (RNF-06). Se in un rifiuto ci sono sia `area` sia `direction`, vince `area` e il conflitto va
  nei log; una `direction` che `geo.move` non sa applicare viene scartata e dichiarata.
- **RF-54** Il `say` di `create_intent` (intento creato) e di `reject_proposal` ripete sempre i
  criteri capiti: sport (o "padel o tennis indifferente"), area, periodo, persone, budget e,
  da M21, durata, livello e lezioni, camere, luoghi esclusi, lettura del budget (RF-70). Così
  il viaggiatore sente, e può correggere, anche un campo inventato dall'agente. Dichiara inoltre
  i campi scartati (RF-53) e, per un motivo di rifiuto che non si traduce in nessun criterio
  ("hotel con spa"), che Vela non sa filtrare per quel motivo e ha escluso solo la proposta
  rifiutata. (M21) Quest'ultima frase vale solo con `reject_kind="other"` esplicito: senza
  tipo, un motivo che non si classifica produce la domanda di RF-75.
- **RF-55** Dopo una proposta ogni cambiamento (luogo, periodo, sport, budget, persone, "più
  fresco") passa da `reject_proposal` sulla proposta corrente con i campi aggiornati, mai da un
  nuovo `create_intent`: l'intento conserva i rifiuti. "Più fresco" si traduce in `north`,
  "più caldo" in `south`; il server usa `geo.move` e il catalogo non contiene dati climatici.
  Un "niente di compatibile" restituito da `reject_proposal` riporta l'id della proposta appena
  rifiutata: un nuovo `reject_proposal` su quella proposta aggiorna i criteri e propone di
  nuovo, senza registrare un secondo rifiuto (nessuna modifica di schema).

### 4.12 Scelta v3: criteri, ordinamento, camere, rifiuti

Origine: richiesta dell'utente del 2026-09-26 sui limiti del chooser v2. Decisioni in
`docs/decisions.md` (2026-09-26, "Scelta v3"), casi d'uso in `docs/usecases/scelta.md`
(UC-A..UC-F), implementazione in roadmap M21. RF-58 e RF-59 (durata) sono implementati da
M21-A, RF-69 e RF-70 (budget a testa o totale) da M21-E, RF-60 e RF-61 (ordinamento e prodotti
equivalenti; il livello "livello e lezioni" attivo da M21-C) da M21-B, RF-65..68 (persone
e camere, con la migrazione 0011) da M21-D, RF-62..64 (livello e lezioni, con la migrazione 0012) da
M21-C, RF-71..75 (rifiuti, con la migrazione 0016) da M21-F. M21 è completata (2026-09-27); design
di M21-F in `docs/superpowers/specs/2026-09-27-rifiuti-motivo-design.md`.

**Criteri dell'intento.** Sono salvati nel JSON di `intents.criteria` (nessuna migrazione) e
restituiti nella risposta `intent_created` (interfaccia pubblica).

| Criterio | Valori | Fonte | Tipo | Dal |
|---|---|---|---|---|
| `sport` | `padel` \| `tennis` \| `any` | campo, parser, Haiku | filtro duro | M2, M17 |
| `area` | luogo di `geo` | campo, parser | morbido (ordinamento) | M2 |
| `period` | inizio, fine | campo, parser | filtro duro (partenza nel periodo) | M2 |
| `pax` | 1..20 | campo, parser, profilo | filtro duro (`minPax`/`maxPax`) | M2 |
| `budget` | EUR, tetto sul totale | campo, parser | morbido | M2 |
| `budget_scope` | `per_person` \| `total` | campo, parser, regola RF-69 | interpretazione di `budget` | M21 |
| `duration_min_nights`, `duration_max_nights` | 1..30 | campo, parser | morbido | M21 |
| `level` | `beginner` \| `intermediate` \| `advanced` | campo, parser | morbido; duro solo con esclusione esplicita (RF-64) | M21 |
| `wants_coaching` | booleano | campo, parser | morbido | M21 |
| `rooms` | 1..pax | campo, parser, default 1 con pax ≤ 2 | filtro duro con `maxPaxPerRoom` (RF-66) | M21 |
| `excluded_areas` | lista di luoghi di `geo` | rifiuto `place` | filtro duro | M21 |
| `language` | `it` \| `en` | parser | — | M2 |

Durata, livello, lezioni e lettura del budget sono criteri morbidi: da soli non escludono mai
un prodotto (eccezione: RF-64). Il tetto di prezzo dopo un rifiuto per prezzo (decisione M7) e
l'esclusione per hotel (RF-72) non sono criteri: si ricavano dai rifiuti dell'intento.

**Etichette del prodotto.** Calcolate dal sync e salvate in colonne nuove di `products`
(migrazioni di M21, roadmap M21-B, M21-C, M21-D): `levels` (insieme ⊆ {`beginner`, `intermediate`, `advanced`, `all`}),
`levels_exclusive`, `coaching`, `max_pax_per_room`, `featured`, `special_offer`.

- **RF-58** (UC-A) Vela estrae dal testo o riceve come campi una durata in notti
  (`duration_min_nights`, `duration_max_nights`): "weekend" 1..3, "ponte" 2..4, "una
  settimana" 6..8, "N giorni" N−1, "N notti" N, intervalli e "almeno N notti". Le notti di un
  prodotto sono `defaultDurationInDays` − 1, o la lunghezza della finestra fissa. La durata
  ordina, non esclude.
- **RF-59** (UC-A) Se il prodotto proposto non rispetta la durata chiesta, la motivazione e il
  `say` lo dicono con la durata vera ("Non ho weekend compatibili: questo dura 5 notti").
- **RF-60** (UC-B) Dopo i filtri duri i candidati si ordinano per: area (decrescente), totale
  entro budget, durata compatibile, livello e lezioni compatibili, distanza della partenza
  dall'inizio del periodo (o da oggi senza periodo), `featured` o `isSpecialOffer`, prezzo
  crescente, id. Senza budget il prezzo decide solo a parità di tutto il resto.
- **RF-61** (UC-B) Prodotti equivalenti (stesso hotel, stesso titolo normalizzato, stessa
  destinazione, prezzo entro il 5%) sono un solo candidato: quello con l'id numerico più basso
  tra quelli rimasti dopo i filtri duri. La trappola 900078 non vince sul 78.
- **RF-62** (UC-C) Vela estrae dal testo o riceve come campi `level` e `wants_coaching`.
- **RF-63** (UC-C) Il sync etichetta ogni prodotto leggendo `description` e `shortDescription`
  (it/en): livelli, esclusività esplicita del livello, presenza di lezioni o coach. Nessuna
  parola sul livello = livello sconosciuto, compatibile con tutti.
- **RF-64** (UC-C) Un prodotto è escluso per livello solo se la descrizione lo riserva
  esplicitamente ad altri livelli ("solo per avanzati", "advanced players only"); se il
  filtro azzera i candidati, `failed_criterion` è `level`. Negli altri casi il livello e le
  lezioni ordinano (RF-60) e il `say` dice se il prodotto proposto li rispetta.
- **RF-65** (UC-D) `create_intent`, `reject_proposal` e `accept_proposal` accettano `rooms`.
  Con più di 2 persone e senza camere, né nei campi né nel testo, `create_intent` restituisce la
  domanda "In quante camere?" / "How many rooms?" e non salva l'intento (RF-04); con 1 o 2
  persone il default è 1 camera. `rooms` su `accept_proposal` è una correzione: sotto il
  minimo del prodotto (RF-66) la risposta è una domanda con l'id della proposta e nessun ordine
  viene creato. Su `reject_proposal`, persone portate oltre 2 senza camere dette → la domanda "In
  quante camere?" con l'id della proposta, senza rifiuto (RF-75, M21-F); un intento salvato prima
  di M21-D resta senza camere.
- **RF-66** (UC-D) Un prodotto con `maxPaxPerRoom` richiede almeno ceil(pax /
  `maxPaxPerRoom`) camere; con meno camere chieste è escluso (`failed_criterion` `rooms` se
  nessuno resta). Il `say` della proposta dice il limite quando conta ("camere da massimo 2
  persone: per 5 servono almeno 3 camere").
- **RF-67** (UC-D) L'ordine salva il numero di camere e il job d'acquisto lo passa a
  `POST /v1/itineraries` (RF-14).
- **RF-68** (UC-D) Un viaggiatore da solo per cui restano solo prodotti con `minPax` ≥ 2
  riceve "niente di compatibile" con `failed_criterion` `pax` e un `say` che spiega che quei
  viaggi partono da 2 persone.
- **RF-69** (UC-E) Il budget si legge a persona o totale, in quest'ordine: campo
  `budget_scope`; "a testa", "a persona", "each", "per person" → a persona; "in tutto",
  "totale", "in total" → totale; cifra sola con più di una persona → a persona se, letta come
  totale, non copre neanche il totale del prodotto compatibile più economico (filtri duri senza
  budget) e letta a persona sì, altrimenti totale; con una persona totale. Nei criteri
  `budget` resta il tetto sul totale e `budget_scope` registra la lettura.
- **RF-70** (UC-E) Il `say` di `create_intent` e `reject_proposal` dichiara sempre la lettura
  del budget ("ho inteso 600 euro a persona, 1.800 in tutto").
- **RF-71** (UC-F) Ogni rifiuto ha un tipo: `price`, `place`, `hotel`, `dates`, `duration`,
  `sport`, `pax`, `level`, `direction`, `other`. Il campo `reject_kind` vince sul testo; senza
  campo il tipo si ricava dal motivo con regole it/en, altrimenti dai campi strutturati; con più
  tipi cambiano tutti i criteri e si registra il primo di questo elenco. Il tipo si salva sul
  rifiuto (migrazione 0016, M21-F; nullo = rifiuto senza tipo, prima di M21-F o di RF-17).
- **RF-72** (UC-F) Dopo un rifiuto `hotel` sono esclusi dalle proposte dell'intento tutti i
  prodotti con lo stesso hotel del prodotto rifiutato (nome normalizzato); se il prodotto non ha
  hotel, quelli con lo stesso titolo e la stessa destinazione (RF-61 senza il prezzo: il 78 e la
  trappola 900078). Vale anche per un motivo con più tipi che parla dell'hotel, non per `other`.
  Se non resta nulla, `failed_criterion` è `hotel`.
- **RF-73** (UC-F) Un rifiuto `place` ("Estepona no, ma la Spagna va bene") aggiunge il luogo a
  `excluded_areas` e mantiene l'area dell'intento. Senza `area` il luogo escluso è quello del
  prodotto rifiutato; con `area` si cambia luogo come oggi. Nel testo un luogo negato ("X no",
  "tranne X", "not X") è un'esclusione, non la nuova area. Un'area dell'intento dentro un'area
  esclusa sale al primo luogo che la contiene e non è escluso. Se il filtro azzera i candidati,
  `failed_criterion` è `place`.
- **RF-74** (UC-F) Un rifiuto `dates` con `keep_product` (campo, o nel testo "questo mi piace
  ma", "quando altro è disponibile", "same trip", "when else") esclude solo la finestra
  proposta: la proposta successiva è lo stesso prodotto con la prima partenza valida diversa,
  nel periodo dei criteri o in quello nuovo. Nessuna partenza → "niente di compatibile" con
  `failed_criterion` `dates` e l'id della proposta (RF-55); un nuovo `reject_proposal` con
  `keep_product=false` aggiorna lo stesso rifiuto e cerca un altro prodotto.
- **RF-75** (UC-F) Un motivo che non si classifica, senza `reject_kind`, non registra il
  rifiuto, non cambia i criteri, non cancella un ordine `queued` (eccezione a RF-49) e
  restituisce una domanda chiusa con l'id della proposta, che resta aperta: "Cosa non ti
  convince: il posto, l'hotel, le date o il prezzo?". Con `reject_kind="other"` esplicito il
  rifiuto si registra ed esclude solo il prodotto (RF-54). Eccezione dichiarata a RF-08. Stessa
  domanda chiusa, con l'id della proposta e senza rifiuto, per "In quante camere?" quando un
  rifiuto porta le persone oltre 2 senza dire le camere (RF-65). Un secondo `reject_proposal`
  su una proposta già rifiutata non chiede più il motivo.

**Cambi di interfaccia pubblica di M21.** MCP e REST cambiano insieme, con gli stessi nomi.

| Cambio | Dove | Tipo |
|---|---|---|
| `duration_min_nights`, `duration_max_nights`, `level`, `wants_coaching`, `rooms`, `budget_scope` in ingresso | `create_intent`, `reject_proposal` | additivo |
| `reject_kind`, `keep_product` in ingresso | `reject_proposal` | additivo |
| `rooms` in ingresso | `accept_proposal` | additivo |
| Criteri nuovi in uscita (tabella sopra) | `intent_created` | additivo |
| `rooms`, `nights` in uscita | `proposal` | additivo |
| `failed_criterion` `rooms`, `place`, `hotel`, `level` | `no_match` | additivo (valori nuovi) |
| Domanda "In quante camere?" con pax > 2 senza camere | `create_intent` | **non additivo**: `pax=5` oggi crea l'intento, dopo M21 riceve `question` |
| `question` con `proposal_id` | `reject_proposal` | **non additivo**: esito nuovo per un motivo non classificabile |
| `question` con il minimo di camere | `accept_proposal` | **non additivo**: esito nuovo |
| "Un weekend" è una durata, non più un periodo | parser | **cambio di comportamento** |
| Luogo negato nel motivo → esclusione invece di nuova area | `reject_proposal` | **cambio di comportamento** |
| Ordinamento RF-60 | `get_proposal`, `reject_proposal` | **cambio di comportamento**: la proposta per lo stesso intento può cambiare |
| Descrizioni dei tool (RF-41) | MCP | cambio di testo |

**Cambio di schema** (da approvare all'inizio di ogni task, decisione 2026-09-26): una
migrazione per task di M21. 0010 (M21-B): `products.featured`, `products.special_offer`. 0011
(M21-D): `products.max_pax_per_room`, `orders.rooms` (intero, default 1). 0012 (M21-C):
`products.levels`, `products.levels_exclusive`, `products.coaching`. 0016 (M21-F, dopo la 0015
di M23; 0013 e 0014 restano numeri non usati): `rejections.kind` (testo, nullo per i rifiuti di
prima), `rejections.keep_product` (booleano, default falso).

## 5. Requisiti non funzionali

- **RNF-01 Stateless.** Il processo non tiene stato tra richieste: intenti, proposte, ordini,
  catalogo, contatore quota e lock stanno in Postgres. Più istanze su Render funzionano senza
  configurazione aggiuntiva.
- **RNF-02 Un processo.** Una sola app FastAPI serve REST, MCP e webhook; i task post-pagamento
  girano in background nello stesso processo (RF-27 copre il crash).
- **RNF-03 Idempotenza.** Webhook duplicati, ripetizioni di `POST /v1/bookings`, doppio
  `accept` sulla stessa proposta non creano ordini o prenotazioni doppie.
- **RNF-04 Timeout.** HofJ rinuncia verso il brand dopo 15 s; il client di Vela aspetta 20 s.
  Un timeout è un esito incerto: si ripetono solo le chiamate idempotenti
  (`POST /v1/bookings`); un timeout su `POST /v1/itineraries` conta un itinerario
  probabilmente orfano. Nessun caso d'uso
  chiama HofJ: il job d'acquisto (RF-46) assorbe i 2-6 secondi della ricerca di
  disponibilità live e i timeout, con ripetizione per passo e stato `failed` come esito
  finale leggibile. L'unico caso d'uso che aspetta è `accept_proposal`, che rilegge l'ordine
  finché il job lo porta fuori da `queued` (prezzo effettivo, link, sostituzione, fallimento):
  dura al massimo il tetto di RF-45 (`accept_wait_seconds`, 100 s), poi risponde comunque.
- **RNF-05 Latenza.** I cinque casi d'uso non chiamano servizi esterni (eccetto il fallback
  LLM di RF-03) e rispondono sotto i 500 ms al 95° percentile in modalità replay sul load
  test. Eccezione: `accept_proposal` aspetta il job d'acquisto fino al tetto di RF-45, senza
  chiamare HofJ né Stripe; sotto load test il tetto è zero.
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
- **RNF-10 Load test.** `loadtest/locustfile.py` esercita il flusso completo contro l'istanza
  locale o un'istanza in modo `loadtest`, con HofJ e Stripe simulati; mai contro HofJ reale. `loadtest/RESULTS.md` riporta utenti simulati, RPS, p50/p95/p99, errori,
  più i numeri reali di `GET /v1/quota` (limite per minuto) e la latenza misurata di un
  flusso di prenotazione reale. Uno scenario "twist" simula 50.000 viaggiatori in dieci
  minuti con un HofJ finto che applica le regole di HofJ (120 chiamate al minuto, finestra ancorata) e 2-6 secondi di latenza
  per chiamata: riporta p95 dei casi d'uso, acquisti completati al minuto (al massimo 17,4 per la quota; ~12 previsti con 4 worker per la
  latenza, da confermare con M13a),
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
attività aggiuntive nell'itinerario (escludere i prodotti di un hotel rifiutato, RF-72, è una
scelta tra prodotti, non dentro l'itinerario); pagamento a rate, promo code, valute diverse da EUR;
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
