# Cache del prezzo con fanout: design

Data: 2026-09-27. Origine: brainstorming "ridurre le chiamate ad HofJ" (branch `task/cache`).
Tocca spec RF-14, RF-16, RF-45, RF-46, RF-48, RF-49 e aggiunge RF-84 (§4.10).
Decisioni in `docs/decisions.md` (2026-09-27, "Cache del prezzo con fanout").

## Problema

Nel picco molti viaggiatori accettano lo stesso viaggio (stesso prodotto, stessa data, stesse
persone e camere). Le proposte non chiamano HofJ (RF-11), ma ogni accettazione accoda un job
d'acquisto che fa 5 chiamate (`create_itinerary`, `set_customer`, `get_pax`, `set_pax`,
`get_itinerary`) solo per scoprire il prezzo effettivo (RF-16). Con 108 chiamate al minuto
sono circa 21 prezzi al minuto: la coda si riempie anche di chi poi dirà no al prezzo, e il
prezzo di viaggi identici si scopre N volte.

Il carrello HofJ è per viaggiatore (dentro ci sono cliente e passeggeri): non si condivide.
Si condivide solo il prezzo.

## Obiettivo

1. **Cache del prezzo**: la prima `accept_proposal` su una chiave già prezzata risponde subito
   con il totale in cache, senza coda e senza chiamate HofJ. Il carrello si crea solo dopo il
   sì del viaggiatore.
2. **Fanout**: se il prezzo di una chiave è in volo, le accettazioni successive con la stessa
   chiave non entrano in coda: si agganciano e ricevono il prezzo quando il primo ordine (il
   leader) lo legge.

Successo: N accettazioni identiche nello stesso picco costano 5 chiamate per il prezzo invece
di 5·N; chi rifiuta il prezzo non costa chiamate (salvo il leader); la suite è verde, test
Postgres compresi.

## Vincoli

- Il link porta sempre il totale reale del carrello del viaggiatore (RF-16): la cache decide
  cosa si chiede di confermare, mai cosa si paga.
- Tutto lo stato condiviso resta in Postgres (decisione "Architettura"): cache e ordini nello
  stesso database, fanout nella stessa transazione. Nessun servizio nuovo, nessuna dipendenza
  nuova.
- Nessuna chiamata esterna nei test.
- Interfacce pubbliche (REST, MCP, forma di `OrderStatusResponse`) invariate.

## Fuori scope

- Condividere il carrello o `create_booking` tra viaggiatori.
- Cache per la sync del catalogo.
- Redis o cache in memoria del processo (scartati: servizio nuovo, niente transazione unica con
  gli ordini; per processo non condivisa tra istanze).
- Rifare i giri di `loadtest/RESULTS.md` per misurare il risparmio (task separata, se serve).

## Design

### Chiave

`(product_id, start_date, adults, rooms, currency)`, con `adults = order.pax`. Il brand è
implicito nel prodotto.

### Dati (migrazione `0015_price_quotes`)

Numero 0015: 0012, 0013 e 0014 sono riservati a M21-C, M21-F e M22 (`docs/decisions.md`).
`down_revision` è la testa al momento dell'implementazione (0011); chi fa il merge per secondo
riaggancia la catena (decisione del 2026-09-27).

Tabella `price_quotes`:

| Colonna | Tipo | Note |
|---|---|---|
| `product_id`, `start_date`, `adults`, `rooms`, `currency` | PK composta | la chiave |
| `status` | `pending` \| `ready` | `pending` = prezzo in volo |
| `total` | numeric, null se `pending` | |
| `leader_order_id` | string | l'ordine il cui job scopre il prezzo |
| `priced_at` | timestamp, null se `pending` | base del TTL |
| `updated_at` | timestamp | |

Colonne nuove su `orders`:

- `follows_quote` (bool, default false). Vero per un ordine `queued` agganciato a un prezzo in
  volo, che non ha un job suo. Campo esplicito invece di dedurlo da "queued senza job": la
  deduzione è falsa nella finestra tra `orders.add` e `jobs.enqueue`.
- `confirmed_total` (numeric, null). Il totale che il viaggiatore ha confermato su un ordine
  senza carrello; il job lo confronta con quello del carrello e `get_order_status` lo usa per
  dire "il prezzo è cambiato: ora è X invece dei Y che avevi confermato".

Nuova porta `QuoteRepository` in `vela/ports/repositories.py`, implementata in
`repo_memory.py` e `repo_postgres.py`:

- `get(key) -> Optional[PriceQuote]`
- `claim(key, order_id, now, ttl, leader_alive) -> bool`: atomica. Crea la riga `pending` con
  questo leader se assente, oppure la prende se è `ready` e scaduta, oppure `pending` con un
  leader non più `queued`. Postgres: `INSERT … ON CONFLICT DO UPDATE … WHERE …` con verifica
  delle righe toccate. Restituisce se l'ordine è diventato leader.
- `publish(key, total, currency, now)`: la riga passa a `ready`; nella stessa transazione gli
  ordini `follows_quote` con la stessa chiave passano a `awaiting_confirmation` con quel totale
  e `follows_quote = false` (il fanout).
- `release(key, leader_order_id)`: cancella la riga `pending` di quel leader e restituisce gli
  ordini agganciati, con `follows_quote = false`.
- `followers(key)`: gli ordini agganciati, per la posizione in coda.

### TTL e interruttore

Campo di tuning `price_quote_ttl_seconds: int = 900` in `Settings` (non una variabile
d'ambiente), passato da `app.py` a `Vela`. Il costruttore di `Vela` ha default 0: **0 spegne
cache e fanout** e l'accettazione è quella di oggi. Così i test che costruiscono `Vela` a mano
restano validi, e in produzione la cache si spegne mettendo il campo a 0. Una riga `ready` con `priced_at` più vecchio del TTL vale come assente e il nuovo
leader la sovrascrive: nessun job di pulizia, al massimo una riga per chiave.

### Prima `accept_proposal` (RF-45)

Dopo le validazioni di oggi (dati mancanti, camere), prima di creare l'ordine:

| Cache | Esito | Chiamate HofJ |
|---|---|---|
| `ready`, non scaduta, prodotto `bookable` | ordine creato `awaiting_confirmation` con `total` dalla cache, senza `itinerary_id`, senza job; risposta immediata | 0 |
| assente, scaduta, o leader non più `queued` | `claim` riuscito: ordine `queued` + job d'acquisto come oggi | 5 |
| `pending` con leader vivo (o `claim` perso) | ordine `queued` con `follows_quote = true`, senza job; `_await_progress` come oggi | 0 |

Ordine dei passi, per non perdere un fanout concorrente:

1. si legge la cache: `ready`, non scaduta e prodotto `bookable` → hit, fine;
2. altrimenti l'ordine si crea già `queued` con `follows_quote = true` (serve il suo id come
   leader, e un `publish` o un `release` che arrivano ora lo vedono);
3. `claim`: se riesce, `follows_quote = false` e si accoda il job;
4. se non riesce si rilegge la riga: `ready` (un leader ha pubblicato nel frattempo) → l'ordine
   passa a `awaiting_confirmation` con quel totale, se il fanout non l'ha già fatto; `pending` →
   resta agganciato.

Un ordine sostitutivo (RF-17) segue le stesse regole, con l'`enqueued_at` ereditato.

### Job d'acquisto (RF-46)

**Passo 3, primo prezzo** (`confirmed_total` è null, caso di oggi): se la chiave ha una riga in
`price_quotes` (la cache è in uso) il job chiama `publish` **prima** di salvare l'ordine
`awaiting_confirmation`: al contrario, un agganciato potrebbe vedere il leader non più `queued`
con la riga ancora `pending` e rilasciare tutti per errore. Il leader ha il suo carrello: alla
conferma riparte dal passo 4 come oggi.

**Conferma di un ordine senza carrello** (hit o agganciato, `itinerary_id` null): `_confirm`
lo rimette `queued` con `confirmed_total = total` e accoda il job dal **passo 0**. Al passo 3:

- totale del carrello uguale a `confirmed_total`: il job prosegue al passo 4 (link) senza
  chiedere di nuovo;
- diverso: l'ordine torna `awaiting_confirmation` con il nuovo totale, la cache della chiave
  viene aggiornata (`ready`, nuovo `priced_at`) e la risposta usa una frase nuova ("il prezzo è
  cambiato: ora è X euro, confermi?"). Il sì successivo riparte dal passo 4: il carrello c'è.

### Ripiego: il leader esce senza prezzo

Regola approvata: se il leader non arriva al prezzo, gli agganciati tornano ordini normali.
Funzione di dominio unica `release_quote(order)`: se l'ordine è il leader di una riga
`pending`, chiama `release` e accoda per ogni agganciato un job d'acquisto con il suo
`enqueued_at` (l'ordine in coda si conserva). Chiamata in ogni uscita del leader:

- `failed` dopo i tentativi, `ConfigError` (dead) — `PurchaseJob._fail_order`;
- prodotto non prenotabile, `replaced` — `PurchaseJob._replace`. Ogni agganciato rifà
  `create_itinerary`, riceve l'errore e segue RF-17 da sé: 1 chiamata ciascuno, accettato per
  semplicità;
- rinuncia del leader, `cancelled` (RF-49) — `reject_proposal`.

Rete di sicurezza per crash o uscite dimenticate: `claim` tratta come scaduta una riga
`pending` il cui leader non è più `queued`; `_await_progress` e `get_order_status` di un
agganciato fanno lo stesso controllo e, se il leader non è più `queued`, chiamano
`release_quote` su di lui.

Un agganciato che rinuncia (RF-49) diventa `cancelled` come oggi; il fanout ignora gli ordini
non più `follows_quote`.

### Coda e attesa (RF-48)

Un agganciato ha la posizione e l'attesa stimata del suo leader. `queued_purchase_position`
per un ordine `follows_quote` usa il `leader_order_id` della riga. La frase resta
`say_queued_for_price`.

### Frasi

Una frase nuova in `vela/domain/say.py`, italiano e inglese: prezzo cambiato dopo la conferma,
con il nuovo totale e la domanda di conferma. Gli altri casi usano le frasi di oggi
(`awaiting_confirmation`, `queued`).

### Load test

In modalità `loadtest` l'accettazione non aspetta (`accept_wait_seconds = 0`): oggi risponde
sempre `202 order_queued`, e `loadtest/journey.py` chiude come fallito ogni altro status. Con
la cache un hit risponde subito `200` con `awaiting_confirmation`; lo scenario usa quattro frasi
con due persone, quindi quasi tutti i viaggiatori dopo i primi sarebbero hit. `journey.py`
accetta anche `200` con `awaiting_confirmation` e prosegue nel ciclo di polling, che conferma
già alla prima lettura di quello stato. Gli agganciati rispondono `202` come oggi; il report
esclude già dagli scarti chi non ha `wait_seconds`.

## Gestione degli errori

- Crash tra `release` (gli agganciati perdono `follows_quote`) e l'accodamento dei loro job:
  quegli ordini restano `queued` senza job. Finestra di pochi millisecondi, accettata; un job
  accodato "per sicurezza" da `get_order_status` rischierebbe due job d'acquisto sullo stesso
  ordine, cioè due carrelli.

- 429 sul leader: il leader aspetta la finestra successiva senza contare il tentativo (RF-38);
  gli agganciati aspettano con lui, la riga resta `pending`.
- Errore di rete o timeout sul leader: tentativi come oggi; alla fine `failed` e ripiego.
- Prezzo in cache vecchio: al più un secondo giro di conferma, mai un pagamento diverso dal
  confermato.
- Prodotto non prenotabile scoperto dopo il sì (ordini senza carrello): `replaced` come RF-17,
  con la proposta sostitutiva. È un peggioramento accettato rispetto a oggi, dove succede prima
  del sì.

## Test

Repository in memoria (sempre) e Postgres (con `DATABASE_URL`):

- hit: ordine `awaiting_confirmation` senza job e senza chiamate;
- miss: leader con job, riga `pending`;
- agganciato: nessun job, fanout al passo 3 del leader, stesso totale;
- TTL scaduto: nuovo leader;
- conferma senza carrello, totale uguale: link senza secondo giro;
- conferma senza carrello, totale diverso: `awaiting_confirmation` con il nuovo totale, cache
  aggiornata, frase nuova; il sì successivo parte dal passo 4;
- ripiego su `failed`, dead, `replaced`, `cancelled`: ogni agganciato ha un job con il suo
  `enqueued_at`;
- leader non più `queued` senza ripiego: `claim` e `_await_progress` sbloccano gli agganciati;
- posizione in coda di un agganciato = quella del leader;
- load test: `journey` con accettazione `200 awaiting_confirmation` arriva a conferma e
  pagamento (`tests/test_loadtest_journey.py`);
- Postgres: `claim` concorrente da più thread, un solo leader; migrazione `0015` su e giù.

## Task

1. Migrazione `0015`, `QuoteRepository` (memoria + Postgres), `follows_quote` e
   `confirmed_total` su `orders`.
2. `accept_proposal`: hit, leader, agganciato; posizione in coda; `publish` al passo 3 del
   leader; `Settings` e cablaggio.
3. Conferma senza carrello: `confirmed_total`, job dal passo 0, prezzo cambiato e frase nuova.
4. Ripiego: `release_quote` nelle uscite del leader e rete di sicurezza.
5. `loadtest/journey.py` per gli hit, spec (RF nuovo in §4.10 e aggiornamenti), `decisions.md`, roadmap.
