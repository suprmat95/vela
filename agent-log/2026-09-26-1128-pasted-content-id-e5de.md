# Contratto agente-tool e sinonimi dello sport

- Sessione: `06396f26-5b58-42d9-8dcd-1edce5199353`
- Inizio: 2026-09-26 11:28

## Utente 11:28

<pasted_content id="e5de">
Voglio registrare nella documentazione le decisioni sul contratto tra l'agente e i tool MCP
e creare una nuova task M17 in docs/roadmap.md. Per ora aggiorna SOLO la documentazione,
non scrivere codice. Branch: doc/agent-contract.

## Problema osservato 
L'utente ha rifiutato una proposta ("troppo caldo, vorrei un posto più freddo"). L'agente ha
"riformulato" chiamando create_intent invece di reject_proposal: il nuovo intento non ha
rifiuti, il chooser è deterministico, ed è tornata la stessa proposta. In più "più freddo"
non è capito né da intent.py né da refine.py. E lo sport non era mai stato chiesto: con il
periodo presente la RF-04 attuale non lo richiede.

## Decisioni già prese (da registrare in docs/decisions.md)
1. Parametri strutturati opzionali su create_intent e reject_proposal (MCP e REST, stesso
   contratto): sport (padel | tennis | any), area, period_start, period_end, pax, budget.
   text/reason restano, sempre passati. Modifica additiva: i client che mandano solo testo
   funzionano come oggi.
2. Precedenza sul server: campi strutturati validi > parser deterministico > fallback Haiku.
   Un campo invalido (es. area sconosciuta a geo) viene scartato, non blocca, e il `say` lo
   dichiara. In caso di conflitto testo/campo vince il campo e il conflitto va nei log.
3. Il `say` ripete sempre i criteri capiti (sport, area, periodo, persone, budget), così
   l'utente vede e corregge eventuali campi inventati dall'agente.
4. RF-04 modificata: lo sport è sempre indispensabile (non più "sport oppure periodo").
   Se manca, `question` "Padel o tennis?" e nessun intento salvato. "Indifferente" / "tutti e
   due" è una risposta valida → sport=any → nessun filtro sport nel chooser.
5. Istruzione nelle descrizioni dei tool: prima di create_intent, se l'utente non ha detto
   padel, tennis o indifferente, chiedilo. Lo schema NON rende sport obbligatorio (l'agente
   indovinerebbe invece di chiedere). Il server è la rete di sicurezza.
6. Dopo una proposta ogni cambiamento (luogo, periodo, sport, budget, "più fresco") passa da
   reject_proposal con i campi aggiornati, mai da un nuovo create_intent. Le descrizioni di
   get_proposal e create_intent non devono più suggerire di "riformulare" o richiamare
   create_intent dopo una proposta.
7. reject_proposal accetta anche direction: north | south. L'agente traduce "più fresco" →
   north e "più caldo" → south; il server usa geo.move. Nessun dato climatico nel catalogo.

## Decisioni aperte sul parser (da mettere in M17, con 2-3 opzioni e una raccomandazione)
- sinonimi: "terra rossa", "clay", "Terrarossa" → tennis; "paddle", "Weebora" → padel
- "padel e tennis" nella stessa frase: oggi vince il primo; proposta: sport=any
- "beach tennis" / "paddle tennis" non devono diventare tennis
- nomi di tornei (es. Internazionali di Roma) → tennis, solo se il catalogo li vende

## Use case da scrivere in docs/usecases/agente-tool.md (referenziati da M17)
Per ciascuno: cosa dice l'utente, chiamata dell'agente, cosa fa il server, cosa legge l'agente.
UC1 richiesta completa in una frase; UC2 periodo dal calendario e sport non detto → l'agente
chiede prima (con la rete di sicurezza del server se non lo fa); UC3 sport indifferente → any;
UC4 rifiuto "troppo caldo" → reject_proposal con direction=north, stesso intento; UC5 rifiuto
che cambia sport → reject_proposal con sport; UC6 rifiuto non traducibile ("hotel con spa") →
solo reason, il say dice cosa Vela non sa filtrare; UC7 campo invalido o inventato (area
sconosciuta, budget non detto) → scartato o ripetuto nel say; UC8 testo e campo in contrasto
→ vince il campo; UC9 client solo testo → parser/Haiku come oggi, più la domanda sullo sport.

## Nuova task M17 in roadmap.md ("Contratto agente-tool e sinonimi dello sport")
Con Risultato, Scope, Test di completamento, Copre, Prompt, Taglia, dipendenze e ondata, e le
righe nella tabella riassuntiva, nel grafo e nella matrice dei requisiti. Non va in M9 o M11:
sono già concluse. Deve poter girare in parallelo con M10 (file quasi disgiunti; unico punto
comune: sport=any nel chooser).

## Prima di modificare
- Leggi docs/spec.md (RF-01, RF-03, RF-04, RF-08, RF-39..42), docs/roadmap.md,
  docs/decisions.md, vela/surfaces/mcp.py, vela/domain/intent.py, vela/domain/refine.py,
  vela/domain/usecases.py.
- Proponimi in pochi punti: RF da modificare o aggiungere in spec.md, la struttura di M17
  e la taglia, le opzioni per le decisioni aperte sul parser.
- Dopo il mio OK: aggiorna spec.md, roadmap.md, scrivi il file degli use case, registra le
  decisioni in docs/decisions.md e fai un commit piccolo.
</pasted_content id="e5de">

## Agente 11:28

Leggo i file indicati prima di proporre.

- 🔧 Bash: List branches, docs and file sizes

- 🔧 Bash: Read the spec

- 🔧 Bash: Read the roadmap

- 🔧 Read /Users/matteodospina/.claude/projects/-Users-matteodospina-orca-workspaces-vela-task-m17/06396f26-5b58-42d9-8dcd-1edce5199353/tool-results/b5vzc01xv.txt

- 🔧 Bash: Read MCP surface, refine and use cases

- 🔧 Bash: Read the intent parser

- 🔧 Bash: Skim decisions.md structure and tail

- 🔧 Bash: Check geo.move, sport handling in chooser/say/rest

- 🔧 Bash: Check Criteria model, storage, REST reject and say

- 🔧 Bash: Check rejections constraints, period handling, NoMatch

Ho letto spec, roadmap, decisions e i quattro file di codice. Non ho ancora modificato niente. Qui sotto la proposta, poi alcune decisioni che i documenti non coprono e che servono prima di scrivere.

## 1. Modifiche a spec.md

Propongo una nuova sezione **§4.11 "Contratto agente-tool"** che raccoglie le regole nuove, e ritocchi brevi ai requisiti esistenti che rimandano lì. Così le regole restano in un posto solo.

- **RF-52** Campi strutturati opzionali su `create_intent` e `reject_proposal`, uguali su MCP e REST: `sport`, `area`, `period_start`, `period_end`, `pax`, `budget`. `text` e `reason` restano. `reject_proposal` accetta in più `direction` (north | south). È una modifica additiva.
- **RF-53** Precedenza: campi strutturati validi > parser > Haiku. Un campo invalido viene scartato, non blocca e il `say` lo dice. Se testo e campo sono in conflitto vince il campo e il conflitto va nei log.
- **RF-54** Il `say` di `create_intent` e di `reject_proposal` ripete sempre i criteri capiti. Se un motivo di rifiuto non è traducibile in un filtro, il `say` lo dice.
- **RF-55** Dopo una proposta ogni cambiamento passa da `reject_proposal`, mai da un nuovo `create_intent`. `direction` usa `geo.move` e il catalogo non contiene dati sul clima.
- **Ritocchi:**
  - RF-01 e RF-08: aggiungono i campi strutturati.
  - RF-02: sport diventa padel | tennis | any.
  - RF-03: il fallback Haiku parte quando manca lo sport, non più quando mancano sport e periodo.
  - RF-04: lo sport è sempre indispensabile e la domanda è "Padel o tennis?".
  - RF-09: toglie "chiede di riformulare l'intento", che contraddice la decisione 6.
  - RF-39 e RF-40: nuovi ingressi.
  - RF-41: le istruzioni delle decisioni 5 e 6 entrano nelle descrizioni dei tool.

## 2. M17 in roadmap.md

- **Taglia M** (3-4 h). Tocca `intent.py`, `refine.py`, `usecases.py`, `chooser.py` (una riga per `any`), `say.py`, `mcp.py`, `rest.py`, `adapters/haiku.py` (lo schema accetta `any`), `docs/rest.md` e i test.
- **Dipende da M3, M4, M9 e M11**, tutte già su master.
- **Ondata 5**, in parallelo con M10, M12, M13 e M14. L'unico file in comune con M10 è `chooser.py`, per il filtro `sport=any`: chi arriva secondo fa il rebase.
- **M12**: le descrizioni dei tool cambiano. Se M12 parte prima di M17, il prompt di ElevenLabs va riletto.
- **Test di completamento**: ognuno dei casi UC1–UC9 diventa un test di `usecases`, uno MCP e uno REST, più le tabelle del parser per i sinonimi.
- Aggiungo le righe nella tabella riassuntiva, nel grafo e nella matrice (RF-01..04, 08, 09, 39..42, 52..55).

## 3. Decisioni aperte sul parser (vanno in M17)

| Tema | Opzioni | Raccomandazione |
|---|---|---|
| Sinonimi ("terra rossa", "clay", "Terrarossa", "paddle", "Weebora") | A) dizionario fisso in `intent.py` · B) dizionario ricavato dai titoli del catalogo · C) solo Haiku | **A**: deterministico e testabile. B lega il parser al catalogo, che oggi non conosce. |
| "padel e tennis" nella stessa frase | A) `any` · B) domanda "Padel o tennis?" · C) vince il primo (come oggi) | **A**: è quello che l'utente ha detto. |
| "beach tennis" e "paddle tennis" | A) esclusioni controllate prima dei sinonimi: lo sport non viene riconosciuto e parte la domanda · B) frase dedicata "non vendiamo beach tennis" | **A**: costa poco. B ha senso solo se capita davvero. |
| Nomi di tornei | A) fuori da M17: li risolve l'agente col campo `sport`, con Haiku come riserva · B) lista fissa attiva solo se un titolo del catalogo la contiene · C) nomi estratti dai titoli del catalogo | **A**: con i campi strutturati il caso resta solo per i client che mandano solo testo. B e C vanno tra i prossimi passi. |
| "più fresco", "più freddo", "cooler", "warmer" nel testo | A) `refine.py` li traduce in north/south come rete di sicurezza per UC9 · B) solo tramite `direction` passato dall'agente | **A**: è il caso del problema osservato, con un client che manda solo testo. |

## 4. Decisioni che i documenti non coprono

1. **Come si rappresenta "indifferente".** Il valore `"any"` finisce nei criteri, quindi anche nella risposta pubblica `intent_created` (modifica additiva al JSON, nessun cambio di schema DB). `None` resta "non detto". **Raccomando `"any"`**: con `None` il server non distinguerebbe "non chiesto" da "indifferente".
2. **Il periodo non è più indispensabile.** Con lo sport sempre obbligatorio, una richiesta con sport ma senza periodo crea l'intento senza chiedere il periodo, come oggi. Se mancano sia lo sport sia il numero di persone, chiedo prima lo sport. Confermi?
3. **Cambiare criteri dopo un `no_match` arrivato da un rifiuto.** `rejections.proposal_id` ha un vincolo unique, quindi un secondo `reject_proposal` sulla stessa proposta oggi fallisce. Ma la decisione 6 vieta di passare da `create_intent`. Opzioni:
   - A) un secondo reject sulla stessa proposta aggiorna i criteri senza registrare un nuovo rifiuto (niente cambio di schema);
   - B) un `no_match` restituisce anche l'ultimo `proposal_id` e vale A;
   - C) dopo un `no_match` è ammesso un nuovo `create_intent`.

   **Raccomando A + B.** Un `no_match` restituito da `get_proposal` all'inizio resta invece libero di passare da `create_intent`: non ci sono rifiuti da perdere.
4. **`direction` e `area` insieme nello stesso reject.** Raccomando che vinca `area`, con il conflitto nei log. Se `geo.move` non trova un'area, `direction` viene scartato e il `say` lo dice.
5. **Nessun Haiku per `reject_proposal`**, come oggi: il fallback resta solo su `create_intent`.
6. **`docs/rest.md`** descrive il contratto già implementato: propongo di aggiornarlo dentro M17, non adesso.

Dopo il tuo OK, e con le risposte ai punti 3 e 4, creo `doc/agent-contract` da master. Poi aggiorno `spec.md` e `roadmap.md`, scrivo `docs/usecases/agente-tool.md` (UC1–UC9), registro le decisioni in `docs/decisions.md` e faccio un solo commit piccolo.

## Utente 11:30

ok

## Agente 11:30

- 🔧 Bash: Create doc/agent-contract branch from master

Parto da spec.md.

- 🔧 Bash: Apply agent-contract changes to spec.md

Ora il file degli use case.

- 🔧 Write /Users/matteodospina/orca/workspaces/vela/task-m17/docs/usecases/agente-tool.md

Ora roadmap.md.

- 🔧 Bash: Add M17 and its references to roadmap.md

Ora registro le decisioni.

- 🔧 Bash: Append decisions and stage doc changes

- 🔧 Bash: Run the test suite

- 🔧 Bash: Summarize test failures

Le failure dipendono dall'interprete (Python 3.7 di sistema). Rilancio nel venv.

- 🔧 Bash: Run tests in the uv virtualenv

- 🔧 Bash: Commit the documentation changes
