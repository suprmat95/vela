# House of Journeys Distribution API — documentazione osservata

Trascrizione degli endpoint della **House of Journeys (HoJ) Distribution API**, ricostruita
il 2026-09-25 da tre fonti:

| Fonte | Sigla | Dove |
|---|---|---|
| Sito di documentazione | **DOCS** | https://docs.api.hofj.com |
| Contratto OpenAPI 3.1 (`info.version` 1.0.0) | **OAS** | https://api.hofj.com/v1/openapi.json |
| Chiamate reali GET in produzione con il client `test-dev-2` | **OSS** (osservato) | 31 richieste autenticate, vedi [counts.md](counts.md) |

Le note sulle discrepanze tra le tre fonti stanno in [differences.md](differences.md).
Il conteggio degli item in [counts.md](counts.md). Solo metodi GET sono stati eseguiti;
nessuna chiamata POST/PUT/PATCH/DELETE.

## Indice

| File | Endpoint | Stato |
|---|---|---|
| [quota-health.md](quota-health.md) | `GET /health`, `GET /v1/openapi.json`, `GET /v1/quota` | verificati |
| [distribution-channels.md](distribution-channels.md) | `GET /v1/distribution-channels` | verificato |
| [locales.md](locales.md) | `GET /v1/locales` | verificato |
| [products.md](products.md) | `GET /v1/products`, `/v1/products/{id}`, `/v1/products/tripcode/{tripCode}`, `/v1/products/providerid/{providerID}` | verificati |
| [categories.md](categories.md) | `GET /v1/categories`, `/v1/categories/{id}` | verificati |
| [destinations.md](destinations.md) | `GET /v1/destinations`, `/v1/destinations/{id}` | verificati |
| [venues.md](venues.md) | `GET /v1/venues`, `/v1/venues/{id}` | verificati |
| [pages.md](pages.md) | `GET /v1/pages`, `/v1/pages/{id}` | verificati |
| [articles.md](articles.md) | `GET /v1/articles`, `/v1/articles/{id}` | verificati |
| [internal-checkout.md](internal-checkout.md) | itinerari, booking, trips, payment, oauth (GET interne + tutte le mutazioni) | **non verificati**, solo OAS/DOCS |
| [recommendations.md](recommendations.md) | `GET /v1/recommendations/*` | **non verificati**, solo DOCS (assenti in OAS) |

## Base URL e ambienti

| Ambiente | URL | Fonte |
|---|---|---|
| Produzione | `https://api.hofj.com` | OAS, DOCS, OSS |
| Sandbox | `https://sandbox.api.hofj.com` | solo OAS (`servers[1]`) |
| Staging | `https://staging.api.hofj.com` | solo DOCS (pagina Staging, esempi curl) |
| Locale | `http://localhost:8080` | OAS, DOCS |

Le risposte in produzione arrivano da Google Frontend (header `server: Google Frontend`,
`x-cloud-trace-context`). Nessun header di rate limit (`X-RateLimit-*`, `Retry-After`) è
presente nelle risposte 200 osservate.

## Autenticazione

- Header `Authorization: Bearer <api_key>` oppure `Authorization: Bearer <access_token>`
  ottenuto da `POST /v1/oauth/token` (client credentials, form-urlencoded). Fonte: OAS
  `securitySchemes.bearerAuth`, DOCS Authentication.
- Endpoint pubblici senza auth: `GET /health`, `GET /v1/openapi.json`, `POST /v1/oauth/token`.
  OSS: `/health` e `/v1/openapi.json` rispondono 200 senza header e non consumano quota.
- Ogni client ha nel registry `allowedEntities` (products, categories, destinations,
  recommendations, itineraries, bookings, trips, …) e `allowedChannelIds` (`*` per i
  client interni). Entità non permessa → 403. Fonte: DOCS.
- Il client `test-dev-2` è **interno**: `extended=true`, `/tripcode/`, `/providerid/`
  rispondono 200 (OAS: "External clients receive 403").

## Envelope e convenzioni

- Successo: `{ "data": ... }`; le liste aggiungono `"meta": { "nextCursor": string|null }`.
  Le rotte checkout usano `"meta": { "now": <epoch ms> }` (DOCS, non verificato).
- Tutti gli `id` sono **stringhe** anche quando numerici (`"12"`). Le date sono ISO-8601
  UTC con millisecondi (`2026-03-09T09:26:05.776Z`); `minDate`/`maxDate`/`startDate`
  sono `YYYY-MM-DD`.
- Errori: RFC 7807. OSS: body `{type, title, status, detail, instance}` con
  `content-type: application/json; charset=utf-8` (non `application/problem+json`, vedi
  differences). `type` è `https://api.hofj.com/problems/<slug>` (`bad-request`,
  `upstream-error`); `instance` è un UUID.

## Paginazione (liste)

| Aspetto | Valore | Fonte |
|---|---|---|
| Parametri | `limit` (1..100, default 25), `cursor` | OAS, OSS |
| `limit` > 100 | 400 Bad Request con `detail` = array di errori di validazione (formato zod) | OSS |
| Cursore | `meta.nextCursor`, `null` sull'ultima pagina | OAS, OSS |
| Formato cursore | base64url di `{"p":<pagina>}` (es. `eyJwIjoyfQ` = `{"p":2}`): è un numero di pagina, non un token opaco | OSS |
| Ordinamento | per `id` crescente | OSS |

## Parametri comuni `brand`, `locale`, `channelIds`

- `brand`: nome o `domainUrl` di un distribution channel (`Weebora`, `weebora.com`,
  `booking.hofj.com`, `terrarossa.com`). Se omesso il server usa
  `CONTENT_DEFAULT_CHANNEL_DOMAIN`. OSS: senza `brand` tutti i prodotti/categorie
  restituiti hanno `channelId: "1"` (Weebora), quindi il default in produzione è
  `weebora.com`. `brand` sconosciuto → 400 con messaggio esplicito.
- `locale`: codice da `GET /v1/locales` (`en`, `es`, `fr`, `it`). OSS: default `en`;
  un valore non valido (`xx`) **non** dà errore ma una lista vuota.
- `channelIds`: lista separata da virgola, intersecata con l'allowlist del client.
  OSS: `channelIds=3` su products e categories restituisce item con `channelId: "3"`
  (House of Journey) che **non compaiono** nella lista di default. OAS dichiara il
  parametro anche su destinations/venues/pages/articles ma con nota "ignored".

## Quota (rate limit)

Vedi [quota-health.md](quota-health.md). In sintesi: 120 richieste/minuto per client,
finestra di 60 s ancorata alla prima richiesta, `/v1/quota` stesso consuma 1 richiesta.
Nessuna richiesta 429 è stata generata durante l'esplorazione.
