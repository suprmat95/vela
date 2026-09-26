# Use case: catalogo multi-brand (padel in Weebora, tennis in Terrarossa)

Data: 2026-09-26. Origine: su claude.ai il tennis non si trova mai, perché Vela carica un solo
brand HofJ (Weebora, padel) e su HofJ ogni brand ha un catalogo separato. Decisioni in
`docs/decisions.md` (2026-09-26, M10 multi-brand), requisiti in `docs/spec.md` RF-28..32 e
RF-56, implementazione in roadmap M10. Il contratto dei tool (campi strutturati, `sport=any`,
domanda "Padel o tennis?") è quello di §4.11 e di `docs/usecases/agente-tool.md` (M17): qui
conta solo in quale catalogo finisce la ricerca e con quale brand parte il carrello.

Brand configurati con `HOFJ_BRANDS` (sport → brand):

| Host | padel | tennis |
|---|---|---|
| Produzione `api.hofj.com` | `weebora.com` | `terrarossa.com` |
| Staging `staging.api.hofj.com` | `staging.weebora.com` | `staging.tennis.weebora.com` |

Per ogni caso: cosa dice il viaggiatore, la chiamata dell'agente, cosa fa il server, cosa legge
l'agente (`say`). Le frasi `say` sono indicative. Chooser, MCP e REST non cambiano in M10: lo
sport di ogni prodotto viene dal suo brand e il filtro sport del chooser basta.

## MB1 — Tennis esplicito

- **Utente.** "Un weekend di tennis in Italia a maggio, siamo in due."
- **Agente.** `create_intent(text="…", sport="tennis", area="Italia", period_start=…,
  period_end=…, pax=2)`, poi `get_proposal(intent_id)`.
- **Server.** Il chooser filtra `sport=tennis`: i candidati sono i prodotti con brand
  Terrarossa. Accettata la proposta, tutte le chiamate del carrello e la prenotazione partono
  con `?brand=terrarossa.com` (RF-56).
- **Agente legge.** "Ho capito: un viaggio di tennis in Italia a maggio per 2 persone…", poi la
  proposta.

## MB2 — Padel esplicito

- **Utente.** "Padel in Spagna a ottobre."
- **Agente.** `create_intent(text="…", sport="padel", area="Spagna", …)`.
- **Server.** Candidati del brand Weebora; carrello e prenotazione con `?brand=weebora.com`.
  Comportamento identico a prima di M10.

## MB3 — In inglese

- **Utente.** "A tennis weekend in Portugal in June for two."
- **Agente.** `create_intent(text="…", sport="tennis", area="Portugal", …)`.
- **Server.** Come MB1: catalogo Terrarossa, `say` in inglese. La lingua del viaggiatore non
  sceglie il brand; il locale delle chiamate HofJ resta quello configurato per l'host.

## MB4 — Cambio di sport dopo un rifiuto

- **Utente.** (dopo una proposta di padel) "No, preferisco il tennis."
- **Agente.** `reject_proposal(proposal_id, reason="Preferisco il tennis", sport="tennis")`
  (RF-55: mai un nuovo `create_intent`).
- **Server.** Stesso intento, rifiuto registrato, criteri con `sport=tennis`: la nuova proposta
  viene dal catalogo Terrarossa. L'eventuale ordine usa il client Terrarossa.
- **Agente legge.** "Ho capito: un viaggio di tennis… Ti propongo …".

## MB5 — Sport indifferente

- **Utente.** "Padel o tennis mi è indifferente, basta che sia al caldo a novembre."
- **Agente.** `create_intent(text="…", sport="any", period_start=…, period_end=…)`.
- **Server.** `sport=any` = nessun filtro sport: i candidati sono i prodotti di entrambi i
  brand, ordinati come sempre dal chooser. Il brand del prodotto scelto decide il client del
  carrello.
- **Agente legge.** "Ho capito: un viaggio di padel o tennis a novembre…", poi una proposta
  singola, di padel o di tennis.

## MB6 — Sport assente, senza periodo

- **Utente.** "Vorrei una vacanza sportiva per due."
- **Agente.** Chiede "Padel o tennis?" prima di chiamare il tool. Se chiama senza sport, il
  server risponde `question` "Padel o tennis?" e non salva l'intento (RF-04).
- **Dopo la risposta.** "Tennis" → MB1; "indifferente" → MB5.

## MB7 — Sport assente, con periodo

- **Utente.** "Qualcosa per il ponte dell'8 dicembre, siamo in due."
- **Agente e server.** Come MB6: il periodo non basta più (RF-04 modificata), la domanda
  "Padel o tennis?" arriva lo stesso e nessun intento viene salvato finché lo sport manca.

## MB8 — Nessun prodotto per lo sport chiesto

- **Utente.** "Tennis in Islanda a gennaio."
- **Server.** Nessun prodotto Terrarossa passa i filtri, oppure il brand del tennis non è
  configurato (`HOFJ_BRANDS` con il solo padel). Il chooser si ferma sul filtro `sport` e
  restituisce il `no_match` esistente con la frase `sport_value`: "Non trovo nessun viaggio di
  tennis: prova con l'altro sport o riformula la richiesta." Nessuna frase nuova.

## Fuori da M10

Il riconoscimento dello sport nel testo (sinonimi come "terra rossa" o "Weebora", "padel e
tennis" nella stessa frase, "beach tennis" e "paddle tennis", nomi di tornei) è deciso in M17
(roadmap, "Decisioni aperte sul parser"). M10 assume che lo sport arrivi già come `padel`,
`tennis` o `any`.
