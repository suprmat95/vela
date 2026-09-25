"""Accesso a Postgres con SQLAlchemy Core (sincrono, psycopg 3).

``metadata`` è condiviso: le task successive vi registrano le tabelle e Alembic lo usa
come ``target_metadata``.
"""
from sqlalchemy import MetaData, create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

CONNECT_TIMEOUT_SECONDS = 3

metadata = MetaData()


def connect_args_for(url: str) -> dict:
    """Argomenti di connessione per dialetto: solo Postgres accetta ``connect_timeout``."""
    if make_url(url).get_backend_name() == "postgresql":
        return {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    return {}


def engine_kwargs_for(url: str) -> dict:
    """Opzioni di engine per dialetto: su Postgres l'attesa di una connessione dal pool è
    limitata, così ``/health`` risponde 503 in tempo anche con il pool esaurito. SQLite in
    memoria usa un pool senza timeout e non accetta l'opzione."""
    if make_url(url).get_backend_name() == "postgresql":
        return {"pool_timeout": CONNECT_TIMEOUT_SECONDS}
    return {}


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args_for(url),
                         **engine_kwargs_for(url))


def check_db(engine: Engine) -> bool:
    """``SELECT 1``: True se il DB risponde, False su qualunque errore (mai un'eccezione)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False
