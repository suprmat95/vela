#!/bin/sh
# Avvio del container: migrazioni Alembic, poi uvicorn. Fallisce esplicitamente senza DATABASE_URL.
set -e
alembic upgrade head
exec uvicorn vela.app:app --host 0.0.0.0 --port "${PORT:-8000}"
