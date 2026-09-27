# Risultati del load test

Un giro da **10.000 viaggiatori** in 5 minuti di arrivi + 3 di coda, divisi in quattro gruppi, e
la **proiezione a 50.000** con gli stessi gruppi. Misurato il 2026-09-27 sul commit `c41a840`
(codice di Vela uguale a `5ec87aa`, `master` con M19 e M21). Come si lancia: `loadtest/README.md`.
Decisioni: `docs/decisions.md` ("Load test a quattro gruppi e RESULTS.md riscritto"). Report
completo in `loadtest/out/10k/report.md` (non versionato; si rigenera con `loadtest/report.py`).
I giri precedenti (M13a, M13b, RF-84, M19) sono nella storia git di questo file.

Etichette: **[misurato]** = dal registro del finto HofJ, da Locust o dalle righe dei viaggiatori;
**[proiezione]** = calcolato da `loadtest/projection.py` a partire dal ritmo misurato.

## Il giro

```sh
docker compose up -d --build
docker compose run --rm locust --travelers 10000 --browse 50 --proposal 30 --link 18 \
    --duration 8 --arrival-minutes 5 --tail-minutes 3 --label 10k
docker compose down -v
python loadtest/projection.py --rate 44.4 --sizes 10000,50000
```


| Gruppo                   | Quota         | Viaggiatori | Cosa fa                                                                             |
| ------------------------ | ------------- | ----------- | ----------------------------------------------------------------------------------- |
| Naviga solo il sito      | 50%           | 5.000       | Contato, nessuna richiesta: la landing è un sito statico separato e non chiama Vela |
| Chiede la proposta       | 30%           | 3.000       | `create_intent`, `get_proposal`, si ferma                                           |
| Arriva al link, non paga | 18%           | 1.800       | Accetta, conferma il prezzo, aspetta il link e se ne va                             |
| Paga                     | 2% (il resto) | 200         | Come sopra, poi paga e aspetta la conferma                                          |


Più due sentinelle fuori dai gruppi: **Marco** accetta a 60 s e paga appena ha il link; **Anna**
arriva a 180 s, rifiuta una volta e accetta. Nessun viaggiatore dei gruppi rifiuta. Chi ha
accettato chiede lo stato ogni 30-60 s, le sentinelle ogni 5 s.

## Banco

- Tutto in locale con `docker compose`: Vela (`VELA_UPSTREAM_MODE=loadtest`, un processo
uvicorn, `worker_concurrency = 10`, cache del prezzo a 900 s), Postgres 16, finto HofJ, Locust.
**Nessuna chiamata a HofJ né a Stripe.** MacBook Pro M4 Pro, Docker Desktop con 12 CPU e 17,5 GB.
- Finto HofJ con le regole di HofJ: 120 chiamate/min per chiave, finestra ancorata, 12/min di
altri usi della stessa chiave, latenza standard (2-6 s su `POST /v1/itineraries`, 0,3-1,5 s
sugli altri). Catalogo dalle fixture dei brand: 190 prodotti.
- Stack lanciato con `docker compose -p lastload` e un override senza porte host. Durante il giro
era acceso, fermo, un altro stack del banco (`master-*`): non tocca la quota, può pesare sui p95.

## Criteri [misurato]


| Criterio                                     | Esito                                                     |
| -------------------------------------------- | --------------------------------------------------------- |
| 429 ricevuti da Vela = 0                     | ✅ 0                                                       |
| Chiamate Vela → HofJ in qualsiasi 60 s ≤ 108 | ✅ 107 (119 con gli altri usi, sotto i 120 di HofJ)        |
| Marco confermato entro il minuto 7 (420 s)   | ✅ 247 s (link a 241 s)                                    |
| Nessun itinerario prenotato due volte        | ✅ 31 booking su 31 itinerari, una POST ciascuno, 0 orfani |


## Dopo quanto tempo si riesce a pagare [misurato]

Tempi dall'arrivo del viaggiatore. Le mediane valgono solo per chi ha avuto il link **entro gli 8
minuti del giro**: chi era ancora in coda alla fine non entra nel calcolo, quindi i tempi veri del
gruppo sono più lunghi (vedi la proiezione).


| Gruppo                   | Viaggiatori | Proposta | Accettazioni | Link | Pagati | Confermati | Esito del gruppo raggiunto | Ancora in coda alla fine | Dall'arrivo al link, mediana / p95 / max (min) | Dall'arrivo al pagamento, mediana / p95 / max (min) |
| ------------------------ | ----------- | -------- | ------------ | ---- | ------ | ---------- | -------------------------- | ------------------------ | ---------------------------------------------- | --------------------------------------------------- |
| Naviga solo il sito      | 5.000       | —        | —            | —    | —      | —          | 5.000                      | 0                        | —                                              | —                                                   |
| Chiede la proposta       | 3.000       | 2.998    | —            | —    | —      | —          | 2.998                      | 0                        | —                                              | —                                                   |
| Arriva al link, non paga | 1.800       | 1.800    | 1.799        | 280  | —      | —          | 280 (16%)                  | 1.519                    | 4,2 / 7,0 / 7,5                                | —                                                   |
| Paga                     | 200         | 200      | 200          | 30   | 30     | 28         | 28 (14%)                   | 172                      | 3,9 / 6,9 / 7,1                                | 3,9 / 6,9 / 7,1                                     |


Dei 200 paganti, quanti hanno pagato entro X minuti dal loro arrivo:


| Entro        | 2 min    | 3 min   | 4 min     | 5 min     | 6 min    | 7 min      | 8 min (fine giro) |
| ------------ | -------- | ------- | --------- | --------- | -------- | ---------- | ----------------- |
| Hanno pagato | 7 (3,5%) | 12 (6%) | 15 (7,5%) | 17 (8,5%) | 24 (12%) | 29 (14,5%) | 30 (15%)          |


1. **Chi paga lo fa appena vede il link**: arrivo → link e arrivo → pagamento coincidono. Il
 limite non è il pagamento ma la coda del link: 2.000 persone accettano in 5 minuti (400 al
 minuto) e Vela produce 44 link al minuto.
2. **Pagamento → confermato**: 5 s per Marco, fino a 58 s per gli altri (p95 58,4 s), perché il
 viaggiatore finto chiede lo stato ogni 30-60 s. I 2 paganti non confermati hanno pagato
 nell'ultimo minuto.
3. **Chi arriva prima passa prima**: Marco (accetta a 60 s) ha il link a 241 s, 3 minuti di coda;
 Anna (accetta a 180 s, posizione 793) non ha il link entro il giro.

## Entro quanto tempo arriva il link [misurato]

Tutti quelli che accettano, gruppi "link" e "paga" insieme: 1.999 accettazioni (1 `accept_proposal`
finito in 500), 310 link entro il giro.

| Entro, dall'arrivo | 1 min | 2 min | 3 min | 4 min | 5 min | 6 min | 7 min | 8 min (fine giro) |
|---|---|---|---|---|---|---|---|---|
| Hanno il link | 0 | 57 (2,9%) | 103 (5,2%) | 147 (7,4%) | 192 (9,6%) | 253 (12,7%) | 296 (14,8%) | 310 (15,5%) |

Chi ha ricevuto il link l'ha avuto tra 65 s e 7,5 minuti dall'arrivo, in mediana 4,2 minuti. La
coda serve chi arriva prima, e dopo il primo minuto quasi nessuno arriva al link entro il giro:

| Arrivati nel minuto | Hanno accettato | Link entro il giro | Dall'arrivo al link, mediana (min) |
|---|---|---|---|
| 1 | 398 | 309 | 4,2 |
| 2 | 411 | 1 | 6,9 |
| 3, 4, 5 | 1.190 | 0 | — |

Chi non ha il link a fine giro resta in coda: per quanto, lo dice la proiezione (sotto): a
10.000 fino a 40 minuti dall'accettazione, a 50.000 fino a 3 ore e 40 minuti.

## Perché si aspetta più del giro precedente [misurato]

Vela non è più lenta: il ritmo dei link è quasi lo stesso del giro precedente, ma arrivano 4 volte
più accettazioni al minuto. Confronto con l'ultimo giro misurato prima di questo (C-2500 dopo
M19, 2026-09-27, stessa finestra di 5 + 3 minuti; `git show 5ec87aa:loadtest/RESULTS.md`):

| | C-2500 dopo M19 | 10k a quattro gruppi |
|---|---|---|
| Viaggiatori in 5 min | 2.500 | 10.000 |
| Accettano | 487 (20%) | 2.001 (20%: 18% link + 2% paga) |
| Accettazioni al minuto | ~97 | ~400 |
| **Link al minuto (ritmo di Vela)** | **47,4** | **44,4** |
| Chiamate Vela → HofJ al minuto | ~100 | ~100 |
| Chiamate per link | 2,11 | 2,11 |
| Pagamenti (3 chiamate ciascuno) | 14 | 31 |
| In coda alla fine | 159 | 1.690 |
| Il più vecchio in coda (s) | 287 | 445 |
| Marco: link a | 90 s | 241 s |

1. **Il limite è lo stesso**: la quota di HofJ, ~100 chiamate al minuto, 2 per link, quindi ~45
   link al minuto. Oltre la saturazione Vela non ne produce di più, qualunque sia il numero di
   viaggiatori.
2. **La domanda è 4 volte più grande.** Prima arrivavano ~97 accettazioni al minuto contro 47
   link: la coda cresceva di ~50 persone al minuto. Ora ne arrivano 400: cresce di ~355 al
   minuto, 7 volte più in fretta. Marco accetta al minuto 1 con ~400 persone davanti invece di
   ~100, e il link gli arriva a 241 s invece che a 90.
3. **Il ritmo scende di poco, da 47,4 a 44,4, per i pagamenti.** Prima pagava il 2% di chi
   riceveva il link (14), ora il 2% di tutti, cioè il 10% di chi accetta (31). Ogni pagamento
   costa 3 chiamate a HofJ: 93 invece di 42 in 8 minuti, ~6 al minuto in più, ~3 link al minuto
   in meno.
4. **Anche prima il link arrivava solo a chi arrivava presto** (159 persone in coda alla fine):
   con 2.500 viaggiatori la coda durava qualche minuto, con 10.000 decine di minuti, a 50.000 ore.
   Per accorciarla servono più link al minuto: più quota su HofJ o meno chiamate per link, non
   un Vela più veloce.

## Il giro minuto per minuto [misurato]


| Minuto | Chiamate Vela → HofJ | 429 | Carrelli creati | Link | In coda | Più vecchio in coda (s) |
| ------ | -------------------- | --- | --------------- | ---- | ------- | ----------------------- |
| 1      | 52                   | 0   | 27              | 0    | 397     | 60                      |
| 2      | 99                   | 0   | 40              | 54   | 756     | 119                     |
| 3      | 99                   | 0   | 44              | 34   | 1.119   | 179                     |
| 4      | 99                   | 0   | 45              | 43   | 1.451   | 239                     |
| 5      | 100                  | 0   | 44              | 45   | 1.809   | 291                     |
| 6      | 102                  | 0   | 47              | 51   | 1.774   | 339                     |
| 7      | 101                  | 0   | 39              | 45   | 1.729   | 392                     |
| 8      | 97                   | 0   | 42              | 39   | 1.690   | 445                     |


- **Ritmo: 44,4 link al minuto** a coda satura (311 link nei minuti 2-8), con ~100 chiamate a HofJ
al minuto. Ogni link costa 2,11 chiamate (328 carrelli per 311 link: alcuni in volo alla fine),
ogni pagamento 3 (cliente, passeggeri, booking). Il limite è la quota di HofJ, non Vela.
- **Cache del prezzo**: 1.991 accettazioni su 2.001 hanno avuto il prezzo subito (4 frasi, pochi
viaggi diversi); la coda è quella del link dopo la conferma. Per questo l'attesa dichiarata
all'accettazione esiste solo per 10 persone e lo scarto con l'attesa reale non è una misura utile.

## Conversazione e REST [misurato]


| Caso d'uso         | Richieste | Errori | p50 ms | p95 ms | p99 ms |
| ------------------ | --------- | ------ | ------ | ------ | ------ |
| `create_intent`    | 5.002     | 0      | 47     | 830    | 1.500  |
| `get_proposal`     | 5.002     | **2**  | 110    | 950    | 1.700  |
| `accept_proposal`  | 4.002     | **1**  | 210    | 1.100  | 1.900  |
| `get_order_status` | 12.370    | 0      | 93     | 800    | 1.600  |
| `replay_checkout`  | 31        | 0      | 100    | 860    | 900    |


- **Picco: 86,8 richieste al secondo** su un solo processo uvicorn. Il p95 sale a 0,8-1,1 s
(contro 0,05-0,2 s a 34 req/s nei giri precedenti): la conversazione rallenta, non si ferma.
- **I 3 errori sono 500 per il pool di connessioni esaurito**
(`QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 3.00`), tutti tra
il minuto 4 e il minuto 5, al picco. Il pool è quello di default di SQLAlchemy
(`vela/adapters/db.py`): 15 connessioni per i 10 worker e le richieste REST insieme. È il primo
limite che Vela incontra prima della quota; non è stato cambiato in questa task.

## Proiezione a 50.000 [proiezione]

Modello a coda satura di `loadtest/projection.py` con il ritmo misurato (44,4 link/min), stessi
gruppi e stessa finestra (5 minuti di arrivi + 3 di coda): chi accetta al minuto *t* aspetta il
link (λ − ritmo) · *t* / ritmo minuti, con λ = accettazioni al minuto.


| Viaggiatori in 5 min | Solo sito / proposta / link / paga | Accettazioni/min | Coda a fine arrivi | Dall'accettazione al link, cioè a poter pagare: Marco (minuto 1) / mediana / ultimo (min) | Smaltimento della coda (min) | Link / pagati entro 8 min | REST req/s a fine arrivi |
| -------------------- | ---------------------------------- | ---------------- | ------------------ | ----------------------------------------------------------------------------------------- | ---------------------------- | ------------------------- | ------------------------ |
| 10.000               | 5.000 / 3.000 / 1.800 / 200        | 400              | 1.778              | 8 / 20 / 40                                                                               | 45                           | 355 / 36                  | 86,8                     |
| 50.000               | 25.000 / 15.000 / 9.000 / 1.000    | 2.000            | 9.778              | 44 / 110 / 220                                                                            | 225                          | 355 / 36                  | 454                      |


Quota di chi accetta che ha il link, cioè può pagare, entro X minuti dal suo arrivo (la stessa
per i gruppi "link" e "paga", mescolati nella coda):


| Viaggiatori in 5 min | Paganti | Entro 5 min | Entro 15 min | Entro 30 min | Entro 1 ora | Entro 2 ore | Entro 4 ore  |
| -------------------- | ------- | ----------- | ------------ | ------------ | ----------- | ----------- | ------------ |
| 10.000               | 200     | 12% (25)    | 37% (75)     | 75% (150)    | 100% (200)  | 100%        | 100%         |
| 50.000               | 1.000   | 2% (23)     | 7% (68)      | 14% (136)    | 27% (272)   | 54% (545)   | 100% (1.000) |


**Il modello contro il giro a 10.000**:


|                                                      | Modello   | Misurato      |
| ---------------------------------------------------- | --------- | ------------- |
| Coda a fine arrivi                                   | 1.778     | 1.809         |
| REST req/s                                           | 86,8      | 86,8 al picco |
| Link entro 8 minuti                                  | 355       | 311           |
| Paganti che hanno pagato entro 5 / 8 min dall'arrivo | 12% / 20% | 8,5% / 15%    |
| Marco, accettazione → link                           | 8 min     | 3 min         |


Il modello è un po' ottimista sul totale, perché nel primo minuto il giro non produce link
(i carrelli partono ma i link arrivano dal minuto 2). È invece pessimista per chi arriva per
primo (Marco: 3 minuti invece di 8); probabilmente perché nella coda del minuto 1 ci sono persone
che non hanno ancora confermato il prezzo (conferma al primo stato, dopo 30-60 s), ma non l'ho
verificato.

Cosa dice la proiezione a 50.000:

1. **Le chiamate a HofJ restano quelle del giro**: ~100 al minuto, ≤ 108 in 60 s. Il confine si
 decide nel limitatore, non nel numero di viaggiatori.
2. **Pagare diventa una questione di ore**: con 10.000 accettazioni in 5 minuti e 44 link al
 minuto, metà dei paganti può pagare solo dopo ~2 ore e l'ultimo dopo ~3 ore e 40 minuti. In 8
 minuti riceve il link lo stesso numero di persone che a 10.000 (~355), perché il ritmo è quello.
3. **Il carico REST è una proiezione, non una misura**: ~454 req/s a fine arrivi, 5 volte il
 picco misurato. A 87 req/s un solo processo ha già un p95 di 1 s e 3 errori per il pool del
 database: a 50.000 servono più processi e un pool più grande, e questo giro non dice se basterebbero.
4. **Gli ordini silenziosi (M19) non sono nel modello**: chi smette di chiedere lo stato per 15
 minuti esce dalla coda, e in una coda di ore lo smaltimento reale sarebbe più corto.

