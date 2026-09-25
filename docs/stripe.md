# Stripe: link di pagamento e webhook (M6)

Vela crea una Checkout Session di Stripe per ogni ordine (RF-18): totale reale in EUR,
`metadata` con `order_id` e `itinerary_id`, scadenza 24 ore dalla creazione dell'ordine
(RF-21). Il pagamento viene confermato solo dal webhook firmato (RF-20). Nessun dato di carta
passa da Vela. Codice: `vela/adapters/stripe_links.py`, `vela/surfaces/webhooks.py`,
`vela/surfaces/checkout_pages.py`.

## Attivazione

| Variabile | Effetto |
|---|---|
| `STRIPE_SECRET_KEY` | Se impostata (`sk_test_...`), i link sono Stripe reali; altrimenti restano i link finti di replay. Indipendente da `VELA_UPSTREAM_MODE` |
| `STRIPE_WEBHOOK_SECRET` | Obbligatoria con la chiave (`whsec_...`); senza, l'app non parte. Senza chiave, il webhook risponde 503 |
| `VELA_PUBLIC_URL` | Obbligatoria con la chiave: base di `/checkout/success` e `/checkout/cancel` |

## Setup dell'account Stripe di test (una volta)

1. Dashboard Stripe in modalità **test** → Developers → API keys: copiare la secret key `sk_test_...`.
2. Developers → Webhooks → Add endpoint:
   - URL: `<VELA_PUBLIC_URL>/webhooks/stripe`
   - Eventi: `checkout.session.completed`, `checkout.session.expired` (nessun altro)
3. Aprire l'endpoint creato e copiare il signing secret `whsec_...`.
4. Render → servizio Vela → Environment: impostare `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
   e verificare `VELA_PUBLIC_URL`. Salvare: Render ridistribuisce.

Mai incollare le chiavi in chat, nei commit o in `docs/`.

## Test manuale (HofJ in replay, Stripe reale)

Costo: 1 Checkout Session e 1 pagamento di test sull'account Stripe di test; nessuna chiamata a HofJ.

1. Flusso REST fino all'ordine (vedi `docs/rest.md`, sezione del flusso con `curl`): `payment_url`
   deve iniziare con `https://checkout.stripe.com/`.
2. Aprire `payment_url`, pagare con `4242 4242 4242 4242`, una data futura, un CVC qualsiasi.
3. Il browser arriva su `/checkout/success`.
4. `GET /v1/orders/<order_id>` entro qualche secondo: `confirmed` con un codice `R-xxxxxx` finto.
5. Nel Dashboard → Webhooks → endpoint: l'evento `checkout.session.completed` risulta consegnato
   con risposta 200 `{"received": true, "outcome": "paid"}`.
6. Facoltativo: "Resend" dello stesso evento dal Dashboard → 200 `duplicate`, ordine invariato.

Registrare l'esito in `docs/acceptance.md` (registro delle esecuzioni) senza chiavi né dati personali.

## Risposte del webhook

| HTTP | Corpo | Quando |
|---|---|---|
| 200 | `{"received": true, "outcome": "paid"}` | pagamento applicato, prenotazione avviata |
| 200 | `outcome` `expired` | ordine non pagato portato a `expired` |
| 200 | `outcome` `duplicate` | evento già elaborato |
| 200 | `outcome` `noop` | evento valido ma l'ordine era già oltre (es. già pagato) |
| 200 | `outcome` `rejected` | ordine sconosciuto, importo, valuta o stato del pagamento non coerenti (warning nei log) |
| 200 | `outcome` `ignored` | tipo di evento non gestito |
| 400 | `{"error": "firma non valida"}` | firma mancante, errata o più vecchia di 300 s |
| 500 | `{"error": "elaborazione non riuscita"}` | errore interno: Stripe ripete l'evento |
| 503 | `{"error": "webhook non configurato"}` | `STRIPE_WEBHOOK_SECRET` o `DATABASE_URL` assenti |
