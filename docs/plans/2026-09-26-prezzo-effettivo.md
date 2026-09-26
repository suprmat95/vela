# Prezzo effettivo prima del link: attesa, conferma, link

## Contesto
L'agente propone con il `price` del catalogo × pax (stima, "a partire da"). Il link porta invece
`checkout.openAmount` del carrello HofJ, prezzato alla data reale con la sistemazione di default.
Caso reale: 163, 2 persone, stima 656 €, link 840 € (`docs/acceptance.md:62`). Il prezzo reale
esiste solo dopo aver creato il carrello: l'API non ha preventivi in sola lettura.
Oggi il link parte senza che l'utente abbia visto il prezzo. L'avviso RF-16 sta solo in
`get_order_status`, e l'agente non si può "svegliare": l'MCP è stateless e il turno parte solo
dall'utente.

**Decisioni dell'utente (2026-09-26):**
- la proposta resta "a partire da", con la formula "è il minimo";
- `accept_proposal` **aspetta** il prezzo effettivo (tetto 100 s, per il test la coda non è
  intasata);
- l'utente conferma e solo allora si crea il link Stripe (che fino ad allora non parte);
- dopo un "troppo caro" sul prezzo effettivo, il tetto M7 usa il totale effettivo.

## Flusso
1. Proposta: "…Il prezzo parte da 328 € a persona: è il minimo, il totale effettivo dipende da
   date e disponibilità. Se ti va, te lo dico prima del link di pagamento. Ti va?"
2. `accept_proposal` crea l'ordine `queued` e il job d'acquisto, poi **aspetta** (polling sul DB,
   nessuna chiamata HofJ nel caso d'uso) finché l'ordine esce da `queued` o scade il tetto.
3. Il job fa carrello, cliente, pax e totale (5 chiamate, come oggi), poi porta l'ordine a
   **`awaiting_confirmation`** e si ferma prima del link.
   Risposta: stato con `total`, `price_from_total`, `total_differs`.
   `say`: "Il prezzo effettivo è 840 € in totale per 2 persone, più dei 656 € stimati. Confermi?"
4. "Sì": seconda chiamata ad `accept_proposal` sulla stessa proposta. L'ordine torna `queued` e
   parte un job d'acquisto dal passo `STEP_LINK`; il caso d'uso aspetta di nuovo, fino ad
   `awaiting_payment`. Poi link in chat e SMS (flusso attuale).
5. "No / troppo caro": `reject_proposal`. L'ordine va in `cancelled` (RF-49 esteso a
   `awaiting_confirmation`), e la proposta successiva deve costare meno del totale effettivo.
6. Tetto superato: risposta `queued` come oggi, e l'utente chiede lo stato.
   `get_order_status` su `awaiting_confirmation` ridà la domanda di conferma.

## Modifiche
- **Verifica preliminare:** con `mcp` 2.2.0 (`uv.lock`), controllare se `MCPServer` esegue i
  tool sincroni in un thread. Se li esegue sul loop, il tool `accept_proposal` in
  `vela/surfaces/mcp.py` va reso `async` con `anyio.to_thread.run_sync`, altrimenti l'attesa
  blocca il server. REST (`def` sincrona) gira già nel threadpool di FastAPI.
- `vela/domain/models.py`: `OrderStatus.AWAITING_CONFIRMATION = "awaiting_confirmation"` tra
  `QUEUED` e `AWAITING_PAYMENT`. La colonna è `String(24)` senza vincoli: **nessuna migrazione**.
- `vela/domain/purchase.py`: nel passo `STEP_TOTAL` salvare `total` e
  `status=AWAITING_CONFIRMATION`. Il ciclo di `run` si ferma già da solo quando lo stato non è
  `queued`, quindi il job si chiude `DONE` con `step=STEP_LINK`. Aggiornare la docstring.
- `vela/domain/usecases.py`:
  - `accept_proposal`: se esiste un ordine `awaiting_confirmation`, è la conferma. L'ordine
    torna `queued` e si accoda `Job(PURCHASE, step=STEP_LINK)` (se `jobs.active_for_order` non
    ne ha già uno).
  - Dopo l'accodamento, sia al primo accept sia alla conferma, `_await(order_id)`: polling
    ogni `accept_poll_seconds` finché lo stato non è `queued` o scade `accept_wait_seconds`,
    con `sleep` iniettato (test senza attese). Poi `get_order_status`, oppure `OrderQueued`
    come oggi.
  - `_cancel_unpaid_order`: includere `AWAITING_CONFIRMATION`.
  - `_price_ceiling`: per le proposte rifiutate per prezzo usare `order.total`
    (`orders.get_by_proposal`) quando c'è, altrimenti `total_from`.
  - `get_order_status`: `awaiting_confirmation` restituisce `total`, `currency`,
    `price_from_total`, `total_differs`, e `payment_url` è `null`.
- `vela/config.py`: `accept_wait_seconds: int = 100` e `accept_poll_seconds: float = 1.0`,
  campi di tuning. Collegarli in `vela/app.py` come gli altri.
- `vela/domain/say.py`:
  - `say_proposal`, it/en: la nuova formula "è il minimo… te lo dico prima del link";
  - `say_status(AWAITING_CONFIRMATION)`: prezzo effettivo con la stima se differisce, poi
    "Confermi?";
  - `say_queued`: "sto preparando il prezzo effettivo" invece di "il link sarà pronto".
- `vela/domain/chooser.py:144-155`: la motivazione non dice più "costa X in totale" ma "la
  stima…" (resta il confronto con il budget).
- `vela/surfaces/mcp.py`, istruzioni e descrizioni (con e senza SMS):
  - `accept_proposal` può rispondere `awaiting_confirmation`: leggi `say`, e se l'utente dice
    sì richiama `accept_proposal` sulla stessa proposta; se dice no, `reject_proposal`;
  - aggiungere il nuovo stato in `_STATES`.
- Documentazione:
  - `docs/spec.md`: RF-16, RF-25 (stati), RF-45, RF-49, RNF-05 (il caso d'uso può aspettare
    fino a 100 s, senza chiamare HofJ);
  - `docs/rest.md`: il nuovo stato;
  - `docs/decisions.md`, voci datate: flusso con conferma, attesa di 100 s, tetto M7 sul
    totale effettivo, formula "è il minimo", `response_timeout_secs` 120 da impostare
    nell'agente ElevenLabs.

**Fuori perimetro, da annotare:**
- nessuna scadenza per gli ordini fermi in `awaiting_confirmation`;
- il link Stripe scade comunque a 24 h dalla creazione dell'ordine;
- il carrello di chi rifiuta resta orfano (5 chiamate spese, come oggi).

## Test (unittest, `tests/`)
- `test_purchase`: dopo il totale l'ordine è `awaiting_confirmation`, nessun link né SMS
  accodato; il job che parte da `STEP_LINK` crea link, verifica pagamento e SMS.
- `test_usecases`:
  - con un `sleep` finto che fa girare il worker: il primo accept restituisce
    `awaiting_confirmation` con il totale;
  - il secondo restituisce `awaiting_payment` con il link;
  - a tetto scaduto, `queued`;
  - `reject_proposal` su `awaiting_confirmation` porta a `cancelled`;
  - il tetto M7 usa `order.total`;
  - aggiornare `KEYS` e lo stato.
- `test_say` (frasi it/en), `test_mcp` (descrizioni), `test_rest` (forma della risposta),
  test del chooser per la motivazione.
- Replay: aggiungere a `hofj_replay` un sovrapprezzo opzionale, così un test copre
  `total_differs=True`.

## Verifica
- `uv run python3 -m unittest discover -s tests` verde e `uv run ruff check .` pulito.
- `scripts/rest_flow.py` in replay in locale: accept → `awaiting_confirmation` → accept →
  `awaiting_payment`.
- Prova end-to-end su staging con il connector claude.ai, solo dopo il tuo OK sulle chiamate
  (circa 5 HofJ + 1 Stripe di test per ordine): misurare il tempo reale tra accept e prezzo e
  verificare che claude.ai non vada in timeout.
- Dopo l'approvazione: branch `task/price-confirmation` e commit piccoli.
