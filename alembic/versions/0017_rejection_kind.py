"""Rifiuti con tipo (M21-F, RF-71, RF-74): `rejections.kind` (testo, nullo) e
`rejections.keep_product` (bool, default falso).

Numero 0017 dopo la 0016 di M19 (`orders.last_seen_at`): la catena su `master` è
0012 → 0015 → 0016, e una 0013 in mezzo romperebbe i database già a 0015 o 0016. Scritta come 0016
dopo la 0015 (M23), rinumerata al merge perché intanto M19 aveva preso la 0016. 0013 e 0014 restano
numeri non usati (0014 era la migrazione proposta di M22-b, archiviata). Le righe già in tabella hanno `kind` nullo, cioè "rifiuto senza tipo": nessun
tipo inventato. `batch_alter_table` perché la migrazione giri anche su SQLite (test).

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
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
