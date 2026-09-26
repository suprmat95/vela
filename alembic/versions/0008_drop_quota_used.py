"""Toglie `quota_window.used` (dopo M18).

Era il contatore della finestra a griglia di M5; con il token bucket di M18 veniva scritto
sempre a 0. Il downgrade la rimette a 0: la migrazione 0007 cancella comunque la riga.
`batch_alter_table` perché la migrazione giri anche su SQLite (test).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("quota_window") as batch:
        batch.drop_column("used")


def downgrade() -> None:
    with op.batch_alter_table("quota_window") as batch:
        batch.add_column(sa.Column("used", sa.Integer, nullable=False, server_default="0"))
