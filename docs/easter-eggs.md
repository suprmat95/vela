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
