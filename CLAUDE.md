# [CLAUDE.md](http://CLAUDE.md)

## Working agreement

- Before implementing any task, propose the approach in a few bullets and wait for my OK.

- If a decision is not covered by the docs in this repository (architecture, data model,

  libraries, interfaces, trade-offs), stop and ask. Give 2-3 options, a recommendation and why.

- Never change public interfaces, the database schema or core architecture without asking.

- One task at a time. After each task: what you did, what you decided, what you're unsure about.

- Record accepted decisions in docs/[decisions.md](http://decisions.md) (date, decision, reason).

## Scope

- Do not add features, dependencies or services that were not agreed.

  If you think one is needed, propose it and wait.

## Git

- Small commits with clear messages.

- Never rewrite history, force push or delete branches without asking.

## Where things live

- Specs, plans, notes and decisions go in docs/.

- Everything that guides the work is saved in the repository, not only in the conversation.

- agents-log/ holds Markdown transcripts of Claude Code sessions, generated automatically

  at every commit by scripts/agents_log.py (see docs/agents-log.md). Do not edit by hand.

## Secrets and external services

- Never open, print or log .env files, keys or tokens. Use environment variables.

- Before calling external APIs or anything that costs money or has usage limits,

  say what you will call and how many times.

## Context

- This is a new project. Do not refer to or reuse anything from previous projects.

## Project details

&lt;!-- To be filled once the stack is decided: tech stack, folder structure,

     commands to run, test, lint and deploy. --&gt;

- Tests: `python3 -m unittest discover -s tests`