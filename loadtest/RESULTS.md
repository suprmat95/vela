# Risultati del load test del twist

Colonna **"prima"**: il codice di oggi (dopo M5, M10, M17), misurato il 2026-09-26 con il banco di
M13a. M18 corregge, M13b rilancia gli stessi giri per la colonna "dopo". Come si lanciano:
`loadtest/README.md`. Decisioni: `docs/decisions.md` ("Twist, seconda lettura", "M13a: banco di
prova"). Report completi dei giri in `loadtest/out/<giro>/report.md` (non versionati; si
rigenerano con `run.py`).

Etichette: **[misurato]** = dal registro del finto HofJ o da Locust; **[proiezione]** = calcolato
da `loadtest/projection.py` a partire dai ritmi misurati.

## Banco

- Tutto in locale con `docker compose`: Vela (`VELA_UPSTREAM_MODE=loadtest`, un processo
  uvicorn, `worker_concurrency = 4`), Postgres 16, finto HofJ, Locust. **Nessuna chiamata a HofJ
  né a Stripe.** MacBook Pro M4 Pro, Docker Desktop (12 CPU, 17,5 GB).
- Finto HofJ con le regole di HofJ: 120 chiamate/min per chiave, finestra **ancorata** (come
  misurato dalla sonda) salvo il giro E; 12/min di altri usi della stessa chiave; latenza
  `standard` = 2-6 s su `POST /v1/itineraries`, 0,3-1,5 s sugli altri endpoint **[previsto]**.
  Una chiamata respinta con 429 conta nella finestra.
- Scenario a modello aperto, seme 13: 100% proposta, 30% "troppo caro", 20% accetta, stato ogni
  30-60 s, 60% di chi riceve il link paga. Sentinelle: Marco accetta a 60 s, Anna arriva al 60%
  della finestra degli arrivi. Catalogo caricato al boot dalle fixture (126 prodotti attivi).
- Giri ridotti (decisione dell'utente): 5 minuti di arrivi + 3 di coda. Con il 20% che accetta la
  coda satura già a 500 viaggiatori in 5 minuti: da lì in poi chiamate HofJ al minuto e ritmo
  degli acquisti non dipendono dal numero di viaggiatori, e i numeri del twist si proiettano.

## Giri misurati

| | A-500 | B-1000 | C-2500 | D-1000-guasti | E-1000-rolling |
|---|---|---|---|---|---|
| Finto HofJ | ancorata, standard | ancorata, standard | ancorata, standard | ancorata, **pessimistic**, guasti | **scorrevole**, standard |
| Viaggiatori in 5 min | 500 | 1.000 | 2.500 | 1.000 | 1.000 |
| **Massimo chiamate Vela → HofJ in 60 s** | **132** | **132** | **138** | 66 | 111 |
| Massimo in 60 s con gli altri usi | 144 | 144 | 150 | 78 | 123 |
| **429 ricevuti** | **0** | **0** | **0** | **0** | **3 (tutti al minuto 1)** |
| Chiamate Vela al minuto, a regime | 84 | 92 | 92 | 58 | 81 |
| Link (acquisti) al minuto, a regime | 14,4 | 17,6 | 16,3 | 9,9 | 15,4 |
| Accettazioni / link / confermati | 110 / 110 / 67 | 216 / 133 / 70 | 487 / 127 / 73 | 216 / 76 / 44 | 216 / 118 / 62 |
| In coda alla fine | 0 | 83 | 360 | 140 | 98 |
| Età massima della coda (s) | 108 | 300 | 414 | 377 | 314 |
| Pagamento → confermato, sentinelle (s) | 5 | 5 | 5 | 10 | 5 |
| POST di booking doppie (stesso itinerario) | 0 | 0 | 0 | 2, **un solo booking** ciascuno | 0 |
| Itinerari orfani | 0 | 0 | 0 | 1 | 0 |
| Marco: attesa dichiarata / reale (s) | 7 / 10 | 49 / 65 | 280 / 311 | 97 / 165 | 69 / 120 |
| Errori REST | 0 | 0 | 0 | 0 | 0 |
| p95 REST peggiore (ms) | 18 | 24 | 30 | 24 | 21 |
| Richieste REST/s, picco | — | 16 | 34 | — | — |

p50/p95/p99 dei casi d'uso, giro C-2500 (il più carico) **[misurato]**:

| Caso d'uso | Richieste | Errori | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|---|
| `create_intent` | 2.502 | 0 | 3 | 10 | 13 |
| `get_proposal` | 2.502 | 0 | 12 | 22 | 39 |
| `reject_proposal` | 720 | 0 | 13 | 30 | 47 |
| `accept_proposal` | 487 | 0 | 7 | 16 | 25 |
| `get_order_status` | 2.902 | 0 | 8 | 15 | 21 |

## Cosa dicono i numeri

1. **Il confine non regge [misurato].** In ogni giro con latenza standard Vela manda a HofJ
   132-138 chiamate in un intervallo di 60 s, oltre il suo limite di 108 e oltre i 120 di HofJ;
   con gli altri usi della chiave si arriva a 150. Con la finestra ancorata HofJ non risponde 429
   (0 in tutti i giri), perché dentro ogni *sua* finestra le chiamate restano sotto 120: le
   raffiche stanno a cavallo dei bordi. È la deriva prevista in §3.1 della seconda lettura, ma
   l'effetto è diverso da quello previsto: non "429 quasi a ogni finestra", bensì un superamento
   che la finestra ancorata non punisce. Con la finestra scorrevole (giro E) la prima raffica prende
   **3 429 al minuto 1**: il 429 azzera il budget (RF-38), Vela rilegge `/v1/quota` e il minuto 2
   scende a 46 chiamate (metà del ritmo); poi Vela si riallinea alla finestra letta e non prende
   altri 429, ma resta a 111 chiamate in 60 s, sopra il suo 108. In entrambi i casi il limite
   dichiarato non è rispettato: la correzione è il token bucket di M18.
2. **Il ritmo dipende dalla latenza [misurato, conferma parziale della §3.2].** Con latenza
   standard Vela fa 16-18 acquisti al minuto, cioè il tetto di quota (17,4): con 4 worker la
   latenza non limita. Con latenza `pessimistic` (2-6 s su tutte e 5 le chiamate) scende a ~10
   al minuto e le chiamate a 58/min, metà del budget: il limite diventa la latenza, come previsto
   (~12/min, misurati ~10 anche per i guasti).
3. **La conversazione non degrada [misurato fino a 34 req/s].** p95 ≤ 30 ms su tutti i casi
   d'uso, 0 errori, anche con 360 persone in coda: la conversazione non chiama HofJ.
4. **Chi ha pagato viene confermato subito [misurato].** Sentinelle: 5-10 s dal pagamento alla
   conferma, anche con la coda d'acquisto piena (riserva `booking`). Il p95 di tutti i paganti
   (~58 s) misura il polling del viaggiatore finto (30-60 s), non Vela.
5. **L'attesa dichiarata è ottimista [misurato].** Marco: dichiarati 280 s, reali 311 s (C);
   97 contro 165 s con latenza pessimistica (D), perché la stima usa il ritmo della quota
   (17,4/min) e non quello reale.
6. **Timeout come esito incerto [misurato, §3.3].** Con `hang_then_execute` sul booking Vela
   ripete la `POST` (2 itinerari prenotati due volte) e l'upsert tiene un solo booking; con lo
   stesso guasto su `POST /v1/itineraries` resta 1 itinerario orfano.

## Proiezione al twist: 10 minuti di arrivi [proiezione]

Modello a coda satura di `loadtest/projection.py`: accettazioni al minuto λ = 20% · N / 10; chi
accetta al minuto *t* aspetta (λ − ritmo) · *t* / ritmo; Marco accetta al minuto 1, Anna al 6.
Ritmo misurato: **16,5 link/min** (media di B e C, latenza standard).

| Viaggiatori in 10 min | Accettazioni/min | Coda a fine arrivi | Attesa di Marco (min) | Attesa di Anna (min) | Attesa dell'ultimo (min) | Smaltimento (h) | REST req/s a fine arrivi |
|---|---|---|---|---|---|---|---|
| 1.000 | 20 | 35 | 0,2 | 1,3 | 2,1 | 0,2 | 4,9 |
| 10.000 | 200 | 1.835 | 11,1 | 66,7 | 111,2 | 2,0 | 82,4 |
| 50.000 | 1.000 | 9.835 | 59,6 | 357,6 | 596,1 | 10,1 | 426,9 |

Con latenza pessimistica (ritmo ~10/min): a 50.000 Marco aspetta ~99 minuti, Anna ~10 ore,
smaltimento ~17 ore.

- **Chiamate a HofJ al minuto**: le stesse dei giri misurati a qualunque N oltre la saturazione
  (84-92/min, picchi di 132-138 in 60 s): il confine si decide nel limitatore, non nel carico.
- **Marco non è confermato entro il minuto 7** a 10.000 e 50.000: con ~1.000 accettazioni al
  minuto ha ~985 persone davanti. La previsione della §6 ("verso il minuto 3 riceve il link") è
  **smentita**; M18 non la cambia (il tetto resta 17,4/min), M19 la migliora (~43 link/min).
- **Il carico REST a 50.000 è una proiezione, non una misura**: ~430 req/s a fine arrivi, 12 volte
  il picco misurato (34 req/s) su un solo processo uvicorn. La proiezione dice solo che serve;
  non dice che regge.

## Previsioni della seconda lettura

| Previsione | Esito |
|---|---|
| §3.1: il contatore a griglia deriva e sotto carico prende 429 quasi a ogni finestra | **In parte confermata.** Deriva misurata: 132-138 chiamate in 60 s con la finestra ancorata, 111 con quella scorrevole. I 429 però non arrivano "quasi a ogni finestra": 0 con l'ancorata, 3 solo alla prima raffica con la scorrevole (un minuto a metà ritmo, poi Vela si riallinea) |
| §3.2: ~12 acquisti/min con 4 worker invece di 17,4 | **Dipende dalla latenza.** 16-18/min con latenza standard (limita la quota), ~10/min con latenza pessimistica (limita la latenza) |
| §3.3: il retry del booking è sicuro, quello dell'itinerario lascia orfani | **Confermata**: 2 booking ripetuti → 1 booking; 1 itinerario orfano |
| §6: Marco ha il codice entro circa un minuto dal pagamento | **Confermata**: 5-10 s |
| §6: Marco riceve il link verso il minuto 3 | **Smentita a 10k e 50k** (proiezione: 11 e 60 minuti di attesa) |
| §6: Anna riceve subito una proposta e un'attesa dichiarata | **Confermata**: proposta in 10-15 ms, attesa dichiarata (ottimista, punto 5) |
