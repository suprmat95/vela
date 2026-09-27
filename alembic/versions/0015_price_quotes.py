"""Cache del prezzo con fanout (RF-84): tabella `price_quotes` e, su `orders`, `follows_quote`
(bool, default falso) e `confirmed_total` (numerico, nullo).

Numero 0015: 0012, 0013 e 0014 sono riservati a M21-C, M21-F e M22. Nata agganciata a 0011,
riagganciata a 0012 (M21-C) al merge in `master`; chi fa il merge dopo riaggancia la catena
(decisione del 2026-09-27).
Gli ordini già in tabella non sono agganciati a niente. `batch_alter_table` perché la migrazione
giri anche su SQLite (test).

Revision ID: 0015
Revises: 0012
Create Date: 2026-09-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_quotes",
        sa.Column("product_id", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("adults", sa.Integer, nullable=False),
        sa.Column("rooms", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("leader_order_id", sa.String(36), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.Column("priced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "start_date", "adults", "rooms", "currency"),
    )
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("follows_quote", sa.Boolean, nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("confirmed_total", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("confirmed_total")
        batch.drop_column("follows_quote")
    op.drop_table("price_quotes")
