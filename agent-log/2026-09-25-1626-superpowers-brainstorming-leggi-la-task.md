# /superpowers:brainstorming: Leggi la task m3 in docs/roadmap.md. Obiettivo: inte

- Sessione: `c8dbb16a-b78c-407c-bd70-25295f759669`
- Inizio: 2026-09-25 16:26

## Utente 16:26

/superpowers:brainstorming: Leggi la task m3 in docs/roadmap.md. Obiettivo: intervistami e scrivi il
    piano di esecuzione in un file in docs/plans/ Il piano dovrà indicare i microtask e i test che coprono il codice prodotto. Dopodiché lancerò l'esecuzione del piano

## Agente 16:26

Uso la skill brainstorming per intervistarti e arrivare al piano. Prima leggo il contesto del progetto.

- 🔧 Bash: List repo docs and read the roadmap

- 🔧 Bash: Read spec refs, decisions and code layout

- 🔧 Bash: Read M2 plan format for reference

- 🔧 Bash: Read spec surfaces, app wiring, use case API, mcp version

- 🔧 Bash: Check mcp lock version and use case details

- 🔧 Bash: Locate the installed mcp SDK

- 🔧 Bash: Inspect mcp 2.2 server API

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 Bash: Inspect MCPServer settings, tool and client API

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 Bash: Check Render deploy config and public URL setting

- 🔧 AskUserQuestion

- 🔧 Bash: Read MCPServer constructor, HTTP app and Client

Ho finito le domande principali e ho verificato l'API dell'SDK (`MCPServer`, `streamable_http_app`, `Client` in-process e via URL). Ti presento il design in tre sezioni. Questa è la prima.

### Sezione 1: architettura e componenti

**File nuovi e modificati**
```
vela/surfaces/mcp.py      build_mcp(vela_provider, settings) -> MCPServer con 5 tool + instructions
                          tool_error(...) / mapping NotFound -> isError con frase italiana
vela/app.py               monta l'app Streamable HTTP su /mcp; il lifespan FastAPI avvia
                          anche mcp.session_manager.run() (un sub-app montato non esegue il proprio)
scripts/mcp_smoke.py      client MCP (mcp.Client(url)) che esegue il flusso §10.1 contro un URL
docs/acceptance.md        tabella dei 7 criteri di §10: data, modalità, superficie, esito, note
README.md                 sezione "Collegare Claude (connector custom)"
docs/decisions.md         decisioni di M3
tests/test_mcp_tools.py   tool in-process (Client(MCPServer)) con repository in memoria
tests/test_mcp_http.py    /mcp montato nell'app FastAPI: HTTP, host check, JSON stateless
```

**Principi**
- **Adapter sottile.** `vela/surfaces/mcp.py` traduce gli argomenti piatti in `TravelerProfile`, chiama `Vela` e restituisce `to_dict()`. Non contiene logica di dominio. Il dominio non importa `mcp`.
- **Trasporto.** `stateless_http=True`, `json_response=True`, `streamable_http_path="/"` con mount su `/mcp`. Gestisco il redirect `/mcp` → `/mcp/` con una route esatta o con il path del mount, e un test lo verifica, perché claude.ai chiama `/mcp` senza slash finale.
- **Host check.**
  - `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[host di VELA_PUBLIC_URL, "localhost:*", "127.0.0.1:*", "testserver"], allowed_origins=[]` più eventuali origin ammessi)`.
  - Nessuna variabile d'ambiente nuova.
- **Dominio assente.** Se `vela` è `None` (niente `DATABASE_URL`), `/mcp` resta montato e ogni tool risponde `isError` con "Vela non è disponibile in questo momento". Senza DB `/mcp` non va in crash.
- **Nessuna nuova superficie di pagamento.** Il link resta `GET /replay/checkout/{id}` di M2, e l'utente lo apre dalla chat.

Ti torna la struttura, prima di passare ai tool?

## Utente 16:44

vai

## Agente 16:45

### Sezione 2: i cinque tool

**Istruzioni del server** (in inglese, lette dal modello una volta):
> "Vela books padel/tennis trips with hotel from one sentence. Always propose exactly ONE option; never list, compare or invent alternatives. After every tool call, speak the `say` field to the user verbatim, in the user's language, and never read URLs aloud: tell the user the payment link is in the chat. Call `get_proposal` right after `create_intent` succeeds."

| Tool | Argomenti | Restituisce | Note nella descrizione |
|---|---|---|---|
| `create_intent` | `text` (obbl.), `first_name`, `last_name`, `email`, `phone`, `pax`, `participants[{first_name,last_name}]` | `IntentCreated` o `IntentQuestion` | Se torna `question`, fai la domanda all'utente e richiama il tool con il testo completato. |
| `get_proposal` | `intent_id` | `ProposalMade` o `NoMatch` | Una sola proposta, da leggere con `say`. Con `NoMatch`, chiedi di riformulare. |
| `reject_proposal` | `proposal_id`, `reason` (la frase dell'utente, es. "troppo caro") | `ProposalMade` o `NoMatch` | Passa il motivo con le parole dell'utente. |
| `accept_proposal` | `proposal_id` + gli stessi campi viaggiatore piatti | `AcceptResponse` o `MissingTravelerData` | Chiamalo solo dopo un "sì" esplicito. Se torna `missing`, chiedi quei dati e richiama il tool: è idempotente. Mostra `payment_url` come link cliccabile senza leggerlo. |
| `get_order_status` | `order_id` | `OrderStatusResponse` | Da usare quando l'utente dice di aver pagato o chiede a che punto è. |

**Output.** Ogni tool restituisce il `dict` di `to_dict()`: l'SDK lo espone come `structuredContent` e come testo JSON. Nei dict di `to_dict()` non c'è un campo "tipo" per distinguere le varianti; il modello le riconosce dalle chiavi presenti (`question`, `failed_criterion`, `missing`). Aggiungerei un campo `kind`, ma cambierebbe il contratto di M2, quindi non lo faccio.

**Errori**
- `NotFound(kind, id)` diventa un risultato con `isError=true` e il testo di `say.say_not_found(kind)`, una frase italiana nuova in `vela/domain/say.py` (es. "Non trovo questa proposta. Ripartiamo dal viaggio che hai in mente?").
- Gli argomenti non validi li gestisce già l'SDK con la validazione pydantic.
- Le eccezioni inattese vengono loggate con `logger.exception` e diventano un errore generico ("Qualcosa non ha funzionato, riprova tra poco"), senza stack trace nel risultato.

**Sincrono e asincrono.** I casi d'uso sono sincroni e usano un engine SQLAlchemy sync, quindi i tool sono `def` e l'SDK li esegue nel threadpool. Se nel piano emerge che l'SDK 2.2 non lo fa, li avvolgo in `anyio.to_thread.run_sync`, e un test lo copre.

**RF-10.** Il test usa `assert_single_product` su ogni risultato. La descrizione di ogni tool ripete "never list alternatives".

Va bene così? Poi presento l'ultima sezione: test, prova manuale e la sequenza dei microtask.

## Utente 16:46

Vai

## Agente 16:46

### Sezione 3: test, prova manuale e microtask

**Test automatici** (tutti senza servizi esterni; i Postgres si saltano senza `DATABASE_URL`)
- `tests/test_mcp_tools.py`: `Client(MCPServer)` in-process su `Vela` con repository in memoria, `FakeHofJ`/`FakePayments`, orologio e id fissi.
  - `list_tools` restituisce esattamente i 5 nomi di RF-39, e ogni descrizione contiene le frasi "never list" e "say".
  - Schema di `accept_proposal` e `create_intent`: campi piatti, con `participants` come array di oggetti.
  - Domanda mancante: `create_intent` senza pax restituisce `question` e non persiste nulla.
  - Flusso §10.1: intento → proposta → `reject("troppo caro")` porta a una proposta diversa e più economica → `accept` con dati mancanti restituisce `missing` → `accept` completo restituisce `payment_url` → `mark_paid` + `InlineRunner` → `get_order_status` è `confirmed` con `R-…`.
  - Doppio `accept` restituisce lo stesso `order_id`.
  - Id sconosciuti sui 4 tool con id: risultato `isError` con la frase di `say_not_found`.
  - Eccezione inattesa: errore generico, senza stack trace nel testo.
  - Dominio assente: `isError` "non disponibile".
  - RF-10: `assert_single_product` su ogni `structuredContent`, e `say` senza URL.
- `tests/test_mcp_http.py`: l'app FastAPI vera con `vela` iniettato e `TestClient` (che esegue il lifespan).
  - `POST /mcp` `initialize` e `tools/list` rispondono 200 con JSON, non SSE, e senza `Mcp-Session-Id`.
  - `/mcp` senza slash finale non restituisce un redirect che i client non seguono.
  - Host non ammesso restituisce 421; host di `VELA_PUBLIC_URL` restituisce 200.
  - `/health` continua a funzionare.
- `tests/test_say.py`: le frasi di `say_not_found` non contengono URL né markdown.

**Microtask** (un commit ciascuno, in TDD)
0. Piano e decisioni in `docs/decisions.md`.
1. `say_not_found` e frasi di errore in `say.py`.
2. `vela/surfaces/mcp.py`: server, instructions e i 5 tool con argomenti piatti; test in-process del flusso, degli errori e di RF-10.
3. Mount su `/mcp` in `app.py`: lifespan del session manager, stateless JSON, host check; test HTTP.
4. `scripts/mcp_smoke.py` (URL come argomento, esegue il flusso §10.1 e apre il checkout replay via HTTP) con test su un'app locale. Nessuna chiamata a HofJ o Stripe.
5. `docs/acceptance.md` (tabella di §10 con righe "da eseguire") e sezione README sul connector.
6. **Manuale, guidato:**
   - (a) merge su `master` → autodeploy Render; verifico `/health` e che `VELA_PUBLIC_URL` sia impostata;
   - (b) eseguo io `mcp_smoke.py` contro l'URL live: un flusso, solo replay, costo zero;
   - (c) **tu** aggiungi il connector in claude.ai (Settings → Connectors → URL `…/mcp`) e fai la conversazione di §10.1;
   - (d) registro l'esito dei criteri 1 (replay) e 6 in `docs/acceptance.md` e le decisioni emerse.

**Fuori scope:** auth (M8), REST (M4), `say` in inglese (M9), campo `kind` nelle risposte.

Se questa sezione ti va bene, scrivo il piano completo in `docs/plans/2026-09-25-m3-superficie-mcp.md`, con codice e test per ogni microtask come in M2, e lo committo su `task/m3`.

## Utente 16:46

Vai

## Agente 16:46

- 🔧 Skill superpowers:writing-plans

Uso la skill writing-plans per scrivere il piano. Prima di mettere codice concreto nel piano, verifico nell'SDK installato come si comportano i tool, gli errori e il client.

- 🔧 Bash: Inspect tool registration, call and error handling

- 🔧 Bash: Read how tool errors become results

- 🔧 Bash: Spike MCP SDK behavior in scratchpad

Lo spike mostra tre cose da sistemare: `-> dict` non produce `structuredContent`, `ToolError` aggiunge un prefisso inglese al messaggio, e `/mcp` risponde 307. Provo le alternative.

- 🔧 Bash: Spike structured output, error result and root mount

- 🔧 Bash: Verify CallToolResult passthrough and read test helpers

- 🔧 Bash: Read test helpers, app tests, orders and say

- 🔧 Bash: Read host and origin validation rules

- 🔧 Bash: Check script test import style, say, response dicts, README

- 🔧 Bash: Run the §10.1 intent against the replay catalog

- 🔧 AskUserQuestion

Lascio il problema a M9: in M3 i test verificano solo che la proposta sia diversa. Prima di scrivere il codice del piano controllo come innestare le route MCP senza un mount catch-all su `/`.

- 🔧 Bash: Spike route splicing and argument descriptions

- 🔧 Bash: Read remaining test patterns and repo API

- 🔧 Bash: Check origin rejection status and say tests

Ho tutto quello che serve. Scrivo il piano.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m3/docs/plans/2026-09-25-m3-superficie-mcp.md

- 🔧 Bash: Fix test count and import in the plan

Ho scritto il piano in `docs/plans/2026-09-25-m3-superficie-mcp.md`. Non l'ho ancora committato: lo fa il Task 0 insieme alle decisioni, come per M2.

**Cosa contiene**
- **Contesto:** quello che ho verificato con tre spike usa e getta sull'SDK `mcp` 2.2.0, tutti buttati:
  - un tool `-> dict` non produce `structuredContent`, quindi i tool restituiscono un `CallToolResult` costruito a mano;
  - `app.mount("/mcp")` risponde 307 al POST, quindi le route MCP vanno innestate nel router di FastAPI;
  - senza configurazione esplicita l'host di Render riceve 421.
- **Decisioni dell'intervista:** vanno in `docs/decisions.md` nel Task 0.
- **Sette task in TDD**, ognuno con codice completo, test e commit:
  - 0: piano e decisioni;
  - 1: frasi d'errore in `say.py` (3 test);
  - 2: `vela/surfaces/mcp.py` con i 5 tool (15 test: elenco, schema, flusso §10.1, errori, RF-10, host/origin);
  - 3: `/mcp` nell'app FastAPI (11 test: JSON stateless, niente 307, 421/403, le altre route invariate);
  - 4: `scripts/mcp_smoke.py` (7 test);
  - 5: `docs/acceptance.md` e la sezione del README per il connector;
  - 6: parte manuale guidata. Il merge su `master` e la conversazione in claude.ai li fai tu; lo smoke live lo lancio io dopo averti detto quante chiamate fa.
- **Review Focus:** 5 casi limite, ciascuno coperto da un test preciso.

**Cosa sapere prima di approvare**
- In replay "troppo caro" porta a una proposta **più cara**, come abbiamo deciso: 279 € → 300 € sul catalogo vero. Il piano registra il criterio 1 come "parziale" finché non arriva M9.
- Nel test `test_traveler_arguments_are_flat` la forma esatta dello schema di `participants` è la mia ipotesi. Il piano dice come adeguare l'asserzione se l'SDK la genera in modo diverso.

**Come eseguirlo**
- **Subagent-driven:** un subagent per task, con una revisione dopo ciascuno.
- **Native:** eseguo tutto io in questa sessione, con una sola revisione a fine branch.

Consiglio **Native**: i task sono pochi, in sequenza, e il codice è già scritto per intero nel piano, quindi una revisione per task costerebbe molto e aggiungerebbe poco.

Il piano dice quello che vuoi? E quale modalità usiamo?

## Utente 16:58

/superpowers:test-driven-development: docs/plans/2026-09-25-m3-superficie-mcp.md

## Agente 16:58

Il piano lo eseguo io in questa sessione, in TDD. Parto dal Task 0: decisioni in `docs/decisions.md` e commit del piano.

- 🔧 Bash: Append M3 decisions and commit the plan

Task 1, fase RED: aggiungo i test delle frasi d'errore.

- 🔧 Bash: Add say tests and watch them fail

- 🔧 Bash: Check failure reason, implement, rerun

- 🔧 Bash: Commit task 1

Task 2, fase RED: scrivo `tests/test_mcp_tools.py` copiandolo dal piano.

- 🔧 Bash: Extract MCP tools test from plan, watch it fail

You've hit your session limit · resets 6pm (Europe/Rome)

## Utente 17:04

contina

## Agente 17:04

- 🔧 Bash: Confirm failure reason, implement mcp.py, rerun

Il RED è quello atteso: il modulo `vela.surfaces.mcp` non esiste. L'estrazione del codice dal piano ha fallito per un marcatore sbagliato; lo correggo.

- 🔧 Bash: Write mcp.py from the plan and run tool tests

I 15 test passano. Resta una riga di log dell'SDK ("rejected arguments") che sporca l'output: nel test degli argomenti non validi la catturo con `assertLogs`, così diventa anche una verifica.

- 🔧 Bash: Capture SDK log in test; run file and full suite

La suite è verde: 289 test, 11 saltati. Allineo il piano al test modificato e faccio il commit.

- 🔧 Bash: Sync plan with test change and commit task 2

Task 3, fase RED: test HTTP di `/mcp` nell'app FastAPI.

- 🔧 Bash: Write HTTP tests and watch them fail

Tutti falliscono perché `/mcp` risponde 404, che è il motivo giusto. `test_other_routes_are_unchanged` passa già: fa da guardia contro le regressioni. Ora modifico `vela/app.py`.

- 🔧 Bash: Mount MCP routes and lifespan in app.py, run HTTP tests

- 🔧 Bash: Capture SDK warnings in tests; run suite
