# Pages

## GET /v1/pages — verificato

Parametri: `limit` (1..100, default 25), `cursor`, `channelIds` (OAS: ignorato), `brand`,
`locale`. Errori OAS: 400, 401, 403, 429, 502.

**Conteggio (default): 32 pagine**, 1 pagina di risultati, id unici 32, id da `1` a `180`.

Distribuzioni: `type` `generic`: 22, `index`: 9, `collections`: 1; `categoryId` null 26,
`1`/`2`/`3` 2 ciascuna; `coverUrl` null in 13.

## GET /v1/pages/{id} — verificato

Path `id`; query `brand`, `locale`. Errori OAS: 400, 401, 403, 404, 502. Stessi 6 campi
della lista.

Campi (schema `Page`, OSS coerente):

| Campo | Tipo | Nullable | OSS |
|---|---|---|---|
| `id` | string | no | `"1"` |
| `title` | string | no | `Home` |
| `slug` | string | no | `home` |
| `type` | string | sì | `index` \| `generic` \| `collections` (enum non dichiarato in OAS) |
| `categoryId` | string | sì | null |
| `coverUrl` | string URL | sì | |

```json
{"data": {"id": "1", "title": "Home", "slug": "home", "type": "index", "categoryId": null,
  "coverUrl": "https://assets.weebora.com/images/large_brandline_e39b5bd392.png"}}
```
