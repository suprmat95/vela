# vela-booking-spec

- Sessione: `d78c1ea9-ede6-44a3-91fe-56f1beb20c0a`
- Inizio: 2026-09-25 12:28

## Agente 12:28

Uso la skill brainstorming per intervistarti e arrivare a `spec.md`. Prima leggo il brief e il contesto del repo.

- 🔧 Bash: List repo files and locate brief.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/brief.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/decisions.md

- 🔧 Read /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/agents-log.md

- 🔧 Bash: List supporting folders and recent commits

- 🔧 ToolSearch

- 🔧 WebFetch

- 🔧 WebFetch

- 🔧 WebFetch

- 🔧 WebFetch

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 WebFetch

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 AskUserQuestion

- 🔧 Write /Users/matteodospina/.claude/plans/premessa-leggi-il-file-keen-newell.md

- 🔧 AskUserQuestion

Cosa vuoi chiarire sull'architettura? Puoi scrivermi la domanda o il dubbio direttamente, poi riformulo le opzioni.

## Utente 12:51

spiegami meglio la proposta a

## Agente 12:52

Ecco la proposta A nel dettaglio.

**L'idea in una frase.** Tutta la logica di Vela vive in un package Python `vela` che non sa nulla di HTTP, MCP o Stripe. Le "superfici" (REST, MCP, webhook, domani A2A) sono strati sottili che traducono una richiesta esterna in una chiamata al dominio e la risposta in un formato. Se domani aggiungi A2A, scrivi solo l'adapter, non tocchi la logica.

**I pezzi del dominio (dentro `vela/`):**

- **Intent parser.** Riceve testo libero ("un weekend di padel a ottobre in Spagna, siamo in due, max 800 euro") e produce criteri strutturati: sport, zona, periodo, pax, budget, lingua. Prima passa il parser deterministico (regole e dizionari it/en). Se non riesce a estrarre almeno sport o periodo, e se c'è `ANTHROPIC_API_KEY`, chiede a Haiku di compilare lo stesso schema. Altrimenti risponde con la domanda mancante.
- **Chooser.** Prende i criteri e il catalogo (in cache) e restituisce **una** proposta con motivazione e prezzo, scartando i prodotti già rifiutati in quell'intento e quelli noti come non prenotabili. Scoring a regole: sport, destinazione, date compatibili con `minDate`/`maxDate`/availabilities, prezzo entro budget, poi prezzo crescente.
- **Booking orchestrator.** Dato un "sì", esegue in ordine: crea itinerario HofJ, mette cliente e pax, legge il totale, crea il Payment Link Stripe, salva l'ordine come `awaiting_payment`. Quando arriva il webhook Stripe, riprende l'ordine e chiama `POST /v1/bookings`, salva il `reservationCode`, stato `confirmed`. Se la creazione dell'itinerario fallisce (prodotto misconfigurato), marca il prodotto come non prenotabile e chiede al chooser la proposta successiva, senza dirlo al viaggiatore.

**Le porte.** Il dominio parla con l'esterno solo tramite due interfacce: `HofjGateway` e `PaymentGateway`. Ognuna ha due implementazioni: quella reale e una replay/fake che legge fixture registrate. Il load test e i test unitari usano la replay; la produzione usa la reale. Il client HofJ reale contiene la cache del catalogo in Postgres, con TTL, e il guardiano della quota: un contatore condiviso, letto da `GET /v1/quota` all'avvio e aggiornato localmente, che rifiuta o accoda le chiamate quando la finestra è quasi piena.

**Le superfici.** Una sola app FastAPI monta tre cose. REST sotto `/v1`: crea intento, leggi proposta, rifiuta con motivo, accetta, stato ordine. MCP sotto `/mcp` con trasporto Streamable HTTP: gli stessi cinque casi d'uso esposti come tool, così Claude ed ElevenLabs si collegano da remoto senza codice specifico. Webhook Stripe sotto `/webhooks/stripe`. I due adapter chiamano le stesse funzioni del dominio: un bug fixato una volta è fixato ovunque.

**Perché un solo processo.** Il passo dopo il pagamento è per natura asincrono: lo scatena il webhook, non l'utente. Lo eseguo come task in background dentro lo stesso processo FastAPI, con lo stato dell'ordine in Postgres. Non serve un worker separato: se il processo muore a metà, l'ordine resta `paid_pending_booking` e un piccolo ciclo di ripresa all'avvio lo completa. `POST /v1/bookings` è idempotente per itinerario, quindi ripetere è sicuro.

**Come scala.** Il container è senza stato: tutto (intenti, proposte, ordini, cache catalogo, contatore quota) sta in Postgres. Su Render alzi il numero di istanze e funziona. Il collo di bottiglia vero è il rate limit di HofJ, e la risposta è nel design: cache del catalogo, una sola chiamata upstream per proposta, prenotazione accodata. È questo il racconto per il 25% di scalabilità, e il load test in replay lo misura.

**Struttura del repo, indicativa:**

```
vela/domain/      intent.py chooser.py orders.py models.py
vela/ports/       hofj.py payments.py (interfacce)
vela/adapters/    hofj_http.py hofj_replay.py stripe_links.py stripe_fake.py db.py
vela/surfaces/    rest.py mcp.py webhooks.py
vela/app.py       compone tutto
loadtest/         locustfile.py + risultati
tests/
```

Costo stimato rispetto a B: nessun secondo deploy, nessuna tabella jobs, stessa scalabilità orizzontale. Rispetto a C: tre chiamate invece di una, ma la conversazione "proposta, no, un'altra, sì" è quella che il brief premia.

Va bene A così, o vuoi cambiare qualcosa prima che passi alle sezioni del design?

## Utente 12:54

Come avviene la sincronizzazione del catalogo?

## Agente 12:54

La sincronizzazione del catalogo è il punto dove il rate limit fa più male, quindi la regola base è: **nessuna richiesta del viaggiatore chiama mai HofJ per cercare**. Il chooser legge solo da Postgres. L'unica chiamata upstream "dal vivo" è quella che crea l'itinerario dopo il sì.

**Cosa sincronizziamo.** Una tabella `catalog_products` con: id HofJ, il JSON grezzo del dettaglio prodotto, i campi estratti che servono al chooser (sport/categoria, destinazione, venue, prezzo "da", valuta, minPax/maxPax, minDate/maxDate, availabilities, durata, hotel di default, `archived`), più `fetched_at`, `upstream_updated_at` e un flag `bookable` con `bookable_checked_at`. Filtriamo a monte: solo categorie padel/tennis, solo non archiviati.

**Come gira il sync.** È un job a passi, non una chiamata sola:

1. Legge `GET /v1/quota` una volta per sapere quanto margine c'è nella finestra.
2. Scorre `GET /v1/products?locale=it&limit=100&cursor=...` finché `meta.nextCursor` è vuoto. Per un catalogo di qualche centinaio di prodotti sono 2-5 chiamate.
3. Confronta `updatedAt` di ogni prodotto con `upstream_updated_at` in tabella. Chiede `GET /v1/products/{id}` **solo** per i prodotti nuovi o cambiati. Alla prima esecuzione sono tutti, poi quasi nessuno.
4. Ogni chiamata passa dal guardiano della quota: se la finestra è quasi piena, il job dorme fino a `windowEndsAt` e riprende. Un sync completo iniziale può richiedere qualche minuto; va bene, è in background.
5. Scrive in Postgres per lotti, così una interruzione a metà lascia comunque un catalogo parziale utilizzabile.

**Quando gira.** All'avvio, se la tabella è vuota o più vecchia di una soglia (propongo 6 ore). Poi con un timer interno alla stessa soglia. Con più istanze su Render, un advisory lock Postgres garantisce che sincronizzi una sola istanza alla volta. C'è anche un comando manuale, `python -m vela.sync`, per forzarlo.

**Prezzi e freschezza.** Il prezzo in catalogo è un "a partire da" per la configurazione base. La proposta lo dichiara come tale. Al "sì", l'itinerario HofJ restituisce il totale reale per pax e date scelte; se differisce dalla proposta, Vela lo dice prima di generare il link di pagamento, e il link porta il totale reale. Così il catalogo può essere vecchio di ore senza che il viaggiatore paghi mai un prezzo sbagliato.

**Prodotti non prenotabili.** Non si scoprono nel sync: creare un itinerario per ognuno costerebbe un'intera quota. Si scoprono al primo tentativo reale: se `POST /v1/itineraries` fallisce, `bookable=false` con timestamp, e il chooser lo salta per tutti da quel momento. Dopo 24 ore lo riproviamo, perché "misconfigurato upstream" può essere temporaneo.

**Snapshot committato.** Il primo sync reale lo salviamo anche come fixture nel repo, `fixtures/catalog.json`. Serve a tre cose: la modalità replay per test e load test, l'avvio a freddo di un'istanza nuova senza consumare quota, e la demo nel caso qualcuno esaurisca la quota proprio mentre registri il video. La fixture non contiene chiavi: solo risposte di catalogo.

**Cosa non so ancora, e va verificato nella prima ora con 2 chiamate.** Quanti prodotti padel/tennis ci sono davvero, e se la risposta della lista contiene già prezzo e date oppure se servono davvero i dettagli uno a uno. Da questo dipende se il sync iniziale dura un minuto o dieci. Lo metto come spike nella spec.

Ti torna? Se sì, passo alle sezioni del design.

## Utente 12:56

Ok quindi abbiamo comunque bisogno di db! ricapitoliamo tutto

## Agente 12:57

Sì, il DB serve: senza uno stato condiviso non c'è né catalogo in cache, né ordine che sopravvive tra "sì", pagamento e webhook, né scalabilità orizzontale. Avevi già scelto Render + Postgres, quindi è coperto. Ecco il riepilogo completo di tutto ciò che abbiamo deciso.

**Cosa costruiamo**
- Vela è un **core service** senza interfaccia propria. Il viaggiatore parla con l'assistente che ha già (Claude, un agente vocale ElevenLabs) e quello chiama Vela.
- Prodotto: solo padel/tennis con hotel, dal catalogo House of Journeys. Niente altro.
- Risultato finale: un `reservationCode` reale da `POST /v1/bookings`, pagato con Stripe test.

**Regole di prodotto**
- Un intento in parole del viaggiatore, in italiano o inglese, basta per arrivare all'acquisto.
- Vela propone sempre **una** sola opzione, con prezzo e motivazione. Mai liste.
- "No" con un motivo produce un'altra proposta singola, senza limite di tentativi.
- Un prodotto che fallisce al carrello viene saltato in silenzio e segnato come non prenotabile.
- Dati raccolti: nome, cognome, email, telefono. Pax aggiuntivi: nome e cognome. Indirizzo di default dichiarato come vincolo demo.
- Il prezzo in proposta è "a partire da"; il totale reale arriva dall'itinerario prima del pagamento.

**Architettura (variante A)**
- Python 3, FastAPI, un solo processo, container su Render, Postgres.
- Dominio puro in `vela/`: intent parser (regole; fallback Haiku 4.5 solo se `ANTHROPIC_API_KEY` esiste), chooser, booking orchestrator.
- Due porte con doppia implementazione: HofJ reale/replay, Stripe reale/fake.
- Tre superfici sullo stesso dominio: REST `/v1`, MCP Streamable HTTP `/mcp`, webhook Stripe. A2A predisposto come quarto adapter, documentato come prossimo sviluppo se non entra nelle 24h.
- Booking post-pagamento come task in background, ordine in Postgres, ripresa all'avvio; `POST /v1/bookings` è idempotente.

**Postgres contiene**
- `catalog_products`: cache del catalogo con campi estratti, `bookable`, timestamp.
- `intents`, `proposals`, `orders`: lo stato della conversazione e dell'acquisto.
- contatore quota condiviso e advisory lock per il sync.

**Sync catalogo**
- Solo il sync chiama `GET /v1/products`; le richiesta dei viaggiatori leggono da DB.
- All'avvio se vuoto o più vecchio di 6 ore, poi ogni 6 ore, incrementale su `updatedAt`, ritmato dal guardiano della quota.
- Snapshot committato in `fixtures/catalog.json` per replay, avvio a freddo e demo di emergenza.

**Pagamento**
- Stripe Payment Link sul tuo account test; webhook `checkout.session.completed` → booking HofJ con `paymentIntentId` e `paymentStatus` forwarded.
- Rischio aperto: se HofJ pretende il proprio PaymentIntent confermato, il fallback è una pagina minima con Stripe.js sul `client_secret` di HofJ. Spike nella prima ora.

**Qualità e consegne**
- Test con `unittest` su dominio e adapter replay.
- Load test Locust contro il core in modalità replay, più numeri reali da `GET /v1/quota`.
- `git mv agents-log agent-log`, con script, hook, doc e test aggiornati.
- `ARCHITECTURE.md`, URL live su Render, video 3-5 minuti con Claude ed ElevenLabs.

**Variabili d'ambiente**: `HOFJ_API_KEY`, `HOFJ_BASE_URL`, `HOFJ_BRAND`, `DATABASE_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY` (opzionale), `VELA_UPSTREAM_MODE=live|replay`.

**Spike nella prima ora (4-5 chiamate HofJ in tutto)**: la chiave funziona e ha profilo interno (`GET /v1/quota`); quanti prodotti padel/tennis ci sono e cosa contiene la lista (`GET /v1/products` + un dettaglio); il booking accetta il pagamento fatto sul nostro Stripe.

Se il riepilogo ti torna, il prossimo passo è scrivere `docs/spec.md` con questi contenuti espansi in requisiti numerati, e aggiungere le decisioni di oggi a `docs/decisions.md`. Per farlo devo uscire dalla modalità piano. Confermi?

## Utente 13:00

si

## Agente 13:01

Perfetto. Aggiorno il piano con la struttura della spec e chiedo l'uscita dalla modalità piano.

- 🔧 Edit /Users/matteodospina/.claude/plans/premessa-leggi-il-file-keen-newell.md

- 🔧 ToolSearch

- 🔧 ExitPlanMode

Scrivo `docs/spec.md`.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/spec.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/spec.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/spec.md

- 🔧 Edit /Users/matteodospina/orca/workspaces/vela/doc-requirements/docs/spec.md

- 🔧 Bash: Append today's decisions to decisions.md and run the test suite
