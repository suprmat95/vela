"""Persone e camere (M21-D): `products.max_pax_per_room` (intero, nullo = nessun limite) e
`orders.rooms` (intero non nullo, default 1: le camere mandate a HofJ, RF-67).

Il sync scrive il limite per camera per ogni prodotto nuovo o cambiato; le righe già in tabella lo
prendono qui dal dettaglio salvato in `raw` (`maxPaxPerRoom`), riga per riga come la 0010, perché
il sync incrementale non le riscriverebbe finché `updatedAt` non cambia. Assente, nullo o zero =
nessun limite. Gli ordini già in tabella restano a una camera: i loro carrelli sono nati con
`rooms: 1` (decisione A, 2026-09-27). `batch_alter_table` perché la migrazione giri anche su
SQLite (test).

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

products = sa.table("products", sa.column("id", sa.String), sa.column("raw", sa.JSON),
                    sa.column("max_pax_per_room", sa.Integer))


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("max_pax_per_room", sa.Integer, nullable=True))
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("rooms", sa.Integer, nullable=False, server_default="1"))
    conn = op.get_bind()
    for pid, raw in conn.execute(sa.select(products.c.id, products.c.raw)):
        value = (raw or {}).get("maxPaxPerRoom")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            conn.execute(sa.update(products).where(products.c.id == pid)
                         .values(max_pax_per_room=value))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("rooms")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("max_pax_per_room")
