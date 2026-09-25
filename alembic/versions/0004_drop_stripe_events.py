"""Elimina stripe_events: niente webhook Stripe (M6, cambio di requisito con HofJ).

Il pagamento si chiude con POST /v1/bookings di HofJ e Vela lo scopre interrogando la Checkout
Session (M5). La 0003 resta perché è già stata pubblicata su master: questa revisione porta
qualunque DB, a 0002 o a 0003, allo stesso schema.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("stripe_events")


def downgrade() -> None:
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
