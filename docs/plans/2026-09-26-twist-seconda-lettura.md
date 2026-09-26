# Twist, seconda lettura: contesto e modifiche ai documenti

Data: 2026-09-26. Branch di destinazione: `doc/twist-2`. Solo documenti, nessun codice,
nessuna chiamata esterna.

Questo file raccoglie tutto quello che è emerso il 2026-09-26 rileggendo il testo dettagliato del
twist (brief, sezione "The twist", richieste 1-5), in una conversazione fuori dal repo. Chi lo
esegue non ha quella conversazione: qui c'è tutto quello che serve. La sezione 8 dice file per
file cosa scrivere; le sezioni 1-7 sono la fonte da cui copiare fatti, ragionamenti e numeri.

Convenzione usata in tutto il file e da mantenere nei documenti:
**[misurato]** = verificato con chiamate reali o leggendo il codice;
**[previsto]** = deduzione da confermare con il load test (M13a);
**[proposta]** = scelta di design non ancora implementata.

---

## 1. Il testo del twist, in breve

- 50.000 viaggiatori in una finestra di dieci minuti al lancio.
- Quota HofJ per client, "rolling 60-second"; nessun `Retry-After` né `RateLimit-*`;
  `GET /v1/quota` è l'unico modo di sapere dove si è e consuma lo stesso budget.
- Le chiamate upstream vanno in timeout a 15 s.
- La ricerca dell'alloggio, inevitabile nel flusso d'acquisto, dura 2-6 s perché interroga la
  disponibilità live.
- "Your prototype must still take a booking at minute six."
- Da consegnare: (1) l'architettura che regge e il diff nel pensiero delle ultime dodici ore;
  (2) il budget di quota per browse, cart, hotel, booking e cosa si sacrifica per primo;
  (3) cosa degrada e cosa non deve mai degradare, con il minuto sei visto dal viaggiatore;
  (4) cosa facciamo del fatto che `POST /v1/bookings` è un upsert idempotente su `itineraryId`,
  e dove ci contiamo già; (5) un load test che i valutatori possano lanciare, con i numeri.
- Vincolo duro: il load test colpisce la nostra edge, con HofJ registrato o simulato. Un load
  test contro l'API reale è "una risposta sbagliata alla domanda".

La prima lettura del twist è del 2026-09-25 (`docs/decisions.md`, "Twist: 50.000 viaggiatori in
dieci minuti"; spec §4.10; roadmap M5) e resta valida. Questo file ne è il seguito.

---

## 2. La sonda della finestra di quota [misurato]

`scripts/quota_probe.py`, eseguito dall'utente il 2026-09-26 su `staging.api.hofj.com`, 6
chiamate a `GET /v1/quota` (nessun'altra chiamata). Output integrale:

```
host: staging.api.hofj.com
step0    local=862.1 used=1 start=11:41:03.039 end=11:42:03.039 hdr={}
A_fresh  local=926.0 used=1 start=11:42:06.769 end=11:43:06.769 hdr={}
B_0@50   local=976.8 used=2 start=11:42:06.769 end=11:43:06.769 hdr={}
B_1@50   local=977.6 used=3 start=11:42:06.769 end=11:43:06.769 hdr={}
B_2@50   local=978.3 used=4 start=11:42:06.769 end=11:43:06.769 hdr={}
Z@63     local=989.8 used=1 start=11:43:10.532 end=11:44:10.532 hdr={}
```

Procedura: `step0` legge la finestra corrente; lo script attende che scada; `A_fresh` apre una
finestra nuova all'istante S; tre chiamate a S + 50 s; una chiamata a S + 63 s (`Z`).

Lettura:
- `Z` ha `used=1`: le tre chiamate di 13 secondi prima non contano più → **non è una finestra
  scorrevole** (con una finestra scorrevole `Z` avrebbe visto `used=5`).
- La finestra di `Z` parte alle 11:43:10.532, cioè all'istante di `Z`, non alle 11:43:06.769
  (fine della precedente) → **non è a griglia fissa di 60 s**.
- Quindi: **finestra fissa di 60 s, ancorata alla prima chiamata dopo la scadenza** della
  precedente. Conferma le osservazioni del 2026-09-25 (`docs/api/quota-health.md`) anche a
  cavallo della scadenza, che allora non era stato verificato.
- Nessun header di rate limit (`hdr={}`) anche nelle risposte 200.
- Il brief ("It is a rolling window") e l'OAS ("rolling 60s window") dicono il contrario.
  Anche la spec, RF-36, dice "finestra mobile": va corretta.

Chiave usata: `API_BEAR_KEY` del `.env` (nel `.env` non esistono `HOFJ_API_KEY` né
`HOFJ_BASE_URL`). La chiave è stata incollata in chiaro in una chat: va rigenerata.

---

## 3. Cosa è cambiato nel ragionamento

### 3.1 Il contatore di quota deriva da quello di HofJ [misurato il codice, previsto l'effetto]

`vela/domain/quota.py`, `rolled()`: quando la finestra scade, la successiva parte da
`window_end + k × 60 s`, cioè su una griglia di 60 s a partire dall'ultimo allineamento
(`sync_from_snapshot`, al boot e dopo un 429). HofJ invece fa partire la nuova finestra alla
prima chiamata dopo la scadenza (sezione 2).

Esempio con i numeri della sonda: finestra HofJ 11:42:06.769 → 11:43:06.769; pausa di 3,8 s; la
chiamata successiva apre 11:43:10.532 → 11:44:10.532. Vela, sulla griglia, pensa
11:43:06.769 → 11:44:06.769. Alle 11:44:06.769 Vela azzera il conto, ma per HofJ la finestra
dura ancora 3,8 s.

Sotto carico [previsto]: i worker in attesa di budget ripartono tutti nell'istante in cui Vela
azzera il conto. Basta uno scarto di pochi decimi di secondo, anche solo la latenza di rete tra
la prenotazione del budget e l'arrivo della chiamata a HofJ, perché quella raffica cada nella
coda della finestra precedente di HofJ, già piena → 429. Il 429 azzera il budget della finestra
(RF-38) e costa un minuto. Il rischio è che succeda quasi a ogni finestra, dimezzando il ritmo.
Da confermare con M13a (il finto HofJ implementa la finestra ancorata).

Conclusione [proposta, M18]: invece di copiare la regola di HofJ (che non si può osservare
senza pagare quota e che il brief descrive in modo diverso), **distribuire le chiamate a ritmo
costante** con un token bucket condiviso: ritmo r, capienza B, con B + 60·r ≤ 108. In qualsiasi
intervallo di 60 s passano al massimo 108 chiamate, **qualunque sia la regola di HofJ**:
ancorata, a griglia o scorrevole. Esempio: B = 8, r = 100/60 ≈ 1,67 chiamate/s.

### 3.2 Il limite può essere la latenza, non la quota [previsto]

Numeri della quota (decisione M5): limite 120/min, margine 10% → limite effettivo 108; riserva
`booking` 20% → 21; restano 87 per gli acquisti; 5 chiamate per acquisto → **17,4 acquisti al
minuto**.

Latenza: 5 chiamate in serie da 2-6 s (media ~4 s) → un acquisto occupa un worker ~20 s → un
thread fa ~3 acquisti/min → con `worker_concurrency = 4` (default attuale) e una sola istanza
(Render `plan: free`) ~**12 acquisti/min**, sotto i 17,4 consentiti.

Legge di Little: concorrenza necessaria = ritmo × latenza = (17,4 × 5 / 60 ≈ 1,45 chiamate/s)
× 4 s ≈ 6 chiamate contemporanee, ~9 con 6 s. Proposta [M18]: ~10 thread, con il ritmo deciso
dal token bucket e non dal numero di thread. Precedente: Google Ads API consiglia di limitare
i task concorrenti e alzarli gradualmente, più un rate limiter di cluster (sezione 7).

### 3.3 Un timeout è un esito incerto [misurato il codice]

HofJ rinuncia verso il brand dopo 15 s; il brand potrebbe aver completato l'operazione. Un
timeout non dice se l'effetto è avvenuto.

- `POST /v1/bookings` è un upsert idempotente su `itineraryId` (docs/api/internal-checkout.md,
  `createBooking`). **Ci contiamo già** in tre punti:
  1. `BookingJob.run` in `vela/domain/booking.py`: su `UpstreamError` (rete, timeout, 5xx) ripete
     la stessa `POST` con lo stesso `itinerary_id`, fino a 5 tentativi con attese 5, 10, 20, 40 s;
  2. un job `running` con lease scaduto (`job_lease_seconds = 120`, `vela/config.py`) torna
     prelevabile e un altro worker o istanza lo riesegue, rifacendo la `POST`;
  3. [da verificare nel codice] se per un caso limite esistessero due job di prenotazione per
     lo stesso ordine (per esempio due verifiche di pagamento concorrenti; `active_for_order`
     dovrebbe impedirlo), `BookingJob.run` esce senza chiamate solo se l'ordine non è più
     `paid_pending_booking`: due worker concorrenti potrebbero mandare la `POST` due volte.
  In tutti e tre i casi la seconda `POST` restituisce lo stesso codice e non crea una seconda
  prenotazione. Senza l'upsert servirebbe una lettura di verifica (come la `Retrieve` di
  Expedia, sezione 7) prima di ogni nuovo tentativo.
- `POST /v1/itineraries` **non** è idempotente. `PurchaseJob` (`vela/domain/purchase.py`) su un
  timeout al passo 0 riprova e crea un secondo itinerario; il primo resta orfano su HofJ e ha
  consumato una chiamata. Proposta [M18]: contare gli orfani (campo o log) e metterli nel budget.
  Domanda per HofJ [da aggiungere a `docs/hofj-questions.md`]: possiamo passare un nostro
  riferimento (es. `affiliateId`) e ritrovare l'itinerario con quello dopo un timeout?
- Timeout del client: oggi 15 s (`TIMEOUT_SECONDS` in `vela/adapters/hofj_http.py`), uguale a
  quello di HofJ verso il brand: rischiamo di chiudere la connessione un attimo prima di ricevere
  la risposta di HofJ che dice "timeout del brand". Proposta [M18]: 20 s. Precedente: Hotelbeds
  chiede un timeout di conferma di almeno 60 s (sezione 7).
- Lease: un acquisto con 5 timeout in fila dura 75 s oggi, 100 s con client a 20 s, contro un
  lease di 120 s. Da rivedere in M18.

### 3.4 Spendere le chiamate su chi pagherà (look-to-book) [proposta, M19]

Oggi ogni accettazione costa 5 chiamate prima di sapere se il viaggiatore pagherà; sotto picco
molti non pagheranno o avranno chiuso la chat.

- Il totale dipende solo da prodotto, data, adulti e camere, fissati da `POST /v1/itineraries`.
  Per il link bastano 2 chiamate (creazione + `GET` itinerario). Cliente e passeggeri (3
  chiamate) potrebbero andare dopo il pagamento, prima del booking: chi non paga costerebbe 2
  chiamate invece di 5; i link al minuto passerebbero da ~17 a ~43. Rischi da verificare su
  staging con 2-3 chiamate: HofJ potrebbe rifiutare `PUT customer`/`PUT pax` dopo il pagamento
  (servirebbe un rimborso); il totale potrebbe cambiare dopo i pax; la riserva `booking`
  salirebbe a 4 chiamate per ordine pagato.
- Ordini silenziosi: un ordine in coda da ore il cui viaggiatore non chiede più lo stato consuma
  comunque 5 chiamate. Scadenza degli ordini senza segni di vita, o conferma al turno.
- Precedenti: OTA e fornitori penalizzano un rapporto ricerche/prenotazioni alto; Hotelbeds "mai
  più di una richiesta di disponibilità per prenotazione"; AWS "scartare il lavoro per cui il
  client ha già rinunciato" (sezione 7).

### 3.5 Il load test dimostra un confine [proposta, M13a]

- Mai contro HofJ, neanche "passando da Render": `render.yaml` ha `VELA_UPSTREAM_MODE: live` su
  HofJ staging, quindi un load test contro Render porterebbe il carico degli utenti a HofJ.
  L'argomento "tanto Vela limita a 108/min" non vale: è proprio la cosa da dimostrare, e con il
  contatore della 3.1 potrebbe fallire su un ambiente condiviso.
- Contro HofJ reale non si potrebbero provocare i timeout, non si vedrebbe la finestra, la
  latenza cambierebbe a ogni giro e i valutatori non potrebbero ripeterlo (non hanno la chiave).
- Finto HofJ HTTP che applica le **regole di HofJ, non le nostre** (finestra ancorata di
  default, scorrevole come opzione): se usasse la nostra finestra il test passerebbe per
  costruzione. Registro di ogni chiamata: le verifiche si fanno sul registro del finto, non sui
  log di Vela.
- La misura chiave: chiamate a HofJ al minuto con 1.000, 10.000 e 50.000 viaggiatori → la stessa
  curva, sotto 108.
- Anche Stripe va simulato: oggi il modo `live` richiede `STRIPE_SECRET_KEY` e non monta il
  checkout finto (`vela/app.py`), quindi serve un modo `loadtest` (HofJ via HTTP verso il finto,
  pagamenti finti), che rifiuta host diversi da localhost/`fake-hofj`.
- Prima e dopo: M13a misura il codice di oggi, M18 corregge, M13b rilancia lo stesso scenario.
  I due risultati affiancati sono la prova del "diff nel pensiero".

### 3.6 M10 entra nel budget [misurato il codice]

Il sync multi-brand (M10) chiama HofJ al boot e ogni 6 ore (pagine e dettagli di due brand)
come classe `sync`, e si ferma se ci sono acquisti in attesa (`vela/sync.py`, `_call` con
`purchase_waiting`). Padel e tennis usano la stessa chiave, quindi la stessa quota. Il sync è la
prima cosa sacrificata sotto picco.

### 3.7 Un'ipotesi sbagliata e corretta

Il 2026-09-26 si era dato per buono il "rolling" del brief e si era proposto il token bucket
per quel motivo. La sonda (sezione 2) l'ha smentito. Il token bucket resta la scelta giusta, ma
per un motivo diverso: la deriva della 3.1, e il fatto che non possiamo osservare HofJ senza
pagare quota. Vale la pena scriverlo: il twist dice di leggere "come rispondete a un cambio di
requisiti sotto pressione".

### 3.8 Accettazione con attesa breve (M20, già in roadmap)

Già registrata in `docs/decisions.md` ("Accettazione con attesa breve") e in roadmap M20: non va
riscritta. Solo da collocare nel grafo delle ondate (sezione 8.5).

---

## 4. Il diff nel pensiero (per decisions.md e ARCHITECTURE.md)

Tre momenti:

1. **Prima del twist (mattina del 2026-09-25).** La quota era un errore da gestire:
   accettazione sincrona entro 30 s (vecchia RNF-04), "riprova tra un minuto" a quota finita
   (vecchia RF-37).
2. **Prima lettura (sera del 2026-09-25).** La quota diventa capacità da pianificare: coda in
   Postgres, scheduler unico per il cluster, accettazione sempre asincrona con attesa dichiarata,
   riserva per le prenotazioni, nessun tetto all'attesa. Scartati Redis/Celery, drenatore unico
   eletto, ibrido sincrono.
3. **Seconda lettura (2026-09-26).** L'impianto regge; cambiano cinque idee:

| Prima pensavamo | Ora pensiamo | Cosa ce l'ha fatto cambiare |
|---|---|---|
| Bisogna copiare la finestra di HofJ e allinearsi | Bisogna essere sicuri con qualunque finestra: ritmo costante | Il brief dice "rolling", la sonda misura una finestra ancorata, il nostro contatore va a griglia. Non potendo osservare HofJ gratis, ci si protegge da tutti i modelli |
| Il limite è la quota | Il limite può essere la latenza: ~12 acquisti/min con 4 thread invece di 17,4 | La ricerca dell'alloggio da 2-6 s; legge di Little |
| Un timeout è un errore: si riprova | Un timeout è un esito incerto: si riprova solo dove è idempotente | Il timeout a 15 s: booking upsert sicuro, itinerario no (orfani); precedenti Expedia e Brandur |
| Le chiamate si spendono in ordine d'arrivo | Le chiamate vanno spese su chi pagherà | Look-to-book: 5 chiamate per link che magari nessuno paga |
| Il load test misura le prestazioni | Il load test dimostra un confine: chiamate a HofJ piatte da 1k a 50k utenti | Il vincolo "mai contro HofJ"; il finto deve applicare le regole di HofJ, non le nostre |

Non cambia: coda in Postgres, accettazione asincrona con un solo percorso, riserva per le
prenotazioni, nessun servizio in più.

---

## 5. Budget di quota (per M15 e per la tabella in decisions.md)

Limite 120/min per chiave (padel e tennis insieme). Margine 10% per gli altri usi della chiave
→ 108. Riserva `booking` 20% → 21. Acquisti → 87, cioè 17,4 al minuto.

| Voce del brief | Chiamate HofJ | Classe | Note |
|---|---|---|---|
| Browse (intento, proposta, rifiuto) | 0 | — | Catalogo nel DB, sincronizzato da M10 |
| Cart | 5 per ordine: itinerario, cliente, lettura pax, scrittura pax, totale | `purchase` | Una sola volta per ordine; ripetizioni solo su rete/5xx, massimo 3 finestre |
| Hotel | Dentro `POST /v1/itineraries` (hotel di default, RF-15) | `purchase` | È la chiamata da 2-6 s; nessuna chiamata a `/accommodations` |
| Booking | 1 per ordine pagato | `booking` | Dalla riserva di 21/min: non aspetta la coda d'acquisto |
| Lettura quota | 1 al boot e dopo un 429 | `booking` | Mai in ciclo |
| Verifica del pagamento | 0 HofJ | — | Interroga Stripe |
| Sync del catalogo | pagine + dettagli dei due brand, ogni 6 h | `sync` | Solo a coda d'acquisto vuota |

Cosa si sacrifica, in ordine: 1) il sync; 2) l'attesa degli acquisti, che cresce, dichiarata,
senza tetto; 3) mai le prenotazioni degli ordini pagati.

---

## 6. Il minuto sei visto dal viaggiatore (per M15)

- **Marco** accetta al minuto 1: è tra i primi in coda, verso il minuto 3 riceve il link, paga,
  e al minuto 6 la prenotazione parte dalla riserva: codice entro circa un minuto dal pagamento.
- **Anna** arriva al minuto 6: scrive la sua frase e riceve subito una proposta; "troppo caro" e
  ne riceve subito un'altra; accetta e si sente dire, per esempio, "sei in coda, circa due ore"
  (il numero dipende da quanti hanno accettato prima). Non vede errori né timeout; può aspettare
  o rinunciare con `reject_proposal`.

Cosa degrada: solo l'attesa del link, dichiarata. Cosa non degrada mai: la conversazione
(0 chiamate HofJ, p95 < 500 ms) e la conferma di chi ha pagato.

---

## 7. Precedenti documentati (per M15)

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

## 8. Modifiche da fare, file per file

### 8.1 `docs/api/quota-health.md`

Nella sezione `GET /v1/quota`, "Comportamento osservato della finestra": aggiungere la sonda del
2026-09-26 (procedura e output integrale della sezione 2) e sostituire la riga "Non è stato
verificato il comportamento a cavallo della scadenza con traffico continuo" con il risultato:
finestra fissa ancorata alla prima chiamata dopo la scadenza, verificata a cavallo della
scadenza; non scorrevole, non a griglia. Resta non verificato: `retryAfterSeconds` nel corpo
del 429 (nessun 429 generato).

### 8.2 `docs/api/differences.md`

Riga della tabella con `#` = 8 (`/v1/quota`, "rolling 60s window"): aggiungere "verificato anche
a cavallo della scadenza il 2026-09-26 (`scripts/quota_probe.py`)".

### 8.3 `docs/hofj-questions.md`

Aggiungere: (a) la finestra è davvero ancorata anche in produzione, o scorrevole come dicono
brief e OAS? (b) si può passare un riferimento del cliente a `POST /v1/itineraries` e ritrovare
l'itinerario con quello dopo un timeout? (c) `PUT customer` e `PUT pax` sono accettati dopo il
pagamento?

### 8.4 `docs/decisions.md`

Nuova voce in coda, `## 2026-09-26 — Twist, seconda lettura`, con:
- paragrafo "Origine": testo dettagliato del twist, rilettura del codice, sonda di sezione 2;
- tabella Decisione | Scelta | Motivo, una riga per ciascuno: finestra misurata (2); ritmo
  costante con token bucket (3.1); thread per la latenza (3.2); timeout come esito incerto,
  orfani, client a 20 s (3.3); spendere su chi paga, condizionato a verifica (3.4); load test
  solo contro il finto, modo `loadtest`, prima e dopo (3.5); sync nel budget (3.6);
  l'ipotesi "rolling" sbagliata e corretta (3.7). Ogni riga dice se è misurata, prevista o
  proposta;
- la tabella della sezione 4 ("diff nel pensiero") e la tabella del budget della sezione 5.

### 8.5 `docs/roadmap.md`

- Intestazione: aggiungere "Aggiornata il 2026-09-26 per la seconda lettura del twist
  (`docs/plans/2026-09-26-twist-seconda-lettura.md`): M13 diventa M13a e M13b, nuove M18 e M19,
  M15 allargata."
- Grafo: in ondata 5 al posto di "M13 Load test" mettere "M13a Banco di prova", "M18 Quota a
  ritmo", "M20 Accept con attesa"; nuova riga "M13b Rilancio" dopo M13a e M18; M19 opzionale
  dopo M13b; M15 dipende da M13b. M10 e M17 risultano concluse.
- Tabella riassuntiva: togliere M13; aggiungere M13a (M, dipende M5, M10; ondata 5, parallela
  con M18, M20; mergiare prima di M18), M13b (S, dipende M13a, M18), M18 (M, dipende M5; ondata
  5, parallela con M13a, M20), M19 (M, dipende M18, M13b; condizionata). Aggiornare la riga di M20:
  "mergiare dopo M13b". Regola dei worktree: `vela/config.py` in comune tra M13a, M18, M20.
- Sezione M13: sostituirla con M13a e M13b (testi sotto).
- Nuove sezioni M18 e M19 (testi sotto).
- Sezione M15: nello scope di `ARCHITECTURE.md` aggiungere la sezione twist con le 5 richieste
  del brief (diff nel pensiero dalla sezione 4; budget dalla sezione 5; minuto sei dalla sezione
  6; idempotenza dalla 3.3 con il riferimento a `BookingJob.run`; load test da `RESULTS.md`) e i
  precedenti della sezione 7. Dipende da M13b.
- Matrice: RNF-05 e RNF-10 → M13a, M13b; RF-36..38 e RF-47 → M5, M18; RNF-04 → M5, M18.

Testo di **M13a — Banco di prova e numeri di partenza** (taglia M):
- Risultato: un load test lanciabile da chiunque con `docker compose up` e un comando, che
  colpisce solo la nostra edge; `RESULTS.md` con la colonna "prima" misurata sul codice attuale.
- Scope: finto HofJ HTTP in `loadtest/fake_hofj/` (app ASGI asincrona, un processo; stato da
  `ReplayHofJ` con latenza 0 e quota illimitata; strato di regole con le rotte del carrello,
  `/v1/quota`, `POST /v1/bookings`, lista e dettaglio prodotti dalle 4 fixture per il sync di
  M10; forme reali dell'envelope e degli errori; quota per chiave con `--window anchored`
  (default) o `rolling`, 120/min; `--background-rpm`; latenza 2-6 s su `POST /itineraries` e
  tarata su `scripts/rest_flow.py` per gli altri, `--latency pessimistic`; guasti per endpoint:
  esegui-e-resta-appeso oltre 15 s, appeso senza eseguire, 5xx, 502 di prodotto; seme fisso;
  registro JSONL; `/_fake/stats` e `/_fake/reset` fuori quota). Modo `VELA_UPSTREAM_MODE=loadtest`
  (HofJ via HTTP, pagamenti finti, checkout di replay; rifiuta host diversi da localhost o
  `fake-hofj`). `docker-compose.yml` con vela, postgres, fake-hofj. Scenario Locust a modello
  aperto: 50.000 arrivi in 10 minuti, imbuto parametrico (100% proposta, 30% "troppo caro", 20%
  accetta, stato ogni 30-60 s, 60% paga), sentinelle Marco (accetta al minuto 1, confermato entro
  il 7) e Anna (arriva al 6, proposta < 500 ms e attesa dichiarata), giri a 1k, 10k, 50k.
  `loadtest/report.py`. `RESULTS.md` e `loadtest/README.md`.
- Non tocca `vela/domain/quota.py` né il `QuotaStore` (M18 in parallelo).
- Test di completamento: test unitari del finto (finestra ancorata e scorrevole ai bordi;
  esegui-e-appeso sul booking → un solo codice); test di contratto del vero `HofJHttp` contro il
  finto via transport ASGI; scenario eseguito e `RESULTS.md` compilato anche se i numeri sono
  cattivi (sono il "prima"). Nessuna chiamata a HofJ né a Stripe.
- Misure del report: massimo di chiamate in qualsiasi 60 s; numero di 429; chiamate per endpoint
  e al minuto nei tre giri; link al minuto; Marco pagamento → confermato; scarto p95 tra attesa
  dichiarata e reale; prenotazioni per `itineraryId`; itinerari orfani; età della coda;
  p50/p95/p99 dei cinque casi d'uso.

Testo di **M13b — Rilancio dopo M18** (taglia S): stesso scenario di M13a (seme, imbuto,
finestre anchored e rolling, tre giri) sul codice con M18; `RESULTS.md` con "prima" e "dopo" e
una frase per differenza; se un criterio fallisce (429 > 0, più di 108 chiamate in 60 s, Marco
oltre il minuto 7, prenotazioni doppie) si riporta il dato, non si aggiusta il test.

Testo di **M18 — Quota a ritmo costante** (taglia M):
- Risultato: nessun intervallo di 60 s contiene più di 108 chiamate HofJ, qualunque sia la
  regola della finestra di HofJ.
- Scope: `QuotaStore` come token bucket condiviso in Postgres (B + 60·r ≤ 108, stesse classi e
  priorità, prenotazione atomica di blocchi); 429 → bucket svuotato e una sola rilettura di
  `/v1/quota` (1 token `booking`); `next_window_start` e attesa stimata (RF-48) aggiornati;
  `worker_concurrency` ~10; timeout del client a 20 s; timeout su `POST /v1/itineraries` contato
  come orfano; lease dei job rivisto per 5 × 20 s; `/health` con età della coda e stato del
  bucket.
- Test di completamento: contratto condiviso memoria/Postgres del bucket (mai più di 108 in
  una finestra scorrevole simulata di 60 s, anche con finestre HofJ ancorate a istanti diversi);
  8 thread su Postgres; riserva `booking` a coda piena; 429 senza ripetizione immediata;
  `LaunchBurstTest` aggiornato. Nessuna chiamata esterna.

Testo di **M19 — Meno chiamate per link e ordini silenziosi** (taglia M, condizionata):
verifica su staging con 2-3 chiamate dichiarate (dal terminale dell'utente) se `PUT customer` e
`PUT pax` sono accettati dopo il pagamento e se il totale resta invariato; se sì, il job
d'acquisto si ferma a itinerario + totale + link e cliente/pax passano nel job di booking
(riserva `booking` a 4 chiamate per ordine); scadenza degli ordini in coda senza richieste di
stato da N minuti. Se la verifica dice no: solo il trade-off in `ARCHITECTURE.md`. Da fare
dopo M13b (cambia i numeri).

Per ciascuna sezione nuova scrivere anche il blocco **Prompt** nello stile delle altre, che
rimandi a questa sezione della roadmap e ai file citati.

### 8.6 `docs/spec.md`

- Intestazione: "RF-36, RF-47, RNF-04, RNF-10 aggiornati il 2026-09-26 per la seconda lettura
  del twist".
- **RF-36**: togliere "per finestra mobile di 60 secondi"; scrivere che il guardiano distribuisce
  le chiamate a ritmo costante (token bucket condiviso in Postgres) in modo che nessun intervallo
  di 60 s superi il limite effettivo, inizializzato da `GET /v1/quota` all'avvio. Nota: la
  finestra di HofJ misurata è fissa e ancorata alla prima chiamata dopo la scadenza
  (`docs/api/quota-health.md`); il ritmo costante è sicuro anche se fosse scorrevole.
- **RF-47**: "un contatore per finestra di 60 s" → "un token bucket condiviso"; resto invariato
  (classi, riserva, blocchi atomici, 429, `/v1/quota` mai in ciclo).
- **RF-48**: acquisti per finestra = (ritmo × 60 − riserva `booking`) ÷ 5, se M18 cambia la
  formula; altrimenti invariato.
- **RNF-04**: "Le chiamate a HofJ hanno timeout di 15 secondi" → "HofJ rinuncia verso il brand
  dopo 15 s; il client di Vela aspetta 20 s. Un timeout è un esito incerto: si ripetono solo le
  chiamate idempotenti (`POST /v1/bookings`); un timeout su `POST /v1/itineraries` conta un
  itinerario probabilmente orfano."
- **RNF-10**: togliere "contro l'URL live"; il load test colpisce l'istanza locale o un'istanza in
  modo `loadtest`, con HofJ e Stripe simulati; mai HofJ reale.

---

## 9. Cosa non fare

- Nessuna chiamata a HofJ, Stripe o Anthropic in questo branch.
- Non scrivere le previsioni (3.1 effetto, 3.2) come fatti: vanno marcate "da confermare con
  M13a".
- Non riscrivere M20 né la sua decisione: esistono già.
- Non cambiare codice: le correzioni sono di M18 e M19.
- Suite verde alla fine: `uv run python -m unittest discover -s tests` (alcuni test leggono
  roadmap o spec: aggiornarli se servono, ed elencarli in decisions.md).
