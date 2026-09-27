# `/v1/itineraries/{id}/accommodations` — sonda di M22-a

Eseguita il 2026-09-27 su `https://staging.api.hofj.com`, brand `staging.weebora.com`, client
`test-dev-2`, `locale=en` (quello della fixture di staging), con
`scripts/accommodations_probe.py`. **11 chiamate HofJ** in due giri (8 + 3), su 13 approvate
dall'utente. Nessun `POST /v1/bookings`, nessuna chiamata Stripe. Una chiamata ogni 12 s: la
chiave è condivisa con il servizio su Render. Contesto e bozza: `docs/plans/2026-09-27-m22-hotel.md`.

## Esito in breve

- **Il `PATCH` non è stato verificato.** Nessuno dei quattro itinerari ha offerto un hotel con
  `roomIds` da mandare: la lista era vuota su tre, e sul quarto l'unico hotel aveva
  `roomsConfiguration: []`. Restano senza risposta: formato e risposta del `PATCH`, `roomIds`
  per 1 e 2 camere, variazione del totale dopo il cambio.
- **`hotelSelection=true` non basta per avere una lista.** Sul prodotto 124
  (`hotelSelection: true`, `allowAccommodationList: false`) la lista è vuota. L'unica lista
  non vuota è arrivata dal prodotto 25, l'unico di staging con `allowAccommodationList: true`.
- **Un prodotto con hotel fisso non dà errore.** `hotelSelection=false` risponde 200 con lista
  vuota, come un prodotto senza alternative.
- **Il prodotto con la lista non ha un hotel preselezionato.** Sul 25 l'itinerario appena creato
  ha `accommodation` con tutti i campi `null` e `removableAccommodation: true`, eppure un totale
  di 1798 €.

## Chiamate

| # | Chiamata | Prodotto, date | Esito | Latenza |
|---|---|---|---|---|
| 1 | `GET /v1/quota` | — | 200, `usedInWindow` 1, `limitPerMinute` 120 | 5617 ms |
| 2 | `POST /v1/itineraries` | 124 "Magnificent Padel in Lanzarote", 08/10, 2 adulti, 1 camera | 200 `arjeuuuzzw9s` | 4053 ms |
| 3 | `GET /v1/itineraries/arjeuuuzzw9s` | | 200, hotel THB Lanzarote Beach, totale 1156 € | 1767 ms |
| 4 | `GET .../accommodations?startDate=2026-10-08&sortByValue=recommended` | | 200, `elements: []`, `totalCount` 0 | 2033 ms |
| 5 | `POST /v1/itineraries` | 28 "Nueva Alcantara Club – 2-day training" (`hotelSelection=false`), 15/10 | 200 `fcocq0pgspd1` | 2246 ms |
| 6 | `GET .../accommodations?startDate=2026-10-15&sortByValue=recommended` | | 200, `elements: []` | 2088 ms |
| 7 | `POST /v1/itineraries` | 124, 08/10, 2 adulti, **2 camere** | 200 `p8htf0mqbarg` | 2321 ms |
| 8 | `GET .../accommodations?startDate=2026-10-08&sortByValue=distance` | | 200, `elements: []` | 1945 ms |
| 9 | `POST /v1/itineraries` | 25 "Padel Travel Weekend Camps – Malaga" (entrambi i flag), 15/10, 2 adulti, 1 camera | 200 `phtjys9d6rip` | 6139 ms |
| 10 | `GET /v1/itineraries/phtjys9d6rip` | | 200, `accommodation` tutto `null`, totale 1798 € | 1466 ms |
| 11 | `GET .../accommodations?startDate=2026-10-15&sortByValue=recommended` | | 200, 1 hotel, `roomsConfiguration: []` | 1476 ms |

I `PATCH` e le riletture previsti (su A, su C e sul 25) non sono partiti: lo script li fa solo
se trova un hotel diverso dall'attuale con almeno una configurazione di camere.

## Latenza

`GET .../accommodations`: 2033, 2088, 1945 e 1476 ms, cioè 1,5-2,1 s, anche con la lista vuota.
`POST /v1/itineraries` 2,2-6,1 s, `GET /v1/itineraries/{id}` 1,5-1,8 s. Un cambio di hotel con
3 chiamate (lista, `PATCH`, rilettura) costerebbe circa 5-10 s, `PATCH` escluso perché non
misurato: ben sotto il tetto di 100 s dell'attesa di `reject_proposal`.

## Forme osservate

**Itinerario** (`GET /v1/itineraries/{id}`): chiavi fuori dall'OAS `removableAccommodation`,
`groupTourId`, `players`, `groupTourAvailability`, `travelProgram`, `travelDetail`,
`paymentOptionsConfiguration`, `withoutNavigations`, `adultCount`, `childCount`, `customer`,
`passengers`, `rooms`. `accommodation` ha anche `componentId`. Sul 124 l'hotel preselezionato
ha `rating: 4` e `totalPrice: 0.00 EUR` (incluso nel pacchetto); `checkout.openAmount` =
`total` = `originalTotal` = 1156 €. Sul 25 `accommodation` c'è ma ogni campo è `null`.

**Lista** (`AccommodationsPagination`):

```json
{"elements": [{"id": "6a91593425000009a05d9a6a",
               "title": "HIGUERON HOTEL MALAGA, CURIO COLLECTION BY HILTON",
               "rating": 5, "guestRating": 0, "reviewsCount": null, "isRecommended": true,
               "totalPrice": {"amount": "1.00", "currency": "EUR"},
               "startDate": "2026-10-15T00:00:00.000Z", "endDate": "...", "nights": 3,
               "address": "...", "coordinates": {"...": "..."}, "source": "NEZASA",
               "roomsConfiguration": [], "image": {}, "gallery": []}],
 "pagination": {"totalCount": 1, "totalPages": 1},
 "aggregate": {"sorting": ["priceAsc", "priceDesc", "recommended", "distance"],
               "filters": [{"id": "guestRating", "type": "checkbox", "values": ["0"]},
                           {"id": "starsRating", "type": "checkbox", "values": ["5"]},
                           {"id": "price", "type": "slide", "values": ["1", "1"]},
                           {"id": "distance", "type": "slide", "values": [1, 40]}]}}
```

## Risposte alle domande della sonda

| Domanda | Risposta |
|---|---|
| Latenza reale di `/accommodations` | 1,5-2,1 s su 4 misure |
| Formato del `PATCH`, `roomIds` per 2 persone in 1 camera e in 2 camere | **Non verificato**: nessun hotel con `roomsConfiguration` |
| Il totale cambia dopo il `PATCH`? | **Non verificato** |
| Prodotto con `hotelSelection=false` | 200 con lista vuota, nessun errore |
| Il primo `recommended` è l'hotel preselezionato? | **Non verificabile**: dove c'è un preselezionato (124) la lista è vuota; dove c'è una lista (25) non c'è un preselezionato. Sul 25 l'unico hotel ha `isRecommended: true` |
| Significato di `rating` | Stelle: l'aggregato chiama il filtro `starsRating` e il valore 5 coincide con il `rating` dell'unico hotel (Hilton Curio, 5 stelle) |
| Significato di `guestRating` | Voto degli ospiti, 0 con `reviewsCount: null`: su staging nessuna recensione, quindi il dato non serve a scegliere |
| `distance` misurata dal venue? | Non verificabile con un solo hotel; l'aggregato dà un intervallo 1..40 (km, presumibilmente) anche con la lista vuota |

## Itinerari orfani

`arjeuuuzzw9s` (124), `fcocq0pgspd1` (28), `p8htf0mqbarg` (124, 2 camere), `phtjys9d6rip` (25).
Nessun pagamento, nessun booking. Registrati anche in `docs/decisions.md`.

## Differenze nuove

In `docs/api/differences.md` dal #28.
