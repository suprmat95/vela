# GET /v1/distribution-channels — verificato

Elenco dei canali di distribuzione (brand). Serve a risolvere il parametro `brand`
(`name` o `domainUrl`) sulle rotte prodotto e contenuto.

| | |
|---|---|
| Auth | Bearer |
| Parametri | nessuno (OAS). Nessuna paginazione: la risposta non ha `meta`. |
| Errori OAS | 401, 403, 502 |
| Item osservati | **3** |

Campi di ogni elemento di `data` (schema `DistributionChannel`):

| Campo | Tipo | Nullable OAS | OSS |
|---|---|---|---|
| `id` | string | no | `"3"`, `"2"`, `"1"` |
| `name` | string | no | `House of Journey`, `Terrarossa`, `Weebora` |
| `domainUrl` | string | no | `booking.hofj.com`, `terrarossa.com`, `weebora.com` |

Risposta completa osservata (ordinata per `id` decrescente):

```json
{"data": [
  {"id": "3", "name": "House of Journey", "domainUrl": "booking.hofj.com"},
  {"id": "2", "name": "Terrarossa",       "domainUrl": "terrarossa.com"},
  {"id": "1", "name": "Weebora",          "domainUrl": "weebora.com"}
]}
```

Note:
- Il canale di default in produzione (senza `brand`) è `1` / `weebora.com` (OSS: tutti gli
  item delle liste di default hanno `channelId: "1"`).
- DOCS (Staging) elenca per staging `staging.weebora.com`, `staging.tennis.weebora.com`,
  `staging.hofj.com`: in produzione il canale "tennis" non esiste e `staging.hofj.com`
  corrisponde a `booking.hofj.com`.
