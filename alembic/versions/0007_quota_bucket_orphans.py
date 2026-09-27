"""Token bucket della quota e itinerari orfani (M18).

`quota_window` riceve `tokens` e `refilled_at` (token bucket a ritmo costante). La riga esistente
viene cancellata: l'adapter la ricrea con il bucket pieno e `needs_refresh`, quindi la prima
chiamata rilegge `/v1/quota`. `orders.orphan_itineraries` conta gli itinerari lasciati su HofJ da
un timeout su `POST /v1/itineraries`. `batch_alter_table` perché la migrazione giri anche su
SQLite (test).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM quota_window")
    with op.batch_alter_table("quota_window") as batch:
        batch.add_column(sa.Column("tokens", sa.Float, nullable=False))
        batch.add_column(sa.Column("refilled_at", sa.DateTime(timezone=True), nullable=False))
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("orphan_itineraries", sa.Integer, nullable=False,
                                   server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("orphan_itineraries")
    op.execute("DELETE FROM quota_window")   # la finestra a griglia riparte dalla prima richiesta
    with op.batch_alter_table("quota_window") as batch:
        batch.drop_column("refilled_at")
        batch.drop_column("tokens")
