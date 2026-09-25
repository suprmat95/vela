"""Tabella stripe_events: idempotenza dei webhook Stripe (M6, RNF-03).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
