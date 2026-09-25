# Vela — criteri di accettazione (spec §10)

Una riga per ogni esecuzione di un criterio. Modalità: `replay` (HofJ e Stripe finti) o `live`.
Esito: `ok`, `parziale` (con il motivo nelle note), `fallito`, `da eseguire`.

| # | Criterio (spec §10) | Data | Modalità | Superficie | Esito | Note |
|---|---|---|---|---|---|---|
| 1 | Flusso da Claude via MCP: proposta singola, "troppo caro" → altra singola più economica, "sì" → link, pagamento, `confirmed` con codice | — | replay | MCP (claude.ai) | da eseguire | M3. In replay il rifiuto non interpreta il motivo (M9): la seconda proposta è diversa ma può essere più cara |
| 1 | idem | — | live | MCP (claude.ai) | da eseguire | M7 |
| 2 | Flusso da agente vocale ElevenLabs, link per testo | — | live | MCP (ElevenLabs) | da eseguire | M12 |
| 3 | Flusso via REST con `curl` e token | — | replay | REST | da eseguire | M4 |
| 3 | idem | — | live | REST | da eseguire | M7 |
| 4 | Prodotto che fallisce al carrello sostituito senza errore visibile | — | live | MCP/REST | da eseguire | M5, M7 |
| 5 | Suite verde e load test in replay, quota HofJ invariata | — | replay | REST | da eseguire | M13 |
| 6 | Nessuna risposta con più di un prodotto, su nessuna superficie | — | replay | MCP | da eseguire | M3: test automatici `tests/test_mcp_tools.py` e smoke `scripts/mcp_smoke.py`; REST in M4 |
| 7 | Nessuna chiave nel repo, `.env` mai letto dagli agenti | — | — | — | da eseguire | M14 |

## Registro delle esecuzioni

Per ogni esecuzione manuale: data, chi, comando o conversazione, esito, riferimenti (id ordine,
codice di prenotazione). Mai incollare token, chiavi o dati personali reali.
