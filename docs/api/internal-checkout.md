# Rotte interne: OAuth, itinerari, booking, trips, payment — carrello e booking verificati su staging (M5)

Nessuna di queste rotte è stata chiamata: richiedono un `itineraryId` creato da
`POST /v1/itineraries`, oppure l'header `X-End-User-Authorization` (token Cognito
dell'utente finale), oppure sono mutazioni (POST/PUT/PATCH/DELETE) escluse dal perimetro.
Contenuto trascritto da OAS e dalle pagine DOCS "Checkout flow" e "Agnostic cart".

Requisiti comuni (DOCS): client con `profile=internal` e `allowedEntities` che include
`itineraries` (carrello), `bookings` (conferma e lookup), `trips` (liste utente). Brand
scelto a ogni chiamata con `?brand=`; il dominio risolto è sia host upstream sia valore di
tenant routing (`X-Nezasa-Channel`). Envelope `{data, meta: {now: <epoch ms>}}`. Timeout
upstream 15 s. `locale` in OAS è enum `it|en|es|fr`.

## Verifica su staging (M5, spec §8)

Eseguita il 2026-09-25 su `https://staging.api.hofj.com`, brand `staging.weebora.com`, client
`test-dev-2`, 9 chiamate HofJ + 1 Stripe (test). Dettagli e decisioni in `docs/decisions.md`
("M5: verifiche di spec §8"). Le sezioni sotto restano la trascrizione OAS/DOCS; dove
differiscono vale questa tabella.

| Chiamata | Esito osservato |
|---|---|
| `GET /v1/quota` | 200 `{clientId, limitPerMinute: 120, usedInWindow, remainingInWindow, windowStartedAt, windowEndsAt, backend: "firestore"}` |
| `POST /v1/itineraries` prodotto 118, `locale=it` | **502** `upstream-error`, `detail`: `Brand "staging.weebora.com" POST /itinerary returned 404: {...NOT_FOUND_ERROR... "queryProps":{"productId":118,"locale":"it"}}`. Il prodotto non esiste nella lingua richiesta |
| `POST /v1/itineraries` prodotto 118, `locale=en`, `{productId, startDate, adults: 2, rooms: 1, currency: "EUR"}` | 200 `{data: {itineraryId}, meta: {now}}` |
| `PUT /v1/itineraries/{id}/customer` con `address {street1, postalCode, city, region, countryCode}` (OAS) | 200 `{data: {now}, meta: {}}` |
| `GET /v1/itineraries/{id}/pax` | 200 `[{refId: "pax-1", firstName, lastName, age: 0, gender: null, nationalityCountryCode}, {refId: "pax-2", ...vuoti}]`. **`pax-1` è precompilato dal customer** |
| `PUT /v1/itineraries/{id}/pax` (array completo, `refId` invariati) | 200 `{data: {now}, meta: {}}` |
| `GET /v1/itineraries/{id}` | 200. `checkout {total: {amount: "368"}, openAmount: {amount: "337"}, originalTotal: {amount: "337"}, status: "BookingInitiated", refId}`, `totalPrice {amount: "368.00"}`. `Money.amount` è una stringa, a volte senza decimali |
| `POST /v1/bookings` `{itineraryId, paymentType: "full", paymentIntentId, paymentStatus: "succeeded"}` | 200 `{data: "<itineraryId>", meta: {now}}`: **nessun codice `R-…`**, il dato è l'`itineraryId` |
| `GET /v1/itineraries/{id}` dopo il booking | 200, `checkout.status` ancora `BookingInitiated`, `openAmount` ancora 337: il pagamento non risulta registrato |

Content-type sempre `application/json; charset=utf-8`, anche sugli errori.

## POST /v1/oauth/token — non chiamato (POST)

Form `application/x-www-form-urlencoded`: `grant_type=client_credentials`, `client_id`,
`client_secret`. Risposta con `access_token`. Pubblico (no Bearer). Durata del token non
documentata.

## Itinerario (carrello)

| Metodo | Path | operationId | Ingresso | Uscita `data` |
|---|---|---|---|---|
| POST | `/v1/itineraries` | `createItinerary` | query `brand`, `locale`; body `{productId (id numerico o tripCode/providerID), startDate YYYY-MM-DD, adults, rooms, affiliateId?, currency? EUR\|USD\|GBP}` | `{itineraryId}` |
| GET | `/v1/itineraries/{itineraryId}` | `getItinerary` | path `itineraryId`; query `brand`, `locale` | `Itinerary` |
| GET | `/v1/itineraries/{itineraryId}/activities` | `listItineraryActivities` | + query `startDate` **obbligatorio** (date) | `Activity[]` |
| GET | `/v1/itineraries/{itineraryId}/activities/{activityId}` | `getItineraryActivity` | path `activityId` | `Activity` |
| POST / PATCH / DELETE | `/v1/itineraries/{itineraryId}/activities/{activityId}` | `addItineraryActivity` / `updateItineraryActivity` / `removeItineraryActivity` | body `AddActivity` `{selectedCategory:{id}, selectedAmenities[], paxNumber, startTime, endTime}` / `PatchActivity` | – |
| GET | `/v1/itineraries/{itineraryId}/accommodations` | `listItineraryAccommodations` | + query `startDate` **obbligatorio**, `page` (int ≥1, default 1), `sortByValue` (`recommended`\|`priceAsc`\|`priceDesc`\|`distance`), `stars`, `rating`, `price`, `distance` (liste separate da virgola) | `AccommodationsPagination` `{elements: Accommodation[], pagination, aggregate: {sorting[], filters[]}}` |
| GET | `/v1/itineraries/{itineraryId}/accommodations/{accommodationId}` | `getItineraryAccommodation` | path `accommodationId` | `Accommodation` |
| PATCH | `/v1/itineraries/{itineraryId}/accommodations/{accommodationId}` | `replaceItineraryAccommodationRooms` | body `AccommodationReplace` `{roomIds: string[]}` | – |
| GET / PUT | `/v1/itineraries/{itineraryId}/customer` | `getItineraryCustomer` / `updateItineraryCustomer` | PUT body `CustomerData` | `CustomerData` |
| GET / PUT | `/v1/itineraries/{itineraryId}/pax` | `getItineraryPax` / `updateItineraryPax` | PUT body `Pax[]`, ogni elemento deve conservare `refId` | `Pax[]` |
| PUT | `/v1/itineraries/{itineraryId}/currency/{currency}` | `setItineraryCurrency` | path `currency` | – |
| POST / DELETE | `/v1/itineraries/{itineraryId}/promo-code` | `applyItineraryPromoCode` / `removeItineraryPromoCode` | body `{code}` | – |
| POST | `/v1/itineraries/{itineraryId}/payment` | `refreshItineraryPayment` | body `PaymentIntentRequest` `{paymentType: full\|plan, planIndex?}` | string `client_secret` Stripe |
| GET | `/v1/itineraries/{itineraryId}/payment` | `refreshItineraryPaymentGet` | query `paymentType` (default `full`), `planIndex` (int ≥0) | string. Alias di compatibilità: il BFF lo traduce in POST verso il brand. **Non chiamato** anche se GET: crea un payment intent (effetto collaterale). |

Errori dichiarati: 400, 401, 403, 404, 429, 502 (404 solo sulle rotte con id).

## Booking e trips (user-scoped)

| Metodo | Path | operationId | Ingresso | Uscita `data` |
|---|---|---|---|---|
| POST | `/v1/bookings` | `createBooking` | body `CreateBookingRequest` `{itineraryId, paymentType?, planIndex?}` | string codice prenotazione (es. `R-789012`). Upsert idempotente per `itineraryId`. |
| GET | `/v1/bookings/{bookingId}` | `getBooking` | path `bookingId`; header `X-End-User-Authorization` **obbligatorio**; query `brand`, `locale` | `Booking` |
| GET | `/v1/trips/{status}` | `listUserTrips` | path `status` enum `active`\|`past`; header `X-End-User-Authorization` | `Trip[]` |
| GET | `/v1/trips/active-summary` | `getActiveTripsSummary` | header `X-End-User-Authorization` | `TripSummary` `{currentTrip: Trip, activeTripsCount}` |

## Schemi principali (OAS)

- `Itinerary` (required: productId, title, titleVenue, image, productUrl, totalPrice,
  cancellationPolicy, startDate, endDate, paxNumber, activities, checkout,
  trackingCommerce, availableLocales): `affiliateId?`, `description?`, `hotelSelection`,
  `allowAccommodationList`, `venue`/`tournamentVenue: ItineraryVenue {id: number, title,
  description, address?, cover, location: Coordinates}`, `accommodation:
  ItineraryAccommodation {id, title, description, rating, totalPrice: Money, image,
  gallery[], startDate, endDate, nights, address, rooms: [{id, name}], coordinates}`,
  `activities: ActivitySelected[]`, `checkout: Checkout {openAmount, total, originalTotal:
  Money, promoCode?, promoCodeDiscount?, status, refId}`, `trackingCommerce
  {transaction_id, currency, value, items[]}`, `bookingCart {id: string|number, totalPrice}`,
  `availableLocales: (it|en|es|fr)[]`.
- `Money {amount: string, currency: string}` (required entrambi). Nota: `amount` è stringa,
  mentre `Product.price` è number.
- `Activity {id, title, description?, areaRefId, source, startDate, endDate,
  possibleStartTime[], categories: [{id, title, price: Money, startDate}], amenityOffers[],
  groupedAmenityOffers[]}`.
- `Accommodation {id, title, description?, rating, guestRating, isRecommended, totalPrice,
  image, gallery[], startDate, endDate, nights, address, roomsConfiguration: [{price,
  isActive, rooms: [{id, name, numPax, description?, count?, numPaxValues[]}]}],
  coordinates, reviewsCount?, source}`.
- `CustomerData {firstName, lastName, email, phone, taxNumber?, marketingOptIn?, address:
  Address {street1, postalCode, city, region, countryCode}}` — DOCS negli esempi usa
  `address: {line1, city, postalCode, country}`, incoerente con `Address` (vedi differences).
- `Pax {refId, firstName?, lastName?, birthDate?, age?, gender?: Female|Male,
  nationalityCountryCode?, marketingOptIn?}`.
- `Booking {id, distributionChannel, productId, affiliateId?, locale, reservationCode,
  firstName, lastName, email, phone?, address?, fiscalCode?, startDate, endDate?, status:
  BookingStatus, currency, totalPrice: number, notes?, itinerary?}`.
- `Trip {reservationCode, title, image?, location, startDate, endDate?, adultCount?,
  childCount?, price: Money, paymentMethod?, status: paid|confirmed|cancelled|completed|refunded}`.
- `CancellationPolicy {name, tourOperator, minimumFee, processingFee: Money,
  processingFeeUnit: "Total", cancellations: [{rangeStart, rangeEnd,
  cancellationPercentage, applicableTo[]}]}`.
