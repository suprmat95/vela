# Venues

## GET /v1/venues — verificato

Parametri: `limit` (1..100, default 25), `cursor`, `channelIds` (OAS: ignorato per
venues), `brand`, `locale`. Errori OAS: 400, 401, 403, 429, 502.

**Conteggio (default): 184 sedi** in 2 pagine (100 + 84), id unici 184, id da `1` a
`1028`, ordinate per id crescente.

Distribuzioni: `categoryId` `1`: 69, `2`: 69, `3`: 44, `13`: 1, `15`: 1 (13 e 15 non sono
tra le categorie di default); `rating` `0` in 158, null in 26 (mai un valore > 0);
`shortDescription` null in 24.

## GET /v1/venues/{id} — verificato

Path `id`; query `brand`, `locale`. Errori OAS: 400, 401, 403, 404, 502. Stessi 8 campi
della lista.

Campi (schema `Venue`, OSS coerente):

| Campo | Tipo | Nullable | OSS |
|---|---|---|---|
| `id` | string | no | `"106"` |
| `title` | string | no | `PADEL IN - Kuwait` |
| `slug` | string | no | `padel-in-kuwait` |
| `shortDescription` | string | sì | null |
| `rating` | number | sì | intero 0 o null |
| `categoryId` | string | sì | `"1"`, sempre valorizzato |
| `destinationId` | string | sì | `"46"`, sempre valorizzato |
| `coverUrl` | string URL | sì | sempre valorizzato |

```json
{"data": {"id": "106", "title": "PADEL IN - Kuwait", "slug": "padel-in-kuwait",
  "shortDescription": null, "rating": null, "categoryId": "1", "destinationId": "46",
  "coverUrl": "https://assets.weebora.com/images/large_..."}}
```
