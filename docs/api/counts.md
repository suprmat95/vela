# Conteggio item e chiamate usate

Data: 2026-09-25, produzione `https://api.hofj.com`, client `test-dev-2`, parametri di
default (nessun `brand`/`locale`/`channelIds` → canale `1` Weebora, locale `en`),
`limit=100`.

| Endpoint | Item | Pagine | Ultimo `nextCursor` | Note |
|---|---|---|---|---|
| `/v1/distribution-channels` | **3** | – | – | nessuna paginazione |
| `/v1/locales` | **4** | – | – | nessuna paginazione |
| `/v1/products` | **123** | 2 (100 + 23) | `null` | 92 non archiviati e prenotabili, 31 archiviati senza disponibilità |
| `/v1/categories` | **3** | 1 | `null` | |
| `/v1/destinations` | **103** | 2 (100 + 3) | `null` | |
| `/v1/venues` | **184** | 2 (100 + 84) | `null` | |
| `/v1/pages` | **32** | 1 | `null` | |
| `/v1/articles` | **28** | 1 | `null` | |

Gli altri canali (`2` Terrarossa, `3` House of Journey) hanno un catalogo proprio non
incluso in questi numeri: `channelIds=3` su products e categories restituisce item diversi
con altre pagine (non contati, per scelta).

## Chiamate eseguite

| Fase | Richieste autenticate | Non autenticate |
|---|---|---|
| Fase 1 (fisse: quota ×2, config ×2, prime pagine ×6, dettagli ×6, extended, tripcode, providerid, casi limite ×6) | 25 | `/health` ×1 |
| Fase 2 (paginazione: quota ×1, pagine ×3) | 4 | – |
| Verifica finale (`/v1/quota`, sync + chiamata esplicita) | 2 | – |
| **Totale** | **31** | 1 (+ `openapi.json` via curl) |

Massimo per finestra di 60 s: 25 (limite 120, cap interno 90). Nessun 429.
Script: `scripts/api_explore.py` (test in `tests/test_api_explore.py`). Le risposte
complete sono state salvate fuori dal repository.
