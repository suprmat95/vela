# Articles

## GET /v1/articles — verificato

Parametri: `limit` (1..100, default 25), `cursor`, `channelIds` (OAS: ignorato), `brand`,
`locale`. Errori OAS: 400, 401, 403, 429, 502.

**Conteggio (default): 28 articoli**, 1 pagina di risultati, id unici 28, id da `1` a
`112`. `tagIds` non vuoto in 24 articoli (es. `["11"]`, `["7"]`); non esiste una rotta per
risolvere i tag.

## GET /v1/articles/{id} — verificato

Path `id`; query `brand`, `locale`. Errori OAS: 400, 401, 403, 404, 502. Stessi 7 campi
della lista.

Campi (schema `Article`, OSS coerente):

| Campo | Tipo | Nullable | OSS |
|---|---|---|---|
| `id` | string | no | `"1"` |
| `title` | string | no | |
| `slug` | string | no | |
| `publishedAt` | date-time | sì | valorizzato |
| `description` | string | sì | valorizzato in tutti |
| `coverUrl` | string URL | sì | valorizzato in tutti |
| `tagIds` | string[] | no | `[]` o id come stringhe |

```json
{"data": {"id": "1", "title": "Train in the Footsteps of Greatness",
  "slug": "train-in-the-footsteps-of-greatness", "publishedAt": "2025-05-08T21:22:57.623Z",
  "description": "This summer, step into the world of high...", 
  "coverUrl": "https://assets.weebora.com/images/large_...", "tagIds": []}}
```
