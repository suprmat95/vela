# Products

Quattro rotte GET. Tutte verificate con il client interno `test-dev-2`.

| Rotta | operationId | Schema OAS della risposta | Campi OSS |
|---|---|---|---|
| `GET /v1/products` | `listProducts` | `data: Product[]` (14 campi) | **32 campi** = `ProductInternal` |
| `GET /v1/products/{id}` | `getProduct` | `data: ProductDetail` | 32 campi, coerente |
| `GET /v1/products/{id}?extended=true` | `getProduct` | `data: ProductExtended` | 39 campi, coerente |
| `GET /v1/products/tripcode/{tripCode}` | `getProductByTripCode` (tag Internal) | `data: ProductInternal` | 32 campi, coerente |
| `GET /v1/products/providerid/{providerID}` | `getProductByProviderID` (tag Internal) | `data: ProductInternal` | 32 campi, identico a tripcode |

## GET /v1/products — lista

Parametri in ingresso (tutti query, tutti opzionali):

| Nome | Tipo | Default | Note | Fonte |
|---|---|---|---|---|
| `limit` | integer 1..100 | 25 | 101 → 400 `too_big` | OAS, OSS |
| `cursor` | string | – | da `meta.nextCursor`; base64url di `{"p":N}` | OAS, OSS |
| `channelIds` | string | – | id canale separati da virgola, intersecati con l'allowlist | OAS, OSS |
| `brand` | string | `weebora.com` (server) | nome o dominio del canale; sconosciuto → 400 | OAS, OSS |
| `locale` | string | `en` (server) | codice da `/v1/locales`; non valido → lista vuota | OAS, OSS |

Risposta: `{ data: [...], meta: { nextCursor } }`. Errori OAS: 400, 401, 403, 429, 502.

**Conteggio (parametri di default, canale Weebora, locale en): 123 prodotti** in 2 pagine
(100 + 23), id unici 123, id da `12` a `1088`, ordinati per id crescente.

Distribuzioni osservate sui 123 item:

| Campo | Valori |
|---|---|
| `archived` | false 92, true 31 |
| `availabilities` | 92 prodotti con almeno una finestra (tutte `status: "Bookable"`, 448 finestre in totale); 31 prodotti con array vuoto = esattamente gli archiviati |
| `categoryId` | `2`: 60, `1`: 39, `3`: 19, `26`: 4, `14`: 1 (gli id 26 e 14 non esistono tra le 3 categorie della lista di default) |
| `channelId` | `1`: 123 |
| `currency` | `EUR`: 123 |
| `price` | min 47, max 3639, mai 0 o null |
| `defaultDurationInDays` | 4: 45, 5: 22, 3: 21, 2: 16, 6: 7, 8: 6, 7: 5, 1: 1 |
| `hotelSelection` | true 69, false 54 |
| `allowAccommodationList` | true 7, false 116 |
| `featured` | true 19 |
| `isSpecialOffer` | false 123 |
| `pageCompositionMode` | `layout`: 123 |
| `videoUrl` | null 123 |
| `tripCode` | null 1 |
| `venueId` / `destinationId` | null 5 / null 5 |
| `minPax` / `maxPax` / `maxPaxPerRoom` | valorizzati in 22 / 2 / 12 prodotti |
| `minDate` .. `maxDate` | da 2026-03-24 a 2027-12-31 |
| `serviceLevels` (dentro availabilities) | sempre `[]` |

Con `channelIds=3` (House of Journey) la lista contiene prodotti diversi (es. id `431`,
`channelId: "3"`) e ha altre pagine: il catalogo degli altri canali **non è incluso** nel
conteggio di 123.

### Campi di un item della lista (OSS = schema `ProductInternal`)

| Campo | Tipo OSS | Nullable OSS | In `Product` (OAS lista) | Note |
|---|---|---|---|---|
| `id` | string | no | sì | numerico come stringa |
| `slug` | string | no | sì | |
| `title` | string | no | sì | |
| `shortDescription` | string | sì (42/123) | sì | |
| `description` | string, markdown | no | sì | |
| `archived` | boolean | no | sì | |
| `channelId` | string | no | sì | |
| `venueId` | string | sì | sì | |
| `categoryId` | string | no | sì | |
| `destinationId` | string | sì | sì | |
| `videoUrl` | null | sempre null | sì | |
| `createdAt`, `updatedAt` | date-time | no | sì | |
| `publishedAt` | date-time | no | sì | |
| `tripCode` | string | sì (1) | **no** | es. `MKT_Sinalunga_220426` |
| `providerID` | string | no | **no** | es. `t0044660` |
| `nezasaSlug` | string | no | **no** | |
| `price` | integer | no | **no** | OAS: number, prezzo base a persona |
| `currency` | string | no | **no** | ISO 4217 |
| `minPax`, `maxPax`, `maxPaxPerRoom` | integer | sì | **no** | |
| `minDate`, `maxDate` | date `YYYY-MM-DD` | no | **no** | |
| `defaultDurationInDays` | integer | no | **no** | notti + 1 |
| `hotelSelection`, `allowAccommodationList`, `isSpecialOffer`, `featured` | boolean | no | **no** | |
| `pageCompositionMode` | string | no | **no** | |
| `availabilities` | array di `{status, startDate, endDate, serviceLevels[]}` | no (può essere `[]`) | **no** | |
| `locale` | string | no | **no** | |

Esempio (troncato a un item):

```json
{"data": [{
  "id": "12", "slug": "toda-sinalunga-3-days-of-full-immersion",
  "title": "TODA Sinalunga - 3 days of full immersion.",
  "shortDescription": "Intense training days in the heart of Tuscany",
  "description": "Enjoy an unforgettable **2-night** stay ...",
  "archived": false, "channelId": "1", "venueId": "194", "categoryId": "1", "destinationId": "17",
  "videoUrl": null,
  "createdAt": "2026-03-09T09:26:05.776Z", "updatedAt": "2026-09-25T09:20:18.757Z", "publishedAt": "2026-03-10T11:54:04.217Z",
  "tripCode": "MKT_Sinalunga_220426", "providerID": "t0044660", "nezasaSlug": "toda-sinalunga-3-dias-de-inmersion-compl...",
  "price": 340, "currency": "EUR", "minPax": 2, "maxPax": null,
  "minDate": "2026-09-25", "maxDate": "2027-01-07", "defaultDurationInDays": 3,
  "hotelSelection": false, "allowAccommodationList": false, "isSpecialOffer": false, "pageCompositionMode": "layout",
  "availabilities": [{"status": "Bookable", "startDate": "2026-09-28", "endDate": "2026-10-01", "serviceLevels": []}],
  "locale": "en", "featured": false, "maxPaxPerRoom": null
}], "meta": {"nextCursor": "eyJwIjoyfQ"}}
```

## GET /v1/products/{id} — dettaglio

| Nome | In | Tipo | Obbligatorio | Note |
|---|---|---|---|---|
| `id` | path | string | sì | id numerico CMS |
| `brand` | query | string | no | come lista |
| `locale` | query | string | no | come lista |
| `extended` | query | boolean | no, default false | solo client interni; esterni → 403 (OAS) |

Errori OAS: 400, 401, 403, 404, 502. **OSS: id inesistente → 502 `upstream-error`
("Upstream get failed: 500"), non 404.**

Campi di `data` (schema `ProductDetail` = `Product` + estensione; OSS 32 campi, coerente):
i 14 campi di `Product` più

| Campo | Tipo | Note OSS |
|---|---|---|
| `price`, `currency`, `minPax`, `maxPax`, `minDate`, `maxDate`, `defaultDurationInDays`, `hotelSelection`, `allowAccommodationList`, `isSpecialOffer`, `pageCompositionMode`, `availabilities`, `locale` | come lista | |
| `category` | `{id, name, slug}` (`ProductCategorySummary`) | |
| `venue` | `{id, title, slug, shortDescription?, rating?, coverUrl?}` (`ProductVenueSummary`) | |
| `destination` | `{id, title, slug, country, shortDescription?, geohierarchy, tileEffectColor, coverUrl}` (`ProductDestinationSummary`) | `coverUrl` puntava a `assets.staging.weebora.com` |
| `image` | `{name, alternativeText?, caption?, width, height, url}` (`ImageAttributes`) | |
| `gallery` | array di `ImageAttributes` + `{source: product\|venue\|accommodation, sourceId?}` | 10 immagini, tutte `source: "venue"` sul prodotto 12 |

Il dettaglio **non** contiene `tripCode`, `providerID`, `nezasaSlug`, `featured`,
`maxPaxPerRoom` (presenti invece nella lista): per averli usare `extended=true` o le rotte
`tripcode`/`providerid`.

## GET /v1/products/{id}?extended=true — dettaglio esteso (interno)

`data` = `ProductDetail` (32 campi) più 7 campi (`ProductExtended`), OSS coerente:

| Campo | Tipo | Note OSS |
|---|---|---|
| `tripCode`, `providerID`, `nezasaSlug`, `featured`, `maxPaxPerRoom` | come lista | |
| `travelProgram` | `{id: string, description: markdown, details: [{id, title, days: [{id, title, description?, events: [{id, time?, text}]}]}]}` | `id` stringa nel DTO, intero (733) in `rawAttributes` |
| `rawAttributes` | oggetto grezzo CMS (populate=*) | 51 chiavi, tra cui `discountAmount`, `discountType`, `group`, `playtomicLevel`, `bookingCutOffDays`, `pagePath`, `playerLevel`, `removableAccommodation`, `whyThisTrip`, `playingHours`, `style[]`, `bestForLevel[]`, `goal[]`, `minPaxTarget`, `acceptsCompanions`, `faqGroup`, `eventAccess`, `ticketCategory`, relazioni `distributionChannel/category/gallery/cover/venue/hotels` nella forma `{data: ...}` |

## GET /v1/products/tripcode/{tripCode} e /v1/products/providerid/{providerID} — interne

| Nome | In | Tipo | Obbligatorio |
|---|---|---|---|
| `tripCode` / `providerID` | path | string | sì (es. `MKT_Sinalunga_220426` / `t0044660`) |
| `brand`, `locale` | query | string | no |

Errori OAS: 401, 403, 404, 502. Risposta `data: ProductInternal` (32 campi): OSS
identica byte per byte tra le due rotte per lo stesso prodotto e identica agli item della
lista. Non include `category`/`venue`/`destination`/`image`/`gallery`.
