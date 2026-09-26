# Use case: contratto tra l'agente e i tool di Vela

Data: 2026-09-26. Origine: conversazione osservata il 2026-09-26 (rifiuto "troppo caldo" gestito
con un nuovo `create_intent`), decisioni in `docs/decisions.md` (2026-09-26), requisiti in
`docs/spec.md` §4.11 (RF-52..55) e RF-01, RF-03, RF-04, RF-08, RF-09, RF-39..42. Implementazione:
roadmap M17. Ogni caso diventa un test di M17 (dominio, MCP, REST).

Per ogni caso: cosa dice il viaggiatore, la chiamata dell'agente, cosa fa il server, cosa legge
l'agente (`say`). Le frasi `say` sono indicative: conta il contenuto, non la forma esatta. Le
chiamate usano i nomi MCP; su REST valgono gli stessi campi nel corpo JSON.

## UC1 — Richiesta completa in una frase

- **Utente.** "Un weekend di padel in Spagna a ottobre, siamo in due, massimo 800 euro."
- **Agente.** `create_intent(text="Un weekend di padel in Spagna a ottobre, siamo in due,
  massimo 800 euro", sport="padel", area="Spagna", period_start="2026-10-01",
  period_end="2026-10-31", pax=2, budget=800)`, poi `get_proposal(intent_id)`.
- **Server.** Campi validi e coerenti col testo: nessun conflitto. Il parser non aggiunge nulla,
  Haiku non parte. Intento salvato.
- **Agente legge.** "Ho capito: un viaggio di padel in Spagna a ottobre per 2 persone con un
  budget massimo di 800 euro. Cerco la proposta giusta." Poi la proposta singola.

## UC2 — Periodo dal calendario, sport non detto

- **Utente.** "Trovami qualcosa per il ponte dell'8 dicembre, siamo in due."
- **Agente (comportamento atteso).** Il periodo lo ricava dal calendario; lo sport non è stato
  detto, quindi prima di chiamare il tool chiede "Padel o tennis?" (descrizione di
  `create_intent`, RF-41). Risposta "tennis" → `create_intent(text="Trovami qualcosa per il
  ponte dell'8 dicembre, siamo in due. Tennis.", sport="tennis", period_start="2026-12-05",
  period_end="2026-12-08", pax=2)`.
- **Rete di sicurezza.** Se l'agente chiama senza sport: il parser non trova lo sport, Haiku
  (se attivo) non lo trova, il server risponde `question` "Padel o tennis?" e **non salva
  l'intento** (RF-04). L'agente pone la domanda e richiama `create_intent` con la frase
  originale più la risposta.
- **Agente legge.** La domanda, poi "Ho capito: un viaggio di tennis dal 5 all'8 dicembre per 2
  persone…".

## UC3 — Sport indifferente

- **Utente.** "Padel o tennis? Indifferente, basta che sia al caldo a novembre."
- **Agente.** `create_intent(text="…", sport="any", period_start="2026-11-01",
  period_end="2026-11-30")`.
- **Server.** `sport=any` è una risposta valida: intento salvato con `sport: "any"`, nessun
  filtro sport nel chooser. Solo testo ("tutti e due", "indifferente", "padel e tennis") → il
  parser produce `any` (decisione aperta di M17 per "padel e tennis").
- **Agente legge.** "Ho capito: un viaggio di padel o tennis a novembre… Cerco la proposta giusta."

## UC4 — Rifiuto "troppo caldo"

- **Utente.** (dopo una proposta a Siviglia) "Troppo caldo, vorrei un posto più fresco."
- **Agente.** `reject_proposal(proposal_id, reason="Troppo caldo, vorrei un posto più
  fresco", direction="north")`. **Non** chiama `create_intent` (RF-55).
- **Server.** Registra il rifiuto sull'intento esistente, applica `geo.move(area del prodotto,
  "north")`, aggiorna i criteri, sceglie un prodotto diverso da quello rifiutato. Nessun dato
  climatico: "più fresco" = più a nord. Client solo testo: `refine.py` riconosce "più fresco",
  "più freddo", "cooler" → north, "più caldo", "warmer" → south (decisione aperta di M17).
- **Agente legge.** "Ho capito: un viaggio di padel più a nord, nel Nord della Spagna, … Ti
  propongo …".

## UC5 — Rifiuto che cambia sport

- **Utente.** "No, ripensandoci preferisco il tennis."
- **Agente.** `reject_proposal(proposal_id, reason="Preferisco il tennis", sport="tennis")`.
- **Server.** Stesso intento, criteri aggiornati con `sport=tennis`, rifiuto registrato,
  proposta di tennis.
- **Agente legge.** "Ho capito: un viaggio di tennis … Ti propongo …".

## UC6 — Rifiuto non traducibile

- **Utente.** "Non mi piace, voglio un hotel con la spa."
- **Agente.** `reject_proposal(proposal_id, reason="Voglio un hotel con la spa")`, senza campi:
  non c'è un campo per la spa e l'agente non ne inventa.
- **Server.** Nessun criterio cambia; il prodotto rifiutato resta escluso; proposta successiva.
- **Agente legge.** "Non so scegliere in base a questo: ho escluso solo la proposta di prima.
  Ti propongo …" (RF-54).

## UC7 — Campo invalido o inventato

- **Utente.** "Padel a Atlantide, siamo in tre." (luogo che `geo` non conosce)
- **Agente.** `create_intent(text="…", sport="padel", area="Atlantide", pax=3, budget=1000)`:
  `area` sconosciuta e `budget` inventato (l'utente non l'ha detto).
- **Server.** `area` scartata: non blocca, intento salvato senza area, lo scarto va nel `say`.
  `budget` è valido e il server non può sapere che è inventato: lo tiene e lo ripete nel `say`.
- **Agente legge.** "Non conosco il luogo Atlantide, cerco ovunque. Ho capito: un viaggio di
  padel per 3 persone con un budget massimo di 1.000 euro…". Il viaggiatore sente il budget e
  può correggerlo ("non ho detto nessun budget") → dopo la proposta passa da `reject_proposal`.

## UC8 — Testo e campo in contrasto

- **Utente.** "Tennis a Roma a maggio."
- **Agente.** `create_intent(text="Tennis a Roma a maggio", sport="padel", …)`.
- **Server.** Il parser legge `tennis`, il campo dice `padel`: vince il campo (RF-53), il
  conflitto va nei log con id intento, campo, valore del parser e valore del campo.
- **Agente legge.** "Ho capito: un viaggio di padel a Roma a maggio…". Il `say` rende visibile
  l'errore; il viaggiatore corregge e l'agente richiama `create_intent` (nessuna proposta ancora
  fatta) o, se la proposta c'è già, `reject_proposal` con `sport="tennis"`.

## UC9 — Client solo testo

- **Utente.** "Vorrei una vacanza a Maiorca a giugno per due."
- **Agente.** Un client che non conosce i campi: `create_intent(text="Vorrei una vacanza a
  Maiorca a giugno per due")`.
- **Server.** Come prima di M17: parser, poi Haiku se lo sport manca e la chiave è presente. Lo
  sport non c'è → `question` "Padel o tennis?", intento non salvato (RF-04). Rifiuti solo testo:
  `refine.py` come prima, più i sinonimi di M17 ("più fresco" → north).
- **Agente legge.** "Padel o tennis?", poi il `say` con i criteri capiti.

## Dopo un "niente di compatibile" (RF-09, RF-55)

- Restituito da `get_proposal` prima di ogni proposta: nessun rifiuto da perdere, l'agente può
  chiamare di nuovo `create_intent` con i criteri cambiati.
- Restituito da `reject_proposal`: la risposta riporta l'id della proposta appena rifiutata;
  l'agente chiama `reject_proposal` su quell'id con i campi cambiati. Il server aggiorna i
  criteri e propone di nuovo senza registrare un secondo rifiuto.
