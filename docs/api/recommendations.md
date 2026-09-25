# GET /v1/recommendations/* — NON verificate, assenti dall'OpenAPI

Descritte solo in DOCS (pagine Introduction, Authentication, Integrations → curl e
Recommendations). Non compaiono in `openapi.json`. Non chiamate: non è noto se il client
`test-dev-2` abbia `recommendations` in `allowedEntities`, e l'esplorazione era limitata al
contratto OAS.

Requisiti (DOCS): `recommendations` in `allowedEntities`; il `brand` deve risolvere a un
canale presente in `allowedChannelIds`. Stessa autenticazione Bearer HoJ; il BFF chiama il
recommender server-side con un proprio segreto.

Parametri comuni:

| Parametro | Obbligatorio | Descrizione |
|---|---|---|
| `brand` | sì, salvo default server | nome o dominio canale |
| `locale` | sì, salvo default server | `it`, `en`, `es`, `fr` |
| `top_n` | no | numero massimo di prodotti (limiti per endpoint) |
| `slim` | no | `true` → item leggeri |

Rotte citate negli esempi:

| Rotta | Parametri specifici |
|---|---|
| `GET /v1/recommendations/product` | `product_id` (es. 1127) |
| `GET /v1/recommendations/search` | `keyword` (es. `padel`), `price_max` (es. 500) |

Risposta (DOCS):

```json
{
  "data": { "locale": "it", "products": [] },
  "meta": { "brand": "weebora.com", "channelId": 1, "cacheLoadedAt": "2026-04-24T03:00:00+00:00" }
}
```

Le chiavi del recommender sono normalizzate in camelCase; `meta.channelId` è un numero
(nelle altre rotte gli id sono stringhe).
