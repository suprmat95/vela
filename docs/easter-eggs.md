# Easter egg — "Five keys, one chain"

Cinque chiavi nascoste nella challenge, da trovare in ordine. Qui teniamo traccia di ogni
chiave, di come è stata trovata e dei dati grezzi utili a riprodurre la ricerca.

## Chiave 2 — "The cart" (+45m)

**Traccia.** Aprire un carrello sull'API HOFJ per il pacchetto Premier Padel Finals
Barcelona 2026 (prodotto 118, brand `staging.weebora.com`), 2 adulti in 1 camera, su una
data che il prodotto accetta. La chiave è l'identificatore dell'hotel più economico che
quel carrello offre.

**Risposta.** `p_g_1d27qron` — La França Travellers, 140.00 EUR, hotel preselezionato nel
carrello aperto sulla data minima del prodotto (2026-12-08). Se la challenge intende invece
il più economico nella lista selezionabile (`GET .../accommodations`), la risposta è
`p_g_np3dww01` — SB Plaza Europa, 182.00 EUR.

**Come.** Ambiente staging (`https://staging.api.hofj.com`), client interno `test-dev-2`,
2026-09-25. Il brand `staging.weebora.com` esiste solo sul CMS di staging.

| Passo | Chiamata | Esito |
|---|---|---|
| 1 | `GET /v1/products/118?brand=staging.weebora.com&locale=en` | `minDate` 2026-12-08, `maxDate` 2026-12-13, una finestra `Bookable` 12-08 → 12-13, `defaultDurationInDays` 3, `hotelSelection` true, prezzo base 245 EUR/pp |
| 2 | `POST /v1/itineraries?brand=staging.weebora.com&locale=en` body `{"productId":118,"startDate":"2026-12-08","adults":2,"rooms":1,"currency":"EUR"}` | 200, `itineraryId` `awp8bacduowd` |
| 3 | `GET /v1/itineraries/awp8bacduowd` | 8→10 dicembre, 2 pax, totale 351.00 EUR, `accommodation` preselezionata **`p_g_1d27qron` La França Travellers 140.00 EUR** (camera `535339841` Standard Double Room, 1 King Bed) |
| 4 | `GET /v1/itineraries/awp8bacduowd/accommodations?startDate=2026-12-08&sortByValue=priceAsc` | 1 pagina, 3 elementi: `p_g_np3dww01` SB Plaza Europa 182.00 · `p_g_96y0wrm1` Leonardo Royal Hotel Barcelona Fira 219.00 · `p_g_y1zez6e1` Estival Vilamarí 291.00 (tutti 2 notti, source TRAVELGATEX) |
| 5 | `GET /v1/itineraries/awp8bacduowd/accommodations/p_g_1d27qron` | 200: stesso hotel, 140.00 EUR, rating 2, source TBO. Il campo `id` del dettaglio è un id upstream lungo (`1694744!TB!2!TB!...`), non `p_g_1d27qron` |

Lo stesso hotel selezionato **non compare** nella lista: la lista mostra solo le alternative.
Complessivamente il carrello dell'8 dicembre offre 4 hotel e il più economico è La França
Travellers.

**Dipendenza dalla data** (carrelli di prova):

| startDate | Creazione | Preselezionato | Lista |
|---|---|---|---|
| 2026-12-07 (prima di `minDate`) | 200 (`yndtvpyqpfib`) | `p_g_1d27qron` La França Travellers 158.00 | SB Plaza Europa 222 · Leonardo Royal 228 · Estival Vilamarí 307 |
| 2026-12-08 (`minDate`) | 200 (`awp8bacduowd`) | `p_g_1d27qron` La França Travellers 140.00 | SB Plaza Europa 182 · Leonardo Royal 219 · Estival Vilamarí 291 |
| 2026-12-11 | 200 (`umdwo1gabhb2`) | `p_g_np3dww01` SB Plaza Europa 207.00 | vuota (un primo tentativo è andato in timeout upstream 502) |
| 2026-12-14 (dopo `maxDate`) | 502, upstream 400 `RESERVATION_PERIOD_ERROR` "Periodo di prenotazione non valido" | – | – |

Note per il progetto:
- Il brand site accetta anche date prima di `minDate`: il controllo upstream è sul periodo
  di prenotazione, non sulla finestra pubblicata nel catalogo.
- Un errore di validazione upstream arriva come 502 `upstream-error` con il body del 400
  dentro `detail`, non come 400.
- La lista alloggi può andare in timeout (502 "upstream timeout") e rispondere alla
  chiamata successiva: serve un retry.
- Costo: 12 richieste in tutto, nessuna chiamata a payment o booking.

## Chiave 3 — "The seal" (+60m)

**Traccia.** Un artefatto compilato è servito a `/api/seal.wasm`; esporta `seal(ptr, len)`
e una `memory`. Va alimentato con `<chiave 2>:<email>` in UTF-8; il valore restituito,
come otto cifre esadecimali minuscole, è la chiave.

**Risposta.** `1f500cd8` per l'input `p_g_1d27qron:matteodospina@gmail.com` (email
dell'account della challenge). Variante con l'altra chiave candidata
`p_g_np3dww01:matteodospina@gmail.com` → `29814149`.

**Come.** Il file sta sul sito della challenge:
`https://vela-dev-challenge.web.app/api/seal.wasm` (200, `application/wasm`, 143 byte,
SHA-256 `4a401b3baa4e2ab61c13e96ea420352880097b6d13de63c9e62980634802b4ca`). Non è
sull'API HOFJ né sui siti brand (404 ovunque).

- Export: `memory` (1 pagina) e `seal: (i32, i32) -> i32`. Nessun import, nessun
  allocatore: l'input va scritto direttamente in `memory` all'offset 0.
- Il codice è un FNV-1a a 32 bit (offset `0x811c9dc5`, primo `0x01000193`) seguito da un
  finalizer `h ^= h>>15; h *= costante; h ^= h>>13`; non serve reimplementarlo,
  basta eseguirlo con Node 20 (`WebAssembly` integrato).
- Controlli: stesso input due volte → stesso valore; uno spazio in più o un'altra chiave
  cambiano il risultato; stringa vuota → `e92884c2`.

Script usato (Node, usa-e-getta):

```js
const inst = new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync("seal.wasm")), {});
const { memory, seal } = inst.exports;
const bytes = Buffer.from("p_g_1d27qron:matteodospina@gmail.com", "utf8");
new Uint8Array(memory.buffer).set(bytes, 0);
console.log((seal(0, bytes.length) >>> 0).toString(16).padStart(8, "0"));
```

## Chiave 4 — "The stream" (+75m)

**Traccia.** `/api/stream` consegna un carattere alla volta e non si fa mettere fretta. Se
prendi più di quanto offre, dimentica tutto ciò che hai raccolto. La chiave è ciò che
assembli arrivando in fondo.

**Risposta.** `VELA-66EP-D57R` (14 caratteri; l'ultima risposta con `done: true` la
restituisce anche per intero nel campo `key`).

**Come.** Endpoint `https://vela-dev-challenge.web.app/api/stream`, 2026-09-25.

- Senza `Authorization` → 401 `missing bearer token`. Con le chiavi precedenti come
  bearer → 401 `Wrong number of segments`: vuole un JWT. Il token giusto è quello di
  sessione del sito della challenge (formato `vela1.<payload>.<firma>`, payload con
  email, nome e `exp`), lo stesso che il frontend manda alle sue `/api/...`.
- Ogni `GET` autenticata risponde `{"data": {"done", "index", "total": 14, "char",
  "remainingInWindow", "windowResetsInMs": 10000}}`. La prima chiamata dà `index 0` con
  `remainingInWindow 2`: la finestra è di 10 s e offre 3 richieste, oltre le quali lo stato
  viene azzerato.
- Ritmo usato, prudente: una richiesta ogni `windowResetsInMs + 1 s` (11 s), sequenziale,
  con cookie jar e log grezzo di ogni risposta. 15 richieste in ~2,5 minuti, nessun reset.
- La quindicesima chiamata (dopo l'indice 13) risponde `index 14, char null, done true,
  key "VELA-66EP-D57R"`.

## Chiave 5 — "The signature" (+90m)

**Traccia.** Chiedere un nonce a `/api/nonce` (vive 60 s). Restituire HMAC-SHA256 di
(nonce + email), con chiave = le quattro chiavi già trovate concatenate in ordine,
"exactly as they were given to you". Inviare in esadecimale minuscolo.

**Risposta.** Accettata il 2026-09-25 con:

- chiave HMAC = `VELA-DMFT-DPN2` + `p_g_np3dww01` + `29814149` + `VELA-66EP-D57R`,
  concatenate senza separatori, UTF-8;
- messaggio = `<nonce>` + `matteodospina@gmail.com`, senza separatori;
- risultato = hex minuscolo dell'HMAC, inviato con `POST /api/key {"key": <hex>}` entro
  pochi millisecondi dalla richiesta del nonce (nonce `af28ff47f5c8d1d2e5c4b2cb72fa8906`).

Catena completa: 5 chiavi su 5, +5 ore di bonus.

**Il trucco.** "Exactly as they were given to you" è la parte importante. Per gli stage 2 e 3
il server aveva accettato `p_g_1d27qron` (l'hotel preselezionato del carrello) e il sigillo
corrispondente `1f500cd8`, ma la firma usa i **valori canonici** dello stage: l'hotel più
economico nella lista `GET .../accommodations` (`p_g_np3dww01`, SB Plaza Europa) e il
sigillo calcolato su di esso (`seal("p_g_np3dww01:matteodospina@gmail.com")` =
`29814149`). Le chiavi corrette della catena sono quindi:

| # | Stage | Chiave |
|---|---|---|
| 1 | The wire | `VELA-DMFT-DPN2` |
| 2 | The cart | `p_g_np3dww01` |
| 3 | The seal | `29814149` |
| 4 | The stream | `VELA-66EP-D57R` |
| 5 | The signature | HMAC per-nonce, vedi sopra |

**Come ci sono arrivato.**

- Il frontend (`js/api.js`, `js/keys.js`) usa `GET /api/state` per lo stato delle chiavi e
  `POST /api/key {"key"}` per l'invio: 422 = chiave sbagliata, 409 = altro errore, 200 =
  accettata. Inviare via API elimina la latenza umana rispetto ai 60 s del nonce.
- Il timing non era il problema: anche con 70 s di silenzio tra i tentativi, e con l'HMAC
  calcolato sul primo di due nonce, il risultato canonico veniva rifiutato.
- La chiave 1 è verificabile: la home page espone `Link: </.well-known/vela/ledger>;
  rel="vela-ledger"`; quella risorsa risponde 402 senza token e, con il token di sessione,
  `{"ledger": "vela-1", "issuedTo": <email>, "entry": "VELA-DMFT-DPN2"}`.
- Varianti rifiutate (tutte 422): nonce come byte grezzi, email+nonce, chiave/messaggio
  invertiti, chiave 3 in decimale o come 4 byte, separatori tra le chiavi (`\n`, spazio,
  `:`, `,`, `-`), `nonce:email`, `nonce+email` letterale, SHA-256 semplice, output
  maiuscolo, chiave 2 = id lungo TBO, chiave 2 = `p_g_np3dww01` con chiave 3 = `1f500cd8`.
- Il server non distingue chiavi già trovate da chiavi sbagliate (sempre 422), quindi non
  si può usare `/api/key` per verificare una chiave precedente.

**Nota di sicurezza.** Il token di sessione del sito (`vela1.<payload>.<firma>`, scadenza
fine ottobre 2026) è passato in chat durante questa sessione e finisce nel transcript
JSONL in `agents-log/`. Vale solo per l'account della challenge.
