"""Ambiente Alembic: URL da DATABASE_URL (normalizzata da vela.config), metadata condiviso."""
import logging.config
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vela.adapters.db import metadata  # noqa: E402
import vela.adapters.schema  # noqa: E402,F401  registra le tabelle sul metadata
from vela.config import Settings  # noqa: E402

config = context.config
if config.config_file_name is not None:
    logging.config.fileConfig(config.config_file_name)

target_metadata = metadata


def database_url() -> str:
    url = Settings.from_env().database_url
    if not url:
        raise RuntimeError("DATABASE_URL non impostata: impossibile eseguire le migrazioni")
    return url


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
