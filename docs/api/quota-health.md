# Health, OpenAPI, Quota

## GET /health — verificato

| | |
|---|---|
| Auth | nessuna (OAS: `security` assente; OSS: 200 senza header) |
| Quota | non consumata (OSS: `usedInWindow` non incrementato) |
| Parametri | nessuno |
| Risposta 200 | `{ "status": "ok" }` — `status` enum `["ok"]` |

## GET /v1/openapi.json — verificato

| | |
|---|---|
| Auth | nessuna |
| Parametri | nessuno |
| Risposta 200 | documento OpenAPI 3.1.0, `info.title` "House of Journeys — Distribution API", `info.version` 1.0.0, 35 path, 45 operazioni, 59 schemi. Dimensione 79 323 byte. |

## GET /v1/quota — verificato

| | |
|---|---|
| Auth | Bearer |
| Quota | **consuma 1 richiesta** (OAS: "counts toward the same rate limit"; OSS confermato: due chiamate consecutive → `usedInWindow` 1 poi 2) |
| Parametri | nessuno |
| Errori OAS | 401, 429 |

Campi di `data` (OAS `required`: `clientId`, `backend`):

| Campo | Tipo | OSS | Note |
|---|---|---|---|
| `clientId` | string | `"test-dev-2"` | |
| `backend` | enum `firestore` \| `process_local` | `"firestore"` | con `process_local` i contatori sono per istanza |
| `limitPerMinute` | integer | `120` | |
| `usedInWindow` | integer | `1`, `2` | include la chiamata corrente |
| `remainingInWindow` | integer | `119`, `118` | `limitPerMinute - usedInWindow` |
| `windowStartedAt` | date-time | `2026-09-25T10:26:41.990Z` | |
| `windowEndsAt` | date-time | `2026-09-25T10:27:41.990Z` | `windowStartedAt + 60 s` |

Comportamento osservato della finestra (2 osservazioni):

- La finestra parte alla **prima richiesta autenticata** e dura 60 s
  (`windowStartedAt` = istante della prima chiamata, non un minuto di orologio).
- Dopo `windowEndsAt` la prima richiesta successiva apre una nuova finestra
  (seconda sessione: `windowStartedAt 10:28:40.536Z`, `usedInWindow 1`).
- OAS descrive la finestra come "rolling 60s window"; quanto osservato è coerente con una
  finestra fissa riavviata alla prima richiesta dopo la scadenza. Non è stato verificato
  il comportamento a cavallo della scadenza con traffico continuo.
- Nessun header `Retry-After` o `X-RateLimit-*` nelle risposte 200. DOCS parla di un campo
  `retryAfterSeconds` nel body del 429: **non verificato** (nessun 429 generato).

Esempio:

```json
{
  "data": {
    "clientId": "test-dev-2",
    "limitPerMinute": 120,
    "usedInWindow": 1,
    "remainingInWindow": 119,
    "windowStartedAt": "2026-09-25T10:26:41.990Z",
    "windowEndsAt": "2026-09-25T10:27:41.990Z",
    "backend": "firestore"
  }
}
```
