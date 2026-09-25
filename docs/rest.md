# Superficie REST

La superficie REST (RF-40) espone i cinque casi d'uso di RF-39 sotto `/v1`. Ogni endpoint richiede
`Authorization: Bearer <VELA_API_TOKEN>` (RF-43); senza la variabile impostata sul server ogni
`/v1/*` risponde 503. Codice: `vela/surfaces/rest.py`, errori in `vela/surfaces/problems.py`.
`GET /health`, `/docs` e `/openapi.json` sono pubblici.

## Endpoint

| Endpoint | Body | Esiti |
|---|---|---|
| `POST /v1/intents` | `{"text": str, "profile"?: Profile}` | 201 `intent_created`, 200 `question` |
| `GET /v1/intents/{intent_id}/proposal` | — | 200 `proposal`, 200 `no_match` |
| `POST /v1/proposals/{proposal_id}/reject` | opzionale `{"reason"?: str}` | 200 `proposal`, 200 `no_match` |
| `POST /v1/proposals/{proposal_id}/accept` | opzionale `{"traveler"?: Profile}` | 202 `order_queued` (con `Location`), 200 `order_status` a un secondo accept, 200 `missing_traveler_data` |
| `GET /v1/orders/{order_id}` | — | 200 `order_status` |

`Profile` = `{"first_name"?, "last_name"?, "email"?, "phone"?, "pax"? (≥ 1), "participants"?: [{"first_name"?, "last_name"?}]}`.
`text` è ripulito dagli spazi e va da 1 a 1000 caratteri. I campi extra sono ignorati.

## Risposte

Ogni risposta di successo è `{"outcome": <esito>, ...}` con le chiavi del contratto `to_dict()`
(vedi `docs/plans/2026-09-25-m2-dominio-replay.md`). Ogni risposta ha `say`, la frase da leggere
al viaggiatore, e contiene al massimo un prodotto (RF-10).

| `outcome` | HTTP | Significato |
|---|---|---|
| `intent_created` | 201 | intento salvato con i criteri estratti |
| `question` | 200 | manca un dato indispensabile: leggere `say`, nulla è stato salvato |
| `proposal` | 200 | una proposta |
| `no_match` | 200 | niente di compatibile; `failed_criterion` dice perché |
| `order_queued` | 202 | ordine in coda (M5, RF-45): `order_id`, `status` `queued`, `position`, `wait_seconds`. Nessun link: arriva con lo stato. Header `Location: /v1/orders/{order_id}` |
| `missing_traveler_data` | 200 | mancano dati del viaggiatore; `missing` li elenca |
| `order_status` | 200 | stato dell'ordine con campi fissi, `null` quando non pertinenti (tabella sotto) |

Campi di `order_status` (RF-25, RF-39): `order_id`, `status`, `position`, `wait_seconds`, `total`,
`currency`, `price_from_total`, `total_differs`, `payment_url`, `booking_code`, `failure_reason`,
`proposal_changed`, `proposal`, `say`.

| `status` | Campi valorizzati |
|---|---|
| `queued` | `position` e `wait_seconds` (ricalcolati a ogni richiesta, RF-48); `null` se il job è già in lavorazione |
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

ORDER=$(curl -s -X POST "$VELA_URL/v1/proposals/$(echo "$P2" | jq -r .proposal_id)/accept" -H "$H")
echo "$ORDER" | jq '{outcome, order_id, position, wait_seconds, say}'   # 202 order_queued
OID=$(echo "$ORDER" | jq -r .order_id)

sleep "$(echo "$ORDER" | jq -r .wait_seconds)"
STATUS=$(curl -s "$VELA_URL/v1/orders/$OID" -H "$H")     # atteso: awaiting_payment con payment_url
echo "$STATUS" | jq '{status, total, total_differs, payment_url, say}'

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
