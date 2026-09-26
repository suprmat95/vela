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

Aspetto e struttura seguono il design fornito dall'utente il 2026-09-26 (file `index_1.html`, non
versionato). Stile chiaro stile Apple, solo tema chiaro, CSS in `styles.css`.

1. **Barra di navigazione** fissa: link alle sezioni e pulsante "Inizia" verso "Con Claude".
2. **Hero**: "Dì cosa vuoi. Vela fa il resto." e una chat d'esempio (intento e proposta).
3. **Come funziona**: tre card. Esprimi l'intento, Vela propone un solo viaggio, accetti e paghi,
   ricevi il codice di prenotazione. Sono passi del flusso, non una lista di prodotti.
4. **Esempi**: quattro conversazioni (coppia, cambio di rotta, gruppo, calendario). Ogni
   conversazione mostra una proposta alla volta; non è un elenco tra cui scegliere.
   - Le frasi del viaggiatore sono quelle che il parser di Vela capisce oggi.
   - Le risposte sono i `say` reali di Vela, accorciati, ottenuti in memoria sulle fixture del
     2026-09-25 (prodotti 688, 695, 369, 1023, 1044). Prezzi e date possono cambiare.
   - L'esempio del calendario attribuisce a Claude (con un suo connettore) la lettura e la
     scrittura del calendario; Vela propone solo il viaggio.
5. **Con Claude**: Settings → Connectors → Add custom connector, nome
   `Pacchetti Viaggio di Padel Tennis`, URL MCP in un campo di sola lettura con un pulsante
   "Copia", e una frase d'esempio da scrivere a Claude.
6. **A voce** e **Al telefono**: due card. Voce: contenitore del widget ElevenLabs. Telefono:
   numero come link `tel:`. Senza agent id o numero, la card mostra "In arrivo".
7. **Codice aperto**: link al repository pubblico. Footer con il copyright.

Nel markup statico l'URL MCP è scritto per esteso, "Copia" è nascosto e le card voce e telefono
sono nello stato "In arrivo". Senza JavaScript la pagina resta completa e leggibile.

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

- Scrive `mcpUrl` nel campo dell'URL MCP e lo usa per il pulsante "Copia"
  (`navigator.clipboard.writeText`; se non è disponibile, il pulsante seleziona il campo).
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
    buildCommand: echo "Landing statica, nessun build"
    staticPublishPath: ./landing
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
  `staticPublishPath: ./landing` e `landing/**` nel `buildFilter`; il servizio `vela` ignora
  `landing/**`.
- `.dockerignore` contiene `landing`.
- Nessun segnaposto del design (`[MAIUSCOLE]`) resta in `index.html`.
- Il nome del connettore è lo stesso in `index.html` e nel README.
- I viaggi citati negli esempi esistono nelle fixture con quel nome (id → nome nel test).
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
