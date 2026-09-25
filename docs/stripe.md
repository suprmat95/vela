# Stripe: link di pagamento (M6)

Vela crea una Checkout Session di Stripe per ogni ordine (RF-18): totale reale in EUR,
`metadata` con `order_id` e `itinerary_id` (sul PaymentIntent anche `checkoutRefId` =
itinerario), scadenza 24 ore meno un minuto dalla creazione dell'ordine (RF-21), idempotency
key per ordine. Nessun dato di carta passa da Vela. Codice: `vela/adapters/stripe_links.py`,
`vela/surfaces/checkout_pages.py`.

La chiave Stripe è una `rk_test` fornita da HofJ: le Checkout Session nascono sull'account
Stripe di HofJ.

## Nessun webhook

Deciso con HofJ: il pagamento si chiude unicamente con le API di HofJ. Vela non espone un
endpoint webhook e non serve registrare nulla nel Dashboard Stripe né un signing secret.

- Vela scopre che il viaggiatore ha pagato leggendo lo stato della Checkout Session
  (`checkout.sessions.retrieve`) con un job del worker: M5, Task 13b.
- Il pagamento si chiude con `POST /v1/bookings` di HofJ, inoltrando `paymentIntentId` e
  `paymentStatus`: M5, nel job di prenotazione.

Finché M5 non è mergiata, un ordine pagato su Stripe resta `awaiting_payment`.

## Attivazione

| Variabile | Effetto |
|---|---|
| `STRIPE_SECRET_KEY` | Se impostata (la `rk_test` di HofJ), i link sono Checkout Session reali; altrimenti restano i link finti di replay. Indipendente da `VELA_UPSTREAM_MODE` |
| `VELA_PUBLIC_URL` | Obbligatoria con la chiave (senza, l'app non parte): base di `/checkout/success` e `/checkout/cancel` |

Mai incollare le chiavi in chat, nei commit o in `docs/`.

## Pagine di ritorno

`/checkout/success` e `/checkout/cancel` sono statiche: non leggono l'ordine e non mostrano
dati. La conferma del pagamento non arriva da lì ma dal job di verifica di M5.

## Test manuale

Il test end-to-end (ordine `confirmed` dopo un pagamento reale) si esegue **dopo M5**, quando
esiste il job che verifica la sessione. Con la sola M6 si può verificare la prima metà:

Costo: 1 Checkout Session e 1 pagamento di test sull'account Stripe di test di HofJ; nessuna
chiamata a HofJ in replay.

1. Flusso REST fino all'ordine (vedi `docs/rest.md`, sezione del flusso con `curl`): `payment_url`
   deve iniziare con `https://checkout.stripe.com/`.
2. Aprire `payment_url`, pagare con `4242 4242 4242 4242`, una data futura, un CVC qualsiasi.
3. Il browser arriva su `/checkout/success`.
4. Con M5: `GET /v1/orders/<order_id>` passa a pagato quando il job di verifica legge la
   sessione, poi a `confirmed` con il codice di HofJ. Senza M5 resta `awaiting_payment`.

Registrare l'esito in `docs/acceptance.md` (registro delle esecuzioni) senza chiavi né dati personali.
