"""Etichette del sync per l'ordinamento di RF-60 (M21-B): `products.featured` e
`products.special_offer`, booleani non nulli con default falso.

Il sync le scrive per ogni prodotto nuovo o cambiato; le righe già in tabella le prendono qui dal
dettaglio salvato in `raw` (`featured`, `isSpecialOffer`), perché il sync incrementale non le
riscriverebbe finché `updatedAt` non cambia. Valore assente o nullo = falso.
`batch_alter_table` perché la migrazione giri anche su SQLite (test).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

products = sa.table("products", sa.column("id", sa.String), sa.column("raw", sa.JSON),
                    sa.column("featured", sa.Boolean), sa.column("special_offer", sa.Boolean))


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("featured", sa.Boolean, nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("special_offer", sa.Boolean, nullable=False,
                                   server_default=sa.false()))
    conn = op.get_bind()
    for pid, raw in conn.execute(sa.select(products.c.id, products.c.raw)):
        raw = raw or {}
        featured, special = bool(raw.get("featured")), bool(raw.get("isSpecialOffer"))
        if featured or special:
            conn.execute(sa.update(products).where(products.c.id == pid)
                         .values(featured=featured, special_offer=special))


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.drop_column("special_offer")
        batch.drop_column("featured")
