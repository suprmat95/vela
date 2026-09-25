# Immagine ufficiale uv con Python 3.12: le dipendenze vengono da uv.lock (uv sync --frozen).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

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
