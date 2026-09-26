# SMS al viaggiatore (Twilio)

Vela manda due SMS al viaggiatore principale, senza che nessuno chieda nulla (decisione del
2026-09-26, design in `docs/superpowers/specs/2026-09-26-sms-notifiche-design.md`):

1. quando l'ordine diventa `awaiting_payment`: riepilogo (titolo, date, persone, totale) e link
   di pagamento Stripe, valido 24 ore;
2. quando l'ordine diventa `confirmed`: riepilogo e codice di prenotazione.

Codice: `vela/domain/sms.py` (job), `vela/domain/sms_text.py` (testi), `vela/domain/phone.py`
(numeri), `vela/adapters/sms_twilio.py`, `vela/adapters/sms_fake.py`.

## Numeri

Il telefono è quello di RF-12. Spazi e separatori vengono tolti; `+…` resta com'è; `00…`
diventa `+…`; altrimenti si aggiunge `+39` (test in Italia). Un numero che non risulta `+` e
8-15 cifre non riceve SMS: il job lo registra nei log e l'ordine va avanti.

## Attivazione

| Variabile | Effetto |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | Tutte e tre: SMS reali con Twilio. Nessuna: SMS finti (replay e test). Solo alcune: l'app non parte. Indipendenti da `VELA_UPSTREAM_MODE` |

`TWILIO_FROM` è il numero Twilio acquistato, in E.164. Mai incollare le chiavi in chat, nei
commit o in `docs/`.

## Tentativi

Job `sms_link` e `sms_confirmed` nella coda del worker, prelevati dopo prenotazioni e verifiche
del pagamento e prima degli acquisti. Errore temporaneo (rete, timeout, 5xx, 429): nuovo
tentativo dopo 30 s, 2 min, 10 min, poi `dead`. Altro 4xx di Twilio: `dead` subito. Un SMS non
cambia mai lo stato dell'ordine. Nei log il numero è mascherato (`+39******4567`) e il testo
non compare.

## Test manuale

Costo: 2 SMS Twilio (circa 3-4 segmenti in tutto), 1 Checkout Session e 1 pagamento di test
Stripe, più quanto indicato in `docs/stripe.md` per HofJ in live.

1. Impostare nell'ambiente le tre variabili Twilio e `STRIPE_SECRET_KEY` con `VELA_PUBLIC_URL`.
2. Eseguire il flusso di `docs/stripe.md` (`scripts/rest_flow.py`) con il proprio numero come
   telefono del viaggiatore.
3. Senza interrogare lo stato: arriva l'SMS con riepilogo e link. Pagare con `4242 4242 4242 4242`.
4. Arriva l'SMS di conferma con lo stesso codice di `GET /v1/orders/<order_id>`.

Registrare l'esito in `docs/acceptance.md` senza numero né chiavi.
