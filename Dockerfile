# Immagine ufficiale uv con Python 3.12: le dipendenze vengono da uv.lock (uv sync --frozen).
# Tre stage: `app` è l'immagine di Render (ultimo stage, quello costruito di default); `loadtest`
# aggiunge le dipendenze dev (locust) per il servizio `locust` del compose (M13a).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# Prima solo le dipendenze, così il layer resta in cache quando cambia il codice.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && chmod +x docker-entrypoint.sh \
    && useradd --create-home --uid 1000 vela && chown -R vela:vela /app

ENV PATH="/app/.venv/bin:$PATH"
USER vela
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]

FROM app AS loadtest
USER root
RUN uv sync --frozen && chown -R vela:vela /app/.venv
USER vela

FROM app
