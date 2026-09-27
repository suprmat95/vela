"""Ordini silenziosi (M19): su `orders`, `last_seen_at` (istante con fuso, nullo).

L'ultimo segno di vita del viaggiatore: accettazione, conferma, richiesta di stato. Nullo per gli
ordini già in tabella, che valgono dalla creazione. Schema approvato dall'utente il 2026-09-27.
`batch_alter_table` perché la migrazione giri anche su SQLite (test).

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("last_seen_at")
