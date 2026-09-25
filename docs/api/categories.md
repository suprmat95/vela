# Categories

## GET /v1/categories — verificato

| Nome | Tipo | Default | Note |
|---|---|---|---|
| `limit` | integer 1..100 | 25 | |
| `cursor` | string | – | |
| `channelIds` | string | – | OAS: "Categories only" (unico caso in cui è dichiarato attivo). OSS: `channelIds=3` → categoria `26` con `channelId: "3"` e `nextCursor` presente anche con `limit=1` |
| `brand`, `locale` | string | server | |

Errori OAS: 400, 401, 403, 429, 502.

**Conteggio (default): 3 categorie**, 1 pagina, `nextCursor: null`. Id `1`, `2`, `3`,
tutte `channelId: "1"`, `locale: "en"`. Altre categorie esistono su altri canali (id 26
su canale 3) e sono referenziate dai prodotti (`categoryId` 26 e 14) pur non comparendo
nella lista di default.

## GET /v1/categories/{id} — verificato

Path `id` (string, obbligatorio); query `brand`, `locale`. Errori OAS: 400, 401, 403,
404, 502. La risposta ha gli stessi 8 campi dell'item di lista.

Campi (schema `Category`, OSS coerente):

| Campo | Tipo | Nullable | OSS |
|---|---|---|---|
| `id` | string | no | `"1"` |
| `name` | string | no | `Academies` |
| `slug` | string | no | `academies` |
| `channelId` | string | sì | `"1"` |
| `createdAt`, `updatedAt` | date-time | no | |
| `publishedAt` | date-time | sì | valorizzato |
| `locale` | string | sì | `en` |

```json
{"data": {"id": "1", "name": "Academies", "slug": "academies", "channelId": "1",
  "createdAt": "2024-04-26T14:28:07.814Z", "updatedAt": "2026-07-02T10:30:43.630Z",
  "publishedAt": "2024-05-03T13:07:54.680Z", "locale": "en"}}
```
