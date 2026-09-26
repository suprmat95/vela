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

Comportamento osservato della finestra (2 osservazioni il 2026-09-25, una sonda il 2026-09-26):

- La finestra parte alla **prima richiesta autenticata** e dura 60 s
  (`windowStartedAt` = istante della prima chiamata, non un minuto di orologio).
- Dopo `windowEndsAt` la prima richiesta successiva apre una nuova finestra
  (seconda sessione: `windowStartedAt 10:28:40.536Z`, `usedInWindow 1`).
- OAS descrive la finestra come "rolling 60s window" (e il brief "It is a rolling window");
  quanto osservato è una **finestra fissa di 60 s ancorata alla prima richiesta dopo la
  scadenza** della precedente, verificata anche a cavallo della scadenza dalla sonda del
  2026-09-26 (sotto): **non scorrevole** e **non a griglia fissa** di 60 s. **[misurato]**
- Nessun header `Retry-After` o `X-RateLimit-*` nelle risposte 200. DOCS parla di un campo
  `retryAfterSeconds` nel body del 429: **non verificato** (nessun 429 generato).

### Sonda della finestra, 2026-09-26 [misurato]

`scripts/quota_probe.py`, eseguito dall'utente il 2026-09-26 su `staging.api.hofj.com`: 6
chiamate a `GET /v1/quota`, nessun'altra chiamata.

Procedura: `step0` legge la finestra corrente; lo script attende che scada; `A_fresh` apre una
finestra nuova all'istante S; tre chiamate a S + 50 s (`B_0`..`B_2`); una chiamata a S + 63 s
(`Z`).

Output integrale:

```
host: staging.api.hofj.com
step0    local=862.1 used=1 start=11:41:03.039 end=11:42:03.039 hdr={}
A_fresh  local=926.0 used=1 start=11:42:06.769 end=11:43:06.769 hdr={}
B_0@50   local=976.8 used=2 start=11:42:06.769 end=11:43:06.769 hdr={}
B_1@50   local=977.6 used=3 start=11:42:06.769 end=11:43:06.769 hdr={}
B_2@50   local=978.3 used=4 start=11:42:06.769 end=11:43:06.769 hdr={}
Z@63     local=989.8 used=1 start=11:43:10.532 end=11:44:10.532 hdr={}
```

Lettura:

- `Z` ha `used=1`: le tre chiamate di 13 s prima non contano più. Con una finestra
  scorrevole `Z` avrebbe visto `used=5` → **non è scorrevole**.
- La finestra di `Z` parte alle 11:43:10.532, cioè all'istante di `Z`, non alle 11:43:06.769
  (fine della precedente) → **non è a griglia fissa di 60 s**.
- Quindi: finestra fissa di 60 s, ancorata alla prima chiamata dopo la scadenza della
  precedente. Conferma le osservazioni del 2026-09-25.
- Nessun header di rate limit (`hdr={}`) nemmeno nelle risposte 200.
- Resta **non verificato** il campo `retryAfterSeconds` nel corpo del 429 (nessun 429
  generato).

Conseguenza per Vela: fino a M18 il contatore di `vela/domain/quota.py` faceva ripartire la
finestra su una griglia di 60 s e poteva derivare rispetto a HofJ. Da M18 le chiamate escono da
un token bucket a ritmo costante (B + 60·r = 108), sicuro con qualunque regola della finestra;
vedi `docs/decisions.md`, "2026-09-26 — Twist, seconda lettura" e "2026-09-26 — M18".

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
