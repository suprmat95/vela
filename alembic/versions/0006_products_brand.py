"""Brand HofJ dei prodotti (M10): `products.brand`, nullable.

Il sync la scrive per ogni prodotto; le righe già presenti restano NULL finché il primo sync
non le riscrive (decisione M10, nessun valore indovinato). Nessun'altra tabella cambia.
`batch_alter_table` perché la migrazione giri anche su SQLite (test).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("brand", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.drop_column("brand")
