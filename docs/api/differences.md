# Differenze tra sito docs (DOCS), OpenAPI (OAS) e comportamento osservato (OSS)

Rilevate il 2026-09-25 su `https://api.hofj.com` con il client interno `test-dev-2`.
Gravità: **alta** = cambia il modo di integrare; media = da gestire nel codice; bassa =
imprecisione documentale.

## OAS vs OSS (contratto vs realtà)

| # | Gravità | Dove | OAS dice | Osservato |
|---|---|---|---|---|
| 1 | **alta** | `GET /v1/products` | `data: Product[]`, 14 campi anagrafici, senza prezzo né disponibilità | Ogni item ha **32 campi** (`ProductInternal`): `price`, `currency`, `availabilities`, `tripCode`, `providerID`, `minDate`/`maxDate`, ecc. Probabile effetto del profilo interno del client; un client esterno potrebbe vedere i 14 campi. Non fare affidamento sul contratto per decidere se serve il dettaglio. |
| 2 | **alta** | `GET /v1/products/{id}` con id inesistente | 404 dichiarato | **502** `https://api.hofj.com/problems/upstream-error`, `detail: "Upstream get failed: 500"`. Un id sbagliato è indistinguibile da un guasto upstream. |
| 3 | **alta** | Cataloghi per canale | `brand` opzionale "if omitted, CONTENT_DEFAULT_CHANNEL_DOMAIN must be set" | Senza `brand` si vede **solo il canale 1 (Weebora)**: 123 prodotti, 3 categorie. Con `channelIds=3` compaiono prodotti e categorie (id 431, 26) di House of Journey non presenti altrove. I prodotti di default referenziano `categoryId` 26 e 14 e i venue `categoryId` 13 e 15 che **non esistono** in `/v1/categories` di default: i riferimenti incrociati non sono chiusi dentro un canale. |
| 4 | media | Errori | `Problem` RFC 7807; DOCS: `application/problem+json` | Body RFC 7807 corretto ma `content-type: application/json; charset=utf-8`. Non filtrare sul media type. |
| 5 | media | `limit` fuori range | 400 | 400 confermato, ma `detail` è una **stringa contenente un array JSON** di errori zod (`code: too_big`, `maximum: 100`, `path: ["limit"]`), da parsare a parte. |
| 6 | media | `locale` non valido | nessuna indicazione | 200 con `data: []` invece di 400: un refuso nel locale svuota silenziosamente il catalogo. |
| 7 | media | `cursor` | string opaca | base64url di `{"p":2}`: è un numero di pagina. Funziona come opaco ma non è stabile se il set cambia tra due pagine. |
| 8 | media | `/v1/quota` | "rolling 60s window" | Finestra **fissa di 60 s ancorata alla prima richiesta** (`windowStartedAt` = istante della prima chiamata; alla scadenza la finestra riparte con la richiesta successiva). Verificato anche a cavallo della scadenza il 2026-09-26 (`scripts/quota_probe.py`, [quota-health.md](quota-health.md)): non scorrevole, non a griglia. Nessun header `Retry-After`/`X-RateLimit-*`. |
| 9 | media | `Venue.rating`, `ProductVenueSummary.rating` | number nullable | Solo `0` (158 su 184) o `null` (26): il campo non è informativo. |
| 10 | media | `Product.price` vs `Money.amount` | `price: number`; `Money.amount: string` | Prezzi interi in catalogo (`340`), stringhe nel checkout: due rappresentazioni del denaro nello stesso contratto. |
| 11 | media | `ProductTravelProgram.id` | string | Nel DTO `"733"` (stringa), in `rawAttributes.travelProgram.id` `733` (intero). |
| 12 | bassa | `channelIds` | dichiarato su tutte e 6 le liste, con nota "Categories only … Ignored for destinations, venues, pages, articles" | Funziona su products (non menzionato nella nota) e categories; su products la nota è quindi incompleta. Non verificato l'effetto sulle altre quattro. |
| 13 | bassa | `Page.type` | string senza enum | Valori osservati: `generic`, `index`, `collections`. |
| 14 | bassa | `ProductDetail.destination.coverUrl` | URL | Sul prodotto 12 punta a `assets.staging.weebora.com` in produzione: asset di staging che trapelano. |
| 15 | bassa | `Problem.detail`, `instance` | string | `instance` è un UUID di correlazione, utile per il supporto. |
| 16 | bassa | `ProductInternal.availabilities[].serviceLevels` | `array<any>` | Sempre `[]` su 448 finestre osservate. |
| 17 | bassa | `POST /v1/oauth/token`, campo `x-default: dev-internal-api-key` in `securitySchemes` | – | Il contratto pubblico contiene una chiave di sviluppo di default (DOCS: "do not use in production"). |

## DOCS vs OAS (sito vs contratto)

| # | Gravità | Argomento | DOCS | OAS |
|---|---|---|---|---|
| 18 | **alta** | `/v1/recommendations/*` | Documentate (`/product`, `/search`, parametri `top_n`, `slim`, `product_id`, `keyword`, `price_max`) | **Assenti** dal contratto. Vedi [recommendations.md](recommendations.md). |
| 19 | **alta** | Ambienti | Staging `https://staging.api.hofj.com` | Server `Sandbox` `https://sandbox.api.hofj.com`; staging non compare. Il playground della pagina Health mostra i server OAS (production, sandbox, localhost). Non verificato quale dei due host risponda. |
| 20 | media | `CustomerData.address` | Esempi curl con `{line1, city, postalCode, country}` | Schema `Address` `{street1, postalCode, city, region, countryCode}`, tutti required. Gli esempi DOCS non passerebbero la validazione del contratto. |
| 21 | media | Envelope `meta.now` | Ogni risposta checkout ha `meta: {now}` | `meta` dichiarato come `object` vuoto sulle rotte checkout; nelle liste è `{nextCursor}`. |
| 22 | media | `/v1/itineraries/{id}/payment` GET | "The brand site does not accept GET (405)… the API translates it to the brand POST" | Dichiarata come GET normale (`refreshItineraryPaymentGet`) con effetto collaterale (crea un payment intent). Non è idempotente pur essendo GET. |
| 23 | bassa | Indice `/llms.txt` | Ogni pagina rimanda a `/llms.txt` "per scoprire tutte le pagine" | Il file risponde **404**. |
| 24 | bassa | `429` | Campo `retryAfterSeconds` nel body (Introduction) | Nessuno schema per il 429 (solo `description`). Non verificato. |
| 25 | bassa | `POST /v1/itineraries` body | `{productId, startDate, adults, rooms, affiliateId?, currency?}` | Schema del body non tra i `components.schemas` elencati (solo `CreateBookingRequest`, `AddActivity`, ecc.). Controllare `requestBody` inline prima di integrare. |
| 26 | bassa | Canali staging | `staging.weebora.com`, `staging.tennis.weebora.com`, `staging.hofj.com` | In produzione: `weebora.com`, `terrarossa.com`, `booking.hofj.com`. Nessun canale "tennis" in produzione. |
| 27 | bassa | Tag `Internal` | DOCS marca come interne tutte le rotte checkout e le lookup `tripcode`/`providerid` | OAS ha un solo tag `Internal` applicato in modo coerente; `extended=true` è descritto solo nel parametro. |

## Osservazioni utili per l'integrazione (non discrepanze)

- 31 prodotti su 123 sono `archived: true` e sono esattamente quelli con
  `availabilities: []`: filtrare su `archived` equivale a filtrare su "ha disponibilità".
  Tutte le 448 finestre di disponibilità hanno `status: "Bookable"`; il brief avverte che
  alcuni prodotti falliscono al carrello, quindi "Bookable" non garantisce l'acquisto.
- `GET /v1/products/{id}` (dettaglio) **non** contiene `tripCode`/`providerID`, che invece
  stanno nella lista e nelle rotte `extended`/`tripcode`/`providerid`.
- `venueId` e `destinationId` sono null in 5 prodotti: il dettaglio di quei prodotti avrà
  `venue`/`destination` non risolti.
- Il dettaglio di categories, destinations, venues, pages, articles restituisce **gli
  stessi campi della lista**: la chiamata per id non aggiunge informazioni.
- `tagIds` degli articoli non ha una rotta di risoluzione.
- Costo quota: la sola lettura completa del catalogo di default costa 12 richieste (2+1+2+2+1+1
  pagine, più config). Un ciclo `/v1/quota` prima e dopo ne aggiunge 2.

## `/v1/itineraries/{id}/accommodations` (sonda M22-a, 2026-09-27)

Staging, brand `staging.weebora.com`, 11 chiamate. Dettagli in [accommodations.md](accommodations.md).

| # | Gravità | Dove | OAS dice | Osservato |
|---|---|---|---|---|
| 28 | **alta** | `GET .../accommodations` su un prodotto con `hotelSelection: true` e `allowAccommodationList: false` (124) | Lista degli hotel dell'itinerario | 200 con `elements: []`: `hotelSelection` da solo non dà alternative. L'unica lista non vuota viene da un prodotto con `allowAccommodationList: true` (25) |
| 29 | **alta** | `Accommodation.roomsConfiguration` | Configurazioni con `rooms[].id` da passare al `PATCH` come `roomIds` | Sull'unico hotel restituito, `[]`: nessun `roomId` da mandare, `PATCH` non eseguibile |
| 30 | **alta** | `Itinerary.accommodation` su un prodotto con `allowAccommodationList: true` (25) | Oggetto `ItineraryAccommodation` richiesto | Presente ma con tutti i campi `null`: nessun hotel preselezionato, eppure `checkout.openAmount` 1798 €. Un acquisto di oggi su quel prodotto parte senza hotel |
| 31 | media | `GET .../accommodations` con `hotelSelection: false` (28) | Nessuna indicazione | 200 con lista vuota, non un 4xx: "hotel fisso" e "nessuna alternativa" sono indistinguibili dalla risposta |
| 32 | media | Filtri di `GET .../accommodations` | Query `stars`, `rating`, `price`, `distance` | `aggregate.filters` usa gli id `starsRating`, `guestRating`, `price`, `distance`: i nomi dei filtri non coincidono con i parametri dell'OAS (non provati) |
| 33 | bassa | `Itinerary` | Chiavi dello schema OAS | Chiavi in più: `removableAccommodation`, `groupTourId`, `players`, `groupTourAvailability`, `travelProgram`, `travelDetail`, `paymentOptionsConfiguration`, `withoutNavigations`, `adultCount`, `childCount`, `customer`, `passengers`, `rooms`; `accommodation.componentId` |
| 34 | bassa | `Accommodation.totalPrice` | Prezzo dell'hotel | `0.00` sull'hotel incluso (124), `1.00` sull'unico hotel della lista (25): valori segnaposto di staging, non un prezzo |
| 35 | bassa | `Accommodation.guestRating` | Voto | `0` con `reviewsCount: null` e filtro `guestRating` con il solo valore `"0"`: su staging nessuna recensione |
