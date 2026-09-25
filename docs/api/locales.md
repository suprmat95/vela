# GET /v1/locales — verificato

Locale supportati; usare `code` come valore del parametro `locale`.

| | |
|---|---|
| Auth | Bearer |
| Parametri | nessuno. Nessuna paginazione. |
| Errori OAS | 401 |
| Item osservati | **4** |

Campi (schema `Locale`):

| Campo | Tipo | OSS |
|---|---|---|
| `code` | string, ISO 639-1 | `en`, `es`, `fr`, `it` |
| `name` | string | `English`, `Español`, `Français`, `Italiano` |

```json
{"data": [
  {"code": "en", "name": "English"},
  {"code": "es", "name": "Español"},
  {"code": "fr", "name": "Français"},
  {"code": "it", "name": "Italiano"}
]}
```

Note: l'enum `locale` delle rotte checkout in OAS è `["it","en","es","fr"]`, coerente.
Un `locale` non in lista (`xx`) sulle liste dà 200 con `data: []`, non 400.
