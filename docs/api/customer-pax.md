# Cliente e passeggeri prima e dopo il totale — sonda di M19

Eseguita il 2026-09-27 su `https://staging.api.hofj.com`, brand `staging.weebora.com`,
`locale=en`, con `scripts/m19_probe.py`, lanciato dall'utente dal suo terminale. **5 chiamate
HofJ**, le 5 dichiarate. Nessun `GET /v1/quota`, nessun pagamento, nessun `POST /v1/bookings`,
nessuna chiamata Stripe. Una chiamata ogni 12 s, perché la chiave è condivisa con il servizio su
Render. Contesto: domanda 10 in `docs/hofj-questions.md`, roadmap M19.

## Esito in breve

- **Il totale non cambia dopo cliente e passeggeri.** `checkout.openAmount` (l'importo del link),
  `checkout.total`, `checkout.originalTotal` e `totalPrice` valgono 1156 € sia subito dopo la
  creazione sia dopo `PUT customer` e `PUT pax`. Tra le due letture cambiano solo `customer` e
  `passengers`; tutte le altre chiavi dell'itinerario sono identiche.
- **I passeggeri esistono dalla creazione.** Il `GET` dell'itinerario appena creato ha già
  `passengers` con i `refId` `pax-1` e `pax-2` (vuoti) e `customer` con tutti i campi vuoti. I
  `refId` sono quelli visti in M5 su un altro prodotto, e `PUT pax` li accetta senza un
  `GET .../pax` prima.
- **Stesso totale della sonda di M22-a.** Lo stesso prodotto, con la stessa data e le stesse
  persone, valeva 1156 € anche il 27/09 (`arjeuuuzzw9s`, `docs/api/accommodations.md`).
- **`PUT customer` e `PUT pax` sono accettati dopo il pagamento** (seconda sonda, sotto): 200 su
  un itinerario con un PaymentIntent di test `succeeded` legato da `checkoutRefId`, totale
  invariato, e `POST /v1/bookings` riuscito subito dopo.

## Chiamate

| # | Chiamata | Esito | Latenza |
|---|---|---|---|
| 1 | `POST /v1/itineraries` prodotto 124 "Magnificent Padel in Lanzarote" (`hotelSelection: true`, `allowAccommodationList: false`), 2026-10-08, 2 adulti, 1 camera, EUR | 200 `deimmovsayfq` | 7138 ms |
| 2 | `GET /v1/itineraries/deimmovsayfq` | 200, `openAmount` = `total` = `originalTotal` = 1156, `totalPrice` 1156.00 EUR, `status` `BookingInitiated`, hotel THB Lanzarote Beach | 1949 ms |
| 3 | `PUT .../customer` (corpo di `HofJHttp.set_customer`, indirizzo di `TravelerDefaults`) | 200 `{data: {now}, meta: {}}` | 2065 ms |
| 4 | `PUT .../pax` `[{refId: pax-1, …}, {refId: pax-2, …}]` (solo `refId`, nome, cognome, come `HofJHttp.set_pax`) | 200 `{data: {now}, meta: {}}` | 1010 ms |
| 5 | `GET /v1/itineraries/deimmovsayfq` | 200, importi identici alla #2 | 1965 ms |

La creazione a 7,1 s è la più lenta vista finora: le sonde precedenti andavano da 2,2 a 6,1 s.

## Forme osservate

Prima (#2):

```json
{"customer": {"firstName": "", "lastName": "", "email": "", "phone": "", "taxNumber": "",
              "marketingOptIn": false,
              "address": {"street1": "", "postalCode": "", "city": "", "region": "", "countryCode": ""}},
 "passengers": [{"refId": "pax-1", "firstName": "", "lastName": "", "age": 0, "gender": null,
                 "nationalityCountryCode": ""},
                {"refId": "pax-2", "firstName": "", "lastName": "", "age": 0, "gender": null,
                 "nationalityCountryCode": ""}],
 "checkout": {"openAmount": {"amount": "1156", "currency": "EUR"},
              "total": {"amount": "1156", "currency": "EUR"},
              "originalTotal": {"amount": "1156", "currency": "EUR"},
              "status": "BookingInitiated", "refId": "deimmovsayfq"},
 "totalPrice": {"amount": "1156.00", "currency": "EUR"}}
```

Dopo (#5): `customer` e `passengers` con i valori mandati (`taxNumber` vuoto,
`marketingOptIn: false`, `age: 0`, `gender: null` invariati), `checkout` e `totalPrice`
identici.

## Risposte alle domande della sonda

| Domanda | Risposta |
|---|---|
| Il totale cambia dopo `PUT customer` e `PUT pax`? | **No** su un prodotto con hotel preselezionato, 2 adulti, 1 camera: nessuno dei quattro importi cambia |
| Il totale del link si conosce con 2 chiamate (creazione + `GET`)? | **Sì**: `openAmount` è già definitivo alla #2 |
| `PUT pax` senza `GET .../pax`? | **Sì**, con i `refId` `pax-1..N`, che il `GET` dell'itinerario mostra già dalla creazione |
| `PUT customer` e `PUT pax` accettati dopo il pagamento? | **Sì su staging**, con un PaymentIntent di test diretto (seconda sonda, sotto) |
| La differenza `total` 368 / `openAmount` 337 di M5 (prodotto 118) dipende dai passeggeri? | Non risolta: sul 124 i due importi coincidono prima e dopo, ma in M5 il 118 fu letto solo dopo i pax. Nessun indizio che dipenda dai passeggeri; il link usa comunque `openAmount` |

## Seconda sonda: `PUT` dopo il pagamento

Eseguita il 2026-09-27 con `scripts/m19_paid_probe.py`, lanciato dall'utente: **6 chiamate
HofJ staging e 1 Stripe in modalità test**, le 7 dichiarate, con i due `PUT` dopo il pagamento.

| # | Chiamata | Esito | Latenza |
|---|---|---|---|
| 1 | `POST /v1/itineraries` 124, 2026-10-08, 2 adulti, 1 camera | 200 `ttlup3o1amxu` | 4282 ms |
| 2 | `GET /v1/itineraries/ttlup3o1amxu` | 200, `openAmount` 1156 EUR, `status` `BookingInitiated` | 1700 ms |
| 3 | Stripe `POST /v1/payment_intents`: 115600 centesimi EUR, `pm_card_visa`, `confirm`, `metadata.checkoutRefId` = itinerario | 200 `pi_3UKJpdRpam3eRRKb0twU1yQi`, `succeeded`, `livemode: false`, `capture_method: automatic` | 1025 ms |
| 4 | `PUT .../customer` **dopo il pagamento** | 200 `{data: {now}, meta: {}}` | 2425 ms |
| 5 | `PUT .../pax` **dopo il pagamento** | 200 `{data: {now}, meta: {}}` | 1059 ms |
| 6 | `GET /v1/itineraries/ttlup3o1amxu` | 200, importi e `status` identici alla #2; cambiano solo `customer` e `passengers`, con i valori mandati | 1704 ms |
| 7 | `POST /v1/bookings` `{itineraryId, paymentType: "full", paymentIntentId, paymentStatus: "succeeded"}` | 200 `{data: "ttlup3o1amxu"}` | 2444 ms |

Cosa dice e cosa non dice:

- HofJ non vede il pagamento: `checkout.status` resta `BookingInitiated` dopo il PaymentIntent
  `succeeded`, come in M5. Dal lato dell'API un carrello pagato non si distingue da uno non
  pagato, e i `PUT` passano.
- **Approssimazione dichiarata:** Vela paga con una Checkout Session, che crea lei il
  PaymentIntent con gli stessi metadata; qui il PaymentIntent è creato direttamente. Il brand
  site potrebbe distinguere i due casi solo da campi che Vela non manda.
- Il booking risponde con l'`itineraryId`, non con un codice `R-…`, come in M5 (domanda 2): la
  sonda prova che il booking dopo i `PUT` tardivi è accettato, non che la prenotazione sia
  confermata più di quanto lo fosse in M5.
- Staging non garantisce la produzione: la domanda 10 resta da mandare a HofJ.

## Itinerari di prova

- `deimmovsayfq` (124), prima sonda: orfano, con cliente e passeggeri di prova, nessun pagamento,
  nessun booking.
- `ttlup3o1amxu` (124), seconda sonda: pagato in modalità test
  (`pi_3UKJpdRpam3eRRKb0twU1yQi`, 1156 €) e prenotato su staging.

Registrati anche in `docs/decisions.md`.

## Differenze nuove

In `docs/api/differences.md`, #36-#39.
