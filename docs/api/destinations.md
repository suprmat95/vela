# Destinations

## GET /v1/destinations — verificato

Parametri: `limit` (1..100, default 25), `cursor`, `channelIds` (OAS: ignorato per
destinations), `brand`, `locale`. Errori OAS: 400, 401, 403, 429, 502.

**Conteggio (default): 103 destinazioni** in 2 pagine (100 + 3), id unici 103, id da `1`
a `613`, ordinate per id crescente.

Distribuzione `country` (top): IT 27, ES 24, GR 5, US 4, FR 4, EG 3, DE 3, MA 2.
`shortDescription` null in 24, `geohierarchy` null in 1.

## GET /v1/destinations/{id} — verificato

Path `id`; query `brand`, `locale`. Errori OAS: 400, 401, 403, 404, 502. Stessi 8 campi
della lista (OSS: nessun campo aggiuntivo nel dettaglio).

Campi (schema `Destination`, OSS coerente):

| Campo | Tipo | Nullable | OSS |
|---|---|---|---|
| `id` | string | no | `"410"` |
| `title` | string | no | `New York` |
| `slug` | string | no | `new-york` |
| `country` | string ISO 3166-1 alpha-2 | sì | `US`, sempre valorizzato |
| `shortDescription` | string | sì | |
| `geohierarchy` | string | sì | `US_5128581` (country + id GeoNames) |
| `tileEffectColor` | string | sì | `black`, `darkblue` |
| `coverUrl` | string URL | sì | `https://assets.weebora.com/images/large_...` |

```json
{"data": {"id": "410", "title": "New York", "slug": "new-york", "country": "US",
  "shortDescription": "New York: sport, energy and iconic city lifestyle",
  "geohierarchy": "US_5128581", "tileEffectColor": "black",
  "coverUrl": "https://assets.weebora.com/images/large_..."}}
```
