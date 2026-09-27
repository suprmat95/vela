# Superficie REST

La superficie REST (RF-40) espone i cinque casi d'uso di RF-39 sotto `/v1`. Ogni endpoint richiede
`Authorization: Bearer <VELA_API_TOKEN>` (RF-43); senza la variabile impostata sul server ogni
`/v1/*` risponde 503. Codice: `vela/surfaces/rest.py`, errori in `vela/surfaces/problems.py`.
`GET /health`, `/docs` e `/openapi.json` sono pubblici.

## Endpoint

| Endpoint | Body | Esiti |
|---|---|---|
| `POST /v1/intents` | `{"text": str, "profile"?: Profile, ...Fields}` | 201 `intent_created`, 200 `question` |
| `GET /v1/intents/{intent_id}/proposal` | — | 200 `proposal`, 200 `no_match` |
| `POST /v1/proposals/{proposal_id}/reject` | opzionale `{"reason"?: str, ...Fields, "direction"?: str}` | 200 `proposal`, 200 `no_match` (con `rejected_proposal_id`) |
| `POST /v1/proposals/{proposal_id}/accept` | opzionale `{"traveler"?: Profile, "rooms"?: int}` | 200 `order_status` (`awaiting_confirmation` alla prima chiamata, `awaiting_payment` alla conferma), 202 `order_queued` (con `Location`) se l'attesa scade, 200 `missing_traveler_data`, 200 `question` (M21-D: `rooms` sotto il minimo del prodotto, nessun ordine) |
| `GET /v1/orders/{order_id}` | — | 200 `order_status` |

`Profile` = `{"first_name"?, "last_name"?, "email"?, "phone"?, "pax"? (≥ 1), "participants"?: [{"first_name"?, "last_name"?}]}`.
`text` è ripulito dagli spazi e va da 1 a 1000 caratteri. I campi extra sono ignorati.

### Campi strutturati (M17, RF-52..55)

`Fields` = `{"sport"?, "area"?, "period_start"?, "period_end"?, "pax"?, "budget"?,
"duration_min_nights"?, "duration_max_nights"?, "budget_scope"?, "rooms"?}` (la durata da M21-A, la
lettura del budget da M21-E, le camere da M21-D), gli stessi
nomi e valori degli argomenti dei tool MCP `create_intent` e `reject_proposal`. Sono i criteri
già capiti dall'agente; `text` e `reason` restano e si passano sempre con le parole del
viaggiatore. Un client che manda solo testo funziona come prima.

| Campo | Valori | Scartato se |
|---|---|---|
| `sport` | `padel`, `tennis`, `any` (indifferente: nessun filtro sport) | fuori dai tre valori |
| `area` | nome di un luogo (paese, regione, città) | sconosciuto a `geo` |
| `period_start`, `period_end` | date `YYYY-MM-DD`, servono entrambe | una sola, non ISO, inizio dopo la fine, fine passata |
| `pax` | intero | fuori da 1..20 |
| `budget` | numero, budget massimo in euro: la cifra così come l'ha detta il viaggiatore, mai moltiplicata o divisa per il numero di persone | non positivo |
| `budget_scope` | `per_person` (il viaggiatore ha detto "a testa", "each"), `total` ("in tutto", "in total"). Solo se il viaggiatore l'ha detto in modo esplicito | altro valore |
| `duration_min_nights`, `duration_max_nights` | interi, notti del viaggio (M21-A, RF-58): weekend 1..3, ponte o weekend lungo 2..4, una settimana 6..8, N giorni = N−1 notti. Basta uno dei due; uno solo sostituisce tutta la durata letta nel testo | fuori da 1..30, minimo maggiore del massimo, non interi |
| `rooms` | intero, camere dell'hotel (M21-D, RF-65): da 1 al numero di persone. Su `accept` è una correzione dell'ultimo momento | fuori da 1..pax (le persone dopo la precedenza campo > testo > profilo), non intero |
| `direction` (solo rifiuto) | `north` ("più fresco"), `south` ("più caldo") | altro valore, o `geo.move` non sa spostare l'area |

- **Precedenza** (RF-53): campo valido > parser del testo > fallback Haiku (solo sulla
  creazione). Se testo e campo non coincidono vince il campo e il conflitto va nei log (logger
  `vela.domain.usecases`, mai il testo). Nel rifiuto `area` vince su `direction`. Su
  `/v1/intents` `pax` al primo livello vince su `profile.pax`, che resta il default.
- **Campo invalido**: scartato senza bloccare la richiesta e dichiarato all'inizio del `say`
  (nessun 422). Un tipo JSON sbagliato (es. `"pax": "tre"`) resta un 422.
- **Durata** (RF-58, RF-59): criterio morbido, non esclude mai. Ordina subito dopo il budget;
  se il viaggio proposto non la rispetta, motivazione e `say` lo dicono con la durata vera
  ("Non ho weekend compatibili: questo dura 5 notti, dal 9 al 14 ottobre."). Nel rifiuto
  "troppo lungo"/"too long" chiede al massimo una notte in meno della proposta, "troppo
  corto"/"too short" almeno una in più. "Un weekend" è solo durata; "questo/prossimo weekend"
  è anche un periodo.
- **Budget a testa o totale** (RF-69, RF-70, M21-E): la lettura segue quest'ordine: campo
  `budget_scope`; nel testo "a testa", "a persona", "each", "per person" → a persona; "in
  tutto", "totale", "in total", "altogether" → totale; con più persone e nessuna lettura detta,
  a persona se la cifra come totale non copre il viaggio compatibile più economico (filtri duri,
  senza budget) e a persona sì, altrimenti totale; con una persona totale. Nei criteri `budget` è
  il tetto sul totale (600 a testa in 3 → `"1800.00"`) e `budget_scope` la lettura; il `say` la
  dichiara sempre ("con un budget di 600 euro a persona, 1800 in tutto"). Nel rifiuto una cifra
  nuova segue le stesse regole; `budget_scope` da solo, o un numero di persone cambiato con la
  lettura a persona, rilegge la cifra già detta; "troppo caro" abbassa il tetto e lo legge in
  totale. `budget_scope` senza nessun budget non ha effetto.
- **Ordinamento** (RF-60, RF-61, M21-B): dopo i filtri duri la proposta è il primo prodotto per
  area, totale entro budget, durata compatibile, partenza più vicina all'inizio del periodo (o a
  oggi senza periodo), `featured` o offerta speciale di HofJ, prezzo crescente, id numerico
  (livello e lezioni da M21-C). Senza budget il prezzo non decide prima della partenza: un viaggio
  che parte il 2 novembre batte uno che parte il 25 anche se costa di più. Prodotti equivalenti
  (stesso hotel, stesso titolo, stessa destinazione, prezzo entro il 5%) contano come uno: resta
  quello con l'id più basso. La `reason` della `proposal` dice il livello che ha deciso ("la
  prima partenza nel periodo che hai chiesto", "è tra i viaggi in evidenza del catalogo") e "la
  più economica" solo quando è vero. Nessun campo nuovo.
- **Sport** (RF-04): sempre indispensabile. Senza sport da campo, testo o fallback la risposta
  è `question` "Padel o tennis?" e nessun intento viene salvato. Le domande, una alla volta, in
  quest'ordine: sport, persone, camere.
- **Persone e camere** (RF-65..68, M21-D): con più di 2 persone e nessuna camera nel campo
  `rooms` né nel testo ("tre camere", "two rooms", "due coppie", "una matrimoniale e una
  doppia") la risposta è `question` "In quante camere?" / "How many rooms?" e nulla viene
  salvato; con 1 o 2 persone la camera è una, senza domanda e senza dirlo nel `say`. Un prodotto
  con `maxPaxPerRoom` vuole almeno ceil(persone / massimo) camere: con meno è escluso (filtro
  duro dopo le persone), e se non resta nulla `no_match` ha `failed_criterion` `rooms` con il
  minimo nel `say` ("camere da massimo 2 persone: per 5 persone servono almeno 3 camere"). La
  `reason` della proposta dice il limite quando obbliga a più di una camera. Con una persona sola
  e soli viaggi da 2 in su, `failed_criterion` è `pax` e il `say` lo spiega. Nel rifiuto le
  camere si cambiano da testo o campo, sempre entro le persone; se cambiano solo le persone le
  camere restano (limitate alle persone) e il `say` le ripete ("per 5 persone in 1 camera"). Su
  `accept` il campo `rooms` corregge le camere: sotto il minimo del prodotto la risposta è
  `question` e nessun ordine nasce; valido, aggiorna ordine e criteri dell'intento; ignorato
  sulla conferma del prezzo. Il job d'acquisto manda le camere dell'ordine a HofJ (RF-67).
- **`say`** (RF-54): `intent_created`, `proposal` e `no_match` di un rifiuto ripetono i criteri
  capiti ("Ho capito: …"); un motivo di rifiuto che non cambia nessun criterio viene dichiarato.
- **Dopo una proposta** (RF-55) ogni cambiamento passa da `reject`, mai da un nuovo
  `POST /v1/intents`. Un `no_match` restituito da `reject` porta `rejected_proposal_id`: un
  nuovo `reject` su quella proposta con i campi cambiati aggiorna i criteri e propone di nuovo,
  senza registrare un secondo rifiuto.

## Risposte

Ogni risposta di successo è `{"outcome": <esito>, ...}` con le chiavi del contratto `to_dict()`
(vedi `docs/plans/2026-09-25-m2-dominio-replay.md`). Ogni risposta ha `say`, la frase da leggere
al viaggiatore, e contiene al massimo un prodotto (RF-10).

| `outcome` | HTTP | Significato |
|---|---|---|
| `intent_created` | 201 | intento salvato con i criteri estratti (da M21-E anche `budget_scope`: `per_person`, `total`, `null` senza budget; da M21-D `rooms`) |
| `question` | 200 | manca un dato indispensabile, oppure (M21-D, su `accept`) le camere sono sotto il minimo del prodotto: leggere `say`, nulla è stato salvato |
| `proposal` | 200 | una proposta; `nights` = notti del viaggio (`end_date` − `start_date`, M21-A); `rooms` = camere dell'intento (M21-D) |
| `no_match` | 200 | niente di compatibile; `failed_criterion` dice perché; `rejected_proposal_id` se arriva da un rifiuto (RF-55) |
| `order_queued` | 202 | ordine ancora in coda allo scadere dell'attesa (RF-45, 100 s): `order_id`, `status` `queued`, `position`, `wait_seconds`. Prezzo e link arrivano con lo stato. Header `Location: /v1/orders/{order_id}` |
| `missing_traveler_data` | 200 | mancano dati del viaggiatore; `missing` li elenca |
| `order_status` | 200 | stato dell'ordine con campi fissi, `null` quando non pertinenti (tabella sotto) |

Campi di `order_status` (RF-25, RF-39): `order_id`, `status`, `position`, `wait_seconds`, `total`,
`currency`, `price_from_total`, `total_differs`, `payment_url`, `booking_code`, `failure_reason`,
`proposal_changed`, `proposal`, `say`.

| `status` | Campi valorizzati |
|---|---|
| `queued` | `position` e `wait_seconds` (ricalcolati a ogni richiesta, RF-48); `null` se il job è già in lavorazione |
| `awaiting_confirmation` | `total` (prezzo effettivo, `openAmount` di HofJ), `currency`, `price_from_total`, `total_differs` (RF-16); `payment_url` `null`. Un nuovo `POST .../accept` sulla stessa proposta conferma il prezzo, `POST .../reject` annulla l'ordine |
| `awaiting_payment` | `total` (importo reale, `openAmount` di HofJ), `currency`, `price_from_total`, `total_differs` (RF-16), `payment_url` |
| `paid_pending_booking` | `total`, `currency` |
| `confirmed` | `total`, `currency`, `booking_code` |
| `replaced` | `proposal_changed: true`, `proposal` = la nuova proposta (stessa forma di `proposal`, RF-17) |
| `cancelled` | — (rinuncia, RF-49) |
| `failed`, `booking_failed` | `failure_reason` leggibile |
| `expired` | `total`, `currency` |

## Errori (RFC 7807)

Solo sotto `/v1`: `content-type: application/problem+json`, corpo
`{type, title, status, detail, instance, say}`.

| HTTP | `type` | Quando |
|---|---|---|
| 401 | `/problems/unauthorized` | token mancante, sbagliato o schema non Bearer; header `WWW-Authenticate: Bearer` |
| 404 | `/problems/not-found` | id sconosciuto (il `detail` dice intento, proposta o ordine) o route sconosciuta |
| 405 | `/problems/method-not-allowed` | metodo sbagliato su una route esistente |
| 422 | `/problems/invalid-request` | body o parametri non validi, JSON malformato; campo `errors` |
| 503 | `/problems/rest-not-configured` | `VELA_API_TOKEN` non impostata |
| 503 | `/problems/domain-unavailable` | `DATABASE_URL` non impostata |
| 500 | `/problems/internal-error` | errore inatteso; il dettaglio è solo nei log |

Ordine dei controlli: token configurato (503), token valido (401), validazione (422), dominio (503).

## Flusso §10.3 con `scripts/rest_flow.py` (M7)

Lo script esegue il flusso e cronometra ogni passo (latenza per M13). Il token si legge solo da
`VELA_API_TOKEN` e non viene stampato.

```bash
# criterio 3: intento, "troppo caro" (la seconda proposta deve costare meno), accept, prezzo
# effettivo, secondo accept (la conferma), link, pagamento a mano con 4242 4242 4242 4242, confirmed con il codice
uv run python scripts/rest_flow.py https://vela-n506.onrender.com
# criterio 4: con una fixture di prova che contiene la trappola e il 78 archiviato
# (`add_trap(catalog, "78", archive_template=True)`, M21-B) la prima proposta di INTENT_TRAP è la
# trappola; dopo l'accept l'ordine diventa replaced con una proposta diversa, senza errori nel `say`
uv run python scripts/rest_flow.py https://vela-n506.onrender.com --trap
```

Opzioni: `--intent` (altra frase), `--poll` (secondi tra due stati, default 5), `--timeout` (attesa
massima per stato, default 900). Esito: una riga per campo (ordine, prodotti, codice) e una tabella
Markdown dei tempi. Uscita 1 con `FALLITO: ...` se un controllo non passa (più di un prodotto, seconda
proposta non più economica, stato terminale inatteso, timeout).

## Flusso §10.3 con `curl`

Richiede `curl` e `jq`. Il token si legge da una variabile già esportata e non va mai scritto
nel comando né stampato.

```bash
# Prerequisiti: export VELA_URL=https://vela-n506.onrender.com  e  VELA_API_TOKEN nell'ambiente.
H="Authorization: Bearer $VELA_API_TOKEN"

curl -s "$VELA_URL/health" | jq

INTENT=$(curl -s -X POST "$VELA_URL/v1/intents" -H "$H" -H 'content-type: application/json' \
  -d '{"text":"un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro",
       "profile":{"first_name":"Anna","last_name":"Rossi","email":"anna@example.com",
                  "phone":"+390000000000","participants":[{"first_name":"Bo","last_name":"Bi"}]}}')
echo "$INTENT" | jq '{outcome, intent_id, say}'
IID=$(echo "$INTENT" | jq -r .intent_id)

P1=$(curl -s "$VELA_URL/v1/intents/$IID/proposal" -H "$H")
echo "$P1" | jq '{outcome, proposal_id, product, total_from, say}'

P2=$(curl -s -X POST "$VELA_URL/v1/proposals/$(echo "$P1" | jq -r .proposal_id)/reject" -H "$H" \
  -H 'content-type: application/json' -d '{"reason":"troppo caro"}')
echo "$P2" | jq '{outcome, proposal_id, product, total_from, say}'

ACCEPT="$VELA_URL/v1/proposals/$(echo "$P2" | jq -r .proposal_id)/accept"
ORDER=$(curl -s -X POST "$ACCEPT" -H "$H")               # aspetta il prezzo effettivo (max 100 s)
echo "$ORDER" | jq '{outcome, status, total, price_from_total, say}'   # awaiting_confirmation
OID=$(echo "$ORDER" | jq -r .order_id)

STATUS=$(curl -s -X POST "$ACCEPT" -H "$H")              # la conferma: aspetta il link
echo "$STATUS" | jq '{status, total, total_differs, payment_url, say}'  # awaiting_payment

curl -s "$(echo "$STATUS" | jq -r .payment_url)" | jq     # replay: simula il pagamento
# con STRIPE_SECRET_KEY: aprire payment_url nel browser e pagare con 4242 4242 4242 4242 (docs/stripe.md)
sleep 2
curl -s "$VELA_URL/v1/orders/$OID" -H "$H" | jq          # atteso: confirmed, booking_code R-xxxxxx

curl -s -o /dev/null -w '%{http_code}\n' -X POST "$VELA_URL/v1/intents"   # atteso: 401
```

In replay nessuna chiamata va a HofJ o Stripe. Con `STRIPE_SECRET_KEY` il link di pagamento è Stripe:
si paga con `4242 4242 4242 4242` e si interroga lo stato finché diventa `confirmed`. Il passaggio a
pagato lo rileva il job di verifica della sessione (ogni 60 s, e subito quando si chiede lo stato;
niente webhook, `docs/stripe.md`).
