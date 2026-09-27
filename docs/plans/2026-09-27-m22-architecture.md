# M22-a — Testi per `ARCHITECTURE.md` §5.2 e §5.3

Testi pronti da incollare in `ARCHITECTURE.md` (branch `doc/architecture`): §5.2 "Budget di
quota: browse, cart, hotel, booking" e §5.3 "Cosa degrada e cosa non deve mai degradare: il
minuto sei". Due varianti: **A** vale ora (verdetto di M22-a: M22-b non si fa, `docs/decisions.md`
2026-09-27); **B** vale se M22 viene riaperta e M22-b mergiata. In entrambe il resto delle due
sezioni resta com'è: cambiano solo le righe indicate.

## Variante A — senza M22-b (quella da usare ora)

### §5.2, riga "Hotel" della tabella

| Voce del brief | Chiamate HofJ | Classe | Note |
|---|---|---|---|
| Hotel | Dentro `POST /v1/itineraries` (hotel di default) | `purchase` | È la chiamata da 2-6 s; nessuna chiamata a `/accommodations`. Il cambio di hotel è stato progettato e sondato (M22-a) e non costruito: su staging `PATCH .../accommodations` non è mai risultato eseguibile |

### §5.2, dopo "Cosa si sacrifica, in ordine"

L'ordine resta: 1) il sync del catalogo; 2) l'attesa degli acquisti, che cresce, dichiarata,
senza tetto; 3) mai le prenotazioni degli ordini pagati.

> Abbiamo progettato un quarto gradino, la scelta dell'hotel, da sacrificare subito dopo il
> catalogo: un cambio di hotel costa circa 3 chiamate (lista, `PATCH`, rilettura del totale) e
> passa solo a coda d'acquisto vuota, prendendo tutti i gettoni insieme o nessuno. La sonda su
> staging ha misurato la lista in 1,5-2,1 s ma non ha mai trovato un hotel con camere da
> mandare al `PATCH`, quindi il cambio non è stato costruito. Progetto e condizioni per
> riprenderlo in `docs/plans/2026-09-27-m22-hotel.md` e `docs/decisions.md` (M22-a).

### §5.3, dopo "Cosa degrada"

> A coda piena come a coda vuota, l'hotel è quello incluso nel viaggio: se il viaggiatore lo
> rifiuta, Vela propone un altro viaggio senza quell'hotel (RF-72). Nessuna chiamata a
> `/accommodations` entra mai nella conversazione.

## Variante B — con M22-b

### §5.2, righe "Hotel" della tabella (al posto dell'unica riga)

| Voce del brief | Chiamate HofJ | Classe | Note |
|---|---|---|---|
| Hotel di default | Dentro `POST /v1/itineraries` | `purchase` | È la chiamata da 2-6 s; l'acquisto costa sempre 5 chiamate |
| Cambio di hotel | ≈ 3 per cambio: lista (1,5-2,1 s misurati), `PATCH`, rilettura del totale; 1 se non c'è alternativa | `hotel` | Solo senza acquisti `pending` e con tutti i gettoni subito, altrimenti 0 chiamate. Il job non aspetta mai |

### §5.2, "Cosa si sacrifica, in ordine" (al posto dell'elenco)

Priorità della quota: `booking` > `purchase` > `hotel` > `sync`. Cosa si sacrifica, in ordine:

1. il sync del catalogo, che cede il passo anche ai cambi di hotel (rischio accettato: catalogo
   oltre le 6 h se i cambi sono continui a coda vuota, coperto da RF-17/RF-33);
2. **la scelta dell'hotel**: con anche un solo acquisto in attesa, si tiene l'hotel incluso e lo
   si dice;
3. l'attesa del link, che cresce, dichiarata, senza tetto;
4. mai le prenotazioni degli ordini pagati.

Un cambio non prende mai i gettoni a rate: tutti insieme o nessuno. Un `PATCH` senza la
rilettura del totale lascerebbe un carrello con un prezzo che il viaggiatore non ha sentito, e
il link Stripe usa il totale dell'ordine. Il costo per gli acquisti è al massimo un blocco già
preso: 3 gettoni, circa 2 s, una volta.

### §5.3, nuovo punto dopo Anna

- **Anna, al prezzo effettivo**, sente "Il prezzo effettivo è 840 euro in totale per 2
  persone, con l'Hotel Sol. Confermi?" e dice "l'hotel non mi piace". Al minuto sei la coda
  d'acquisto è piena: Vela non chiama HofJ e risponde subito "Adesso ci sono molte prenotazioni
  in corso e non posso cambiare hotel: ti tengo quello incluso, l'Hotel Sol. Il totale resta
  840 euro per 2 persone. Confermi?". A coda vuota, la stessa frase avrebbe prodotto un solo
  hotel alternativo con il nuovo totale.

### §5.3, "Cosa degrada" (al posto della frase)

**Cosa degrada:** la scelta dell'hotel, che sotto picco diventa "l'hotel incluso", detto; poi
l'attesa del link, dichiarata. **Cosa non degrada mai:** la conversazione (0 chiamate HofJ, p95
< 500 ms) e la conferma di chi ha già pagato.
