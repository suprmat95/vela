# Risultati del load test del twist

Colonna **"prima"**: il codice dopo M5, M10 e M17, misurato il 2026-09-26 con il banco di M13a.
Colonna **"dopo"**: il codice con M18 (token bucket, 10 worker, client a 20 s), misurato il
2026-09-26 da M13b sul commit `a9d1f57` con **gli stessi giri**: stesso banco, stesso finto,
stesso scenario, stesso seme, stessi viaggiatori. Tra i due cambia solo `vela/`
(`git diff 14ddd31..a9d1f57 -- loadtest docker-compose.yml Dockerfile docker-entrypoint.sh` è
vuoto). Come si lanciano: `loadtest/README.md`. Decisioni: `docs/decisions.md` ("Twist, seconda
lettura", "M13a: banco di prova", "M18: quota a ritmo costante", "M13b: rilancio"). Report
completi dei giri in `loadtest/out/<giro>/report.md` (non versionati; si rigenerano con
`run.py`).

Etichette: **[misurato]** = dal registro del finto HofJ o da Locust; **[proiezione]** = calcolato
da `loadtest/projection.py` a partire dai ritmi misurati.

## Banco

- Tutto in locale con `docker compose`: Vela (`VELA_UPSTREAM_MODE=loadtest`, un processo
  uvicorn), Postgres 16, finto HofJ, Locust. **Nessuna chiamata a HofJ né a Stripe.** MacBook
  Pro M4 Pro, Docker Desktop (12 CPU, 17,5 GB), la stessa macchina per "prima" e "dopo".
- Vela "prima": contatore a finestra a griglia di 60 s, `worker_concurrency = 4`, client HofJ a
  15 s. Vela "dopo" (M18): token bucket in Postgres con capienza B = 8 e ritmo r = 100/60
  gettoni/s (B + 60·r = 108), `worker_concurrency = 10`, client a 20 s, attesa dichiarata
  calcolata sull'80% del ritmo (16 acquisti/min).
- Finto HofJ con le regole di HofJ: 120 chiamate/min per chiave, finestra **ancorata** (come
  misurato dalla sonda) salvo il giro E; 12/min di altri usi della stessa chiave; latenza
  `standard` = 2-6 s su `POST /v1/itineraries`, 0,3-1,5 s sugli altri endpoint **[previsto]**.
  Una chiamata respinta con 429 conta nella finestra.
- Scenario a modello aperto, seme 13: 100% proposta, 30% "troppo caro", 20% accetta, stato ogni
  30-60 s, 60% di chi riceve il link paga. Sentinelle: Marco accetta a 60 s, Anna arriva al 60%
  della finestra degli arrivi. Catalogo caricato al boot dalle fixture (126 prodotti attivi).
- Giri ridotti (decisione dell'utente): 5 minuti di arrivi + 3 di coda
  (`--duration 8 --arrival-minutes 5 --tail-minutes 3`), ognuno da compose pulito. Con il 20%
  che accetta la coda satura già a 500 viaggiatori in 5 minuti: da lì in poi chiamate HofJ al
  minuto e ritmo degli acquisti non dipendono dal numero di viaggiatori, e i numeri del twist si
  proiettano.

## Criteri

Un criterio fallito si riporta con il numero, senza aggiustare il test (roadmap M13b).

| Criterio | | A-500 | B-1000 | C-2500 | D-1000-guasti | E-1000-rolling |
|---|---|---|---|---|---|---|
| 429 ricevuti = 0 | prima | ✅ 0 | ✅ 0 | ✅ 0 | ✅ 0 | ❌ **3** |
| | dopo | ✅ 0 | ✅ 0 | ✅ 0 | ✅ 0 | ✅ 0 |
| Chiamate Vela → HofJ in qualsiasi 60 s ≤ 108 | prima | ❌ **132** | ❌ **132** | ❌ **138** | ✅ 66 | ❌ **111** |
| | dopo | ✅ 108 | ✅ 105 | ✅ 106 | ✅ 107 | ✅ 107 |
| Marco confermato entro il minuto 7 (420 s) | prima | ✅ 75 s | ✅ 130 s | ✅ 376 s | ✅ 235 s | ✅ 185 s |
| | dopo | ✅ 95 s | ✅ 140 s | ✅ 367 s | ✅ 180 s | ✅ 140 s |
| Nessun `itineraryId` con due prenotazioni (booking distinti nel finto = itinerari prenotati) | prima | ✅ | ✅ | ✅ | ✅ | ✅ |
| | dopo | ✅ 67 = 67 | ✅ 83 = 83 | ✅ 85 = 85 | ✅ 74 = 74 | ✅ 82 = 82 |

**Dopo M18 tutti i criteri passano in tutti i giri.** Il quarto passa solo grazie all'upsert di
`POST /v1/bookings`: dopo M18 Vela manda due volte la stessa `POST` anche senza guasti (punto 6
di "Cosa cambia con M18").

## Giri misurati

| | A prima | A dopo | B prima | B dopo | C prima | C dopo | D prima | D dopo | E prima | E dopo |
|---|---|---|---|---|---|---|---|---|---|---|
| Finto HofJ | ancorata, standard | = | ancorata, standard | = | ancorata, standard | = | ancorata, **pessimistic**, guasti | = | **scorrevole**, standard | = |
| Viaggiatori in 5 min | 500 | 500 | 1.000 | 1.000 | 2.500 | 2.500 | 1.000 | 1.000 | 1.000 | 1.000 |
| **Massimo chiamate Vela → HofJ in 60 s** | **132** | **108** | **132** | **105** | **138** | **106** | 66 | 107 | 111 | 107 |
| Massimo in 60 s con gli altri usi | 144 | 120 | 144 | 117 | 150 | 118 | 78 | 119 | 123 | 119 |
| **429 ricevuti** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **3** | **0** |
| Chiamate Vela al minuto, a regime | 84 | 99 | 92 | 99 | 92 | 99 | 58 | 96 | 81 | 99 |
| Link (acquisti) al minuto, a regime | 14,4 | 17,6 | 17,6 | 17,8 | 16,3 | 17,8 | 9,9 | 16,0 | 15,4 | 17,8 |
| Accettazioni / link / confermati | 110 / 110 / 67 | 110 / 110 / 67 | 216 / 133 / 70 | 216 / 138 / 71 | 487 / 127 / 73 | 487 / 135 / 74 | 216 / 76 / 44 | 216 / 125 / 66 | 216 / 118 / 62 | 216 / 137 / 72 |
| In coda alla fine | 0 | 0 | 83 | 78 | 360 | 352 | 140 | 91 | 98 | 79 |
| Età massima della coda (s) | 108 | 108 | 300 | 301 | 414 | 402 | 377 | 310 | 314 | 301 |
| Pagamento → confermato, sentinelle (s) | 5 | 5 | 5 | 5 | 5 | 5 | 10 | 30 | 5 | 5 |
| Itinerari con `POST /v1/bookings` ripetuta | 0 | **1** | 0 | 0 | 0 | **4** | 2 | **6** | 0 | **2** |
| Booking distinti nel finto | — | 67 | — | 83 | — | 85 | — | 74 | — | 82 |
| Itinerari orfani | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | 0 | 0 |
| Marco: attesa dichiarata / reale (s) | 7 / 10 | 27 / 30 | 49 / 65 | 75 / 75 | 280 / 311 | 327 / 302 | 97 / 165 | 79 / 90 | 69 / 120 | 75 / 75 |
| Marco: confermato a (s) | 75 | 95 | 130 | 140 | 376 | 367 | 235 | 180 | 185 | 140 |
| Errori REST | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p95 REST peggiore (ms) | 18 | 20 | 24 | **110** | 30 | **200** | 24 | 27 | 21 | **110** |
| Richieste REST/s, picco | — | 7,8 | 16 | 15,9 | 34 | 34,0 | — | 15,9 | — | 15,8 |

"A regime" nella colonna "dopo" = media dei minuti 2-6. Le POST ripetute del "dopo" sono state
contate sul registro del finto; i job doppi osservati sul DB di Vela durante D ed E, in sola
lettura.

p50/p95/p99 dei casi d'uso, giro C-2500 (il più carico) **[misurato]**:

| Caso d'uso | Richieste | Errori | p50 ms prima / dopo | p95 ms prima / dopo | p99 ms prima / dopo |
|---|---|---|---|---|---|
| `create_intent` | 2.502 | 0 / 0 | 3 / 8 | 10 / 29 | 13 / 42 |
| `get_proposal` | 2.502 | 0 / 0 | 12 / 25 | 22 / 140 | 39 / 160 |
| `reject_proposal` | 720 | 0 / 0 | 13 / 35 | 30 / 200 | 47 / 240 |
| `accept_proposal` | 487 | 0 / 0 | 7 / 12 | 16 / 130 | 25 / 150 |
| `get_order_status` | 2.902 / 2.906 | 0 / 0 | 8 / 37 | 15 / 70 | 21 / 92 |

## Cosa cambia con M18 [misurato]

Una frase per ogni differenza tra "prima" e "dopo".

1. **Il confine regge.** Il massimo di chiamate Vela in 60 s scende da 132-138 a 105-108 con la
   finestra ancorata e da 111 a 107 con quella scorrevole: il token bucket non supera mai 108,
   qualunque sia la regola di HofJ. A-500 tocca esattamente 108, che è il tetto per costruzione
   (B + 60·r): nessun margine oltre quello del 10% già dichiarato.
2. **Con gli altri usi della chiave Vela non supera più i 120 di HofJ:** il massimo passa da
   123-150 a 117-120.
3. **Niente più 429 con la finestra scorrevole:** i 3 429 del minuto 1 di E-prima (con un minuto
   a metà ritmo dopo) diventano 0.
4. **Il ritmo è piatto e usa il budget:** 99 chiamate al minuto a regime in ogni giro con latenza
   standard (prima 81-92, a raffiche), cioè il ritmo r = 100/min del bucket.
5. **Con latenza pessimistica il limite torna a essere la quota e non la latenza:** in D i link
   al minuto passano da 9,9 a 16,0 e le chiamate da 58 a 96 al minuto, perché 10 worker coprono
   le 5 chiamate da 2-6 s (legge di Little, §3.2 della seconda lettura); in coda alla fine
   restano 91 persone invece di 140 e l'età massima della coda scende da 377 a 310 s. D è l'unico
   giro in cui il massimo in 60 s sale (66 → 107): prima Vela non riusciva a usare il budget.
6. **Regressione: `POST /v1/bookings` doppie senza guasti.** Itinerari con la POST ripetuta: 1 in
   A, 4 in C, 2 in E (prima 0) e 6 in D (prima 2). Le due POST partono nello stesso istante e
   rispondono entrambe 200. Causa, verificata sul DB di Vela: due job `booking` per lo stesso
   ordine, accodati a 2-6 ms di distanza, perché checkout e verifica del pagamento chiamano
   insieme `mark_paid` e il controllo "c'è già un job attivo?" in `_enqueue_booking`
   (`vela/domain/orders.py`) non è atomico. È la corsa teorica già annotata in `docs/decisions.md`
   (M18, "Timeout come esito incerto"); con 10 worker e più pagamenti al minuto diventa
   frequente. In D il DB mostra 1 ordine con due job: le altre 5 ripetizioni sono quelle previste
   dopo un timeout con esecuzione (`hang_then_execute`). Il finto registra sempre un booking per
   itinerario (upsert), quindi il criterio passa, ma ogni doppione costa un gettone e l'upsert di
   HofJ vero è stato visto solo in due sonde. Corretta in `task/booking-race` (sotto, "Dopo il
   fix").
7. **Più itinerari orfani nel giro con guasti:** 3 invece di 1, con lo stesso 3% di
   `hang_then_execute` su `POST /v1/itineraries`, perché Vela fa più acquisti (125 link contro
   76). Adesso sono contati (`orders.orphan_itineraries` e `/health`).
8. **Marco con guasti: 30 s dal pagamento alla conferma invece di 10.** La sua `POST
   /v1/bookings` (a 150,2 s) è caduta su un `hang_then_execute` ed è rimasta appesa 24 s: il
   client aspetta 20 s invece di 15 prima di ripetere. È il prezzo previsto del timeout più
   lungo; resta confermato a 180 s, prima di quanto accadeva prima (235 s).
9. **L'attesa dichiarata è diventata onesta.** Marco: dichiarati/reali 27/30, 75/75, 327/302,
   79/90, 75/75 s (prima 7/10, 49/65, 280/311, 97/165, 69/120). Con l'80% del ritmo nella stima
   (RF-48) l'attesa reale non supera più la dichiarata di oltre 11 s, e a coda piena (C) Vela
   dichiara un po' più di quanto serve.
10. **Marco è confermato allo stesso punto o prima, tranne a coda vuota:** 95 contro 75 s in A e
    140 contro 130 s in B. A 500 viaggiatori la coda non satura e il bucket, a ritmo costante,
    non concede più le raffiche del contatore a griglia; in C, D ed E Marco arriva prima (367,
    180, 140 s contro 376, 235, 185).
11. **Il ritmo pieno di acquisti fa salire un po' tutti i conteggi:** confermati 71-74 contro
    70-73 con latenza standard, 66 contro 44 con i guasti, 72 contro 62 con la finestra
    scorrevole.
12. **La conversazione rallenta, senza errori.** p95 REST peggiore: 110 ms in B ed E e 200 ms in
    C (prima 21-30 ms); in C `get_proposal` passa da 22 a 140 ms e `get_order_status` da 15 a
    70 ms. Il picco REST è lo stesso (16 e 34 req/s): cambia il lavoro in background nello stesso
    processo uvicorn, 10 worker invece di 4 sullo stesso interprete e sullo stesso pool di
    connessioni. **[Ipotesi, non misurata a parte.]** Restiamo ben sotto la soglia di 500 ms per
    la proposta (sentinella Anna: 10-12 ms), ma il margine a 430 req/s della proiezione si
    riduce.

## Dopo il fix delle prenotazioni doppie (task/booking-race) [misurato]

Passaggio di stato atomico dell'ordine più indice unico sui job `booking` attivi (decisione in
`docs/decisions.md`). Rilanciati identici A-500 e C-2500 il 2026-09-26 sul commit `49cc1cb`.

| | A dopo M18 | A dopo il fix | C dopo M18 | C dopo il fix |
|---|---|---|---|---|
| Itinerari con `POST /v1/bookings` ripetuta | 1 | **0** | 4 | **0** |
| `POST /v1/bookings` / itinerari prenotati | 68 / 67 | 67 / 67 | 89 / 85 | 85 / 85 |
| Massimo chiamate Vela → HofJ in 60 s | 108 | 106 | 106 | 106 |
| 429 ricevuti | 0 | 0 | 0 | 0 |
| Marco confermato a (s) | 95 | 95 | 367 | 372 |
| Accettazioni / link / confermati | 110 / 110 / 67 | 110 / 110 / 67 | 487 / 135 / 74 | 487 / 135 / 75 |
| Errori REST / p95 REST peggiore (ms) | 0 / 20 | 0 / 19 | 0 / 200 | 0 / 190 |

Una sola `POST /v1/bookings` per itinerario prenotato, in entrambi i giri. Gli altri numeri
restano quelli di M18: criteri tutti passati. Il p95 della conversazione non cambia (punto 12).

## Dopo la cache del prezzo (RF-84) [misurato]

Un solo giro, per scelta dell'utente: C-2500 identico ai precedenti (`--travelers 2500 --duration 8
--arrival-minutes 5 --tail-minutes 3`, seme 13, finto ancorato con latenza standard), il
2026-09-27 sul commit `526459e` (`master` con la conferma del prezzo, M21-A..E, RF-83 e la cache
del prezzo, `price_quote_ttl_seconds = 900`), da compose pulito, stessa macchina (Apple M4 Pro,
Docker Desktop 12 CPU, 17,5 GB). Nessun giro di controllo con la cache spenta: tra `49cc1cb` e
`526459e` cambia anche altro (conferma del prezzo prima del link, M20 assorbita, M21, RF-83), quindi
solo le righe sugli hit e sul prezzo sentito sono attribuibili alla cache da sola. Report completo
in `loadtest/out/2500-cache/report.md` (non versionato).

Gli hit sono contati a posteriori da `travelers.jsonl`: un'accettazione servita dalla cache
risponde `200 order_status` in `awaiting_confirmation`, senza `position` né `wait_seconds`; un
`202 order_queued` appena accodato le ha. `t_priced` è il polling in cui il viaggiatore finto vede
il prezzo. `report.py` non calcola ancora queste due misure.

| | C dopo M18 (fix) | C con la cache |
|---|---|---|
| Massimo chiamate Vela → HofJ in 60 s | 106 | 106 |
| Massimo in 60 s con gli altri usi | 118 | 118 |
| 429 ricevuti | 0 | 0 |
| Chiamate Vela al minuto, a regime (minuti 2-6) | 99 | 99 |
| Link (acquisti) al minuto, a regime | 17,8 | 17,8 |
| Accettazioni / link / confermati | 487 / 135 / 75 | 487 / 127 / 72 |
| **Accettazioni con il prezzo subito (hit)** | — (il prezzo arrivava con il carrello) | **473 su 487** |
| **Prezzo effettivo sentito entro il giro** | 135 su 487 (chi è arrivato al link) | **487 su 487** |
| Prezzo sentito dopo l'accettazione, p50 / p95 (s) | — | 44,7 / 58,9 (polling di 30-60 s del viaggiatore finto; Marco e Anna, che interrogano ogni 5 s, 5 s) |
| Accettazioni in coda per il prezzo (leader) | 487 | 14, posizione media 1,9, attesa dichiarata 8-12 s |
| Richieste `accept_proposal` | 487 | 974 (accettazione e conferma) |
| Carrelli creati / `POST /v1/bookings` / itinerari prenotati | — / 85 / 85 | 136 / 78 / 78 |
| Itinerari con `POST /v1/bookings` ripetuta, orfani | 0, 0 | 0, 0 |
| In coda alla fine | 352 | 360, tutti con il prezzo già sentito |
| Età massima della coda (s) | 402 | 422 |
| Marco: prezzo sentito a / link a / confermato a (s) | — / — / 372 | 65 / 155 / **160** |
| Anna (arriva a 180 s): proposta (ms) / prezzo sentito a (s) / link | 10-12 / — / — | 15 / 185 / nessuno entro il giro |
| Pagamento → confermato, sentinelle (s) | 5 | 5 |
| Errori REST / p95 REST peggiore (ms) | 0 / 190 | 0 / 220 (`reject_proposal`) |
| p95 `create_intent` / `get_proposal` / `accept_proposal` / `get_order_status` (ms) | 29 / 140 / 130 / 70 | 47 / 140 / 150 / 79 |

**Criteri: tutti e quattro passano** (429 = 0; 106 ≤ 108; Marco confermato a 160 s; 78
booking = 78 itinerari prenotati, massimo una POST per itinerario).

Cosa cambia con la cache, una frase per differenza.

1. **Il prezzo arriva subito a quasi tutti.** 473 accettazioni su 487 (97%) sono hit: rispondono
   `awaiting_confirmation` senza job e senza chiamate. Solo 14 hanno fatto la coda per il prezzo,
   i leader delle poche chiavi dello scenario (quattro frasi, sempre due persone in una camera),
   con posizione 1-3 e attesa dichiarata 8-12 s. Il ritardo misurato (p50 45 s, p95 59 s) è il
   polling del viaggiatore finto, non Vela: Marco e Anna sentono il prezzo 5 s dopo aver
   accettato. Prima il prezzo effettivo arrivava con il carrello, cioè a 135 accettazioni su 487
   dentro il giro; ora a tutte e 487.
2. **Marco è confermato a 160 s invece di 372.** Sente il prezzo a 65 s e la sua conferma entra in
   coda quando davanti ha solo le conferme arrivate nei primi 30-60 s; prima il suo carrello per
   il prezzo aveva davanti quelli di tutti gli accettati prima di lui. È un anticipo, non un
   ritmo diverso (punto 3).
3. **Il ritmo non cambia, e non poteva: il limite resta la quota.** 99 chiamate e 17,8 link al
   minuto a regime, come dopo M18. 127 link contro 135 e 72 confermati contro 75 perché i
   carrelli partono dopo il sì, che nel viaggiatore finto arriva al primo polling (30-60 s): il
   minuto 1 fa 0 link (prima 12-14) e il giro di 8 minuti perde circa una finestra di polling.
   A regime è lo stesso flusso spostato di 30-60 s.
4. **Chiamate per ordine confermato invariate: 5 più il booking.** 136 carrelli per 127 link (9 in
   corso alla fine), 78 booking per 78 pagati. Nel funnel del banco chi accetta conferma sempre:
   il risparmio della cache (zero chiamate per chi rifiuta il prezzo, un solo carrello per il
   prezzo di N accettazioni identiche) non è esercitato. Un giro con una quota di rifiuti del
   prezzo lo misurerebbe; non fatto, per scelta.
5. **La coda alla fine è la stessa, ma aspetta il link e non il prezzo.** 360 in coda contro 352,
   età massima 422 s contro 402: sono gli stessi viaggiatori, che però hanno già sentito il
   prezzo. Per gli hit non esiste più un'attesa dichiarata (`position` e `wait_seconds` nulli
   nella risposta): lo scarto del report (152 s) confronta l'attesa dichiarata per il prezzo dei
   14 leader con il loro tempo al link e non è più una misura utile. **Aperto:** cosa dichiarare
   a un hit sul tempo al link (RF-48), e `report.py` da adeguare.
6. **La conversazione resta nello stesso ordine di grandezza.** p95 peggiore 220 ms contro 190,
   `create_intent` 47 contro 29 (il parser di M21 fa più lavoro), `accept_proposal` 150 contro
   130 con il doppio delle richieste; `get_proposal` invariata a 140. Nessun errore su 9.700
   richieste.

## Cosa dicevano i numeri prima di M18

1. **Il confine non reggeva [misurato].** In ogni giro con latenza standard Vela mandava a HofJ
   132-138 chiamate in un intervallo di 60 s, oltre il suo limite di 108 e oltre i 120 di HofJ;
   con gli altri usi della chiave si arrivava a 150. Con la finestra ancorata HofJ non risponde
   429 (0 in tutti i giri), perché dentro ogni *sua* finestra le chiamate restano sotto 120: le
   raffiche stavano a cavallo dei bordi. È la deriva prevista in §3.1 della seconda lettura, ma
   l'effetto è diverso da quello previsto: non "429 quasi a ogni finestra", bensì un superamento
   che la finestra ancorata non punisce. Con la finestra scorrevole (giro E) la prima raffica
   prendeva **3 429 al minuto 1**: il 429 azzera il budget (RF-38), Vela rilegge `/v1/quota` e il
   minuto 2 scendeva a 46 chiamate (metà del ritmo); poi Vela si riallineava alla finestra letta
   e non prendeva altri 429, ma restava a 111 chiamate in 60 s, sopra il suo 108.
2. **Il ritmo dipendeva dalla latenza [misurato, conferma parziale della §3.2].** Con latenza
   standard Vela faceva 16-18 acquisti al minuto, cioè il tetto di quota (17,4): con 4 worker la
   latenza non limitava. Con latenza `pessimistic` (2-6 s su tutte e 5 le chiamate) scendeva a
   ~10 al minuto e le chiamate a 58/min, metà del budget.
3. **La conversazione non degradava [misurato fino a 34 req/s].** p95 ≤ 30 ms su tutti i casi
   d'uso, 0 errori, anche con 360 persone in coda.
4. **Chi ha pagato veniva confermato subito [misurato].** Sentinelle: 5-10 s dal pagamento alla
   conferma, anche con la coda d'acquisto piena (riserva `booking`). Il p95 di tutti i paganti
   (~58 s) misura il polling del viaggiatore finto (30-60 s), non Vela.
5. **L'attesa dichiarata era ottimista [misurato].** Marco: dichiarati 280 s, reali 311 s (C);
   97 contro 165 s con latenza pessimistica (D), perché la stima usava il ritmo della quota
   (17,4/min) e non quello reale.
6. **Timeout come esito incerto [misurato, §3.3].** Con `hang_then_execute` sul booking Vela
   ripeteva la `POST` (2 itinerari prenotati due volte) e l'upsert teneva un solo booking; con lo
   stesso guasto su `POST /v1/itineraries` restava 1 itinerario orfano.

## Proiezione al twist: 10 minuti di arrivi [proiezione]

Modello a coda satura di `loadtest/projection.py`: accettazioni al minuto λ = 20% · N / 10; chi
accetta al minuto *t* aspetta (λ − ritmo) · *t* / ritmo; Marco accetta al minuto 1, Anna al 6.

**Dopo M18**, ritmo misurato **17,8 link/min** (media di B e C, latenza standard;
`python loadtest/projection.py --rate 17.8`):

| Viaggiatori in 10 min | Accettazioni/min | Coda a fine arrivi | Attesa di Marco (min) | Attesa di Anna (min) | Attesa dell'ultimo (min) | Smaltimento (h) | REST req/s a fine arrivi |
|---|---|---|---|---|---|---|---|
| 1.000 | 20 | 22 | 0,1 | 0,7 | 1,2 | 0,2 | 4,7 |
| 10.000 | 200 | 1.822 | 10,2 | 61,4 | 102,4 | 1,9 | 82,2 |
| 50.000 | 1.000 | 9.822 | 55,2 | 331,1 | 551,8 | 9,4 | 426,6 |

**Prima di M18**, ritmo misurato 16,5 link/min:

| Viaggiatori in 10 min | Accettazioni/min | Coda a fine arrivi | Attesa di Marco (min) | Attesa di Anna (min) | Attesa dell'ultimo (min) | Smaltimento (h) | REST req/s a fine arrivi |
|---|---|---|---|---|---|---|---|
| 1.000 | 20 | 35 | 0,2 | 1,3 | 2,1 | 0,2 | 4,9 |
| 10.000 | 200 | 1.835 | 11,1 | 66,7 | 111,2 | 2,0 | 82,4 |
| 50.000 | 1.000 | 9.835 | 59,6 | 357,6 | 596,1 | 10,1 | 426,9 |

Con latenza pessimistica il ritmo era ~10/min (a 50.000: Marco ~99 minuti, Anna ~10 ore,
smaltimento ~17 ore); dopo M18 è 16,0/min (a 50.000: Marco ~62 minuti, Anna ~6 ore, smaltimento
~10 ore).

- **Chiamate a HofJ al minuto**: le stesse dei giri misurati a qualunque N oltre la saturazione.
  Prima 84-92/min con picchi di 132-138 in 60 s; dopo 99/min con un massimo di 105-108 in 60 s:
  il confine si decide nel limitatore, non nel carico, e ora sta sotto 108.
- **Marco non è confermato entro il minuto 7** a 10.000 e 50.000, né prima né dopo M18: con
  ~1.000 accettazioni al minuto ha ~980 persone davanti. M18 alza il ritmo di poco (da 16,5 a
  17,8 link/min, il tetto della quota); la previsione della §6 ("verso il minuto 3 riceve il
  link") resta **smentita**. M19 la migliora (~43 link/min, stima).
- **Il carico REST a 50.000 è una proiezione, non una misura**: ~430 req/s a fine arrivi, 12
  volte il picco misurato (34 req/s) su un solo processo uvicorn, dove dopo M18 il p95 è già
  200 ms. La proiezione dice solo che serve; non dice che regge.

## Previsioni della seconda lettura

| Previsione | Esito prima di M18 | Esito dopo M18 |
|---|---|---|
| §3.1: il contatore a griglia deriva e sotto carico prende 429 quasi a ogni finestra | **In parte confermata.** Deriva misurata: 132-138 chiamate in 60 s con la finestra ancorata, 111 con quella scorrevole. I 429 però non arrivano "quasi a ogni finestra": 0 con l'ancorata, 3 solo alla prima raffica con la scorrevole | **Corretta**: 105-108 in 60 s con entrambe le finestre, 0 429 |
| §3.2: ~12 acquisti/min con 4 worker invece di 17,4 | **Dipende dalla latenza.** 16-18/min con latenza standard (limita la quota), ~10/min con latenza pessimistica (limita la latenza) | **Corretta**: con 10 worker 17,8/min con latenza standard e 16,0/min con latenza pessimistica: limita la quota |
| §3.3: il retry del booking è sicuro, quello dell'itinerario lascia orfani | **Confermata**: 2 booking ripetuti → 1 booking; 1 itinerario orfano | **Confermata**, orfani ora contati (3 in D). Nuovo: POST di booking doppie senza guasti, per job doppi (punto 6) |
| §6: Marco ha il codice entro circa un minuto dal pagamento | **Confermata**: 5-10 s | **Confermata**: 5 s, 30 s con un guasto sul suo booking |
| §6: Marco riceve il link verso il minuto 3 | **Smentita a 10k e 50k** (proiezione: 11 e 60 minuti di attesa) | **Smentita a 10k e 50k** (proiezione: 10 e 55 minuti) |
| §6: Anna riceve subito una proposta e un'attesa dichiarata | **Confermata**: proposta in 10-15 ms, attesa dichiarata ottimista | **Confermata**: proposta in 10-12 ms, attesa dichiarata non più ottimista |
