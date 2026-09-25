# agent-log

Trascrizioni in Markdown delle sessioni Claude Code su questo repo.

## Cosa fa

Quando l'agente esegue un `git commit`, un hook Claude Code (`PreToolUse` su `Bash`,
configurato in `.claude/settings.json`) lancia `scripts/agents_log.py --hook`, che:

1. legge il transcript JSONL della sessione corrente (`transcript_path` fornito dall'hook);
2. lo converte in Markdown;
3. lo scrive in `agent-log/YYYY-MM-DD-HHMM-<slug>.md` (data e ora locali del primo
   messaggio, slug del primo messaggio utente);
4. salva accanto una copia identica del transcript, `agent-log/YYYY-MM-DD-HHMM-<slug>.jsonl`;
5. esegue `git add` su entrambi i file, così entrano nello stesso commit.

I file di una sessione hanno sempre lo stesso nome: a ogni commit vengono rigenerati da zero.
Lo script esce sempre con codice 0: un errore di trascrizione finisce su stderr ma non
blocca il commit.

## Contenuto del file Markdown

- Intestazione: titolo, id sessione, data di inizio.
- `## Utente HH:MM` — il messaggio dell'utente.
- `## Agente HH:MM` — la risposta testuale dell'agente e, in ordine cronologico, una riga
  per ogni tool usato (`- 🔧 Edit src/app.py`).

Non vengono inclusi: output dei tool, "thinking", messaggi interni (`isMeta`),
sottoconversazioni dei subagent (`isSidechain`), blocchi `<system-reminder>`,
messaggi di servizio dei comandi locali. Un messaggio che avvia uno slash command con
argomenti (`/superpowers:brainstorming ...`) entra come `/comando: argomenti`; senza
argomenti (`/clear`) è rumore. Per il tool `Bash` viene usata la
`description` del comando, non il comando stesso.

## Contenuto del file JSONL

È la copia byte per byte del transcript di Claude Code. Contiene tutto: thinking, input e
output dei tool, messaggi interni. Serve per riprocessare la sessione in futuro.

## Rigenerare a mano

```bash
python3 scripts/agents_log.py ~/.claude/projects/<cartella-progetto>/<session-id>.jsonl --out-dir agent-log
```

## Test

```bash
python3 -m unittest discover -s tests
```

## Limiti noti

- Commit fatti fuori da Claude Code (terminale, IDE) non producono alcun log.
- `git commit <pathspec>` esplicito committa solo i path indicati: il log resta staged
  e finisce nel commit successivo.
- Al momento del commit il transcript arriva fino alla chiamata `git commit` inclusa. La
  risposta finale dell'agente dopo il commit entra nel log al commit successivo.
- Il `.jsonl` include i contenuti dei file letti dall'agente durante la sessione. Se
  l'agente legge un file con una chiave o un token, quel valore finisce versionato.
- Non modificare i file in `agent-log/` a mano: verrebbero sovrascritti.
