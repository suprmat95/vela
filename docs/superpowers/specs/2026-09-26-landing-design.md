# Landing statica di Vela: design

Data: 2026-09-26. Origine: brainstorming del task `task/landingpage`. Decisioni in
`docs/decisions.md` (2026-09-26, "Landing: design").

## Obiettivo

Una pagina statica, nello stesso repository, che spiega cos'è Vela e come raggiungerlo dai canali
che il viaggiatore usa già: Claude via MCP, l'agente vocale ElevenLabs nel browser e lo stesso
agente al telefono. È pubblicata come servizio Render separato dall'API.

La pagina **non vende viaggi**. Il brief (`docs/brief.md`) dice "In 2029 Vela has no homepage":
niente viaggi, prezzi, liste, griglie, tabelle o ricerca. La landing è una guida ai canali, non una
vetrina.

Successo: l'URL del servizio `vela-landing` risponde 200 con la pagina; da lì un utente collega
Claude al connector MCP seguendo i passi; le sezioni voce e telefono mostrano "in arrivo" finché
M12 non fornisce agent id e numero, e si attivano cambiando solo `landing/config.js`; un commit che
tocca solo `landing/` non ridistribuisce l'API.

## Vincoli

- HTML, CSS e JavaScript scritti a mano: nessun build step, nessun framework, nessuna dipendenza
  (né Python né Node).
- Solo italiano (`<html lang="it">`).
- Nessun codice condiviso con il pacchetto `vela/`. La pagina non chiama l'API di Vela.
- Nessuna analytics, nessun form, nessun cookie.
- Unica risorsa esterna ammessa: lo script del widget ElevenLabs, caricato solo quando l'agent id
  è configurato.
- La creazione dell'agente ElevenLabs e del numero di telefono appartiene a M12, fuori da questo
  task.

## Componenti

### `landing/` (radice del repository)

```
landing/
  index.html    unica pagina
  styles.css    stile della pagina, responsive (mobile e desktop)
  config.js     unico punto con i valori configurabili
  main.js       applica config.js alla pagina
  assets/       favicon SVG (ed eventuale logo SVG)
```

### Contenuto di `index.html`

1. **Hero**: Vela in una frase ("Dì cosa vuoi: Vela prenota il tuo viaggio di padel o tennis con
   hotel") e un esempio di intento a parole ("Un weekend di padel a ottobre, in due, al caldo,
   sotto i 600 euro").
2. **Come funziona**: tre passi. Esprimi l'intento, Vela propone un solo viaggio, accetti e
   paghi, ricevi il codice di prenotazione. Sono passi del flusso, non una lista di prodotti.
3. **Con Claude**: Settings → Connectors → Add custom connector, nome `Vela`, URL MCP con un
   pulsante "Copia" e una frase d'esempio da scrivere a Claude.
4. **A voce**: contenitore del widget ElevenLabs. Se non c'è l'agent id, mostra un blocco
   "In arrivo".
5. **Al telefono**: numero come link `tel:`. Se non c'è il numero, mostra un blocco "In arrivo".
6. **Footer**: link al repository pubblico.

Nel markup statico l'URL MCP è scritto per esteso e le sezioni voce e telefono sono nello stato
"In arrivo". Senza JavaScript la pagina resta completa e leggibile.

### `config.js`

```js
window.VELA_LANDING = {
  mcpUrl: "https://vela-n506.onrender.com/mcp",
  elevenLabsAgentId: "",
  phoneNumber: ""   // formato E.164, es. "+390212345678"
};
```

Sono valori pubblici per natura, non segreti, e stanno nel repository. Quando M12 è pronta basta
valorizzare `elevenLabsAgentId` e `phoneNumber`.

### `main.js`

- Scrive `mcpUrl` nel testo dell'URL MCP e lo usa per il pulsante "Copia"
  (`navigator.clipboard.writeText`; se non è disponibile, il pulsante seleziona il testo).
- Se `elevenLabsAgentId` non è vuoto: nasconde "In arrivo", inserisce
  `<elevenlabs-convai agent-id="…">` e aggiunge lo script ufficiale del widget dal CDN di
  ElevenLabs. Se è vuoto, non fa nessuna richiesta esterna.
- Se `phoneNumber` non è vuoto: nasconde "In arrivo" e mostra il link `tel:` con il numero.
- Non fa altre richieste di rete.

## Deploy su Render

In `render.yaml`, stesso blueprint:

```yaml
  - type: web
    name: vela-landing
    runtime: static
    buildCommand: ""
    staticPublishPath: landing
    buildFilter:
      paths:
        - landing/**
```

Al servizio `vela` esistente si aggiunge `buildFilter.ignoredPaths: ["landing/**"]`: un commit che
tocca solo la landing non ricostruisce l'immagine Docker dell'API. Nessun'altra riga del servizio
`vela` cambia.

`.dockerignore` esclude `landing`, così l'immagine dell'API non contiene la pagina.

Il servizio nasce facendo "Sync" del blueprint dalla dashboard Render. È un'azione dell'utente,
non dell'agente. Il dominio è il sottodominio `*.onrender.com` assegnato da Render; nessun dominio
custom.

## Test

`tests/test_landing.py`, stdlib `unittest`, sul modello di `tests/test_docker_files.py`:

- `landing/index.html` esiste, si parsa con `html.parser` e ha `lang="it"`.
- Ogni `href` o `src` relativo di `index.html` punta a un file esistente sotto `landing/`.
- L'URL MCP scritto in `index.html` è uguale a `mcpUrl` di `config.js`.
- `render.yaml` contiene il servizio `vela-landing` con `runtime: static`,
  `staticPublishPath: landing` e `landing/**` nel `buildFilter`; il servizio `vela` ignora
  `landing/**`.
- `.dockerignore` contiene `landing`.
- Guardia "no homepage": `index.html` non contiene `<table>` e `main.js` non contiene `fetch(`
  né `XMLHttpRequest`.

I controlli su `render.yaml` sono testuali, senza aggiungere dipendenze.

## Verifica manuale

- `python3 -m unittest discover -s tests` è verde.
- `python3 -m http.server -d landing 8080`: la pagina si controlla a larghezza desktop e mobile,
  nello stato "In arrivo" e con agent id e numero finti in `config.js` (senza committarli).
- Dopo il Sync del blueprint: l'URL di `vela-landing` risponde 200, e un commit solo su `landing/`
  non avvia un deploy di `vela`.

## Documentazione

- `README.md`: sezione "Landing" con cartella, anteprima locale, deploy e dove si configurano
  agent id e numero.
- `docs/decisions.md`: sezione "Landing: design".

## Fuori scope

- Creazione dell'agente ElevenLabs e del numero di telefono (M12).
- Documentazione REST sulla landing.
- Traduzione inglese, dominio custom, analytics.
