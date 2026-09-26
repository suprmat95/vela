# Notifiche SMS (Twilio): design

Data: 2026-09-26. Origine: brainstorming "setup Twilio" (branch `task/twilio-setup`). Tocca spec
RF-19 (consegna del link), RF-20/RF-23 (pagamento e conferma), §4.10 (coda). Decisioni in
`docs/decisions.md` (2026-09-26, "SMS: design delle notifiche").

## Problema

Dopo `accept_proposal` l'ordine va in coda: il viaggiatore deve chiedere più volte all'agente se
il link di pagamento è pronto, e dopo aver pagato deve chiedere di nuovo per la conferma.
L'agente non è proattivo e il contratto attuale (RF-19, istruzioni MCP) lo spinge a interrogare
`get_order_status`.

## Obiettivo

Vela manda al viaggiatore principale due SMS via Twilio, senza che nessuno chieda nulla:

1. **Link di pagamento** con il riepilogo di cosa sta prenotando, quando l'ordine diventa
   `awaiting_payment`.
2. **Conferma della prenotazione** con il codice, quando l'ordine diventa `confirmed`.

Successo: in un test reale su un numero italiano arrivano i due SMS, nell'ordine, senza
richiedere lo stato all'agente; la suite automatica è verde senza chiamate a Twilio.

## Vincoli

- Il telefono è già obbligatorio prima dell'accettazione (`TravelerProfile.phone`, RF-12):
  nessun dato nuovo da raccogliere.
- Test in Italia: i numeri si normalizzano in E.164 con prefisso `+39` di default.
- Un SMS non blocca mai l'ordine: nessuna transizione di stato dipende dall'esito dell'invio.
- Nessuna dipendenza nuova: Twilio si chiama con `httpx`, già presente. Nessuna modifica allo
  schema del DB (`jobs.kind` è `String(16)`).
- Nessuna chiamata a Twilio nei test automatici; le chiamate reali si dichiarano prima.
- Il numero compare nei log solo mascherato; il testo dell'SMS (contiene il link) mai.

## Fuori scope

- SMS per gli altri esiti (`failed`, `replaced`, `expired`, `booking_failed`, `cancelled`).
- Link corto / redirect `/pay/<order_id>`: l'SMS 1 resta di 2-3 segmenti.
- Mittente alfanumerico o Messaging Service; numeri esteri con regole dedicate.
- Registro degli invii per un'idempotenza perfetta (vedi "Doppioni").

## Componenti

### Normalizzazione del numero (`vela/domain/phone.py`)

`normalize_it(raw: Optional[str]) -> Optional[str]`:

1. Rimuove spazi, trattini, punti, parentesi e `/`.
2. Se inizia con `+`: resta com'è (un numero estero dichiarato non diventa italiano).
3. Se inizia con `00`: `00` → `+` (quindi `0039…` → `+39…`).
4. Altrimenti: `+39` davanti.
5. Il risultato deve essere `+` seguito da 8-15 cifre; altrimenti `None`.

`mask(e164: str) -> str`: `+39******1234` (prefisso, asterischi, ultime 4 cifre). Usata nei log.

### Porta (`vela/ports/notifier.py`)

```python
class NotifierError(Exception): ...      # temporaneo: rete, timeout, 5xx, 429 → si riprova
class NotifierRejected(NotifierError): ... # definitivo: altri 4xx → nessun nuovo tentativo

class Notifier(Protocol):
    def send_sms(self, to: str, body: str) -> str: ...   # id del messaggio del fornitore
```

`to` è sempre già in E.164. I messaggi delle eccezioni non contengono né il numero in chiaro né
il testo né le credenziali.

### Adapter

- `vela/adapters/sms_twilio.py` — `TwilioSms(account_sid, auth_token, from_number, client)`:
  `POST https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json`, Basic auth
  (`sid`, `token`), form `To`, `From`, `Body`, timeout 10 s. 2xx → `sid` del messaggio;
  429 e 5xx, errori di rete e timeout → `NotifierError`; altri 4xx → `NotifierRejected` con il
  `code` Twilio dell'errore (senza `message`, che può contenere il numero).
- `vela/adapters/sms_fake.py` — `FakeSms`: salva `(to, body)` in `sent`; può essere
  programmato per sollevare un'eccezione (test dei retry). Usato in replay e nei test.

### Testi (`vela/domain/say.py`)

Lingua dell'intento (`criteria.language`), `it` e `en`. Solo caratteri GSM-7 (niente apostrofi
tipografici, trattino lungo o puntini tipografici; `€` e le minuscole accentate italiane sono ammessi).

`sms_payment_link(title, start, end, pax, total, url, lang)`:

```
Vela: il tuo viaggio è pronto da pagare.
<titolo prodotto>
dal 10/10 al 12/10, 2 persone
Totale: 640,00 €
Paga entro 24 ore: <url>
```

`sms_confirmed(title, start, end, pax, booking_code, lang)`:

```
Vela: prenotazione confermata!
<titolo prodotto>
dal 10/10 al 12/10, 2 persone
Codice prenotazione: <codice>
```

Date da `Proposal.start_date` / `end_date`, persone da `Order.pax`, totale da `Order.total`
(importo reale, non il prezzo "da"). Il titolo del prodotto, se contiene caratteri fuori da
GSM-7, viene traslitterato (es. `’` → `'`, `–` → `-`) per non passare a UCS-2.

Frasi dell'agente aggiornate:

- `say_queued`: dice che il link arriverà via SMS al numero che finisce con le ultime 4 cifre del
  numero normalizzato, e che arriverà un secondo SMS alla conferma. Non invita più a chiedere lo
  stato. Se il numero non si normalizza, resta la frase di oggi.
- `awaiting_payment` (`say_status`): aggiunge che il link è stato mandato anche via SMS.

### Job SMS (`vela/domain/sms.py`)

Due tipi nuovi in `JobKind`: `SMS_LINK = "sms_link"`, `SMS_CONFIRMED = "sms_confirmed"`.
`SmsJob(repos, notifier, now, backoff=(30, 120, 600))` gestisce entrambi:

1. Rilegge l'ordine. Stato atteso: `awaiting_payment` per `sms_link`, `confirmed` per
   `sms_confirmed`. Stato diverso (pagato, annullato, scaduto…) → job `done` senza invio.
2. `normalize_it(order.traveler.phone)`; `None` → job `done`, log
   `sms saltato: numero non valido` con l'id dell'ordine.
3. Compone il testo con proposta e prodotto dell'ordine, invia.
4. Esiti: successo → `done` (log con id del messaggio e numero mascherato);
   `NotifierRejected` → `dead` subito; `NotifierError` → nuovo tentativo dopo 30 s, poi 2 min, poi 10 min;
   al quarto fallimento (quattro tentativi in tutto) `dead`. `last_error` senza numero in chiaro né testo.

L'ordine non viene mai modificato da `SmsJob`.

### Accodamento

- `purchase.py`, passo `STEP_LINK`: dopo il job `payment_check`, accoda `sms_link` se non ne
  esiste già uno attivo per l'ordine (`active_for_order`).
- `booking.py`, alla conferma: accoda `sms_confirmed` con la stessa regola.

### Coda e quota

- `quota_needs`: i job SMS non consumano quota HofJ (`None, 0`, già il default).
- Priorità di prelievo (`CLAIM_PRIORITY` in `repo_memory.py` e `repo_postgres.py`):
  `booking` 0, `payment_check` 1, `sms_link` / `sms_confirmed` 2, `purchase` 3. Senza questo gli
  SMS finirebbero dietro migliaia di acquisti in coda (§4.10).

### Configurazione (`vela/config.py`, `vela/app.py`)

| Variabile | Effetto |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | Tutte e tre → `TwilioSms`; nessuna → `FakeSms`; solo alcune → l'app non parte con un errore che nomina le mancanti. Indipendenti da `VELA_UPSTREAM_MODE` |

`TWILIO_FROM` è il numero Twilio acquistato, in E.164. `render.yaml`: le tre variabili con
`sync: false`. `app.py` collega il notificatore e registra `SmsJob` per i due tipi nel
`JobProcessor`.

### Contratto MCP (`vela/surfaces/mcp.py`)

Istruzioni: la frase "the payment link comes later from get_order_status" diventa "Vela texts
the payment link and the booking confirmation to the traveler's phone; do not poll
get_order_status, call it only when the user asks". Nessun campo o tool cambia.

## Flusso

```
accept_proposal → queued (say: "ti mando un SMS al numero che finisce con 1234…")
  → purchase … STEP_LINK → awaiting_payment + payment_check + sms_link
       sms_link → SmsJob → Twilio → SMS 1 (link + riepilogo)
  → payment_check → paid_pending_booking → booking → confirmed + sms_confirmed
       sms_confirmed → SmsJob → Twilio → SMS 2 (codice)
```

## Doppioni

Un solo job attivo per ordine e tipo: un retry di `STEP_LINK` o della prenotazione non crea un
secondo job. Resta un caso: il processo muore dopo che Twilio ha accettato il messaggio e prima
che il job sia salvato `done`; alla scadenza del lease il job riparte e l'SMS parte due volte.
Accettato come raro; eliminarlo richiede un registro degli invii (cambio di schema).

## Test

Tutti con `unittest`, senza rete.

- `phone`: `333 123 4567` → `+393331234567`; `+39 333…`; `0039333…`; `+44 20…` invariato;
  `""`, `None`, `"abc"`, troppe o troppo poche cifre → `None`; `mask`.
- `say`: i due SMS in `it` e `en`; solo caratteri GSM-7 anche con un titolo che contiene `’` o
  `–`; `say_queued` con e senza numero valido; `awaiting_payment` con la frase SMS.
- `SmsJob` con `FakeSms`: invio con testo e numero giusti; ordine in stato diverso → nessun
  invio; numero non valido → `done` senza invio; `NotifierError` → retry con backoff e `dead` al
  quarto; `NotifierRejected` → `dead` subito; `last_error` senza numero in chiaro.
- Accodamento: `STEP_LINK` e conferma accodano un solo job anche se rieseguiti.
- Flusso completo in replay (memoria e Postgres dove già previsto): da `accept_proposal` a
  `confirmed` `FakeSms.sent` contiene esattamente 2 messaggi, nell'ordine, anche con più giri
  di `payment_check` e un retry della prenotazione.
- Priorità: con acquisti in coda, un `sms_link` pendente viene prelevato prima.
- `TwilioSms` con `httpx.MockTransport`: URL, Basic auth, campi del form; 201 → sid; 400 →
  `NotifierRejected`; 429, 500, timeout → `NotifierError`; nessuna eccezione contiene token,
  numero o testo.
- `config`: tre variabili, nessuna, solo alcune (errore).
- Test esistenti aggiornati: frasi di `say_queued`, `awaiting_payment` e istruzioni MCP.

## Test manuale reale

Con le variabili Twilio impostate e il flusso di `docs/stripe.md` (`scripts/rest_flow.py`) su un
numero italiano del team. Costo dichiarato: 2 SMS Twilio (circa 3-4 segmenti in tutto),
1 Checkout Session e 1 pagamento di test Stripe, le letture della sessione ogni 60 s finché non
è pagata; in live anche le chiamate HofJ di `docs/stripe.md`. Esito in `docs/acceptance.md`
senza numero né chiavi.

## Documenti da aggiornare

- `docs/sms.md` (nuovo): attivazione, variabili, testo degli SMS, test manuale.
- `docs/spec.md`: RF-19 (Vela manda il link via SMS; l'agente non deve più interrogare lo
  stato), nuova RF-57 per l'SMS di conferma.
- `docs/decisions.md`: decisioni di questo design.
