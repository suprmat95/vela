# Domande per HofJ: pagamento e prenotazione

Stato: da inviare. Nato dalle verifiche di spec §8 in M5 (`docs/decisions.md`, sezioni "M5:
verifiche di spec §8" e "M5: seconda sonda sul pagamento"). Le risposte decidono come M6
incassa e come Vela conferma la prenotazione.

## Contesto

Vela è un agente che prenota viaggi padel/tennis dall'API interna di HofJ. Il flusso previsto:

1. `POST /v1/itineraries`, `PUT .../customer`, `GET/PUT .../pax`, `GET /v1/itineraries/{id}`.
2. Vela crea una Stripe Checkout Session con la chiave `rk_test_…` che ci avete fornito
   (quindi sul vostro account Stripe) e manda il link al viaggiatore.
3. A pagamento avvenuto Vela chiama `POST /v1/bookings` e comunica il codice al viaggiatore.

## Cosa abbiamo osservato su staging (2026-09-25)

Host `https://staging.api.hofj.com`, brand `staging.weebora.com`, client `test-dev-2`, prodotto 118,
partenza 2026-12-08, 2 adulti, 1 camera.

| Prova | Carrello | Pagamento | `POST /v1/bookings` | Carrello dopo il booking |
|---|---|---|---|---|
| 1 | `dlp5lyj338uf` | PaymentIntent creato da noi con la vostra chiave, 368,00 €, senza metadata, `succeeded` (`pi_3UJcAaRpam3eRRKb1EBxdpH6`) | body `{itineraryId, paymentType: "full", paymentIntentId, paymentStatus: "succeeded"}` → 200 `{"data": "dlp5lyj338uf"}` | `checkout.status` `BookingInitiated`, `openAmount` 337 |
| 2 | `iznhotwwgneg` | PaymentIntent creato da `POST .../payment` (337,00 €, `metadata.checkoutRefId = iznhotwwgneg`), confermato con carta di test, `succeeded` (`pi_3UJcdsRpam3eRRKb0xNWuDCh`) | body `{itineraryId, paymentType: "full"}` → 200 `{"data": "iznhotwwgneg"}` | `checkout.status` `BookingInitiated`, `openAmount` 337 |

In entrambi i casi il booking restituisce l'`itineraryId` e non un codice `R-…` come indicato
nella documentazione, e dall'API interna non vediamo differenze tra un carrello pagato e uno
non pagato.

## Domande

1. **Riconciliazione del pagamento.** Se creiamo noi il pagamento (Checkout Session con la vostra
   chiave) invece di usare `POST /v1/itineraries/{id}/payment`, il vostro sistema lo riconosce come
   pagamento del carrello? Basta impostare sul PaymentIntent `metadata.checkoutRefId = itineraryId`
   e importo = `checkout.openAmount`? Oppure serve passare `paymentIntentId` e `paymentStatus` a
   `POST /v1/bookings` (il contratto dice "forwarded to the brand site when present")? Se nessuna
   delle due cose basta, dobbiamo usare il vostro PaymentIntent e confermarlo con Stripe.js: in quel
   caso ci serve la chiave pubblicabile `pk_test_…` dell'account.

2. **Codice di prenotazione.** Perché su staging `POST /v1/bookings` restituisce l'`itineraryId`
   invece di un codice `R-…`? È il comportamento atteso su staging, o indica che la prenotazione
   non è stata confermata? Come possiamo verificare dall'API interna che una prenotazione è
   confermata e pagata, senza il token dell'utente finale richiesto da `GET /v1/bookings/{id}`?

3. **Notifica del pagamento a Vela.** Per sapere quando il viaggiatore ha pagato abbiamo due
   possibilità:
   - (a) un webhook Stripe (`checkout.session.completed`, `checkout.session.expired`) registrato
     sul vostro account verso un nostro URL. Potete registrarlo voi e darci il signing secret,
     oppure abilitare il permesso sui webhook alla nostra chiave? Questi eventi arriverebbero
     anche ai vostri sistemi: è un problema?
   - (b) leggere noi lo stato delle Checkout Session con l'API (nessuna registrazione sul vostro
     account).

   Quale preferite?

4. **Permessi della chiave `rk_test_…`.** Include la creazione e la lettura delle Checkout Session
   (`checkout_sessions` in scrittura e lettura) e la lettura dei PaymentIntent? Ci sarà una chiave
   equivalente per la produzione?

5. **Importi.** Su un carrello `checkout.total` vale 368 e `openAmount`/`originalTotal` 337
   (`totalPrice` 368.00). Che cosa rappresenta la differenza di 31 €? L'importo da incassare con
   `paymentType: "full"` è sempre `openAmount`?

6. **Lingua.** Su staging il prodotto 118 con `locale=it` dà 502 (upstream 404) e con `locale=en`
   funziona. In produzione i prodotti del catalogo italiano sono tutti prenotabili con `locale=it`?

7. **Carrelli di prova.** I due carrelli sopra e i relativi pagamenti di test vanno annullati o
   segnalati da qualche parte?
