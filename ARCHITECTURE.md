# Vela — architettura

Stato: **bozza** del 2026-09-26 (roadmap M15). I numeri del load test mancano: la colonna
"prima" arriva da M13a, la colonna "dopo" da M13b, e fino ad allora sono segnaposto. Da non
mergiare su `master` prima di M13b.

Fonti: `docs/brief.md`, `docs/spec.md`, `docs/decisions.md`,
`docs/plans/2026-09-26-twist-seconda-lettura.md`, `docs/api/quota-health.md`. Le decisioni
datate, con le alternative scartate, stanno in `docs/decisions.md`; qui c'è il quadro.

Etichette usate nella sezione sul twist: **[misurato]** = verificato con chiamate reali o
leggendo il codice; **[previsto]** = deduzione da confermare con il load test (M13a);
**[proposta]** = scelta di design non ancora implementata, con la task che la implementa.

---

## 1. Che cosa è Vela

Vela non ha una homepage. È un servizio senza interfaccia propria che l'agente del viaggiatore
chiama dove il viaggiatore già si trova: Claude (claude.ai, Claude Desktop) via MCP, un agente
vocale ElevenLabs via MCP, qualunque client via REST. Il viaggiatore dice una frase ("un
weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro"), Vela propone **un solo
viaggio**, e ogni "no, perché…" produce un'altra proposta, sempre una. Dal "sì" si arriva a un
link di pagamento Stripe e poi a un codice di prenotazione reale su House of Journeys (HofJ).

Ogni risposta contiene una frase `say` pronta da leggere ad alta voce, senza markdown e senza
URL letti per esteso: funziona per chi non ha occhi, schermo o pazienza.

## 2. Forma del sistema

```
  Claude (MCP)    ElevenLabs (MCP)    client REST        [A2A: prossimo passo]
        \               |                 /
   vela/surfaces/   mcp.py   rest.py   health.py   checkout_pages.py
                         |
   vela/domain/     5 casi d'uso: create_intent, get_proposal, reject_proposal,
                    accept_proposal, get_order_status
                    intent + refine (parser it/en), chooser, geo, say
                    orders, purchase, booking, payment_check, quota
                         |
   vela/ports/      hofj, payments, llm, repositories, jobs, quota, catalog
                         |
   vela/adapters/   hofj_http + hofj_router (un client per brand) | hofj_replay
                    stripe_links | stripe_fake      haiku      repo_postgres | repo_memory
                    worker (thread nel processo)
                         |
                    Postgres: catalogo, intenti, proposte, ordini, job, quota
```

- **Esagonale, un processo.** Il dominio non conosce HTTP né Stripe. Le superfici sono adapter
  sottili che chiamano gli stessi cinque casi d'uso; una superficie in più (A2A) è un adapter,
  non nuova logica. REST, MCP, pagine di ritorno e worker vivono nella stessa app FastAPI.
- **Stateless.** Tutto lo stato (catalogo, ordini, job, contatore di quota, lock) è in
  Postgres. MCP usa Streamable HTTP senza sessioni: qualunque istanza serve qualunque
  richiesta.
- **Due modi.** `VELA_UPSTREAM_MODE=replay` sostituisce HofJ e Stripe con finti che leggono
  `fixtures/`; `live` usa HofJ e Stripe veri. Il load test userà un terzo modo, `loadtest`
  (sezione 5.5).

### Il percorso di un acquisto

1. `create_intent` → parser deterministico it/en; campi strutturati dall'agente se presenti;
   fallback Claude Haiku solo se c'è la chiave. Se manca lo sport, una domanda: "Padel o
   tennis?".
2. `get_proposal` → il chooser legge il catalogo **dal DB**, esclude i non prenotabili, i non
   viaggi, i rifiutati; ordina per area, budget, prezzo. Zero chiamate HofJ.
3. `reject_proposal` → il motivo diventa criteri ("troppo caro", "più fresco" → nord); nuova
   proposta. Zero chiamate HofJ.
4. `accept_proposal` → valida i dati del viaggiatore, crea l'ordine `queued` e risponde
   **subito** con posizione e attesa stimata. Non chiama HofJ né Stripe.
5. Job d'acquisto nel worker: itinerario, cliente, lettura pax, scrittura pax, totale
   (5 chiamate HofJ), poi Checkout Session Stripe. L'ordine passa ad `awaiting_payment`.
6. `get_order_status` → link e totale reale; poi, pagato, il job `payment_check` interroga la
   Checkout Session e accoda il job di prenotazione.
7. Job di prenotazione: `POST /v1/bookings` con `paymentIntentId` (1 chiamata HofJ) → ordine
   `confirmed` con il codice.

## 3. Decisioni e compromessi

Le principali; motivazioni complete e alternative in `docs/decisions.md`.

| Decisione | Compromesso accettato |
|---|---|
| Nessuna interfaccia: core service chiamato dall'agente del viaggiatore | La qualità della conversazione dipende dall'agente; la compensiamo con descrizioni dei tool scritte per un modello che parla a voce, `say` pronte e campi strutturati (contratto agente-tool) |
| Sempre una proposta, rifiuti senza limite | Il chooser deve saper spiegare i compromessi ("non ho Lanzarote: questa è a Tenerife") invece di dire "niente" |
| Catalogo copiato in Postgres, sincronizzato ogni 6 h per brand (padel = Weebora, tennis = Terrarossa) | Il prezzo in proposta è "a partire da"; il totale reale arriva dall'itinerario e, se diverso, è dichiarato prima del link |
| Parser deterministico, LLM solo di riserva | Meno flessibile di un LLM su frasi strane; in cambio nessun costo né dipendenza nel percorso principale, e l'agente passa comunque i campi strutturati |
| Accettazione sempre asincrona, un solo percorso | Anche chi è solo riceve "sei in coda"; mitigato da un'attesa breve in posizione 1 (M20) |
| Coda e scheduler della quota in Postgres, worker in ogni istanza (`FOR UPDATE SKIP LOCKED`) | Postgres fa da coda: basta per questo volume, niente Redis/Celery da mantenere |
| Pagamento chiuso via HofJ (`POST /v1/bookings` con `paymentIntentId`), senza webhook | Vela verifica il pagamento interrogando Stripe (ogni 60 s e quando il viaggiatore chiede lo stato) |
| Prodotto che fallisce al carrello → non prenotabile per 24 h, proposta sostitutiva | Il viaggiatore riaccetta perché prezzo e hotel cambiano; mantiene il posto in coda |
| Staging HofJ per il live della demo | Un booking su staging non è una prenotazione vera; è l'ambiente in cui il carrello è verificato |

## 4. Vincoli del prototipo

- **Campi di default (RF-13).** HofJ richiede indirizzo e paese del cliente; Vela non li
  chiede. Si usano valori dichiarati in `TravelerDefaults` (`vela/domain/models.py`):
  `Via del Prototipo 1`, `20100 Milano (MI)`, `IT`. Al viaggiatore si chiedono solo nome,
  cognome, email, telefono, e nome e cognome degli altri partecipanti.
- **Hotel di default.** Vela accetta la sistemazione di default dell'itinerario: nessuna scelta
  di hotel alternativi, nessuna attività aggiunta.
- **Una chiave HofJ** per padel e tennis: una sola quota.
- **Clima approssimato con la latitudine**: "più fresco" = più a nord.
- **Pacchetti evento esclusi** (guardare un torneo non è un viaggio per giocare).
- **Render `plan: free`, una istanza**: sleep dopo inattività; il design regge più istanze ma
  la demo ne usa una.
- **REST con token statico** (`VELA_API_TOKEN`).
- **Nessuna cancellazione o modifica** dopo la prenotazione; solo EUR.

---

## 5. Il twist: 50.000 viaggiatori in dieci minuti

Il testo, in breve: un accordo di distribuzione porta 50.000 viaggiatori in una finestra di
dieci minuti. La quota HofJ è per client, dichiarata "rolling 60-second", senza `Retry-After`
né `RateLimit-*`, e `GET /v1/quota` consuma lo stesso budget. Le chiamate upstream vanno in
timeout a 15 s; la ricerca dell'alloggio, inevitabile nel flusso d'acquisto, dura 2-6 s. "Your
prototype must still take a booking at minute six." Il load test colpisce la nostra edge, mai
HofJ.

Le cinque richieste del brief, una per sottosezione.

### 5.1 L'architettura che regge e il diff nel pensiero

**L'architettura.** La conversazione (intento, proposta, rifiuto) non tocca HofJ: legge il
catalogo dal DB, scala con le istanze e resta sotto i 500 ms. Il collo di bottiglia è solo
l'acquisto, e il suo tetto è fisico: la quota. Il design trasforma quel tetto in **attesa
dichiarata** invece che in errori:

- `accept_proposal` mette l'ordine in una coda in Postgres e risponde subito con posizione e
  attesa stimata (posizione × 60 s ÷ acquisti per finestra), senza tetto: un'attesa di ore si
  dichiara, non si rifiuta. Il viaggiatore può rinunciare con `reject_proposal`.
- Uno scheduler della quota unico per il cluster, in Postgres, con tre classi: `booking`
  (riserva garantita), `purchase` (FIFO), `sync` (solo a coda vuota). Un job prenota
  atomicamente il blocco di chiamate che gli serve o aspetta.
- I worker girano in ogni istanza e prelevano i job con `FOR UPDATE SKIP LOCKED`; ogni passo
  salva il suo esito, quindi un crash riprende dal passo successivo.

**Il diff nel pensiero**, in tre momenti.

1. **Prima del twist (mattina del 2026-09-25).** La quota era un errore da gestire:
   accettazione sincrona entro 30 s, "riprova tra un minuto" a quota finita.
2. **Prima lettura (sera del 2026-09-25).** La quota diventa capacità da pianificare: coda in
   Postgres, scheduler unico per il cluster, accettazione sempre asincrona con attesa
   dichiarata, riserva per le prenotazioni, nessun tetto all'attesa. Scartati Redis/Celery
   (un secondo servizio), un drenatore unico eletto (nessuna alta disponibilità), l'ibrido
   sincrono-se-c'è-budget (due percorsi da testare).
3. **Seconda lettura (2026-09-26).** L'impianto regge; cambiano cinque idee:

| Prima pensavamo | Ora pensiamo | Cosa ce l'ha fatto cambiare |
|---|---|---|
| Bisogna copiare la finestra di HofJ e allinearsi | Bisogna essere sicuri con qualunque finestra: ritmo costante | Il brief dice "rolling", la sonda misura una finestra ancorata, il nostro contatore va a griglia. Non potendo osservare HofJ gratis, ci si protegge da tutti i modelli |
| Il limite è la quota | Il limite può essere la latenza: ~12 acquisti/min con 4 thread invece di 17,4 (**[previsto]**, da confermare con M13a) | La ricerca dell'alloggio da 2-6 s; legge di Little |
| Un timeout è un errore: si riprova | Un timeout è un esito incerto: si riprova solo dove è idempotente | Il timeout a 15 s: booking upsert sicuro, itinerario no (orfani); precedenti Expedia e Brandur |
| Le chiamate si spendono in ordine d'arrivo | Le chiamate vanno spese su chi pagherà | Look-to-book: 5 chiamate per un link che magari nessuno paga |
| Il load test misura le prestazioni | Il load test dimostra un confine: chiamate a HofJ piatte da 1k a 50k utenti | Il vincolo "mai contro HofJ"; il finto deve applicare le regole di HofJ, non le nostre |

Non cambia: coda in Postgres, accettazione asincrona con un solo percorso, riserva per le
prenotazioni, nessun servizio in più.

**Le cinque idee nel dettaglio.**

- **Ritmo costante invece di finestra copiata.** **[misurato]** La sonda del 2026-09-26
  (`scripts/quota_probe.py`, 6 chiamate a `GET /v1/quota` su staging) mostra una finestra
  fissa di 60 s ancorata alla prima chiamata dopo la scadenza: non scorrevole, non a griglia,
  nessun header. **[misurato il codice]** `rolled()` in `vela/domain/quota.py` fa invece
  ripartire la finestra su una griglia di 60 s dall'ultimo allineamento. Esempio con i numeri
  della sonda: dopo una pausa di 3,8 s HofJ apre 11:43:10.532 → 11:44:10.532, Vela pensa
  11:43:06.769 → 11:44:06.769 e azzera il conto 3,8 s troppo presto. **[previsto]** Sotto
  carico i worker in attesa ripartono tutti all'azzeramento di Vela; la raffica cade nella
  coda della finestra di HofJ, già piena → 429, che azzera il budget e costa un minuto, quasi
  a ogni finestra. **[proposta, M18]** Token bucket condiviso in Postgres con ritmo r e
  capienza B, B + 60·r ≤ 108 (es. B = 8, r = 100/60 ≈ 1,67 chiamate/s): in qualsiasi
  intervallo di 60 s passano al massimo 108 chiamate, **qualunque sia la regola di HofJ**.
- **Il limite può essere la latenza.** Quota: 17,4 acquisti/min (sezione 5.2). Latenza: 5
  chiamate in serie da 2-6 s (media ~4 s) tengono un worker ~20 s; con `worker_concurrency = 4`
  e una istanza **[previsto]** ~12 acquisti/min. Legge di Little: 1,45 chiamate/s × 4-6 s ≈
  6-9 chiamate contemporanee. **[proposta, M18]** ~10 thread, con il ritmo deciso dal bucket e
  non dal numero di thread.
- **Un timeout è un esito incerto**: sezione 5.4.
- **Spendere su chi pagherà.** **[proposta, M19, condizionata]** Il totale dipende solo da
  prodotto, data, adulti e camere, fissati da `POST /v1/itineraries`: per il link bastano
  itinerario e totale (2 chiamate). Cliente e pax potrebbero passare nel job di booking, dopo
  il pagamento: chi non paga costerebbe 2 chiamate invece di 5, e i link al minuto
  passerebbero da ~17 a ~43 **[previsto]**. Condizionata a una verifica su staging: HofJ
  accetta `PUT customer`/`PUT pax` dopo il pagamento, e il totale non cambia? Più la scadenza
  degli ordini in coda il cui viaggiatore non dà più segni di vita.
- **Il load test dimostra un confine**: sezione 5.5.

**Un'ipotesi sbagliata e corretta.** Il 2026-09-26 avevamo preso per buono il "rolling" del
brief e proposto il token bucket per quel motivo. La sonda l'ha smentito. Il token bucket resta
la scelta giusta, ma per un motivo diverso: la deriva del nostro contatore e il fatto che non
possiamo osservare HofJ senza pagare quota. Lo scriviamo perché il twist chiede proprio come si
risponde a un cambio di requisiti sotto pressione.

### 5.2 Budget di quota: browse, cart, hotel, booking

Limite 120/min per chiave (padel e tennis insieme). Margine 10% per gli altri usi della chiave
→ 108. Riserva `booking` 20% → 21. Acquisti → 87, cioè **17,4 acquisti al minuto**.

| Voce del brief | Chiamate HofJ | Classe | Note |
|---|---|---|---|
| Browse (intento, proposta, rifiuto) | 0 | — | Catalogo nel DB, sincronizzato dal sync multi-brand |
| Cart | 5 per ordine: itinerario, cliente, lettura pax, scrittura pax, totale | `purchase` | Una sola volta per ordine; ripetizioni solo su rete/5xx, al massimo 3 finestre |
| Hotel | Dentro `POST /v1/itineraries` (hotel di default) | `purchase` | È la chiamata da 2-6 s; nessuna chiamata a `/accommodations` |
| Booking | 1 per ordine pagato | `booking` | Dalla riserva di 21/min: non aspetta la coda d'acquisto |
| Lettura quota | 1 al boot e dopo un 429 | `booking` | Mai in ciclo |
| Verifica del pagamento | 0 HofJ | — | Interroga Stripe |
| Sync del catalogo | pagine + dettagli dei due brand, ogni 6 h | `sync` | Solo a coda d'acquisto vuota (`vela/sync.py`) |

**Cosa si sacrifica, in ordine:** 1) il sync del catalogo; 2) l'attesa degli acquisti, che
cresce, dichiarata, senza tetto; 3) mai le prenotazioni degli ordini pagati.

### 5.3 Cosa degrada e cosa non deve mai degradare: il minuto sei

- **Marco** accetta al minuto 1: è tra i primi in coda, verso il minuto 3 riceve il link,
  paga, e al minuto 6 la prenotazione parte dalla riserva `booking`: codice entro circa un
  minuto dal pagamento.
- **Anna** arriva al minuto 6: scrive la sua frase e riceve subito una proposta; "troppo caro"
  e ne riceve subito un'altra; accetta e si sente dire, per esempio, "sei in coda, circa due
  ore" (il numero dipende da quanti hanno accettato prima). Non vede errori né timeout; può
  aspettare o rinunciare con `reject_proposal`.

**Cosa degrada:** solo l'attesa del link, dichiarata. **Cosa non degrada mai:** la
conversazione (0 chiamate HofJ, p95 < 500 ms) e la conferma di chi ha già pagato.

Il load test controlla entrambi con due viaggiatori sentinella con questi nomi (sezione 5.5).

### 5.4 `POST /v1/bookings` è un upsert idempotente su `itineraryId`: dove ci contiamo già

HofJ rinuncia verso il brand dopo 15 s, ma il brand potrebbe aver completato l'operazione: un
timeout non dice se l'effetto è avvenuto. Per `POST /v1/bookings` non importa, perché è un
upsert su `itineraryId`: la seconda `POST` restituisce lo stesso codice e non crea una seconda
prenotazione. **[misurato il codice]** Ci contiamo già in tre punti:

1. **`BookingJob.run`** (`vela/domain/booking.py`): su `UpstreamError` (rete, timeout, 5xx)
   ripete la stessa `POST` con lo stesso `itinerary_id`, fino a 5 tentativi con attese di 5,
   10, 20, 40 s. Un 4xx non si ripete; un 429 torna nella finestra successiva senza contare
   il tentativo.
2. **Lease scaduto.** Un job `running` più vecchio di `job_lease_seconds = 120`
   (`vela/config.py`) torna prelevabile: un altro worker o un'altra istanza lo riesegue e
   rifà la `POST`.
3. **Due job per lo stesso ordine.** `_enqueue_booking` (`vela/domain/orders.py`) controlla
   con `active_for_order` che non ci sia già un job attivo e poi accoda, senza lock né vincolo
   unico sulla tabella `jobs`. Due verifiche di pagamento concorrenti possono quindi creare due
   job. `BookingJob.run` esce senza chiamate solo se l'ordine non è più
   `paid_pending_booking`: due worker contemporanei manderebbero la `POST` due volte. Letto nel
   codice, non riprodotto.

In tutti e tre i casi l'upsert rende la ripetizione innocua. Senza l'upsert servirebbe una
lettura di verifica prima di ogni nuovo tentativo, come la `Retrieve` di Expedia.

**Dove non possiamo contarci.** `POST /v1/itineraries` **non** è idempotente. Su un timeout
al passo 0, `PurchaseJob` (`vela/domain/purchase.py`) riprova e crea un secondo itinerario; il
primo resta orfano su HofJ e ha consumato una chiamata. **[proposta, M18]** Contare gli orfani
e metterli nel budget. Domanda aperta a HofJ (`docs/hofj-questions.md`, domanda 9): possiamo
passare un nostro riferimento e ritrovare l'itinerario con quello dopo un timeout?

**Timeout del client.** **[misurato il codice]** Oggi 15 s (`TIMEOUT_SECONDS` in
`vela/adapters/hofj_http.py`), uguale a quello di HofJ verso il brand: rischiamo di chiudere
la connessione un attimo prima della risposta "timeout del brand". **[proposta, M18]** 20 s, e
lease rivisto: un acquisto con 5 timeout di fila dura 75 s oggi, 100 s con il client a 20 s,
contro un lease di 120 s.

### 5.5 Il load test

**Cosa dimostra.** Non le prestazioni in astratto, ma un confine: **le chiamate a HofJ al
minuto restano piatte e sotto 108 con 1.000, 10.000 e 50.000 viaggiatori**, mentre cresce solo
l'attesa dichiarata.

**Mai contro HofJ.** Nemmeno "passando da Render": `render.yaml` ha
`VELA_UPSTREAM_MODE: live` su HofJ staging, quindi un load test contro Render porterebbe il
carico a HofJ. "Tanto Vela limita a 108/min" non vale come argomento: è proprio la cosa da
dimostrare. Contro HofJ reale, inoltre, non si provocano i timeout, non si vede la finestra, la
latenza cambia a ogni giro e i valutatori non possono ripeterlo senza la nostra chiave.

**Come è fatto** (M13a):

- un **finto HofJ HTTP** (`loadtest/fake_hofj/`) che applica le **regole di HofJ, non le
  nostre**: 120/min per chiave, finestra ancorata come misurato (default) o scorrevole come
  dice il brief; latenza 2-6 s su `POST /v1/itineraries`; guasti iniettabili (esegue e resta
  appeso oltre 15 s, appeso senza eseguire, 5xx, errore di prodotto); seme fisso; registro di
  ogni chiamata. Le verifiche si fanno sul registro del finto, non sui log di Vela;
- il modo `VELA_UPSTREAM_MODE=loadtest`: HofJ via HTTP verso il finto, pagamenti finti,
  rifiuta host diversi da localhost o `fake-hofj`;
- `docker compose` con vela, postgres e fake-hofj;
- scenario Locust a modello aperto: 50.000 arrivi in 10 minuti con un imbuto (tutti chiedono
  una proposta, 30% "troppo caro", 20% accetta, stato ogni 30-60 s, 60% paga), le sentinelle
  Marco e Anna, e giri a 1k, 10k, 50k.

**Prima e dopo.** M13a misura il codice di oggi ("prima"); M18 introduce il token bucket, la
concorrenza, il client a 20 s e gli orfani contati; M13b rilancia lo stesso scenario ("dopo").
I due risultati affiancati sono la prova del diff nel pensiero. Dettaglio in
`loadtest/RESULTS.md`.

| Misura | Atteso | Prima (M13a) | Dopo (M13b) |
|---|---|---|---|
| Massimo di chiamate HofJ in qualsiasi 60 s | ≤ 108 | [numeri da M13a] | [numeri da M13b] |
| Numero di 429 | 0 | [numeri da M13a] | [numeri da M13b] |
| Chiamate HofJ al minuto con 1k / 10k / 50k viaggiatori | stessa curva, ≤ 108 | [numeri da M13a] | [numeri da M13b] |
| Link di pagamento al minuto | ≤ 17,4 (~12 previsti con 4 worker) | [numeri da M13a] | [numeri da M13b] |
| Marco: pagamento → confermato | < 60 s, confermato entro il minuto 7 | [numeri da M13a] | [numeri da M13b] |
| Anna al minuto 6: proposta | < 500 ms, attesa dichiarata | [numeri da M13a] | [numeri da M13b] |
| p50 / p95 / p99 dei cinque casi d'uso | p95 < 500 ms | [numeri da M13a] | [numeri da M13b] |
| Scarto p95 tra attesa dichiarata e reale | — | [numeri da M13a] | [numeri da M13b] |
| Prenotazioni per `itineraryId` | 1 | [numeri da M13a] | [numeri da M13b] |
| Itinerari orfani | contati | [numeri da M13a] | [numeri da M13b] |
| Età massima della coda | — | [numeri da M13a] | [numeri da M13b] |

Come lanciarlo: [comandi da `loadtest/README.md`, M13a].

### 5.6 Precedenti documentati

Nessuna di queste idee è nostra; le abbiamo prese da chi ha già risolto il problema.

| Da | Cosa | Dove in Vela |
|---|---|---|
| Google Ads API, [Rate limits](https://developers.google.com/google-ads/api/docs/productionize/rate-limits) | Nessun header; limitare i task concorrenti, rate limiter di cluster (token bucket), coda di messaggi | Coda (M5), token bucket e thread (M18) |
| GitHub, [Best practices for the REST API](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api) | Richieste in serie, pause tra le scritture, senza `Retry-After` attendere e crescere | Ritmo costante invece di raffiche (M18) |
| Expedia Rapid, [Handling booking requests](https://developers.expediagroup.com/rapid/resources/handle-booking-reqs-lodging) | Dopo un timeout di prenotazione, `Retrieve` con lo stesso `affiliate_reference_id`; non presumere il fallimento | Upsert su `itineraryId` (già); riferimento cliente per l'itinerario (domanda a HofJ) |
| Hotelbeds, [Best practices](https://developer.hotelbeds.com/documentation/hotels/knowledge-base/best-practices/) | Timeout di conferma ≥ 60 s; una sola disponibilità per prenotazione | Client a 20 s (M18); una sola `POST /itineraries` per ordine |
| Brandur, [Idempotency keys](https://brandur.org/idempotency-keys) | Punti di ripresa; con terze parti non idempotenti non ripetere alla cieca dopo un esito incerto | Passi salvati del job (M5); orfani contati (M18) |
| Stripe, [Rate limiters](https://stripe.com/blog/rate-limiters); Google SRE, [Handling overload](https://sre.google/sre-book/handling-overload/) | Capacità riservata alle richieste critiche; livelli di criticità | Riserva `booking` (M5) |
| AWS Builders' Library, [Avoiding insurmountable queue backlogs](https://d1.awsstatic.com/builderslibrary/pdfs/avoiding-insurmountable-queue-backlogs.pdf) | Misurare l'età della coda; scartare il lavoro abbandonato | Età della coda (M18), ordini silenziosi (M19) |
| SeatGeek ([AWS](https://aws.amazon.com/blogs/architecture/build-a-virtual-waiting-room-with-amazon-dynamodb-and-aws-lambda-at-seatgeek/)), Shopify ([parte I](https://shopify.engineering/surviving-flashes-of-high-write-traffic-using-scriptable-load-balancers-part-i)) | Sala d'attesa: traffico illimitato fuori, insieme attivo con tetto, attesa = persone davanti ÷ uscite al minuto; FIFO invece di lotteria | Accettazione asincrona con posizione e attesa (M5) |

---

## 6. Prossimi passi

- **Adapter A2A (RF-44).** Una quarta superficie accanto a REST e MCP, senza toccare il
  dominio: un'agent card che descrive Vela come agente che vende un viaggio di padel o tennis
  alla volta; i cinque casi d'uso come skill; un task A2A per acquisto. **[proposta, da
  confermare]** Stati del task mappati su quelli dell'ordine: `queued` e lavorazione →
  `working`, link da pagare → `input-required`, `confirmed` → `completed` con il codice come
  artefatto, `failed`/`cancelled` → `failed`/`canceled`. Stessa autenticazione della
  superficie MCP.
- **Email del codice (RF-26).** Oggi il codice resta disponibile senza limite di tempo via
  `get_order_status`. Inviarlo per email richiede un servizio di invio non concordato nelle
  24 ore.
- **OAuth per REST.** La superficie REST usa un token statico; per client di terze parti
  servirebbe lo stesso authorization server previsto per MCP.
- **Una seconda chiave HofJ.** Il tetto degli acquisti è per client: con due chiavi raddoppia.
  Scartato nelle 24 ore perché serve un accordo con HofJ, non codice.
- **Meno chiamate per link (M19)**, se la verifica su staging la consente; altrimenti resta
  il trade-off descritto nella sezione 5.1.
- **Domande aperte a HofJ** (`docs/hofj-questions.md`): la regola vera della finestra
  (il brief e l'OAS dicono "rolling", la sonda dice ancorata), un riferimento cliente per
  ritrovare un itinerario dopo un timeout, cliente e pax dopo il pagamento.
