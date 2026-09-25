#!/usr/bin/env python3
"""Trascrive un transcript JSONL di Claude Code in Markdown dentro agent-log/.

Uso:
  agents_log.py --hook                      # come hook PreToolUse (legge il JSON da stdin)
  agents_log.py <transcript.jsonl> [--out-dir DIR]

Solo stdlib, compatibile con Python 3.7.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import namedtuple
from datetime import datetime, timezone

Entry = namedtuple("Entry", "role text ts")  # role: user | assistant | tool

LOG_DIR = "agent-log"
SLUG_MAX = 40
CMD_MAX = 80
NOISE_PREFIXES = ("<local-command-caveat>", "<command-name>", "<command-message>",
                  "<local-command-stdout>")
SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
GIT_COMMIT_RE = re.compile(r"\bgit\b[^|;&\n]*\bcommit\b")
COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.S)
COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def is_git_commit(command):
    return bool(GIT_COMMIT_RE.search(command or ""))


def parse_ts(value):
    """'2026-09-24T21:10:48.356Z' -> datetime UTC (3.7 non accetta la 'Z')."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def clean_text(text):
    text = SYSTEM_REMINDER_RE.sub("", text)
    return text.strip()


def tool_label(name, tool_input):
    tool_input = tool_input or {}
    if name == "Bash":
        desc = tool_input.get("description")
        if desc:
            return "Bash: " + desc.strip()
        cmd = (tool_input.get("command") or "").strip().replace("\n", " ")
        if len(cmd) > CMD_MAX:
            cmd = cmd[:CMD_MAX] + "…"
        return "Bash: " + cmd
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return "%s %s" % (name, path) if path else name
    if name == "Agent" and tool_input.get("description"):
        return "Agent: " + tool_input["description"].strip()
    if name == "Skill" and tool_input.get("skill"):
        return "Skill " + tool_input["skill"]
    return name


def slash_command_text(text):
    """Messaggio di uno slash command con argomenti -> "/comando: argomenti", altrimenti None.

    Senza <command-args> (es. /clear) il messaggio e' rumore e non entra nel log.
    """
    args = COMMAND_ARGS_RE.search(text)
    if not args or not args.group(1).strip():
        return None
    name = COMMAND_NAME_RE.search(text)
    prefix = name.group(1).strip() + ": " if name else ""
    return prefix + args.group(1).strip()


def _user_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def parse_transcript(lines):
    """Ritorna (entries, meta). meta: title, session_id."""
    entries = []
    meta = {"title": None, "session_id": None}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        kind = rec.get("type")
        if kind == "ai-title" and rec.get("aiTitle"):
            meta["title"] = rec["aiTitle"]
            continue
        if kind not in ("user", "assistant"):
            continue
        if rec.get("isSidechain") or rec.get("isMeta"):
            continue
        if not meta["session_id"] and rec.get("sessionId"):
            meta["session_id"] = rec["sessionId"]
        ts = parse_ts(rec["timestamp"]) if rec.get("timestamp") else None
        content = rec.get("message", {}).get("content")
        if content is None:
            continue
        if kind == "user":
            text = _user_text(content)
            if text.lstrip().startswith(NOISE_PREFIXES):
                text = slash_command_text(text)
                if text is None:
                    continue
            text = clean_text(text)
            if text:
                entries.append(Entry("user", text, ts))
            continue
        for block in content if isinstance(content, list) else [{"type": "text", "text": content}]:
            btype = block.get("type")
            if btype == "text":
                text = clean_text(block.get("text", ""))
                if text:
                    entries.append(Entry("assistant", text, ts))
            elif btype == "tool_use":
                entries.append(Entry("tool", tool_label(block.get("name"), block.get("input")), ts))
    if not meta["title"]:
        for e in entries:
            if e.role == "user":
                meta["title"] = e.text.splitlines()[0][:80]
                break
    return entries, meta


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text[:SLUG_MAX].strip("-")


def session_filename(entries, session_id=None):
    first = next((e for e in entries if e.role == "user"), None)
    if first is None or first.ts is None:
        return None
    slug = slugify(first.text.splitlines()[0]) or (session_id or "sessione")[:8]
    return first.ts.astimezone().strftime("%Y-%m-%d-%H%M") + "-" + slug + ".md"


def render_markdown(entries, meta):
    out = ["# " + (meta.get("title") or "Sessione Claude Code"), ""]
    if meta.get("session_id"):
        out.append("- Sessione: `%s`" % meta["session_id"])
    first_ts = next((e.ts for e in entries if e.ts), None)
    if first_ts:
        out.append("- Inizio: " + first_ts.astimezone().strftime("%Y-%m-%d %H:%M"))
    out.append("")
    current = None
    for e in entries:
        role = "assistant" if e.role == "tool" else e.role
        if role != current:
            heading = "Utente" if role == "user" else "Agente"
            clock = e.ts.astimezone().strftime("%H:%M") if e.ts else ""
            out.append(("## %s %s" % (heading, clock)).rstrip())
            out.append("")
            current = role
        out.append("- 🔧 " + e.text if e.role == "tool" else e.text)
        out.append("")
    return "\n".join(out)


SESSION_LINE_RE = re.compile(r"^- Sessione: `([^`]+)`", re.M)


def _free_path(md_path, session_id):
    """Il percorso del log per questa sessione. Se il nome e' gia' occupato dal log di un'altra
    sessione (stessa ora di inizio, stesso slug), aggiunge le prime 8 cifre dell'id sessione."""
    if not session_id or not os.path.exists(md_path):
        return md_path
    with open(md_path, encoding="utf-8") as f:
        found = SESSION_LINE_RE.search(f.read())
    if found is None or found.group(1) == session_id:
        return md_path
    return md_path[:-len(".md")] + "-" + session_id[:8] + ".md"


def transcribe(transcript_path, out_dir):
    """Scrive <out_dir>/<nome>.md e una copia identica del transcript in <nome>.jsonl.

    Ritorna (md_path, jsonl_path), oppure None se non c'e' alcun messaggio utente.
    """
    with open(transcript_path, encoding="utf-8") as f:
        entries, meta = parse_transcript(f)
    name = session_filename(entries, meta.get("session_id"))
    if name is None:
        return None
    os.makedirs(out_dir, exist_ok=True)
    md_path = _free_path(os.path.join(out_dir, name), meta.get("session_id"))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(entries, meta))
    jsonl_path = md_path[:-len(".md")] + ".jsonl"
    shutil.copyfile(transcript_path, jsonl_path)
    return md_path, jsonl_path


def run_hook():
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") != "Bash":
            return
        if not is_git_commit((payload.get("tool_input") or {}).get("command")):
            return
        cwd = payload.get("cwd") or os.getcwd()
        paths = transcribe(payload["transcript_path"], os.path.join(cwd, LOG_DIR))
        if paths:
            subprocess.run(["git", "add", "--"] + list(paths), cwd=cwd, check=True)
    except Exception as exc:  # mai bloccare il commit
        sys.stderr.write("agents_log: %s\n" % exc)


def main(argv):
    if "--hook" in argv:
        run_hook()
        return 0
    if not argv:
        sys.stderr.write(__doc__)
        return 2
    out_dir = LOG_DIR
    if "--out-dir" in argv:
        out_dir = argv[argv.index("--out-dir") + 1]
    paths = transcribe(argv[0], out_dir)
    print("\n".join(paths) if paths else "nessun messaggio utente: nessun file scritto")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
