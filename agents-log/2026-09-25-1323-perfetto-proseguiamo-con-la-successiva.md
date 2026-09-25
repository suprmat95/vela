# wasm-seal-challenge

- Sessione: `de2a16b3-344c-4915-b3ff-4690991e804d`
- Inizio: 2026-09-25 13:07

## Agente 13:07

Sto usando la skill brainstorming. Classificazione: questo è uno **spike** (una domanda da rispondere, non codice da tenere). Prima esploro il repo in sola lettura per capire cos'è l'API HOFJ e come si apre un carrello.

- 🔧 Bash: List repo files and read the brief

- 🔧 Bash: Read decisions, agents-log docs and list folders

- 🔧 Bash: Download HOFJ OpenAPI spec and list endpoints; check env var names only

- 🔧 Bash: Print the relevant endpoint definitions from the spec

- 🔧 Bash: Print product, accommodation and itinerary schemas; check whether an env file exists without reading it

- 🔧 Bash: Print availability and itinerary schemas; list docs in sibling worktrees

Sto leggendo la documentazione API già raccolta nel worktree gemello `api-recognition` (checkout interno, canali, differenze) per capire come si autentica e come si apre un carrello.

- 🔧 Bash: Read API notes from the sibling worktree

- 🔧 Bash: Read channel and quota notes; find which env var names were used for credentials

- 🔧 Bash: List env variable names (never values) in the sibling worktree

- 🔧 Bash: Check env var names, how the explore script authenticates, and the docs site page list

- 🔧 Bash: Get the auth env var name, hide values, and download the docs pages on staging and cart as Markdown

- 🔧 Bash: Download and extract text of the docs pages on staging, checkout flow and agnostic cart

Ho abbastanza contesto. Scrivo il piano e ti faccio una domanda sulle credenziali.

- 🔧 Write /Users/matteodospina/.claude/plans/obiettivo-ricercare-degli-easter-melodic-meerkat.md

- 🔧 AskUserQuestion

- 🔧 Edit /Users/matteodospina/.claude/plans/obiettivo-ricercare-degli-easter-melodic-meerkat.md

- 🔧 ToolSearch

- 🔧 ExitPlanMode

Scrivo lo script usa-e-getta in scratchpad e lo lancio, step per step, partendo da quota e canali su staging.

- 🔧 Bash: Create the throwaway API client and call quota and distribution channels on staging

La Python 3.7 di sistema non ha i certificati CA. Passo lo script a `curl` (che ha già funzionato) e rilancio quota e canali.

- 🔧 Bash: Rewrite the client on curl and call quota and distribution channels on staging

Staging accetta la chiave e risolve `staging.weebora.com`. Ora leggo il prodotto 118 per titolo e date accettate.

- 🔧 Bash: Fetch product 118 on staging and print its title, dates and availabilities

Prodotto confermato: finestra Bookable 8-13 dicembre 2026, durata 3 giorni. Apro il carrello con inizio 2026-12-08.

- 🔧 Bash: Create the cart for product 118 on staging

Carrello creato. Ora scorro la lista alloggi (tutte le pagine) e leggo lo snapshot del carrello.

- 🔧 Bash: List all accommodation pages sorted by price and read the cart snapshot

- 🔧 Bash: Fetch the recommended-sorted list, the preselected hotel detail and remaining quota

- 🔧 Bash: Open carts on another accepted date and two out-of-window dates to compare the cheapest hotel

- 🔧 Bash: Retry the accommodation list for the 11 December cart and check quota

Il carrello dell'11 dicembre offre un solo hotel (SB Plaza Europa, 207 EUR). Annoto il risultato in `docs/easter-eggs.md`, registro la decisione e committo.

- 🔧 Bash: Write the easter egg notes and decision entry, then commit them

Chiave 2 trovata. Il carrello aperto sulla data minima del prodotto offre come hotel più economico **`p_g_1d27qron`** (La França Travellers, 140 EUR). Ho annotato tutto in `docs/easter-eggs.md` e committato.

**Come ci sono arrivato**

- Il brand `staging.weebora.com` esiste solo nel CMS di staging, quindi ho usato `https://staging.api.hofj.com` con la chiave del client interno test-dev-2, mai letta né stampata.
- Il prodotto 118 dichiara una sola finestra Bookable, dall'8 al 13 dicembre 2026, durata 3 giorni.
- Carrello creato con inizio 2026-12-08 per 2 adulti in 1 camera. Lo snapshot del carrello ha già un hotel preselezionato, La França Travellers a 140 EUR. La lista alloggi mostra solo le 3 alternative, tutte più care.

| Hotel | Id | Prezzo (8 dic) |
|---|---|---|
| La França Travellers (preselezionato) | `p_g_1d27qron` | 140.00 EUR |
| SB Plaza Europa | `p_g_np3dww01` | 182.00 EUR |
| Leonardo Royal Hotel Barcelona Fira | `p_g_96y0wrm1` | 219.00 EUR |
| Estival Vilamarí | `p_g_y1zez6e1` | 291.00 EUR |

**Un'ambiguità da tenere presente.** Se la challenge intende "il più economico nella lista selezionabile" e non conta il preselezionato, la risposta è `p_g_np3dww01`. Proverei prima `p_g_1d27qron`, poi l'altro.

**Cosa ho scoperto provando altre date**

- L'11 dicembre il carrello offre un solo hotel, SB Plaza Europa a 207 EUR, e la lista è vuota. La risposta dipende quindi dalla data, e la data minima del prodotto è quella più "canonica".
- Il 14 dicembre viene rifiutato con un errore upstream "Periodo di prenotazione non valido", ma il 7 dicembre viene accettato pur essendo prima della data minima pubblicata.
- Un errore upstream di validazione arriva come 502 e non come 400, e la lista alloggi può andare in timeout al primo tentativo.

Quota consumata: 12 richieste, nessuna chiamata a pagamento o booking. Decisioni su ambiente e credenziali registrate in `docs/decisions.md`. Quando vuoi, passami la traccia della chiave 3.

## Utente 13:23

perfetto proseguiamo con la successiva!

## Agente 13:23

Non ho ancora il testo della traccia della chiave 3: nella challenge dovrebbe essersi sbloccato dopo l'inserimento di `p_g_1d27qron`. Incollami il testo della chiave 3 (titolo e descrizione) e ti dico anche se la chiave 2 è stata accettata così com'era.

## Utente 13:23

<pasted_content id="afac">
 The seal
  +60m
  A compiled artifact is served at /api/seal.wasm. It exports seal(ptr, len) and a memory. Feed it the key
  you just earned, a colon, then your email address, in UTF-8. The key is the value it returns, as eight
  lowercase hex digits.
</pasted_content id="afac">

## Agente 13:23

Classifico anche questa come **spike**: scaricare il wasm, capire cosa esporta e chiamarlo. Prima verifico dove è servito (`/api/seal.wasm` su quale host) e quale runtime ho a disposizione.

- 🔧 Bash: Probe candidate hosts for the seal.wasm file and check available wasm runtimes

- 🔧 Write /Users/matteodospina/.claude/plans/obiettivo-ricercare-degli-easter-melodic-meerkat.md

- 🔧 AskUserQuestion

- 🔧 Bash: Check that the challenge site serves the wasm file

- 🔧 Edit /Users/matteodospina/.claude/plans/obiettivo-ricercare-degli-easter-melodic-meerkat.md

- 🔧 ExitPlanMode

Scarico il wasm e lo ispeziono con Node: export, import e firma di `seal`.

- 🔧 Bash: Download the wasm module, hex-dump it and list its exports and imports

Nessun import, memoria da 1 pagina, `seal(i32,i32)->i32`: è un hash FNV-1a con un finalizer. Lo eseguo con l'input concordato, più le varianti di controllo.

- 🔧 Bash: Run the seal function on the agreed input and on control inputs

Deterministico e sensibile all'input. Annoto la chiave 3 nel documento e committo.

- 🔧 Bash: Append the key 3 notes to the easter egg doc and commit
