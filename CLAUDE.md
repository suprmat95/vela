# CLAUDE.md

Welcome to Vela. This file is what I'd tell you on your first day: what the project is, where
things live, how to test, build and lint, and the rules we work by. For the details it points
you to the README and `docs/`; read those when you need depth, not before.

## What Vela is

A traveller says one sentence ("a padel weekend in Spain in October, two of us, max 800 euro")
to the assistant they already use: Claude via MCP, an ElevenLabs voice agent, or a REST client.
Vela proposes **one** trip at a time (never a list), books it on the House of Journeys (HofJ) API
after payment, and returns the booking code.

The five use cases are the whole product: `create_intent`, `get_proposal`, `reject_proposal`,
`accept_proposal`, `get_order_status`. They live in `vela/domain/usecases.py`. If you understand
that file, you understand Vela.

Requirements are in `docs/spec.md`, the milestone plan in `docs/roadmap.md`, and every choice we
made (and why) in `docs/decisions.md`. When something looks odd, check `decisions.md` first:
it's usually deliberate.

## How the code is laid out

The code is ports and adapters. The rule that keeps it sane: **`domain` and `ports` never
import `adapters` or `surfaces`.** The domain doesn't know if HofJ is real or a replay, or if
the caller is MCP or REST.

```
vela/
  domain/     The business logic, pure Python. Intent parsing, the chooser that picks the one
              proposal, the `say` sentences, orders, quota, and the jobs (purchase, payment
              check, booking). Start reading here.
  ports/      Interfaces the domain depends on: HofJPort, PaymentsPort, repositories,
              JobRepository, QuotaStore, CatalogSource, LLM.
  adapters/   Implementations of the ports: Postgres and in-memory repositories, HofJ over HTTP
              and in replay, per-brand router, Stripe and fake payments, Haiku, the worker.
  surfaces/   How the outside world reaches the use cases: mcp.py, rest.py (+ problems.py),
              health.py, replay and checkout pages. Thin: translate, call the domain, reply.
  app.py      FastAPI factory. The only place that wires adapters into the domain, based on
              `VELA_UPSTREAM_MODE` (replay, live, loadtest).
  config.py   `Settings`: env vars plus tuning fields with defaults (not env vars).
  sync.py     Multi-brand catalogue sync and `python -m vela.sync`.
alembic/      Database migrations. Never change the schema without asking (see below).
fixtures/     Recorded HofJ catalogues, one per host and brand. Replay mode and tests use them.
loadtest/     Fake HofJ, Locust scenario, reports and results (see loadtest/README.md).
landing/      Static landing page, hand-written HTML/CSS/JS, no build step.
scripts/      One-off tools: smoke tests, API exploration, quota probe, agents_log.py.
tests/        unittest suite. support.py has the shared fakes and helpers.
docs/         Spec, roadmap, decisions, plans, API notes.
agent-log/    Generated transcripts of Claude Code sessions. Hands off.
```

Replay is the default mode: no external calls, the catalogue comes from `fixtures/`. You only
need real HofJ and Stripe keys for `live`, and you should almost never need `live` locally.

## How to run tests

```bash
uv sync
uv run python3 -m unittest discover -s tests
```

- Always go through `uv run` (or the activated `.venv`). The system `python3` may be older than
  3.12; the suite checks and complains.
- No test calls external services.
- Postgres tests run only if `DATABASE_URL` is set; otherwise they are skipped (about 56). They
  use the `vela_test` schema, except the migration test, which runs `alembic upgrade head` on
  the main schema. So point `DATABASE_URL` at a throwaway database, not a shared one.
- Every change comes with tests, and the full suite must be green before you commit.

## How to build

There's nothing to compile. "Build" means two things:

```bash
uv sync                     # local: creates .venv with Python 3.12 from uv.lock
docker build -t vela .      # the image Render runs (no dev dependencies)
```

- To try the image: `docker run --rm -e DATABASE_URL=sqlite:////tmp/vela.db -p 8000:8000 vela`,
  then `curl -s localhost:8000/health`. The entrypoint runs migrations, then uvicorn.
- To run locally without Docker: `alembic upgrade head`, then `uvicorn vela.app:app --reload`.
- The landing has no build: `python3 -m http.server -d landing 8080`.
- Load test stack: `docker compose up -d --build` (see `loadtest/README.md`).
- Deploy is the Render blueprint in `render.yaml`. Don't deploy or push without asking.

## How to lint

```bash
uv run ruff check .
```

- Rules are pinned in `pyproject.toml` (`E4`, `E7`, `E9`, `F`): no line-length check, no
  formatter. Match the style of the surrounding code.
- Don't widen the rules or run `ruff check --fix` with extra rules on your own: it rewrites
  half the repo. Why is in `docs/decisions.md` ("Lint con ruff").
- Lint must be clean before you commit, like the tests.

## How we work

These are not suggestions. They're why the project stays readable.

**Working agreement**
- Before implementing any task, propose the approach in a few bullets and wait for my OK.
- If a decision isn't covered by the docs in this repository (architecture, data model,
  libraries, interfaces, trade-offs), stop and ask. Give 2-3 options, a recommendation and why.
- Never change public interfaces, the database schema or core architecture without asking.
- One task at a time. After each task, tell me: what you did, what you decided, what you're
  unsure about.
- Record accepted decisions in `docs/decisions.md` (date, decision, reason).

**Scope**
- Don't add features, dependencies or services that weren't agreed. If you think one is
  needed, propose it and wait.

**Git**
- Small commits with clear messages.
- Never rewrite history, force push or delete branches without asking.

**Where things live**
- Specs, plans, notes and decisions go in `docs/`.
- Everything that guides the work is saved in the repository, not only in the conversation.
- `agent-log/` holds Markdown transcripts of Claude Code sessions, generated automatically at
  every commit by `scripts/agents_log.py` (see `docs/agents-log.md`). Don't edit it by hand.

**Secrets and external services**
- Never open, print or log `.env` files, keys or tokens. Use environment variables; the code
  never reads `.env` itself.
- Before calling external APIs or anything that costs money or has usage limits (HofJ,
  Stripe, Anthropic, ElevenLabs), say what you will call and how many times.

**Context**
- This is a new project. Don't refer to or reuse anything from previous projects.
