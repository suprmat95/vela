"""Rifiuti con tipo (M21-F, RF-71, RF-74): `rejections.kind` (testo, nullo) e
`rejections.keep_product` (bool, default falso).

Numero 0016 dopo 0015 (M23): la catena su `master` è 0012 → 0015, e una 0013 in mezzo romperebbe
i database già a 0015. 0013 e 0014 restano numeri non usati (0014 era la migrazione proposta di
M22-b, archiviata). Le righe già in tabella hanno `kind` nullo, cioè "rifiuto senza tipo": nessun
tipo inventato. `batch_alter_table` perché la migrazione giri anche su SQLite (test).

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
    with op.batch_alter_table("rejections") as batch:
        batch.add_column(sa.Column("kind", sa.String(16), nullable=True))
        batch.add_column(sa.Column("keep_product", sa.Boolean, nullable=False,
                                   server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("rejections") as batch:
        batch.drop_column("keep_product")
        batch.drop_column("kind")
