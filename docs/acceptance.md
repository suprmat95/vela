# Vela — criteri di accettazione (spec §10)

Una riga per ogni esecuzione di un criterio. Modalità: `replay` (HofJ e Stripe finti) o `live`.
Esito: `ok`, `parziale` (con il motivo nelle note), `fallito`, `da eseguire`.

| # | Criterio (spec §10) | Data | Modalità | Superficie | Esito | Note |
|---|---|---|---|---|---|---|
| 1 | Flusso da Claude via MCP: proposta singola, "troppo caro" → altra singola più economica, "sì" → link, pagamento, `confirmed` con codice | — | replay | MCP (claude.ai) | da eseguire | M3. In replay il rifiuto non interpreta il motivo (M9): la seconda proposta è diversa ma può essere più cara |
| 1 | idem | — | live | MCP (claude.ai) | da eseguire | M7 |
| 2 | Flusso da agente vocale ElevenLabs, link per testo | — | live | MCP (ElevenLabs) | da eseguire | M12 |
| 3 | Flusso via REST con `curl` e token | — | replay | REST | da eseguire | M4 |
| 3 | idem | 2026-09-25 | live (HofJ staging + Stripe test) | REST | ok | M7, `scripts/rest_flow.py`, frase su Barcellona (vedi registro). Codice `wury5zaxzkec` |
| 3 | idem, con Stripe reale in test (HofJ replay): pagamento `4242…` → `confirmed` | — | replay + Stripe test | REST | da eseguire | Dopo M5 (job di verifica della sessione); guida in `docs/stripe.md` |
| 4 | Prodotto che fallisce al carrello sostituito senza errore visibile | 2026-09-25 | live (HofJ staging) | REST | parziale | M7: fallimento naturale del 867 sostituito dal 14 senza errore visibile (vedi registro); resta da eseguire la prova con la trappola (`rest_flow.py --trap`) |
| 5 | Suite verde e load test in replay, quota HofJ invariata | — | replay | REST | da eseguire | M13 |
| 6 | Nessuna risposta con più di un prodotto, su nessuna superficie | — | replay | MCP | da eseguire | M3: test automatici `tests/test_mcp_tools.py` e smoke `scripts/mcp_smoke.py`; REST in M4 |
| 7 | Nessuna chiave nel repo, `.env` mai letto dagli agenti | — | — | — | da eseguire | M14 |

## Registro delle esecuzioni

Per ogni esecuzione manuale: data, chi, comando o conversazione, esito, riferimenti (id ordine,
codice di prenotazione). Mai incollare token, chiavi o dati personali reali.

### 2026-09-25 — M7, Render in live su HofJ staging

Ambiente: `https://vela-n506.onrender.com`, `VELA_UPSTREAM_MODE=live`, HofJ staging
(`staging.weebora.com`, catalogo `fixtures/catalog-staging.json`), Stripe in test con la chiave di
HofJ. Esecuzioni dell'agente con `scripts/rest_flow.py`; pagamento fatto dall'utente con
`4242 4242 4242 4242`.

| Esecuzione | Esito | Riferimenti |
|---|---|---|
| Criterio 3, frase di §10.1 ("padel in Spagna a ottobre, siamo in due, massimo 800 euro") | Fallito come criterio 3, vale come criterio 4 naturale: proposta 28 (398 €), "troppo caro" → 867 (200 €, più economica, fuori dalla Spagna dichiarata); accept → il carrello del 867 fallisce su HofJ (`502 ... POST /itinerary returned 500`, `CONFIGURATION_ERROR`: "Prodotto con acceptsCompanions attivo ma il template Nezasa non espone le due activity di sistema attese"); l'ordine diventa `replaced` con la proposta del 14 (Milano, 370 €) e un `say` senza errori tecnici; 867 marcato non prenotabile per 24 h. 1 chiamata HofJ, nessuna Checkout Session | ordine `6b590046-3641-45a7-bbb7-d4231e08974b` |
| Criterio 3, frase su Barcellona ("un weekend di padel a Barcellona a ottobre, siamo in due, massimo 1500 euro") | ok: proposta 158 (Bela Padel, 1390 €), "troppo caro" → 115 (Tarragona, 720 €, "in Catalogna"), accept 202 `queued`, link Stripe, pagamento, `confirmed` | ordine `b7d7f84c-8582-484f-8bff-8e04657bea5f`, codice `wury5zaxzkec`, totale reale 720,00 € |

Su staging la frase di §10.1 è sostituita da quella su Barcellona: la Spagna non ha prodotti più
economici del 28 oltre al 867, che ha un errore di configurazione lato HofJ. Il codice di
prenotazione su staging è l'`itineraryId` restituito da `POST /v1/bookings` (domanda 2 di
`docs/hofj-questions.md`).

Latenza del flusso REST reale (criterio 3, per M13):

| Passo | Secondi |
|---|---|
| intento | 0.34 |
| proposta | 0.14 |
| rifiuto | 0.33 |
| accept | 0.21 |
| accept → link (coda, 5 chiamate HofJ, Checkout Session) | 53.25 |
| link → confirmed (include il tempo del pagamento a mano, verifica della sessione e booking) | 42.67 |
| totale | 96.93 |

