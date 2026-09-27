# M21-F — Rifiuti con motivo sempre capito (UC-F): design

Data: 2026-09-27. Task M21-F della roadmap, in modalità autonoma con l'OK anticipato dell'utente.
Requisiti: `docs/spec.md` RF-08, RF-09, RF-39..41, RF-49, RF-52..55, RF-71..75, RF-84; casi d'uso:
`docs/usecases/scelta.md` UC-F; decisioni: `docs/decisions.md` ("Scelta v3", M21-E, M21-B, M21-D,
M21-C, M22-a, M23). Le scelte non coperte dai documenti sono in `docs/decisions.md` ("M21-F").

## 1. Obiettivo

Ogni rifiuto ha un tipo (`price`, `place`, `hotel`, `dates`, `duration`, `sport`, `pax`,
`level`, `direction`, `other`). Il tipo decide cosa si esclude oltre ai criteri aggiornati:
l'hotel del prodotto (RF-72), un luogo (RF-73), solo le date (RF-74). Un motivo che non si
classifica non diventa più una proposta a caso: diventa una domanda chiusa, senza effetti (RF-75).

## 2. Flusso di `reject_proposal`

```
proposta, intento, rifiuto già registrato (se c'è)
  → refine (puro): criteri aggiornati + tipo + keep_product + domanda
  → domanda? ──sì──> IntentQuestion(proposal_id), nessuna scrittura (RF-75, RF-49)
  → no: cancella l'ordine non pagato (RF-49, ripiego RF-84 come oggi)
        registra il rifiuto (kind, keep_product) oppure aggiorna quello esistente (RF-55)
        salva i criteri → scelta → say
```

Oggi l'ordine si cancella e il rifiuto si registra prima di interpretare il motivo; adesso si
interpreta prima, così la domanda chiusa non lascia tracce. `refine` non legge il catalogo se non
per la regola 4 del budget (lettura condivisa con la scelta, come in M21-E): la domanda non costa
letture del catalogo.

## 3. Classificazione (RF-71) in `refine.py`

Precedenza: `reject_kind` valido > regole sul testo > campi strutturati. Un `reject_kind` fuori
elenco è scartato e detto (RF-53). Regole it/en, ogni tipo che si accende conta; il tipo
registrato è il primo nell'ordine di RF-71 (decisione A della roadmap):

| Tipo | Testo | Campi |
|---|---|---|
| `price` | "troppo caro" e simili, una cifra, "a testa"/"in tutto" | `budget`, `budget_scope` |
| `place` | un luogo di `geo` (nuova area o negato), "posto", "zona", "località", "destinazione", "lontano", "place", "location", "destination", "far" (solo senza direzione) | `area` |
| `hotel` | "hotel", "albergo", "struttura", "resort", "accommodation" | — |
| `dates` | un periodo, "date", "periodo", "dates", frasi di `keep_product` | `period_*` |
| `duration` | una durata, "troppo lungo/corto" | `duration_*` |
| `sport` | padel, tennis, indifferente | `sport` |
| `pax` | persone, camere | `pax`, `rooms` |
| `level` | livello, "troppo difficile/facile", lezioni | `level`, `wants_coaching` |
| `direction` | "più a sud/nord", "più fresco/caldo" | `direction` |
| `other` | mai dal testo | solo `reject_kind="other"` |

Nessun tipo → la domanda di RF-75. Motivo vuoto senza campi = nessun tipo.

## 4. Effetti per tipo

- **`hotel` (RF-72).** Esclusione ricavata dai rifiuti, come il tetto di prezzo: un rifiuto vale
  per l'hotel se il tipo è `hotel` oppure il motivo contiene le parole dell'hotel (motivo con più
  tipi, "troppo caro e l'hotel non mi piace"). Dopo sono esclusi i prodotti con lo stesso hotel,
  a nome normalizzato (minuscole, spazi singoli). Prodotto senza hotel: sono esclusi i prodotti con
  la stessa chiave di equivalenza di RF-61 (nessun hotel, stesso titolo, stessa destinazione),
  prezzo a parte. È il caso del 78 di staging e della trappola 900078. Filtro `hotel` nel chooser
  dopo `place` e prima di `price`; `NoChoice("hotel")`.
- **`place` (RF-73).** `Criteria.excluded_areas` (tupla di `Area`, nel JSON dei criteri e in
  `intent_created`). Luogo negato nel testo ("X no", "non a X", "tranne X", "eccetto X",
  "not X", "anywhere but X", "except X") → esclusione, area invariata. Luogo non negato → nuova
  area come oggi. Tipo `place` senza nuova area né luogo negato → esclusa l'area del prodotto
  rifiutato. Se l'area dell'intento sta dentro un'area esclusa, l'area diventa il primo antenato
  non escluso. Filtro duro `place` dopo `level` (anche in `cheapest_total`); `NoChoice("place")`.
  Marbella entra in `geo` (città, Costa del Sol).
- **`dates` con `keep_product` (RF-74).** `keep_product` dal campo o dal testo ("mi piace",
  "tienimi questo", "stesso viaggio", "quando altro", "altre date", "I like", "same trip",
  "when else", "other dates"; mai negato: "non mi piace" non conta). Vale solo con tipo `dates`;
  con `keep_product` e nessun altro tipo il tipo è `dates`. Il prodotto resta candidato senza le
  finestre rifiutate: `chooser.departure` salta le partenze che si sovrappongono a una finestra
  esclusa (per le finestre aperte riprova dal giorno di fine della finestra esclusa). Subito dopo
  un rifiuto con `keep_product` la scelta è solo tra quel prodotto; nessuna partenza →
  `NoMatch("dates")` con `rejected_proposal_id` e la frase "Questo viaggio non ha altre partenze…
  Vuoi che cerchi un altro viaggio?".
- **RF-55 sulla stessa proposta.** Un secondo `reject_proposal` sulla stessa proposta non registra
  un rifiuto nuovo: se il tipo o `keep_product` cambiano, aggiorna quello esistente (porta
  `RejectionRepository.update`). `keep_product` della seconda chiamata vale solo se detto di nuovo
  (campo o testo); altrimenti diventa falso e il prodotto è escluso. Senza tipo nella seconda
  chiamata resta il tipo registrato e non c'è domanda: la proposta è già rifiutata.
- **`other` esplicito.** Esclude solo il prodotto; la frase di RF-54 ("Non so scegliere in base a
  questo…") solo qui e solo se nessun criterio cambia.
- **Prezzo.** Il tetto di M7 vale per i rifiuti di tipo `price` o con un motivo di prezzo
  (`is_price_reason`, come oggi): "troppo caro" del load test resta `price`, stesso tetto.

## 5. Domande chiuse

`IntentQuestion` riceve `proposal_id` (facoltativo, in `to_dict()` solo se c'è; esito REST
`question`, 200). Tre casi, stesso formato:

1. RF-75: nessun tipo, proposta non ancora rifiutata → "Cosa non ti convince: il posto, l'hotel, le
   date o il prezzo?" / "What doesn't convince you: the place, the hotel, the dates or the price?".
2. Da M21-D: le persone cambiano e superano 2 senza camere dette nel rifiuto → "In quante camere?"
   con `proposal_id`, al posto delle camere di prima limitate a `pax`.
3. Da M21-D: `accept_proposal` con camere sotto il minimo → la domanda di oggi, con `proposal_id`.

Nei casi 1 e 2 nessun rifiuto, criteri invariati, ordine invariato (RF-49): la domanda non tocca un
leader o un agganciato di `price_quotes`.

## 6. Schema: migrazione 0017

Scritta come 0016 con `down_revision = "0015"`; al merge in `master` M19 aveva già la 0016
(`orders.last_seen_at`), quindi è la 0017 con `down_revision = "0016"` (0013 e 0014 restano numeri non usati: M21-F doveva usare 0013, M22-b
0014, archiviata). `rejections.kind` `String(16)` nullo: nullo = rifiuto senza tipo, cioè
registrato prima di M21-F o esclusione di RF-17 (prodotto non prenotabile), senza inventarne uno.
`rejections.keep_product` booleano non nullo, default falso. Downgrade: drop delle due colonne.

## 7. Superfici

- MCP `reject_proposal`: `reject_kind` (stringa, i dieci tipi) e `keep_product` (booleano);
  descrizione: passare il tipo quando è chiaro, `keep_product=true` quando il viaggio piace ma non
  le date, porre la domanda chiusa se torna `question` e richiamare con il tipo, `other` se il
  viaggiatore non sa dire cosa non va.
- REST `POST /v1/proposals/{id}/reject`: stessi campi; `keep_product` di tipo sbagliato è un 422
  come `wants_coaching`. `docs/rest.md` aggiornato.

## 8. Test

UC-F (F1-F4, "Altri tipi": una frase it e una en per tipo), i tre casi rimandati, la tabella di
classificazione, il load test ("troppo caro" → `price`, nessuna domanda, stesse chiamate HofJ),
RF-84 (cancellazione di un leader tramite `reject_proposal` con passaggio del testimone, domanda
senza sganci, rifiuto in `awaiting_confirmation` su prezzo dalla cache come senza cache),
repository in memoria e Postgres (`kind`, `keep_product`, `update`), migrazione 0017 (upgrade da
zero, righe esistenti, downgrade). I test che fissavano "motivo non capito → proposta successiva"
passano `reject_kind="other"` e tengono le stesse asserzioni.
