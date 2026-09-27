# Use case: scelta v3 (durata, ordinamento, livello, camere, budget, rifiuti)

Data: 2026-09-26. Origine: richiesta dell'utente del 2026-09-26 sui limiti del chooser v2
(`vela/domain/chooser.py`), del parser (`vela/domain/intent.py`), del rifiuto
(`vela/domain/refine.py`) e dell'acquisto (`vela/domain/purchase.py`, `rooms=1` fisso).
Decisioni in `docs/decisions.md` (2026-09-26, "Scelta v3"), requisiti in `docs/spec.md` §4.12
(RF-58..75) e RF-02, RF-04, RF-06..09, RF-12, RF-14, RF-39..41, RF-52..54. Implementazione:
roadmap M21, sei task nell'ordine A, E, B, D, C, F.

Stesso formato di `docs/usecases/agente-tool.md`: cosa dice il viaggiatore, la chiamata
dell'agente, cosa fa il server, cosa legge l'agente (`say`). Le frasi `say` sono indicative:
conta il contenuto, non la forma esatta. Le chiamate usano i nomi MCP; su REST valgono gli stessi
campi nel corpo JSON. Per ogni caso: varianti di frase, comportamento con solo testo e con campi
strutturati, test da scrivere.

Dati del catalogo usati qui (fixture `fixtures/catalog*.json`, contate il 2026-09-26):
`defaultDurationInDays` è su tutti i prodotti (= notti + 1, già letto come `duration_days`);
`maxPaxPerRoom` è valorizzato su 16 prodotti padel (sempre 2) e 4 tennis; `minPax` vale 2 su 15 prodotti padel;
`featured` è vero su 18 prodotti padel; `isSpecialOffer` è falso ovunque; `description` c'è su
quasi tutti e contiene "principianti", "tutti i livelli", "avanzat", "coach", "clinic",
"lezioni", "allenamenti". Tutti questi campi sono già nelle fixture: nessuna nuova registrazione.

Tempo di riferimento degli esempi: oggi 2026-09-26.

## UC-A — Durata

- **Utente.** "Un weekend di padel in Spagna a ottobre, siamo in due."
- **Varianti.**
  - it: "Cinque giorni di tennis in Sardegna a maggio"; "un ponte di padel a dicembre";
    "una settimana di tennis in Portogallo, siamo in due"; "3 o 4 notti di padel".
  - en: "A padel weekend in Spain in October for two"; "a week of tennis in Portugal";
    "four nights of padel in May".
- **Tabella delle durate** (notti; `duration_days` del prodotto = notti + 1):

  | Frase | `duration_min_nights` | `duration_max_nights` |
  |---|---|---|
  | weekend, fine settimana, weekend | 1 | 3 |
  | ponte, long weekend | 2 | 4 |
  | una settimana, a week | 6 | 8 |
  | N giorni, N days | N − 1 | N − 1 |
  | N notti, N nights | N | N |
  | N-M notti, da N a M notti | N | M |
  | almeno N notti, at least N nights | N | — |

- **Agente.** `create_intent(text="…", sport="padel", area="Spagna",
  period_start="2026-10-01", period_end="2026-10-31", pax=2, duration_min_nights=1,
  duration_max_nights=3)`, poi `get_proposal(intent_id)`.
- **Solo testo.** Il parser produce la stessa durata dalla tabella. "Weekend" non è più un
  periodo quando è preceduto da un articolo indeterminato ("un weekend", "a weekend"): è solo
  durata. "Questo weekend", "il prossimo weekend", "this weekend", "next weekend" restano
  anche un periodo (sabato-domenica prossimi), come oggi.
- **Campi strutturati.** `duration_min_nights`, `duration_max_nights` interi 1..30, min ≤ max;
  uno solo dei due è ammesso. Campo invalido scartato e dichiarato (RF-53). Campo e testo
  diversi: vince il campo, conflitto nei log.
- **Server.** La durata è un criterio morbido (RF-58): non esclude mai. Nell'ordinamento
  (UC-B) i prodotti con durata dentro [min, max] vengono prima. Un prodotto senza
  `defaultDurationInDays` (finestra fissa) usa la lunghezza della finestra.
- **Agente legge.**
  - Compatibile: "Ho capito: un viaggio di padel in Spagna a ottobre, da 1 a 3 notti, per 2
    persone. … Ti propongo <titolo>, 3 notti dal <data>…".
  - Nessuno compatibile (RF-59): "Non ho weekend di padel compatibili: questo dura 5 notti.
    Ti propongo …".
- **Test.**
  - Dominio: tabella del parser (tutte le righe sopra, it/en); "un weekend a ottobre" → periodo
    ottobre, durata 1..3; "questo weekend" → periodo + durata; chooser: a parità di area e
    budget vince il prodotto con durata compatibile anche se più caro; nessun prodotto
    compatibile → proposta comunque, motivazione con la frase di RF-59; campo invalido
    (`duration_min_nights=0`, min > max) scartato e nel `say`.
  - MCP: `create_intent` con `duration_*` → criteri nella risposta; schema dei tool con i due
    campi opzionali.
  - REST: `POST /v1/intents` con `duration_*` → 201 con i criteri; tipo sbagliato → 422.

## UC-B — Ordinamento

- **Utente.** "Padel in Italia a novembre, siamo in due." (nessun budget)
- **Varianti.**
  - it: "Tennis in Spagna la prima settimana di ottobre"; "padel dove vuoi a marzo".
  - en: "Tennis in Spain in early October"; "padel anywhere in March, two of us".
- **Ordine nuovo** (RF-60), dopo i filtri duri:
  1. area (dentro 3, stessa regione 2, stesso paese 1, altrove 0), decrescente;
  2. totale entro budget prima (nessun budget = tutti entro);
  3. durata compatibile prima (UC-A; nessuna durata chiesta = tutti compatibili);
  4. livello e lezioni compatibili prima (UC-C; nessuna preferenza = tutti compatibili);
  5. partenza più vicina all'inizio del periodo (senza periodo: più vicina a oggi);
  6. `featured` o `isSpecialOffer` prima;
  7. prezzo crescente;
  8. id.
- **Prodotti equivalenti** (RF-61). Stesso hotel, stesso titolo normalizzato (minuscole, senza
  spazi doppi) e stessa destinazione, prezzo entro il 5%: tra loro resta candidato solo quello
  con l'id numerico più basso; gli altri escono dalla scelta. La trappola 900078 (clone del 78,
  prezzo −1) non passa più davanti al 78. Il raggruppamento avviene dopo i filtri duri: se il
  78 è escluso (rifiutato, non prenotabile), il suo equivalente può essere proposto; un rifiuto
  `hotel` (UC-F) li esclude entrambi.
- **Agente.** `create_intent(text="…", sport="padel", area="Italia", period_start="2026-11-01",
  period_end="2026-11-30", pax=2)`, poi `get_proposal`.
- **Solo testo / campi strutturati.** Nessun campo nuovo: l'ordinamento è interno.
- **Server.** Senza budget il prezzo non decide prima di durata, partenza e `featured`: un
  prodotto che parte il 2 novembre batte uno che parte il 25 anche se costa di più.
- **Agente legge.** "Ti propongo <titolo> dal 2 novembre, 3 notti, <totale> in totale." La
  motivazione dice perché: "Parte il 2 novembre 2026, la prima partenza nel periodo che hai
  chiesto, con un totale a partire da <totale>" (M21-B: la frase dice la regola, non il mese;
  senza periodo "la prima partenza disponibile"; quando decide `featured`, "ed è tra i viaggi in
  evidenza del catalogo"; "la più economica compatibile" resta solo quando è vero).
- **Test.**
  - Dominio: una tabella di coppie di prodotti che differiscono per un solo livello
    dell'ordine, e per ognuna il vincitore atteso; senza budget, a parità di area e durata,
    vince la partenza più vicina anche se più cara; `featured` batte un prezzo più basso a
    parità dei livelli 1-5; trappola: catalogo con 78 e 900078 → proposto il 78; 78 rifiutato
    per date → proposto il 900078; 78 rifiutato per hotel → nessuno dei due; stessi ingressi
    danno sempre lo stesso risultato.
  - MCP / REST: un flusso replay con fixture e trappola (`add_trap`) che propone il 78.
  - Regressione: i test esistenti che fissano "il più economico dell'area" aggiornati ed
    elencati in `docs/decisions.md`.

## UC-C — Livello e lezioni

- **Utente.** "Siamo principianti, vorremmo lezioni di padel in Spagna a ottobre, in due."
- **Varianti.**
  - it: "Non abbiamo mai giocato, ci serve un maestro"; "giochiamo a livello intermedio,
    vorremmo allenarci con un coach"; "siamo agonisti, niente corsi per principianti".
  - en: "We're beginners and would like lessons"; "intermediate players, looking for a
    clinic"; "advanced players, no coaching needed".
- **Parser (richiesta).** `level`: `beginner` ("principiant*", "mai giocato", "alle prime armi",
  "beginner*", "never played"), `intermediate` ("intermedi*", "intermediate"), `advanced`
  ("avanzat*", "agonist*", "esperti", "advanced", "competitive"). `wants_coaching`: `true` con
  "lezion*", "maestr*", "coach*", "clinic", "corso", "allenarci", "lessons", "coaching",
  "training"; `false` con "niente corsi", "senza lezioni", "no coaching"; altrimenti non detto.
- **Etichette del prodotto (sync, RF-63).** Lette da `description` e `shortDescription`:
  `levels` ⊆ {`beginner`, `intermediate`, `advanced`, `all`} con le stesse radici più "tutti i
  livelli", "ogni livello", "all levels", "any level" → `all`; `coaching` vero con "coach*",
  "clinic", "lezion*", "maestr*", "allenament*", "lessons", "training". `levels_exclusive` vero
  solo con un'esclusione esplicita: "solo per avanzati", "riservato a giocatori esperti",
  "advanced players only", "not suitable for beginners". Esempio del catalogo: il 962 ("per
  giocatori di livello intermedio e avanzato") ha `levels = {intermediate, advanced}` ma non è
  esclusivo, quindi per un principiante è solo meno preferito. Nessuna parola → `levels` vuoto
  (sconosciuto), che conta come compatibile.
- **Agente.** `create_intent(text="…", sport="padel", area="Spagna",
  period_start="2026-10-01", period_end="2026-10-31", pax=2, level="beginner",
  wants_coaching=true)`.
- **Campi strutturati.** `level` (`beginner` | `intermediate` | `advanced`), `wants_coaching`
  (booleano). Valore fuori elenco scartato e dichiarato.
- **Server.** Filtro duro `level` solo per i prodotti `levels_exclusive` che non contengono il
  livello chiesto (RF-64); se azzera i candidati → `NoChoice("level")`. Negli altri casi
  preferenza (livello 4 dell'ordine di UC-B): compatibile = `levels` vuoto, contiene `all` o il
  livello chiesto; con `wants_coaching=true` conta anche `coaching`. `wants_coaching=false` non
  penalizza nessuno: la descrizione non dice in modo affidabile che le lezioni sono
  obbligatorie.
- **Agente legge.**
  - Compatibile: "… Ti propongo … Il programma è pensato anche per principianti e include
    lezioni o allenamenti." (M21-C: "lezioni o allenamenti", perché l'etichetta si accende anche
    su "allenamento"; con livello sconosciuto "Il programma non indica un livello di gioco…")
  - Non compatibile ma proposto: "Non ho trovato viaggi per principianti con lezioni: questo
    è pensato per giocatori intermedi e avanzati e include lezioni o allenamenti."
  - Nessuno: `NoChoice("level")` → "I viaggi compatibili sono riservati a giocatori avanzati.
    Vuoi cambiare qualcosa?"
- **Test.**
  - Dominio: tabella del parser (varianti sopra, it/en); tabella delle etichette su frasi vere
    del catalogo (962, 1027, 218, un "tutti i livelli", un prodotto senza parole); filtro duro
    solo con `levels_exclusive`; preferenza nell'ordinamento; `say` nelle tre forme; il sync
    salva le etichette e un nuovo sync le ricalcola.
  - MCP / REST: `level` e `wants_coaching` accettati e restituiti nei criteri; valore invalido
    scartato con il `say`.

## UC-D — Persone e camere

- **Utente.** "Padel in Portogallo a novembre, siamo in cinque."
- **Varianti.**
  - it: "Siamo tre amici, tennis a Maiorca"; "in quattro, due coppie"; "vado da solo, padel
    a Valencia".
  - en: "Five of us, padel in Portugal in November"; "three friends, tennis in Mallorca";
    "just me, padel in Valencia".
- **Agente.** Con pax > 2 l'agente chiede "In quante camere?" prima di chiamare il tool (la
  descrizione di `create_intent` lo dice), poi `create_intent(text="… Siamo in cinque. Tre
  camere.", sport="padel", area="Portogallo", period_start="2026-11-01",
  period_end="2026-11-30", pax=5, rooms=3)`.
- **Rete di sicurezza.** Se l'agente chiama con pax > 2 e senza `rooms`, e il testo non le dice,
  il server risponde `question` "In quante camere?" / "How many rooms?" e **non salva
  l'intento**, come per lo sport (RF-04, RF-65). Ordine delle domande: sport, persone, camere.
  Con pax ≤ 2 e senza `rooms` il default è 1 camera, senza domanda.
- **Solo testo.** "Due camere", "tre stanze", "two rooms", "una matrimoniale e una doppia" (= 2)
  → `rooms`. "Due coppie" → 2 camere.
- **Campi strutturati.** `rooms` intero 1..pax su `create_intent`, `reject_proposal` e
  `accept_proposal`; fuori intervallo scartato e dichiarato. Su `accept_proposal` vale come
  correzione dell'ultimo momento e deve rispettare il minimo del prodotto (sotto), altrimenti
  risposta `question` con il minimo e nessun ordine.
- **Server.**
  - Chooser (RF-66): per un prodotto con `maxPaxPerRoom` servono almeno
    ceil(pax / `maxPaxPerRoom`) camere. Se `rooms` è minore il prodotto è escluso (filtro duro
    `rooms`, dopo `pax`); se azzera i candidati → `NoChoice("rooms")`. Prodotti senza
    `maxPaxPerRoom` accettano qualunque numero di camere.
  - Proposta: la risposta riporta `rooms`.
  - Acquisto (RF-67): l'ordine salva `rooms`; il job d'acquisto passa `rooms` reale a
    `POST /v1/itineraries` invece di 1.
  - "Da solo" (RF-68): pax = 1 con i soli prodotti a `minPax` 2 compatibili → `NoChoice("pax")`.
- **Agente legge.**
  - "Ho capito: un viaggio di padel in Portogallo a novembre per 5 persone in 3 camere…"
  - Con `maxPaxPerRoom`: "Le camere di questo viaggio ospitano al massimo 2 persone: per 5
    servono almeno 3 camere, come hai chiesto."
  - `NoChoice("rooms")`: "I viaggi compatibili hanno camere da massimo 2 persone: per 5
    persone servono almeno 3 camere. Vuoi cambiare il numero di camere?"
  - Da solo: "I viaggi di padel compatibili partono da 2 persone: da solo non posso
    prenotarli. Vuoi cambiare qualcosa?"
- **Test.**
  - Dominio: pax 5 senza `rooms` → `question`, nessun intento salvato; pax 2 senza `rooms` →
    1 camera; parser di "tre camere", "two rooms", "due coppie"; filtro `rooms` con
    `maxPaxPerRoom` 2 (5 persone, 2 camere → escluso; 3 camere → ammesso); `NoChoice("rooms")`
    e `NoChoice("pax")` con i `say`; job d'acquisto chiama `create_itinerary` con `rooms=3`
    (HofJ finto); `accept_proposal` con `rooms` sotto il minimo → `question`, nessun ordine.
  - MCP: descrizione di `create_intent` con la domanda sulle camere; `rooms` negli schemi di
    `create_intent`, `reject_proposal`, `accept_proposal`.
  - REST: `POST /v1/intents` con `pax: 5` senza `rooms` → 200 `question`; con `rooms: 3` →
    201; `POST /v1/proposals/{id}/accept` con `rooms`.
  - Postgres: l'ordine salva e rilegge `rooms` (migrazione 0011).

## UC-E — Budget a testa o totale

- **Utente.** "Tennis in Spagna a maggio, siamo in tre, massimo 600 euro."
- **Varianti.**
  - it: "600 euro a testa"; "1.800 euro in tutto"; "non più di 600 a persona"; "budget
    totale 1.500".
  - en: "600 euros each"; "1,800 in total"; "up to 600 per person"; "total budget 1,500".
- **Regole** (RF-69), in ordine:
  1. campo `budget_scope` valido (`per_person` | `total`) → vince;
  2. "a testa", "a persona", "per persona", "each", "per person", "per head", "pp" → per persona
     (già riconosciuto oggi);
  3. "in tutto", "totale", "in totale", "complessivi", "in total", "total", "altogether" →
     totale;
  4. cifra sola con pax > 1: il server calcola il prodotto compatibile più economico (filtri
     duri senza budget); se la cifra letta come totale non copre neanche il suo totale
     (prezzo × pax) ma letta a persona sì, → per persona; altrimenti totale;
  5. pax = 1 o pax non detto: totale (le due letture coincidono).
- **Agente.** `create_intent(text="…", sport="tennis", area="Spagna", period_start="2026-05-01",
  period_end="2026-05-31", pax=3, budget=600)`; se l'utente l'ha detto, anche
  `budget_scope="per_person"` o `"total"`.
- **Server.** Nei criteri `budget` resta il tetto totale usato dal chooser (600 × 3 = 1800 se
  per persona) e `budget_scope` dice come è stato letto; la regola 4 si applica in
  `create_intent`, quando il catalogo è disponibile, e il risultato si salva nei criteri. Su
  `reject_proposal` valgono le stesse regole per una cifra nuova nel motivo o nei campi.
- **Agente legge** (RF-70, sempre, anche con le regole 1-3): "Ho capito: un viaggio di tennis
  in Spagna a maggio per 3 persone con un budget di 600 euro a persona, 1800 in tutto." oppure
  "… con un budget di 600 euro in tutto per 3 persone." Il viaggiatore sente l'interpretazione
  e la corregge con `reject_proposal(…, budget_scope="total")`.
- **Test.**
  - Dominio: tabella delle frasi (regole 2-3, it/en); regola 4 con un catalogo finto in cui il
    più economico costa 400 a persona (600 in tre → per persona) e 150 a persona (600 → totale);
    pax 1 → totale; campo `budget_scope` che vince sul testo con conflitto nei log; `say` con
    l'interpretazione in tutti i casi; rifiuto con `budget_scope` che ricalcola il tetto.
  - MCP / REST: `budget_scope` accettato su `create_intent` e `reject_proposal`, restituito nei
    criteri; valore invalido scartato.

## UC-F — Rifiuti con motivo sempre capito

Ogni rifiuto ha un tipo (`reject_kind`, RF-71): `price`, `place`, `hotel`, `dates`,
`duration`, `sport`, `pax`, `level`, `direction`, `other`. Il campo dell'agente vince sul testo;
senza campo, `refine.py` classifica il motivo con regole it/en. Se il motivo tocca più tipi
("troppo caro e troppo lontano"), tutti i criteri cambiano come oggi e il tipo registrato è il
primo nell'ordine dell'elenco sopra. Il tipo si salva sul rifiuto (migrazione 0013).

### F1 — Hotel

- **Utente.** "L'hotel non mi piace."
- **Varianti.** it: "quell'albergo no", "vorrei un altro hotel"; en: "I don't like the hotel",
  "another hotel please".
- **Agente.** `reject_proposal(proposal_id, reason="L'hotel non mi piace", reject_kind="hotel")`.
- **Server** (RF-72). Esclusi dalle proposte successive tutti i prodotti con lo stesso hotel
  del prodotto rifiutato (confronto sul nome normalizzato); criteri invariati. Esclusione
  ricavata dai rifiuti, come il tetto di prezzo (decisione M7). Prodotto senza hotel → si
  esclude solo il prodotto.
- **Agente legge.** "Ho escluso i viaggi all'<hotel del prodotto rifiutato>. Ti propongo …"
- **Test.** Dominio: tre prodotti, due con lo stesso hotel → dopo il rifiuto nessuno dei due;
  testo senza campo classificato `hotel`; `NoChoice` con `failed_criterion` `hotel` quando
  restano solo prodotti di quell'hotel. MCP / REST: `reject_kind` accettato.

### F2 — Luogo escluso, area padre mantenuta

- **Utente.** (dopo una proposta a Estepona) "Estepona no, ma la Spagna va bene."
- **Varianti.** it: "non a Estepona", "ovunque tranne Estepona"; en: "not Estepona, Spain is
  fine", "anywhere but Estepona". Marbella non è nel dizionario `geo`: la frase della richiesta
  ("Marbella no") funziona solo dopo averla aggiunta a `geo` (Costa del Sol), in M21-F.
- **Agente.** `reject_proposal(proposal_id, reason="Estepona no, ma la Spagna va bene",
  reject_kind="place")`. Con `reject_kind="place"` e senza `area` il luogo escluso è quello del
  prodotto rifiutato; con `area` è il nuovo luogo richiesto, come oggi.
- **Server** (RF-73). Il luogo va in `excluded_areas` (criteri, lista); `area` resta quella
  dell'intento (Spagna). Filtro duro: esclusi i prodotti dentro un'area esclusa; se azzera i
  candidati → `NoChoice("place")`. Solo testo: un luogo preceduto o seguito da negazione ("X
  no", "non a X", "tranne X", "not X", "but X") è un'esclusione; oggi invece diventa la nuova
  area (difetto corretto).
- **Agente legge.** "Ho capito: un viaggio di padel in Spagna, esclusa Estepona … Ti propongo …"
- **Test.** Dominio: negazione it/en → `excluded_areas`, area invariata; luogo senza negazione
  → nuova area (comportamento di oggi); esclusione di una regione esclude le sue città;
  `NoChoice("place")`. MCP / REST: `reject_kind="place"` senza `area`.

### F3 — Stesso viaggio, altre date

- **Utente.** "Questo mi piace ma non posso in quelle date."
- **Varianti.** it: "tienimi questo viaggio, quando altro è disponibile?", "stesso viaggio
  ma a novembre"; en: "I like this one, but I can't make those dates", "when else is it
  available?", "same trip in November".
- **Agente.** `reject_proposal(proposal_id, reason="…", reject_kind="dates",
  keep_product=true)`; con un periodo nuovo anche `period_start`, `period_end`.
- **Server** (RF-74). Il rifiuto si registra con `keep_product`; il prodotto non è escluso, è
  esclusa solo la finestra proposta (inizio e fine della proposta rifiutata). La proposta
  successiva è lo **stesso prodotto** con la prima partenza valida diversa dalle finestre
  escluse, nel periodo dei criteri (o nel periodo nuovo detto nel motivo o nei campi).
  Nessuna partenza → `NoChoice("dates")` con `rejected_proposal_id`: l'agente può richiamare
  `reject_proposal` sulla stessa proposta con `keep_product=false`, che aggiorna il rifiuto
  esistente (RF-55) e propone un altro viaggio. Solo testo: "mi piace", "tieni(mi) questo",
  "stesso viaggio", "quando altro", "altre date", "I like", "same trip", "when else", "other
  dates" → `keep_product=true`.
- **Agente legge.** "Stesso viaggio, <titolo>, con la partenza successiva: dal <data>, 3
  notti…" oppure "Questo viaggio non ha altre partenze a ottobre. Vuoi che cerchi
  un altro viaggio?"
- **Test.** Dominio: prodotto con tre finestre → dopo il rifiuto la seconda, poi la terza,
  poi `NoChoice("dates")`; periodo nuovo nel motivo → prima finestra nel periodo nuovo;
  `keep_product=false` sulla stessa proposta → prodotto escluso, un solo rifiuto registrato;
  frasi it/en → `keep_product`. MCP / REST: `keep_product` nello schema. Postgres: il
  rifiuto salva `kind` e `keep_product`.

### F4 — Motivo non capito: domanda chiusa

- **Utente.** "Non mi convince."
- **Varianti.** it: "mah, non so", "non fa per me"; en: "not convinced", "not for me",
  "meh".
- **Agente.** `reject_proposal(proposal_id, reason="Non mi convince")`, senza `reject_kind`.
- **Server** (RF-75). Il motivo non si classifica e non c'è `reject_kind`: il server **non
  registra il rifiuto**, non cambia i criteri, non cancella un ordine `queued` (eccezione a
  RF-49) e risponde `question` con lo stesso `proposal_id`: "Cosa non ti convince: il posto,
  l'hotel, le date o il prezzo?". La proposta resta aperta e accettabile.
- **Seconda chiamata.** L'agente pone la domanda e richiama `reject_proposal` sulla stessa
  proposta con motivo originale più risposta (e il `reject_kind` corrispondente). Se il
  viaggiatore non sa dirlo, l'agente passa `reject_kind="other"`: il server registra il
  rifiuto, esclude solo quel prodotto e propone il successivo, come fa oggi (RF-54). Così la
  domanda si fa una volta sola.
- **Agente legge.** "Cosa non ti convince: il posto, l'hotel, le date o il prezzo?"
- **Test.** Dominio: motivo non classificabile → `question` con `proposal_id`, nessun rifiuto
  nel repository, criteri invariati, ordine `queued` ancora `queued`; seconda chiamata con
  "l'hotel" → rifiuto `hotel`; `reject_kind="other"` → comportamento di oggi. MCP: descrizione
  di `reject_proposal` con la domanda e con `reject_kind="other"` come uscita. REST: 200
  `question` con `proposal_id`.

### Altri tipi

`price`, `direction`, `sport`, `pax`, `duration`, `level` si comportano come oggi o come nei
casi A-E: il testo o il campo aggiornano il criterio corrispondente. `duration` senza numeri
("troppo lungo", "troppo corto", "too long", "shorter") sposta la durata: più corta = max
notti del prodotto − 1, più lunga = min notti del prodotto + 1. `level` senza livello ("troppo
difficile", "too advanced") abbassa di un livello rispetto al prodotto rifiutato.
Test: tabella di classificazione (una frase it e una en per tipo) e per ognuna il criterio
cambiato.

## Cambi di interfaccia pubblica (riepilogo)

Dettaglio in `docs/spec.md` §4.12. Additivi: i campi nuovi di `create_intent`,
`reject_proposal`, `accept_proposal`; i campi nuovi nei criteri e nella proposta; i valori nuovi
di `failed_criterion`. **Non additivi**: la domanda sulle camere con pax > 2 (un client che oggi
manda `pax=5` riceve una `question` invece dell'intento); la `question` restituita da
`reject_proposal` (un client che si aspetta solo `proposal` o `no_match` deve gestirla); "un
weekend" che non è più un periodo; `excluded_areas` al posto della nuova area per un luogo
negato; l'ordinamento senza budget non più guidato dal prezzo.
