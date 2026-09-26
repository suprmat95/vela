# Task M10 multi-brand HofJ

- Sessione: `a708c644-423d-419b-9cd6-1af5d89fd32e`
- Inizio: 2026-09-26 11:38

## Utente 11:38

<pasted_content id="768d">
Voglio aggiornare la task M10 in docs/roadmap.md per supportare più brand HofJ.
Per ora aggiorna SOLO la documentazione, non scrivere codice. Branch: doc/m10-multibrand.

## Contesto
- Su HofJ ogni brand ha un catalogo separato. Padel = Weebora, tennis = Terrarossa.
  - Produzione (api.hofj.com): weebora.com, terrarossa.com
  - Staging (staging.api.hofj.com): staging.weebora.com, staging.tennis.weebora.com
  (vedi i log di M1/M8 in agent-log/)
- Oggi Vela usa un solo brand (HOFJ_BRAND) e carica il catalogo dalla fixture al boot
  (decisione M7). Per questo su claude.ai il tennis non si trova mai.
- Obiettivo: se l'utente chiede tennis, Vela cerca in Terrarossa; se chiede padel, cerca in
  Weebora; con sport=any cerca in entrambi.
- Le decisioni del contratto agente-tool sono già in docs/decisions.md e nella task M17:
  lo sport è sempre indispensabile (RF-04 modificata) e "indifferente" diventa sport=any.

## Modifiche da proporre per M10 ("Sync multi-brand del catalogo da HofJ")
1. Config: mappa sport → brand (es. HOFJ_BRANDS="padel=...,tennis=...") al posto di
   HOFJ_BRAND. Proponi il formato.
2. Il sync scorre i brand: lista e dettaglio con ?brand=<brand> per ciascuno, poi scrittura
   nella stessa tabella products.
3. products: nuova colonna `brand` (migrazione Alembic 0006). Lo sport si ricava dal brand;
   detect_sport resta solo come fallback.
4. Id prodotto: verificare se sono unici fra i brand. Se non lo sono, servono una chiave
   (brand, id) o un id con prefisso. Dammi le opzioni.
5. Carrello: un client HofJHttp per ogni brand e un router che sceglie il client dal brand
   del prodotto (ordine → product_id → products.brand), così il brand sopravvive a riavvii e
   retry dei job. HofJPort resta invariato, a meno che tu non veda un motivo per cambiarlo.
6. Fixture: una per (host, brand), rigenerata dallo stesso codice del sync;
   select_fixture/replay vanno adattati. Le fixture servono solo per replay/test.
7. Chooser, MCP e REST non cambiano in M10: il filtro sport basta (sport=any = nessun filtro).
8. Test di completamento da aggiungere: sync con due brand finti; un ordine tennis usa il
   client Terrarossa in tutte le chiamate del carrello; una ricerca con sport=any restituisce
   prodotti di entrambi i brand; un retry del job di booking dopo un riavvio usa ancora il
   brand giusto.

## Use case da scrivere in docs/usecases/multi-brand.md (referenziati da M10)
Funzionano col multi-brand: tennis esplicito; padel esplicito; in inglese; cambio di sport
dopo un rifiuto ("preferisco il tennis", via reject_proposal); sport=any ("mi è
indifferente") → entrambi i cataloghi; sport assente (con o senza periodo) → domanda "Padel
o tennis?"; nessun match → messaggio "sport_value" esistente.
Le decisioni sul parser (sinonimi, "padel e tennis", beach/paddle tennis, tornei) sono in
M17: non vanno in M10, al massimo un rimando.

## Prima di modificare
- Leggi docs/spec.md §4.6 e §4.8, docs/roadmap.md M10 e M17, docs/decisions.md (M7 e
  contratto agente-tool), vela/app.py (build_hofj, realign_catalog), vela/domain/catalog.py,
  vela/adapters/hofj_http.py, vela/adapters/schema.py.
- Proponimi le modifiche in pochi punti: cosa cambia in M10 (Risultato, Scope, Test, Copre,
  Prompt), se la taglia M è ancora giusta, cosa succede in spec.md (RF da aggiungere o
  modificare).
- Le decisioni aperte (formato config, chiave degli id) presentale con 2-3 opzioni e una
  raccomandazione.
- Dopo il mio OK: aggiorna roadmap.md e spec.md, registra le decisioni in docs/decisions.md
  e fai un commit piccolo.
- Non fare chiamate HofJ. Per verificare gli id fra i brand dimmi prima quali chiamate
  servono e quante, e aspetta il mio OK.
</pasted_content id="768d">

## Agente 11:38

- 🔧 Bash: List docs and sizes of files to read

- 🔧 Bash: Show headings of roadmap, spec, decisions

- 🔧 Bash: Read roadmap intro, M7-M10, M17 and matrix

- 🔧 Bash: Read spec sections and decisions

- 🔧 Bash: Read app, catalog, HofJ adapter, schema

Sto leggendo il codice e i documenti richiesti; ora controllo fixture, `docs/api/` e i log di M1/M8 per capire cosa si sa già sugli id tra i brand.

- 🔧 Bash: Inspect fixtures and grep brand mentions

- 🔧 Bash: Read API notes on channels and ids

- 🔧 Bash: Count sports in fixtures, find HOFJ_BRAND usages

- 🔧 Bash: Find HofJ call sites and port methods

- 🔧 Bash: Find brand mentions in spec and roadmap; usecase format

Ho letto tutto quello che mi hai indicato. Prima di proporre, quattro cose che ho trovato e che cambiano la proposta:

- **Le fixture non contengono nessun prodotto di tennis.** Sia `catalog.json` (produzione, `it`) sia `catalog-staging.json` risultano 100% padel con `detect_sport`. Il tennis quindi non manca solo su claude.ai in live: manca anche in replay.
- **5 metodi di `HofJPort` su 7 ricevono solo `itinerary_id`** (`set_customer`, `get_pax`, `set_pax`, `get_itinerary`, `create_booking`). Solo `create_itinerary` riceve il `Product`. Un router con la porta invariata dovrebbe quindi ricavare il brand dall'itinerario leggendo il DB.
- **Lo spazio degli id sembra condiviso fra i canali, ma non è verificato.** Il canale 3 ha l'id 431, che non è nella lista Weebora; i cataloghi `it` ed `en` hanno id diversi (181-1093 contro 12-1088). Sembra un'unica tabella CMS.
- **`spec.md` §7 mette "più brand" fuori scope**, e anche M15 (riga 543) lo elenca tra i prossimi passi: vanno corretti entrambi.

## Decisioni aperte

**D1 — Formato della config**
- **A) `HOFJ_BRANDS="padel=weebora.com,tennis=terrarossa.com"`**: una sola variabile, una chiave in `render.yaml`. Validazione: sport in {padel, tennis}, brand distinti, almeno una voce.
- B) Due variabili, `HOFJ_BRAND_PADEL` e `HOFJ_BRAND_TENNIS`: semplice, ma ogni nuovo sport richiede una variabile nuova.
- C) JSON in una variabile: scomodo da quotare in shell e su Render.

Raccomando **A**. `HOFJ_BRAND` viene rimossa: se è impostata senza `HOFJ_BRANDS`, l'app non parte e il messaggio dice perché (nessuna compatibilità silenziosa). Con una sola voce (solo padel), il tennis dà il `no_match` "sport" esistente.

**D2 — Chiave degli id**
- **A) Id HofJ come chiave primaria + colonna `brand`.** Il sync si ferma con un errore esplicito se lo stesso id arriva da due brand. Nessuna FK cambia.
- B) Chiave composta `(brand, id)`: `proposals`, `orders` e `rejections` hanno una FK su `products.id`, quindi servirebbe `brand` in 4 tabelle, con relativi repository e test.
- C) Id con prefisso, più una colonna `hofj_id`: cambia gli id pubblici e le righe già su Render. Attenzione alla lunghezza: `staging.tennis.weebora.com:900078` sono 33 caratteri contro `String(32)`, quindi servirebbe un prefisso corto (`t:`/`p:`).

Raccomando **A se la verifica conferma l'unicità**, altrimenti C con prefisso corto.

**D3 — Router del carrello** (qui vedo un motivo per non lasciare tutto invariato)
- A) Il router implementa `HofJPort` e ricava il brand dall'`itinerary_id` con una query (`orders.itinerary_id → product_id → products.brand`). La porta non cambia, ma l'adapter dipende dai repository. C'è anche un rischio: se una chiamata parte prima che `itinerary_id` sia salvato, la ricerca fallisce.
- **B) `HofJPort` invariata, più una piccola porta nuova `HofJRouter`** con `client(brand) → HofJPort` e `get_quota()`. `PurchaseJob` e `BookingJob` ricavano il brand da ordine → prodotto (lo caricano già) e usano quel client per tutte le chiamate. Il brand viene dal DB a ogni esecuzione del job, quindi regge riavvii e retry.
- C) Parametro `brand` su ogni metodo della porta: invasivo.

Raccomando **B**: esplicita, senza query nascoste nell'adapter. La quota è per chiave API, quindi resta una sola (`get_quota` da un client qualsiasi). In replay tutti i brand puntano allo stesso `ReplayHofJ`.

**D4 — Righe esistenti su Render.** La migrazione 0006 aggiunge `brand` nullable; il primo sync la riempie. Se `brand` è NULL, il router usa il brand dello sport del prodotto (`products.sport` → mappa della config).

## Modifiche a M10 ("Sync multi-brand del catalogo da HofJ")

- **Risultato:** il catalogo in Postgres contiene tutti i brand configurati; il tennis si trova in Terrarossa e il padel in Weebora; ogni chiamata di carrello e prenotazione usa il brand del prodotto, anche dopo un riavvio.
- **Scope:** i tuoi 8 punti, più:
  - archiviazione dei prodotti mancanti **per brand**: il sync di Terrarossa non archivia Weebora, e un brand che fallisce non archivia nulla;
  - in live il sync sostituisce `realign_catalog` e la fixture;
  - in replay si caricano tutte le fixture dell'host (fixture di produzione per Weebora e Terrarossa);
  - `is_trip`: la gift card di un brand qualsiasi, non solo "Weebora";
  - `render.yaml`, `docs/fixtures.md` e la registrazione delle fixture Terrarossa e `staging.tennis.weebora.com`, con le chiamate dichiarate.
- **Test:** i tuoi 4, più l'archiviazione per brand con un brand che fallisce e la config invalida che blocca l'avvio.
- **Copre:** RF-28..32, RF-56 (nuovo).
- **Prompt:** aggiornato con le letture e il rimando a `docs/usecases/multi-brand.md`.
- **Taglia: da M a L.** Al sync incrementale si aggiungono config, migrazione, router, fixture per brand e replay multi-fixture. Si potrebbe separare "multi-brand" da "sync incrementale", ma lo terrei in una task sola come l'hai impostata.

## Cosa cambia in `spec.md`

- RF-28: aggiungere `brand`; lo sport si ricava dal brand della config, `detect_sport` resta solo come fallback.
- RF-29: lista e dettaglio per ogni brand della mappa, con `?brand=`.
- RF-31: archiviazione per brand.
- RF-32: una fixture per (host, brand).
- **RF-56 nuovo:** carrello e prenotazione usano il brand del prodotto (`orders → products.brand`), anche dopo riavvii e retry.
- §6: `HOFJ_BRANDS` al posto di `HOFJ_BRAND`.
- §7: togliere "più brand" dal fuori scope, e aggiornare di conseguenza anche M15 e la matrice.

## Use case (`docs/usecases/multi-brand.md`, MB1-MB8)

Tennis esplicito, padel esplicito, in inglese, cambio di sport via `reject_proposal`, `sport=any`, sport assente senza periodo, sport assente con periodo, nessun match (`sport_value`). Stesso formato di `agente-tool.md`. Per sinonimi e tornei solo un rimando a M17.

## Verifica degli id: chiamate proposte (non ancora fatte)

1. Produzione: `GET /v1/quota` ×1, poi `GET /v1/products?brand=terrarossa.com&locale=it&limit=100`, 1-2 pagine. Confronto gli id con `fixtures/catalog.json`.
2. Staging: `GET /v1/quota` ×1, poi `GET /v1/products?brand=staging.tennis.weebora.com&locale=en&limit=100`, 1-2 pagine. Confronto con `catalog-staging.json`.

In totale **4-6 chiamate autenticate**: niente dettagli, niente carrelli, risposte tenute fuori dal repo. Servono anche a confermare che i cataloghi tennis sono tutti tennis.

Per procedere mi servono le tue scelte su D1-D4 (le mie raccomandazioni sono A, A, B e il fallback sullo sport) e l'OK sulle 4-6 chiamate, oppure l'indicazione di lasciare D2 aperta per il brainstorm di M10. Dopo il tuo OK creo `doc/m10-multibrand` da `doc/m10`, aggiorno `roadmap.md`, `spec.md` e `decisions.md`, scrivo il file dei casi d'uso e faccio un commit piccolo.

## Utente 11:41

ok

## Agente 11:41

Procedo: creo il branch, poi faccio la verifica degli id (4-6 chiamate) e infine scrivo i documenti.

- 🔧 Bash: Create branch, check how scripts load key

La chiave HofJ non è nell'ambiente e io non apro `.env`: preparo uno script di verifica da farti lanciare, e intanto scrivo i documenti.

- 🔧 Bash: Read api_explore Client and QuotaGuard

- 🔧 Bash: Read rest of Client.get

- 🔧 Write /private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-doc-m10/a708c644-423d-419b-9cd6-1af5d89fd32e/scratchpad/verify_brand_ids.py

Script pronto. Mentre aspetti di lanciarlo, scrivo i documenti; la decisione D2 la chiudo col risultato.

- 🔧 Bash: Read spec §6-7, roadmap M15 and M1, usecase examples

- 🔧 Bash: Find the sport_value no-match message

Ora scrivo il file dei casi d'uso.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/doc-m10/docs/usecases/multi-brand.md

Adesso riscrivo la sezione M10 della roadmap.

- 🔧 Bash: Replace M10 section and related roadmap lines

- 🔧 Bash: Fix graph alignment and shared-file notes

Ora `spec.md`.

- 🔧 Bash: Check spec header and RF-14/23 lines

- 🔧 Bash: Read spec §4.3-4.5

- 🔧 Bash: Update spec.md RF-28..32, RF-56, §6, §7

Scrivo la voce in `decisions.md`; la riga sulla chiave degli id la completo col risultato della verifica.

- 🔧 Bash: Append M10 multi-brand decisions entry

Ho scritto roadmap, spec, casi d'uso e decisioni, ma non ho ancora fatto il commit: manca la verifica degli id. La chiave HofJ non è nell'ambiente di questa sessione e `.env` non lo apro, quindi non ho fatto nessuna chiamata.

**Lo script da lanciare** è in scratchpad:
- per ogni host fa 1 chiamata a `/v1/quota` e 1-2 pagine della lista tennis (al massimo 3, poi si ferma): in totale 4-6 chiamate autenticate, niente dettagli né carrelli;
- confronta gli id con le fixture padel e stampa solo conteggi, id in comune e sport rilevati;
- legge la chiave da `HOFJ_API_KEY` o `API_BEAR_KEY` senza stamparla e salva le risposte fuori dal repo.

Lancialo dal prompt con la chiave nell'ambiente, come fai di solito:

```
! python3 /private/tmp/claude-501/-Users-matteodospina-orca-workspaces-vela-doc-m10/a708c644-423d-419b-9cd6-1af5d89fd32e/scratchpad/verify_brand_ids.py
```

(per esempio anteponendo `HOFJ_API_KEY=…`, o dopo aver caricato il tuo `.env` nella shell).

**Cosa ho scritto sul branch `doc/m10-multibrand`:**
- `docs/roadmap.md`: M10 riscritta ("Sync multi-brand", taglia L) con Risultato, Scope, Test, Copre, Prompt. Aggiornati anche la tabella, la nota sui file comuni (ora `usecases.py`, non più `chooser.py`), la riga di M17, M15 (tolto multi-brand dai prossimi passi) e la matrice (RF-56).
- `docs/spec.md`: modificati RF-28..32, aggiunta la nuova RF-56 (brand del prodotto per carrello e prenotazione), in §6 `HOFJ_BRANDS` al posto di `HOFJ_BRAND`, e in §7 i brand HofJ di padel e tennis non sono più fuori scope.
- `docs/usecases/multi-brand.md`: MB1-MB8, con il rimando a M17 per il parser.
- `docs/decisions.md`: la voce "M10: sync multi-brand", con la riga "Chiave degli id" ancora da completare.

**Cosa succede col risultato:**
- **Nessun id in comune:** la chiave resta l'id HofJ con la colonna `brand` (opzione A), il sync si ferma se trova un duplicato, e registro l'esito nella decisione.
- **Id in comune:** si passa all'id con prefisso corto (C) e ti propongo come aggiornare RF-28 prima di scriverlo.

Nei due casi faccio poi il commit unico dei quattro file.

**Dubbio aperto:** lo script dice se il catalogo Terrarossa è tutto tennis solo con `detect_sport`, che senza la parola "tennis" nel testo classifica il prodotto come padel. Se i titoli non la contengono, il conteggio sottostimerà il tennis: in quel caso guardo a mano qualche titolo tra le risposte salvate.

## Utente 11:45

lancia tu il teste

## Agente 11:46

- 🔧 Bash: Run the brand id verification script

Ho lanciato lo script, ma si è fermato prima di fare qualunque chiamata con `manca HOFJ_API_KEY (o API_BEAR_KEY)`. Le mie shell partono dal tuo profilo e lì la chiave non c'è; in questo worktree non c'è nemmeno un `.env`. Nessuna chiamata HofJ è partita.

Per lanciarlo io ho due strade:

1. **Mi autorizzi a caricare il `.env` senza leggerlo**: carico le variabili con `set -a; . <percorso>/.env; set +a` nello stesso comando dello script, senza mai stamparne il contenuto. È un'eccezione alla regola "never open .env" del CLAUDE.md, quindi serve il tuo sì esplicito e il percorso del file.
2. **Lo lanci tu** con il comando `! …` del messaggio precedente. L'output finisce direttamente nella conversazione e io proseguo da lì.

Io sceglierei la 2, perché rispetta la regola senza eccezioni. Quale preferisci?

## Utente 11:46

autorizzo

## Agente 11:46

- 🔧 Bash: Locate .env files in worktrees without reading them

Uso il `.env` del checkout principale (`/Users/matteodospina/orca/vela/.env`), caricato senza stamparlo.

- 🔧 Bash: Run id verification with env loaded silently

Il handshake TLS è fallito prima di inviare qualsiasi richiesta: al Python 3.7 di sistema mancano i certificati CA. Quindi nessuna chiamata consumata. Cerco un bundle CA da usare.

- 🔧 Bash: Find a CA bundle for Python TLS

- 🔧 Bash: Rerun verification with certifi CA bundle

Nessun id in comune, con 4 chiamate. Controllo i titoli dei prodotti che `detect_sport` ha classificato padel nei cataloghi tennis.

- 🔧 Bash: List tennis-catalog products misdetected as padel

Verifica chiusa: nessun id in comune, e i titoli confermano che lo sport va preso dal brand. Completo la decisione e faccio il commit.

- 🔧 Bash: Fill id decision and commit docs
