"""Livello e lezioni (M21-C, RF-63): `products.levels` (lista JSON non nulla, default `[]`:
livello sconosciuto), `products.levels_exclusive` e `products.coaching` (booleani non nulli, default
falso).

Il sync scrive le tre etichette per ogni prodotto nuovo o cambiato; le righe già in tabella le
prendono qui dal dettaglio salvato in `raw` (`description`, `shortDescription`), riga per riga come
la 0010 e la 0011, perché il sync incrementale non le riscriverebbe finché `updatedAt` non cambia.
Le regole non si duplicano: il backfill chiama `vela.domain.labels.labels_of`, la stessa funzione
che il sync usa in `catalog.project_detail`. Rieseguita da zero, la migrazione applica quindi le
regole del codice di quel momento, come un sync completo. `batch_alter_table` perché la
migrazione giri anche su SQLite (test).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from vela.domain.labels import labels_of, ordered

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

products = sa.table("products", sa.column("id", sa.String), sa.column("raw", sa.JSON),
                    sa.column("levels", sa.JSON), sa.column("levels_exclusive", sa.Boolean),
                    sa.column("coaching", sa.Boolean))


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("levels", sa.JSON, nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("levels_exclusive", sa.Boolean, nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("coaching", sa.Boolean, nullable=False, server_default=sa.false()))
    conn = op.get_bind()
    for pid, raw in conn.execute(sa.select(products.c.id, products.c.raw)).all():
        labels = labels_of(raw)
        if labels.levels or labels.levels_exclusive or labels.coaching:
            conn.execute(sa.update(products).where(products.c.id == pid)
                         .values(levels=ordered(labels.levels), levels_exclusive=labels.levels_exclusive,
                                 coaching=labels.coaching))


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.drop_column("coaching")
        batch.drop_column("levels_exclusive")
        batch.drop_column("levels")
